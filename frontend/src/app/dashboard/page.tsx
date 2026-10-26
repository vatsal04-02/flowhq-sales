"use client";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, BarRow, Badge, Card, Empty, Kpi, Link, PageHeader, Skeleton, inputCls, th, td } from "@/components/ui";
import { api, Metric, Overview } from "@/lib/api";

type Camp = { id: string; name: string; status: string; contacted: number; sent: number; reply_rate: Metric; positive_reply_rate: Metric };
type Attn = { failed_jobs: number; failed_actions: number; drafts_to_review: number; positive_replies: number; upcoming_sends: number; llm_failures: number };

const pct = (m: Metric) => (m.denominator ? `${m.value}%` : "—");
const frac = (m: Metric) => (m.denominator ? `${m.numerator} of ${m.denominator} leads` : "no leads contacted yet");

export default function Dashboard() {
  const [days, setDays] = useState(""); const [ov, setOv] = useState<Overview | null>(null);
  const [camps, setCamps] = useState<Camp[]>([]); const [attn, setAttn] = useState<Attn | null>(null);
  const [channels, setChannels] = useState<{ channel: string; kind: string; messages: number; leads: number }[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOv(null);
    api<Overview>(`/analytics/overview${days ? `?days=${days}` : ""}`).then(setOv).catch((e) => setError(e.message));
  }, [days]);
  useEffect(() => {
    api<Camp[]>("/analytics/campaigns").then(setCamps).catch(() => {});
    api<Attn>("/analytics/attention").then(setAttn).catch(() => {});
    api<typeof channels>("/analytics/channels").then(setChannels).catch(() => {});
  }, []);

  const c = ov?.cards;
  const maxFunnel = ov ? Math.max(...ov.funnel.map((f) => f.count), 1) : 1;
  const maxIcp = ov ? Math.max(...ov.icp_distribution.map((f) => f.count), 1) : 1;
  return (
    <Shell>
      <PageHeader title="Dashboard">
        <select aria-label="Time window" className={`${inputCls} !w-auto`} value={days} onChange={(e) => setDays(e.target.value)}>
          <option value="">All time</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select>
      </PageHeader>
      {error && <Alert>{error}</Alert>}
      {attn && (attn.failed_jobs + attn.failed_actions + attn.positive_replies + attn.drafts_to_review > 0) && (
        <section aria-label="Needs attention" className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {attn.positive_replies > 0 && <Link href="/inbox" className="rounded border border-success/40 bg-success/10 p-3 text-sm"><b>{attn.positive_replies}</b> positive repl{attn.positive_replies === 1 ? "y" : "ies"} waiting</Link>}
          {attn.drafts_to_review > 0 && <Link href="/review" className="rounded border border-primary/30 bg-primary/10 p-3 text-sm"><b>{attn.drafts_to_review}</b> draft{attn.drafts_to_review === 1 ? "" : "s"} to review</Link>}
          {attn.failed_actions > 0 && <Link href="/jobs" className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm"><b>{attn.failed_actions}</b> failed or unconfirmed send{attn.failed_actions === 1 ? "" : "s"}</Link>}
          {attn.failed_jobs > 0 && <Link href="/jobs" className="rounded border border-destructive/40 bg-destructive/10 p-3 text-sm"><b>{attn.failed_jobs}</b> failed background job{attn.failed_jobs === 1 ? "" : "s"}</Link>}
        </section>)}
      {!c ? <Skeleton rows={4} /> : (
        <>
          <section aria-label="Key metrics" className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Kpi label="Imported leads" value={c.imported_leads.value} title={c.imported_leads.definition} />
            <Kpi label="Qualified leads" value={c.qualified_leads.value} caption="strong or possible fit" title={c.qualified_leads.definition} />
            <Kpi label="Leads contacted" value={c.leads_contacted.value} caption={ov!.window} title={c.leads_contacted.definition} />
            <Kpi label="Messages sent" value={(c.messages_sent_real.value ?? 0) + (c.messages_sent_simulated.value ?? 0) + (c.messages_sent_manual.value ?? 0)}
              caption={`${c.messages_sent_real.value} real · ${c.messages_sent_simulated.value} simulated · ${c.messages_sent_manual.value} manual`} />
            <Kpi label="Reply rate" value={pct(c.reply_rate)} caption={frac(c.reply_rate)} title={c.reply_rate.definition} />
            <Kpi label="Positive reply rate" value={pct(c.positive_reply_rate)} caption={frac(c.positive_reply_rate)} title={c.positive_reply_rate.definition} />
            <Kpi label="Meeting conversion" value={pct(c.meeting_conversion)} caption={frac(c.meeting_conversion)} title={c.meeting_conversion.definition} />
            <Kpi label="Opportunities / won" value={`${c.opportunities.value} / ${c.conversions.value}`} title={c.opportunities.definition} />
            <Kpi label="Unsubscribes" value={c.unsubscribes.value} tone={c.unsubscribes.value ? "danger" : undefined} title={c.unsubscribes.definition} />
            <Kpi label="Bounces" value={c.bounces.value} tone={c.bounces.value ? "danger" : undefined} title={c.bounces.definition} />
          </section>
          <p className="mt-2 text-xs text-muted-foreground">Rates are unique leads, never message counts. Simulated sends come from the mock sandbox and are not real emails. Hover a card for its definition.</p>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Funnel (leads)">
              {ov!.funnel[0].count === 0 ? <Empty icon="users" title="No data yet">Import a CSV to start.</Empty> :
                <div className="space-y-2">{ov!.funnel.map((f) => <BarRow key={f.stage} label={f.stage} value={f.count} max={maxFunnel} />)}</div>}
            </Card>
            <Card title="ICP fit distribution (all leads)">
              <div className="space-y-2">{ov!.icp_distribution.map((f) => <BarRow key={f.class} label={f.class} value={f.count} max={maxIcp} />)}</div>
            </Card>
          </div>
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <Card title="Campaign performance">
              {camps.length === 0 ? <Empty icon="megaphone" title="No campaigns yet"><Link className="text-primary underline" href="/campaigns/new">Create your first campaign</Link></Empty> : (
                <div className="-m-4 overflow-x-auto"><table className="w-full min-w-[460px] text-sm"><thead><tr><th className={th}>Campaign</th><th className={th}>Contacted</th><th className={th}>Reply</th><th className={th}>Positive</th></tr></thead>
                  <tbody className="divide-y divide-border">{camps.map((x) => (<tr key={x.id}><td className={td}><Link className="text-primary hover:underline" href={`/campaigns/${x.id}`}>{x.name}</Link> <Badge>{x.status}</Badge></td>
                    <td className={td}>{x.contacted}</td><td className={td}>{pct(x.reply_rate)}<div className="text-xs text-muted-foreground">{x.reply_rate.numerator ?? 0}/{x.reply_rate.denominator ?? 0}</div></td>
                    <td className={td}>{pct(x.positive_reply_rate)}</td></tr>))}</tbody></table></div>)}
            </Card>
            <Card title="By channel (sent messages)">
              {channels.length === 0 ? <Empty icon="send" title="Nothing sent yet" /> : (
                <ul className="divide-y divide-border text-sm">{channels.map((x, i) => (<li key={i} className="flex items-center justify-between py-2">
                  <span className="capitalize">{x.channel} <Badge tone={x.kind === "real" ? "success" : x.kind === "manual" ? "info" : "warning"}>{x.kind}</Badge></span>
                  <span className="tabular-nums">{x.messages} msgs · {x.leads} leads</span></li>))}</ul>)}
            </Card>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">Window: {ov!.window}. Funnel and ICP figures count all leads; contact metrics respect the selected window.</p>
        </>)}
    </Shell>
  );
}
