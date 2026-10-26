// Browser journey (Playwright). Needs: API+worker+web running, ALLOW_PRIVATE_FETCH=true LLM_PROVIDER=none, an admin user e2e@example.com,
// and a static fixture site on 127.0.0.1:8765 (see e2e/README.md). Writes screenshots to ./shots.
const { chromium } = require('playwright'); const fs = require('fs'); const { execSync } = require('child_process');
const D = __dirname; fs.mkdirSync(D + '/shots', { recursive: true }); const B = 'http://localhost:3000';
fs.writeFileSync(D + '/dental.csv', `Company,First Name,Last Name,Email,Website,Country,Title
Bright Smile Dental,Asha,Rao,asha@brightsmile.in,brightsmile.in,IN,Owner
Pune Ortho Care,Rohan,Mehta,rohan@puneortho.in,puneortho.in,IN,Director
`);
const sql = (q) => execSync(`PGPASSWORD=flowhq psql -h localhost -U flowhq flowhq -qAt -c "${q}"`).toString().trim();
(async () => {
  const b = await chromium.launch(); const errs = [];
  const p = await b.newPage({ viewport: { width: 1360, height: 860 } });
  p.on('pageerror', e => errs.push(String(e))); p.on('console', m => m.type() === 'error' && !/fonts\.g|ERR_|Failed to load resource/.test(m.text()) && errs.push(m.text()));
  const shot = (n, full = true) => p.screenshot({ path: `${D}/shots/${n}.png`, fullPage: full });
  const step = (s) => console.log('•', s);

  await p.goto(B + '/login'); await p.getByLabel('Email').fill('e2e@example.com'); await p.getByLabel('Password').fill('e2e-password-123');
  await p.getByRole('button', { name: 'Sign in' }).click(); await p.waitForURL('**/dashboard'); await p.getByText('Imported leads').waitFor(); await shot('01-dashboard-empty');
  step('logged in, empty dashboard');

  await p.goto(B + '/integrations'); await p.getByRole('button', { name: 'Add sandbox' }).click(); await p.getByText('Sandbox account added').waitFor(); await shot('02-integrations');
  step('sandbox account added');

  await p.goto(B + '/import'); await p.setInputFiles('input[type=file]', D + '/dental.csv'); await p.getByRole('button', { name: /Upload and preview/ }).click();
  await p.getByRole('button', { name: 'Start import' }).click(); await p.getByText('Import completed').waitFor({ timeout: 30000 });
  sql(`UPDATE company SET website='http://127.0.0.1:8765'`); step('imported 2 leads (websites pointed at local fixture site)');

  await p.goto(B + '/campaigns/new');
  await p.getByLabel('Campaign name').fill('Dental clinics – appointment reminders');
  await p.getByLabel(/^Offer/).fill('We automate appointment reminders so clinics see fewer no-shows.');
  await p.getByLabel('Sender name').fill('Vatsal'); await p.getByLabel('Sender company').fill('FlowHQ');
  await p.getByLabel(/Physical postal address/).fill('1 Example Street, Pune, India');
  await p.getByLabel('Target industries').fill('dental'); await p.getByLabel('Target regions (ISO codes)').fill('IN'); await p.getByLabel('Service / pain-point keywords').fill('implants, orthodontics');
  await p.getByLabel('Send from (hour)').fill('0'); await p.getByLabel('Send until (hour)').fill('24');
  const sel = p.getByLabel('Sending account (email)'); await sel.selectOption({ index: 1 });
  await shot('03-campaign-builder'); await p.getByRole('button', { name: 'Create campaign' }).click(); await p.waitForURL(/campaigns\/[0-9a-f-]+$/);
  step('campaign created');

  await p.getByLabel('Add all leads from an import').selectOption({ index: 1 }); await p.getByRole('button', { name: 'Add leads' }).click(); await p.getByText('Added 2 lead').waitFor();
  await p.getByRole('button', { name: 'Research all' }).click(); await p.waitForFunction(() => document.body.innerText.includes('2/2 researched'), null, { timeout: 60000 });
  await p.getByRole('button', { name: 'Score all' }).click(); await p.waitForFunction(() => document.body.innerText.includes('2 scored'), null, { timeout: 60000 });
  await p.getByRole('button', { name: 'why' }).first().click(); await shot('04-campaign-scored');
  step('researched + scored: ' + sql(`select string_agg(icp_class||':'||icp_score, ', ') from campaign_lead`));

  await p.getByRole('button', { name: 'Generate drafts' }).click(); await p.waitForFunction(() => /6 draft/.test(document.body.innerText), null, { timeout: 60000 });
  step('drafts generated'); await p.goto(B + '/review'); await p.locator('ul button').first().click(); await p.getByText('Evidence behind the personalization').waitFor(); await shot('05-review');
  await p.getByRole('button', { name: 'Approve all clean drafts' }).waitFor({ state: 'detached' }).catch(() => {});
  const cid = (await p.evaluate(() => fetch('/api/v1/campaigns').then(r => r.json())))[0].id;
  await p.goto(`${B}/review?campaign=${cid}`); await p.getByRole('button', { name: 'Approve all clean drafts' }).click(); await p.getByText('Approved every clean draft').waitFor();
  await shot('06-review-approved'); step('approved all clean drafts');

  await p.goto(`${B}/campaigns/${cid}`); await p.getByRole('button', { name: /Launch campaign/ }).click(); await p.getByText('Launched').waitFor();
  step('launched; waiting for worker to send'); await p.waitForFunction(() => true);
  for (let i = 0; i < 30 && sql(`select count(*) from message where direction='out' and state='sent'`) < 2; i++) await new Promise(r => setTimeout(r, 1000));
  console.log('  sent:', sql(`select count(*) from message where direction='out' and state='sent'`), 'simulated:', sql(`select count(*) from message where simulated`));
  await p.goto(B + '/inbox'); await p.locator('ul button').first().click(); await p.getByText('Sandbox tools').waitFor(); await shot('07-inbox-sent');
  await p.getByLabel('Simulated reply text').fill('Sounds interesting - can we book a call next week?'); await p.getByRole('button', { name: 'Simulate reply' }).click();
  await p.getByText('Simulated reply received').waitFor(); await shot('08-inbox-reply'); step('simulated reply -> ' + sql(`select intent from message where direction='in'`));

  await p.goto(B + '/dashboard'); await p.getByText('Reply rate', { exact: true }).waitFor(); await p.waitForTimeout(500); await shot('09-dashboard');
  console.log('  dashboard text:', (await p.locator('section[aria-label="Key metrics"]').innerText()).replace(/\n+/g, ' | ').slice(0, 420));
  await p.goto(B + '/pipeline'); await p.getByText('engaged', { exact: false }).first().waitFor(); await shot('10-pipeline');
  await p.goto(B + '/leads'); await p.getByText('Asha Rao').waitFor(); await shot('11-leads');
  await p.getByRole('link', { name: 'Asha Rao' }).click(); await p.getByText('Research evidence').waitFor(); await p.waitForTimeout(300); await shot('12-lead-detail');
  await p.goto(B + '/jobs'); await p.getByText('Upcoming & held sends').waitFor(); await shot('13-jobs');
  await p.goto(B + '/activity'); await p.getByText('message.sent').first().waitFor(); await shot('14-activity');
  const m = await b.newPage({ viewport: { width: 375, height: 800 } }); await m.context().addCookies(await p.context().cookies());
  for (const [path, name] of [['/dashboard', 'm-dashboard'], ['/review', 'm-review'], ['/pipeline', 'm-pipeline']]) {
    await m.goto(B + path); await m.waitForTimeout(700);
    console.log('  mobile overflow', path, await m.evaluate(() => document.documentElement.scrollWidth > window.innerWidth)); await m.screenshot({ path: `${D}/shots/${name}.png` });
  }
  console.log('console errors:', errs); await b.close();
})().catch(e => { console.error('FAIL', e.message.split('\n').slice(0, 6).join('\n')); process.exit(1); });
