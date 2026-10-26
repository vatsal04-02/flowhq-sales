"use client";
import { useEffect, useMemo, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, AreaChart, Avatar, Badge, Card, Donut, Empty, Funnel, Icon, Link, PageHeader, Ring, Skeleton, StatCard, inputCls, td, th } from "@/components/ui";
import { api, Metric, Overview } from "@/lib/api";

type Camp = { id: string; name: string; status: string; contacted: number; sent: number; reply_rate: Metric; positive_reply_rate: Metric };
type Attn = { mailbox_errors: number; failed_jobs: number; failed_actions: number; drafts_to_review: number; positive_replies: number; upcoming_sends: number; llm_failures: number };
type Day = { date: string; sent: number; replies: number; positive: number };

const ICP_COLOR: Record<string, number> = { strong: 1, possible: 0, weak: 3, unqualified: 5, insufficient: 2, "not scored": 4 };
const pct = (m: Metric) => (m.denominator ? Math.round(m.value ?? 0) : null);
const frac = (m: Metric) => (m.denominator ? `${m.numerator} of ${m.denominator} leads` : "no leads contacted yet");

export default function Dashboard() {
  const [days, setDays] = useState(""); const [ov, setOv] = useState<Overview | null>(null); const [series, setSeries] = useState<Day[]>([]);
  const [camps, setCamps] = useState<Camp[]>([]); const [attn, setAttn] = useState<Attn | null>(null);
  const [channels, setChannels] = useState<{ channel: string; kind: string; messages: number; leads: number }[]>([]);
  const [me, setMe] = useState<string>(""); const [error, setError] = useState<string | null>(null);

  useEffect(() => { setOv(null); api<Overview>(`/analytics/overview${days ? `?days=${days}` : ""}`).then(setOv).catch((e) => setError(e.message)); }, [days]);
  useEffect(() => { api<Day[]>(`/analytics/timeseries?days=${days || 30}`).then(setSeries).catch(() => {}); }, [days]);
  useEffect(() => {
    api<Camp[]>("/analytics/campaigns").then(setCamps).catch(() => {}); api<Attn>("/analytics/attention").then(setAttn).catch(() => {});
    api<typeof channels>("/analytics/channels").then(setChannels).catch(() => {}); api<{ email: string }>("/me").then((m) => setMe(m.email.split("@")[0])).catch(() => {});
  }, []);

  const c = ov?.cards;
  const roll = (a: number[]) => a.map((_, i) => a.slice(Math.max(0, i - 6), i + 1).reduce((x, y) => x + y, 0)); // 7-day rolling sum reads as a trend
  const sentSpark = useMemo(() => roll(series.map((d) => d.sent)), [series]); const replySpark = useMemo(() => roll(series.map((d) => d.replies)), [series]);
  const tot = useMemo(() => ({ sent: series.reduce((a, d) => a + d.sent, 0), replies: series.reduce((a, d) => a + d.replies, 0), positive: series.reduce((a, d) => a + d.positive, 0) }), [series]);
  const hour = new Date().getHours(); const greet = hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const attention = attn ? [
    attn.positive_replies > 0 && { href: "/inbox", tone: "border-success/30 bg-success/10", icon: "inbox", text: <><b>{attn.positive_replies}</b> positive repl{attn.positive_replies === 1 ? "y" : "ies"} waiting</> },
    attn.drafts_to_review > 0 && { href: "/review", tone: "border-primary/30 bg-primary/10", icon: "edit", text: <><b>{attn.drafts_to_review}</b> draft{attn.drafts_to_review === 1 ? "" : "s"} to review</> },
    attn.failed_actions > 0 && { href: "/jobs", tone: "border-destructive/30 bg-destructive/10", icon: "alert", text: <><b>{attn.failed_actions}</b> failed or unconfirmed send{attn.failed_actions === 1 ? "" : "s"}</> },
    attn.mailbox_errors > 0 && { href: "/integrations", tone: "border-destructive/30 bg-destructive/10", icon: "alert", text: <><b>{attn.mailbox_errors}</b> mailbox{attn.mailbox_errors === 1 ? "" : "es"} can't be checked for replies</> },
    attn.failed_jobs > 0 && { href: "/jobs", tone: "border-destructive/30 bg-destructive/10", icon: "alert", text: <><b>{attn.failed_jobs}</b> failed background job{attn.failed_jobs === 1 ? "" : "s"}</> },
  ].filter(Boolean) as { href: string; tone: string; icon: any; text: React.ReactNode }[] : [];
  return (
    <Shell>
      <PageHeader title={`${greet}${me ? `, ${me}` : ""}`} subtitle={new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" })}>
        <select aria-label="Time window" className={`${inputCls} !w-auto`} value={days} onChange={(e) => setDays(e.target.value)}>
          <option value="">All time</option><option value="7">Last 7 days</option><option value="30">Last 30 days</option><option value="90">Last 90 days</option></select>
      </PageHeader>
      {error && <Alert>{error}</Alert>}
      {attention.length > 0 && (
        <section aria-label="Needs attention" className="mb-5 flex flex-wrap gap-2">{attention.map((a, i) => (
          <Link key={i} href={a.href} className={`flex items-center gap-2 rounded-full border px-3.5 py-1.5 text-sm transition-shadow hover:shadow-lift ${a.tone}`}><Icon name={a.icon} />{a.text}<span aria-hidden="true">→</span></Link>))}</section>)}
      {!c || !ov ? <Skeleton rows={6} /> : (
        <div className="space-y-5">
          <section aria-label="Key metrics" className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Imported leads" value={c.imported_leads.value} icon="users" caption="in your workspace" title={c.imported_leads.definition} />
            <StatCard label="Qualified leads" value={c.qualified_leads.value} icon="check" tone="success" caption="strong or possible fit" title={c.qualified_leads.definition} />
            <StatCard label="Messages sent" value={(c.messages_sent_real.value ?? 0) + (c.messages_sent_simulated.value ?? 0) + (c.messages_sent_manual.value ?? 0)} icon="send" spark={sentSpark}
              caption={`${c.messages_sent_real.value} real · ${c.messages_sent_simulated.value} simulated · ${c.messages_sent_manual.value} manual`} />
            <StatCard label="Replies (unique leads)" value={c.reply_rate.numerator ?? 0} icon="inbox" tone="accent" spark={replySpark} caption={`${c.leads_contacted.value} leads contacted`} title={c.reply_rate.definition} />
          </section>
          <div className="grid gap-5 lg:grid-cols-[1.7fr_1fr]">
            <Card title="Outreach activity" actions={<span className="text-xs text-muted-foreground">Messages per day · {days ? `last ${days} days` : "last 30 days"}</span>}>
              <AreaChart data={series} series={[{ key: "sent", label: "Sent", color: 0 }, { key: "replies", label: "Replies", color: 3, dash: "6 4" }, { key: "positive", label: "Positive replies", color: 1, dash: "2 3" }]} />
              <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-border pt-3 text-center">
                {([["Sent", tot.sent], ["Replies", tot.replies], ["Positive", tot.positive]] as const).map(([k, v]) => (<div key={k}><dt className="text-xs text-muted-foreground">{k} in period</dt><dd className="text-xl font-semibold tabular-nums">{v}</dd></div>))}
              </dl>
            </Card>
            <Card title="Conversion rates" actions={<span className="text-xs text-muted-foreground">of leads contacted</span>}>
              <div className="space-y-4">
                <Ring value={pct(c.reply_rate)} label="Reply rate" caption={frac(c.reply_rate)} color={0} />
                <Ring value={pct(c.positive_reply_rate)} label="Positive replies" caption={frac(c.positive_reply_rate)} color={1} />
                <Ring value={pct(c.meeting_conversion)} label="Meetings booked" caption={frac(c.meeting_conversion)} color={2} />
              </div>
              <p className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">Rates count unique leads, never messages. Simulated sends are sandbox only.</p>
            </Card>
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Pipeline funnel" actions={<span className="text-xs text-muted-foreground">% = from previous stage</span>}>
              {ov.funnel[0].count === 0 ? <Empty icon="users" title="No leads yet">Import a CSV to see your funnel.</Empty> : <Funnel steps={ov.funnel} />}
            </Card>
            <Card title="ICP fit distribution"><Donut parts={ov.icp_distribution.map((d) => ({ label: d.class, value: d.count, color: ICP_COLOR[d.class] ?? 4 }))} /></Card>
          </div>
          <section aria-label="Risk indicators" className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <StatCard label="Opportunities" value={c.opportunities.value} icon="kanban" caption={`${c.conversions.value} won`} title={c.opportunities.definition} />
            <StatCard label="Leads contacted" value={c.leads_contacted.value} icon="send" caption={ov.window} title={c.leads_contacted.definition} />
            <StatCard label="Unsubscribes" value={c.unsubscribes.value} icon="ban" tone={c.unsubscribes.value ? "danger" : "primary"} caption="permanently suppressed" title={c.unsubscribes.definition} />
            <StatCard label="Bounces" value={c.bounces.value} icon="alert" tone={c.bounces.value ? "danger" : "primary"} caption="permanently suppressed" title={c.bounces.definition} />
          </section>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card title="Campaign performance">
              {camps.length === 0 ? <Empty icon="megaphone" title="No campaigns yet"><Link className="text-primary underline" href="/campaigns/new">Create your first campaign</Link></Empty> : (
                <div className="-m-4 overflow-x-auto"><table className="w-full min-w-[460px] text-sm"><thead><tr><th className={th}>Campaign</th><th className={th}>Contacted</th><th className={th}>Reply</th><th className={th}>Positive</th></tr></thead>
                  <tbody className="divide-y divide-border">{camps.map((x) => (<tr key={x.id} className="transition-colors hover:bg-muted/40"><td className={td}><Link className="font-medium text-primary hover:underline" href={`/campaigns/${x.id}`}>{x.name}</Link> <Badge tone={x.status === "active" ? "success" : "neutral"}>{x.status}</Badge></td>
                    <td className={td}>{x.contacted}</td><td className={td}>{x.reply_rate.denominator ? `${x.reply_rate.value}%` : "—"}<div className="text-xs text-muted-foreground">{x.reply_rate.numerator ?? 0}/{x.reply_rate.denominator ?? 0}</div></td>
                    <td className={td}>{x.positive_reply_rate.denominator ? `${x.positive_reply_rate.value}%` : "—"}</td></tr>))}</tbody></table></div>)}
            </Card>
            <Card title="By channel">
              {channels.length === 0 ? <Empty icon="send" title="Nothing sent yet" /> : (
                <ul className="divide-y divide-border text-sm">{channels.map((x, i) => (<li key={i} className="flex items-center justify-between py-2.5">
                  <span className="flex items-center gap-2.5"><Avatar name={x.channel} size={28} /><span className="capitalize">{x.channel}</span> <Badge tone={x.kind === "real" ? "success" : x.kind === "manual" ? "info" : "warning"}>{x.kind}</Badge></span>
                  <span className="tabular-nums text-muted-foreground">{x.messages} msgs · {x.leads} leads</span></li>))}</ul>)}
            </Card>
          </div>
          <p className="text-xs text-muted-foreground">Window: {ov.window}. Funnel and ICP figures count all leads; contact metrics respect the selected window. Hover any card for its definition.</p>
        </div>)}
    </Shell>
  );
}
