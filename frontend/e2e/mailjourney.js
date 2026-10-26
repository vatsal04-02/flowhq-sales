// Real-mail journey (Playwright): SMTP send to a local SMTP server, reply via an independent IMAP server (pymap), sync, inbox, outage alert.
// Needs the same setup as journey.js plus: pymap on :14343 (pymap --port 14343 --no-tls dict) and an SMTP sink on :12525 (backend/tests/fakes/smtp_sink.py).
const { chromium } = require('playwright'); const fs = require('fs'); const { execSync } = require('child_process');
const D = __dirname; fs.mkdirSync(D + '/shots', { recursive: true }); const B = 'http://localhost:3000'; const PY = '/home/user/backend/.venv/bin/python';
fs.writeFileSync(D + '/dental2.csv', `Company,First Name,Last Name,Email,Website,Country,Title\nBright Smile Dental,Asha,Rao,asha@brightsmile.in,brightsmile.in,IN,Owner\n`);
const sql = (q) => execSync(`PGPASSWORD=flowhq psql -h localhost -U flowhq flowhq -qAt -c "${q}"`).toString().trim();
const append = (from, irt, body, extra = '') => execSync(`${PY} - <<'EOF2'
import sys, imaplib; sys.path.insert(0,'/home/user/backend')
from tests.fakes import mail
raw = mail.reply(${JSON.stringify(from)}, 'sales@flowhq-mail.com', ${JSON.stringify(body)}, in_reply_to=${irt ? JSON.stringify(irt) : 'None'}${extra})
c = imaplib.IMAP4('127.0.0.1', 14343); c.login('demouser','demopass'); c.append('INBOX', None, None, raw); c.logout()
EOF2`);
(async () => {
  const b = await chromium.launch(); const errs = [];
  const p = await b.newPage({ viewport: { width: 1360, height: 900 } });
  p.on('pageerror', e => errs.push(String(e))); p.on('console', m => m.type() === 'error' && !/fonts\.g|ERR_|Failed to load resource/.test(m.text()) && errs.push(m.text()));
  const api = (path, body) => p.evaluate(async ([path, body]) => { const r = await fetch('/api/v1' + path, { method: body === undefined ? 'GET' : 'POST', headers: { 'X-Requested-With': 'flowhq', 'Content-Type': 'application/json' }, body: body === undefined ? undefined : JSON.stringify(body) }); return r.json(); }, [path, body]);
  const step = (s) => console.log('•', s);
  await p.goto(B + '/login'); await p.getByLabel('Email').fill('e2e@example.com'); await p.getByLabel('Password').fill('e2e-password-123'); await p.getByRole('button', { name: 'Sign in' }).click(); await p.waitForURL('**/dashboard');

  await p.goto(B + '/integrations'); await p.getByRole('button', { name: 'Add SMTP' }).click();
  await p.getByLabel('Name', { exact: true }).fill('Sales mailbox'); await p.getByLabel('From address').fill('sales@flowhq-mail.com'); await p.getByLabel('SMTP host').fill('127.0.0.1');
  await p.getByLabel('Port', { exact: true }).fill('12525'); await p.locator('form select').nth(0).selectOption('none');
  await p.getByLabel('IMAP host', { exact: true }).fill('127.0.0.1'); await p.getByLabel('IMAP port', { exact: true }).fill('14343'); await p.getByLabel('IMAP username').fill('demouser'); await p.getByLabel('IMAP password').fill('demopass'); await p.locator('form select').nth(1).selectOption('none');
  await p.screenshot({ path: D + '/shots/50-smtp-form.png', fullPage: true });
  await p.getByRole('button', { name: 'Save account' }).click(); await p.getByText('SMTP account saved').waitFor();
  await p.getByText(/read-only sync OK|waiting for first check/).waitFor({ timeout: 20000 }); step('account saved with reply sync: ' + (await p.getByText(/Replies:/).first().innerText()));
  await p.getByRole('button', { name: 'Test', exact: true }).click(); await p.getByText('Sending: connection OK').waitFor({ timeout: 15000 }); step('connection test OK for SMTP');
  const acct = (await api('/integrations')).accounts[0];

  await p.goto(B + '/import'); await p.setInputFiles('input[type=file]', D + '/dental2.csv'); await p.getByRole('button', { name: /Upload and preview/ }).click();
  await p.getByRole('button', { name: 'Start import' }).click(); await p.getByText('Import completed').waitFor({ timeout: 30000 });
  sql(`UPDATE company SET website='http://127.0.0.1:8765'`);
  const batch = (await api('/imports'))[0]; const camp = await api('/campaigns', { name: 'Real mail test', offer: 'We automate appointment reminders so clinics see fewer no-shows.', sender_name: 'Vatsal', sender_company: 'FlowHQ', physical_address: '1 Example Street, Pune, India',
    channel_account_id: acct.id, work_start: 0, work_end: 24, icp: { industries: ['dental'], keywords: ['implants'], regions: ['IN'] } });
  await api(`/campaigns/${camp.id}/leads`, { batch_id: batch.id }); await api(`/campaigns/${camp.id}/research`, {});
  const wait = async (fn, what, ms = 60000) => { const t = Date.now(); while (Date.now() - t < ms) { if (await fn()) return; await new Promise(r => setTimeout(r, 700)); } throw new Error('timeout: ' + what); };
  await wait(() => sql(`select count(*) from research_evidence`) > 0, 'research'); await api(`/campaigns/${camp.id}/qualify`, {});
  await wait(() => sql(`select count(*) from campaign_lead where icp_class='strong'`) > 0, 'score'); await api(`/campaigns/${camp.id}/generate-messages`, {});
  await wait(() => sql(`select count(*) from generated_message`) >= 3, 'drafts'); await api(`/campaigns/${camp.id}/approve`, { all_clean: true });
  const l = await api(`/campaigns/${camp.id}/launch`, {}); step('launched: ' + JSON.stringify(l));
  await wait(() => sql(`select count(*) from message where direction='out' and state='sent' and not simulated`) > 0, 'real send');
  const mid = sql(`select message_id_header from message where direction='out' limit 1`);
  step('sent through real SMTP, Message-ID ' + mid + '; simulated=' + sql(`select simulated from message where direction='out'`));

  append('Asha Rao <asha@brightsmile.in>', mid, 'Sounds interesting - can we book a call next week?');
  append('Stranger <stranger@elsewhere.com>', null, 'Hello, do you sell widgets?', ', subject="Widgets?"');
  await p.goto(B + '/integrations'); await p.getByRole('button', { name: 'Check mailbox now' }).click(); await p.getByText('Mailbox check queued').waitFor();
  await wait(() => sql(`select count(*) from message where direction='in'`) > 0, 'reply ingested', 30000);
  step('reply ingested: intent=' + sql(`select intent from message where direction='in'`) + ' lead status=' + sql(`select status from lead`) + ' unmatched=' + sql(`select count(*) from provider_event where kind='reply_unmatched'`));
  await p.goto(B + '/inbox'); await p.getByText('Asha Rao').first().waitFor(); await p.getByText('could not be matched').waitFor(); await p.getByText('Asha Rao').first().click();
  await p.getByText('Sounds interesting').waitFor(); await p.locator('details summary').click(); await p.screenshot({ path: D + '/shots/51-inbox-real-reply.png', fullPage: true });
  await p.goto(B + '/integrations'); await p.waitForTimeout(800); await p.screenshot({ path: D + '/shots/52-integrations-synced.png', fullPage: true });

  execSync("ps aux | grep 'bin/pymap' | grep -v grep | awk '{print $2}' | xargs -r kill"); await new Promise(r => setTimeout(r, 600));
  await p.getByRole('button', { name: 'Check mailbox now' }).click(); await p.getByText(/mailbox check failing/).waitFor({ timeout: 40000 }); step('mailbox outage is visible: ' + (await p.getByText(/mailbox check failing/).first().innerText()).slice(0, 110));
  await p.goto(B + '/dashboard'); await p.getByText(/can't be checked for replies/).waitFor(); await p.waitForTimeout(500); await p.screenshot({ path: D + '/shots/53-dashboard-mailbox-alert.png' });
  step('dashboard shows the mailbox alert'); console.log('console errors:', errs); await b.close();
})().catch(e => { console.error('FAIL', e.message.split('\n').slice(0, 5).join('\n')); process.exit(1); });
