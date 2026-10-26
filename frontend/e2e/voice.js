// Voice dictation journey (Playwright + real Chrome with a fake microphone). See e2e/README.md for setup.
// Needs: API + worker + web running with STT_PROVIDER=fake (or a real speech server), and an admin user (E2E_EMAIL / E2E_PASSWORD).
// It records a generated tone, so it asserts behaviour (review step, insertion, cancel, denial), not particular words.
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path'); const os = require('os');
const B = process.env.E2E_BASE || 'http://localhost:3000'; const EMAIL = process.env.E2E_EMAIL || 'e2e@example.com'; const PASSWORD = process.env.E2E_PASSWORD || 'e2e-password-123';
const D = __dirname; fs.mkdirSync(D + '/shots', { recursive: true });
let failed = 0; const ok = (name, cond, extra = '') => { if (!cond) failed++; console.log((cond ? 'PASS ' : 'FAIL ') + name + (extra ? '  ' + extra : '')); };

// 4 s of 16 kHz mono 16-bit PCM (a quiet 220 Hz tone) so the fake microphone has something to play; no dependencies needed.
function toneWav(seconds = 4, rate = 16000) {
  const n = seconds * rate, data = Buffer.alloc(n * 2); for (let i = 0; i < n; i++) data.writeInt16LE(Math.round(6000 * Math.sin((2 * Math.PI * 220 * i) / rate)), i * 2);
  const h = Buffer.alloc(44); h.write('RIFF', 0); h.writeUInt32LE(36 + data.length, 4); h.write('WAVEfmt ', 8); h.writeUInt32LE(16, 16); h.writeUInt16LE(1, 20); h.writeUInt16LE(1, 22);
  h.writeUInt32LE(rate, 24); h.writeUInt32LE(rate * 2, 28); h.writeUInt16LE(2, 32); h.writeUInt16LE(16, 34); h.write('data', 36); h.writeUInt32LE(data.length, 40); return Buffer.concat([h, data]);
}
async function login(p) {
  await p.goto(B + '/login'); await p.getByLabel('Email').fill(EMAIL); await p.getByLabel('Password').fill(PASSWORD);
  await p.getByRole('button', { name: 'Sign in' }).click(); await p.waitForURL('**/dashboard');
}

(async () => {
  const wav = path.join(os.tmpdir(), 'flowhq-e2e-tone.wav'); fs.writeFileSync(wav, toneWav());
  const b = await chromium.launch({ args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${wav}%noloop`], channel: process.env.E2E_CHANNEL || 'chrome' });
  const p = await (await b.newContext({ viewport: { width: 1360, height: 900 }, permissions: ['microphone'] })).newPage(); const errs = [];
  p.on('pageerror', e => errs.push(String(e))); p.on('console', m => m.type() === 'error' && !/Failed to load resource|fonts\.g/.test(m.text()) && errs.push(m.text()));
  await login(p); await p.goto(B + '/campaigns/new');
  const offer = p.getByRole('textbox', { name: /^Offer/ }); await offer.waitFor();
  ok('microphone buttons on the campaign form', (await p.getByRole('button', { name: /^Dictate / }).count()) >= 4);
  ok('field is named by its label only (not by the mic buttons)', (await p.getByRole('textbox', { name: /Dictat/ }).count()) === 0);

  await offer.fill('We help clinics cut no-shows.'); await offer.evaluate(el => el.setSelectionRange(el.value.length, el.value.length));
  await p.getByRole('button', { name: 'Dictate offer' }).click();
  const stop = p.getByRole('button', { name: 'Stop and transcribe' }); await stop.waitFor(); await p.waitForFunction(() => !document.querySelector('[aria-label="Stop and transcribe"]').disabled);
  ok('recording indicator is visible', await p.getByTestId('recording-indicator').isVisible()); await p.waitForTimeout(2500);
  ok('field untouched while recording', (await offer.inputValue()) === 'We help clinics cut no-shows.');
  await stop.click();
  const dlg = p.getByRole('dialog', { name: /review your dictation/i }); await dlg.waitFor({ timeout: 60000 });
  const heard = await dlg.getByLabel('Transcript').inputValue(); ok('review step shows a transcript', heard.trim().length > 0, JSON.stringify(heard));
  ok('field untouched until Insert', (await offer.inputValue()) === 'We help clinics cut no-shows.'); await p.screenshot({ path: D + '/shots/voice-review.png' });
  await dlg.getByRole('button', { name: 'Insert' }).click();
  const after = await offer.inputValue(); ok('inserted after the existing text, nothing overwritten', after.startsWith('We help clinics cut no-shows. ') && after.length > 30, JSON.stringify(after));
  ok('nothing was submitted', p.url().endsWith('/campaigns/new'));

  await p.getByRole('button', { name: 'Dictate offer' }).click(); await p.getByTestId('recording-indicator').waitFor();
  await p.getByRole('button', { name: 'Cancel and discard recording' }).click();
  ok('cancel leaves the field alone', (await p.getByTestId('recording-indicator').count()) === 0 && (await offer.inputValue()) === after);

  await p.goto(B + '/integrations'); await p.getByRole('heading', { name: 'Voice dictation' }).waitFor();
  p.once('dialog', d => d.accept()); await p.getByRole('button', { name: 'Clear dictation history' }).click(); await p.getByText(/Cleared \d+ dictation/).waitFor();
  ok('history can be cleared', (await p.getByText('Nothing stored.').count()) === 1);
  ok('no JavaScript errors', errs.length === 0, errs.slice(0, 2).join(' | ')); await b.close();

  // a blocked microphone: no auto-accept flag, so headless Chrome refuses the permission prompt
  const b2 = await chromium.launch({ args: ['--use-fake-device-for-media-stream'], channel: process.env.E2E_CHANNEL || 'chrome' }); const p2 = await (await b2.newContext()).newPage(); await login(p2);
  await p2.goto(B + '/campaigns/new'); const o2 = p2.getByRole('textbox', { name: /^Offer/ }); await o2.fill('Keep me');
  await p2.getByRole('button', { name: 'Dictate offer' }).click(); const msg = await p2.getByRole('alert').first().innerText({ timeout: 15000 }).catch(() => '');
  ok('blocked microphone explains how to fix it and keeps the text', /microphone/i.test(msg) && (await o2.inputValue()) === 'Keep me', JSON.stringify(msg)); await b2.close();
  console.log(failed ? `\n${failed} CHECK(S) FAILED` : '\nALL VOICE E2E CHECKS PASSED'); process.exit(failed ? 1 : 0);
})().catch(e => { console.error('E2E CRASH', e); process.exit(2); });
