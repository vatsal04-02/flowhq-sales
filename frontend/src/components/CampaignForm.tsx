"use client";
import { useEffect, useState } from "react";
import { Alert, Button, Card, Field, Input, inputCls } from "@/components/ui";
import { Account, Campaign, api } from "@/lib/api";

const list = (s: string) => s.split(",").map((x) => x.trim()).filter(Boolean);
const TZ = ["UTC", "Asia/Kolkata", "America/New_York", "America/Los_Angeles", "Europe/London", "Asia/Dubai", "Asia/Singapore", "Australia/Sydney"];

export default function CampaignForm({ initial, onSaved }: { initial?: Campaign; onSaved: (c: Campaign) => void }) {
  const [f, setF] = useState({
    name: initial?.name ?? "", offer: initial?.offer ?? "", objective: initial?.objective ?? "Book a short intro call", tone: initial?.tone ?? "friendly, concise, professional",
    sender_name: initial?.sender_name ?? "", sender_company: initial?.sender_company ?? "", physical_address: initial?.physical_address ?? "",
    timezone: initial?.timezone ?? "UTC", work_start: initial?.work_start ?? 9, work_end: initial?.work_end ?? 17, daily_limit: initial?.daily_limit ?? 30,
    channels: initial?.channels ?? ["email"], channel_account_id: initial?.channel_account_id ?? "",
    industries: (initial?.icp.industries ?? []).join(", "), regions: (initial?.icp.regions ?? []).join(", "), keywords: (initial?.icp.keywords ?? []).join(", "),
    exclude: (initial?.icp.exclude_keywords ?? []).join(", "), min_evidence: initial?.icp.min_evidence ?? 2,
    strong: initial?.thresholds.strong ?? 80, possible: initial?.thresholds.possible ?? 60, weak: initial?.thresholds.weak ?? 40,
    blocked: (initial?.blocked_regions ?? ["GB", "DE", "FR", "IT", "ES", "NL", "IE", "CA"]).join(", "),
  });
  const [seq, setSeq] = useState(initial?.sequence ?? [{ step: 0, day: 0 }, { step: 1, day: 3 }, { step: 2, day: 7 }]);
  const [accounts, setAccounts] = useState<Account[]>([]); const [err, setErr] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const set = (k: string, v: any) => setF((p) => ({ ...p, [k]: v }));
  useEffect(() => { api<{ accounts: Account[] }>("/integrations").then((r) => setAccounts(r.accounts.filter((a) => a.status === "active"))).catch(() => {}); }, []);

  async function save(e: React.FormEvent) {
    e.preventDefault(); setErr(null); setBusy(true);
    const body = {
      name: f.name, offer: f.offer, objective: f.objective, tone: f.tone, sender_name: f.sender_name, sender_company: f.sender_company,
      physical_address: f.physical_address, timezone: f.timezone, work_start: +f.work_start, work_end: +f.work_end, daily_limit: +f.daily_limit,
      channels: f.channels, channel_account_id: f.channel_account_id || null, sequence: seq,
      icp: { industries: list(f.industries), regions: list(f.regions), keywords: list(f.keywords), exclude_keywords: list(f.exclude), min_evidence: +f.min_evidence },
      thresholds: { strong: +f.strong, possible: +f.possible, weak: +f.weak }, blocked_regions: list(f.blocked).map((x) => x.toUpperCase()),
    };
    try { onSaved(initial ? await api<Campaign>(`/campaigns/${initial.id}`, { method: "PATCH", json: body }) : await api<Campaign>("/campaigns", { method: "POST", json: body })); }
    catch (e2) { setErr((e2 as Error).message); } finally { setBusy(false); }
  }
  const toggle = (ch: string) => set("channels", f.channels.includes(ch) ? f.channels.filter((c) => c !== ch) : [...f.channels, ch]);
  return (
    <form onSubmit={save} className="space-y-4">
      {err && <Alert>{err}</Alert>}
      <Card title="Offer & sender">
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Campaign name"><Input value={f.name} onChange={(e) => set("name", e.target.value)} required /></Field>
          <Field label="Objective"><Input value={f.objective} onChange={(e) => set("objective", e.target.value)} /></Field>
          <div className="md:col-span-2"><Field label="Offer (1–2 plain sentences, no claims you can't prove)" hint="This sentence goes into every message verbatim.">
            <textarea className={`${inputCls} py-2`} rows={3} value={f.offer} onChange={(e) => set("offer", e.target.value)} required /></Field></div>
          <Field label="Sender name"><Input value={f.sender_name} onChange={(e) => set("sender_name", e.target.value)} /></Field>
          <Field label="Sender company"><Input value={f.sender_company} onChange={(e) => set("sender_company", e.target.value)} /></Field>
          <div className="md:col-span-2"><Field label="Physical postal address" hint="Required in the email footer (CAN-SPAM). Sending is blocked without it."><Input value={f.physical_address} onChange={(e) => set("physical_address", e.target.value)} /></Field></div>
          <Field label="Tone"><Input value={f.tone} onChange={(e) => set("tone", e.target.value)} /></Field>
        </div>
      </Card>
      <Card title="Ideal customer profile (scoring)">
        <p className="mb-3 text-sm text-muted-foreground">Comma-separated. Anything the research can't determine stays <b>unknown</b>: it neither helps nor hurts the score, it lowers confidence.</p>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Target industries"><Input value={f.industries} onChange={(e) => set("industries", e.target.value)} placeholder="dental, clinic" /></Field>
          <Field label="Target regions (ISO codes)"><Input value={f.regions} onChange={(e) => set("regions", e.target.value)} placeholder="IN, US" /></Field>
          <Field label="Service / pain-point keywords"><Input value={f.keywords} onChange={(e) => set("keywords", e.target.value)} placeholder="implants, orthodontics" /></Field>
          <Field label="Exclude if found"><Input value={f.exclude} onChange={(e) => set("exclude", e.target.value)} placeholder="franchise" /></Field>
          <Field label="Min. evidence items"><Input type="number" min={0} value={f.min_evidence} onChange={(e) => set("min_evidence", e.target.value)} /></Field>
          <div className="grid grid-cols-3 gap-2">
            <Field label="Strong ≥"><Input type="number" value={f.strong} onChange={(e) => set("strong", e.target.value)} /></Field>
            <Field label="Possible ≥"><Input type="number" value={f.possible} onChange={(e) => set("possible", e.target.value)} /></Field>
            <Field label="Weak ≥"><Input type="number" value={f.weak} onChange={(e) => set("weak", e.target.value)} /></Field></div>
        </div>
      </Card>
      <Card title="Channels & sequence">
        <fieldset className="mb-3"><legend className="mb-1 text-sm font-medium">Channels</legend>
          <div className="flex flex-wrap gap-4 text-sm">
            {[["email", "Email (sent automatically after approval)"], ["linkedin", "LinkedIn (manual: you send)"], ["instagram", "Instagram (manual: you send)"]].map(([k, l]) => (
              <label key={k} className="flex min-h-[44px] items-center gap-2 md:min-h-0"><input type="checkbox" checked={f.channels.includes(k)} onChange={() => toggle(k)} />{l}</label>))}</div></fieldset>
        <div className="grid gap-3 md:grid-cols-2">
          <Field label="Sending account (email)"><select className={inputCls} value={f.channel_account_id} onChange={(e) => set("channel_account_id", e.target.value)}>
            <option value="">None selected</option>{accounts.map((a) => <option key={a.id} value={a.id}>{a.name}{a.simulated ? " (simulated)" : ""}</option>)}</select></Field>
          <Field label="Daily limit (this campaign)"><Input type="number" min={1} max={500} value={f.daily_limit} onChange={(e) => set("daily_limit", e.target.value)} /></Field>
          <Field label="Time zone"><select className={inputCls} value={f.timezone} onChange={(e) => set("timezone", e.target.value)}>{[...new Set([f.timezone, ...TZ])].map((t) => <option key={t}>{t}</option>)}</select></Field>
          <div className="grid grid-cols-2 gap-2"><Field label="Send from (hour)"><Input type="number" min={0} max={23} value={f.work_start} onChange={(e) => set("work_start", e.target.value)} /></Field>
            <Field label="Send until (hour)"><Input type="number" min={1} max={24} value={f.work_end} onChange={(e) => set("work_end", e.target.value)} /></Field></div>
          <div className="md:col-span-2"><Field label="Never contact these regions (ISO codes)" hint="Default blocks EU/UK/CA until you record a lawful basis. Check your own legal position."><Input value={f.blocked} onChange={(e) => set("blocked", e.target.value)} /></Field></div>
        </div>
        <div className="mt-4"><div className="mb-1 text-sm font-medium">Follow-up sequence (days after the first message)</div>
          <ul className="space-y-2">{seq.map((s, i) => (<li key={i} className="flex items-center gap-2 text-sm">
            <span className="w-20 text-muted-foreground">{i === 0 ? "First message" : `Follow-up ${i}`}</span>
            <label className="flex items-center gap-1">day <Input type="number" min={0} className="w-20" value={s.day} disabled={i === 0} onChange={(e) => setSeq(seq.map((x, j) => (j === i ? { ...x, day: +e.target.value } : x)))} /></label>
            {i > 0 && <Button type="button" variant="ghost" onClick={() => setSeq(seq.filter((_, j) => j !== i).map((x, j) => ({ ...x, step: j })))}>Remove</Button>}</li>))}</ul>
          {seq.length < 5 && <Button type="button" className="mt-2" onClick={() => setSeq([...seq, { step: seq.length, day: (seq[seq.length - 1]?.day ?? 0) + 4 }])}>Add follow-up</Button>}
          <p className="mt-2 text-xs text-muted-foreground">Follow-ups stop automatically on a reply, opt-out, bounce, pause or kill switch. Each follow-up draft needs approval too.</p></div>
      </Card>
      <Button variant="primary" disabled={busy}>{busy ? "Saving…" : initial ? "Save changes" : "Create campaign"}</Button>
    </form>
  );
}
