"use client";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, Avatar, Badge, Button, Card, Empty, Icon, Link, PageHeader, Skeleton, pretty, statusTone } from "@/components/ui";
import { api, LeadDetail } from "@/lib/api";

const rtone = (r: string) => (r === "match" ? "success" : r === "no_match" ? "danger" : "warning") as any;

export default function LeadPage() {
  const { id } = useParams<{ id: string }>();
  const [lead, setLead] = useState<LeadDetail | null>(null); const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const load = useCallback(() => api<LeadDetail>(`/leads/${id}`).then(setLead).catch((e) => setError(e.message)), [id]);
  useEffect(() => { load(); }, [load]);

  async function apply(status: string) {
    setError(null);
    try { await api(`/leads/${id}`, { method: "PATCH", json: { status } }); setConfirming(null); load(); }
    catch (e) { setError((e as Error).message); setConfirming(null); }
  }
  if (!lead) return <Shell>{error ? <Alert>{error}</Alert> : <Skeleton />}</Shell>;
  const rows: [string, string | null][] = [["Email", lead.email_norm], ["Phone", lead.phone_e164], ["LinkedIn", lead.linkedin_url],
    ["Instagram", lead.instagram_url], ["Region", lead.region], ["Lawful basis", lead.lawful_basis],
    ["Company", lead.company?.name ?? null], ["Domain", lead.company?.domain ?? null]];
  const stopped = ["unsubscribed", "suppressed", "bounced"].includes(lead.status);
  return (
    <Shell>
      <p className="mb-2 text-sm"><Link href="/leads" className="text-primary underline">← Leads</Link></p>
      <PageHeader title={[lead.first_name, lead.last_name].filter(Boolean).join(" ") || "(no name)"} subtitle={[lead.title, lead.company?.name].filter(Boolean).join(" · ") || lead.email_norm}>
        <Avatar name={[lead.first_name, lead.last_name].filter(Boolean).join(" ") || lead.email_norm || "?"} size={40} />
        <Badge tone={statusTone(lead.status)}>{pretty(lead.status)}</Badge>
        {lead.opted_out && <Badge tone="danger">opted out</Badge>}
        {lead.possible_duplicate_of && <Badge tone="warning">possible duplicate</Badge>}
      </PageHeader>
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}
      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Contact & company">
          <dl className="grid grid-cols-[110px_1fr] gap-y-1.5 text-sm">
            {rows.map(([k, v]) => (<div key={k} className="contents"><dt className="text-muted-foreground">{k}</dt><dd className="mono break-all text-xs leading-6">{v ?? "—"}</dd></div>))}
          </dl>
          <details className="mt-4"><summary className="cursor-pointer text-sm font-medium">Original CSV values</summary>
            <pre className="mono mt-2 max-h-56 overflow-auto rounded bg-muted p-2 text-xs">{JSON.stringify(lead.raw, null, 2)}</pre></details>
        </Card>
        <Card title="Activity timeline">
          {lead.timeline.length === 0 ? <Empty icon="activity" title="No activity yet" /> : (
            <ol className="space-y-2 text-sm">{lead.timeline.map((t, i) => (
              <li key={i} className="flex justify-between gap-3 border-b border-border pb-2 last:border-0"><span>{t.kind.replace(/[._]/g, " ")}</span>
                <time className="text-xs text-muted-foreground" dateTime={t.at}>{new Date(t.at).toLocaleString()}</time></li>))}</ol>)}
        </Card>
        <Card title="Research evidence" actions={<div className="flex items-center gap-2"><Badge tone={lead.research_status === "done" ? "success" : "warning"}>{lead.research_status === "none" ? "not researched" : lead.research_status}</Badge>
          <Button variant="ghost" onClick={() => api(`/leads/${id}/research?force=true`, { method: "POST" }).then(() => alert("Research queued. Reload in a few seconds.")).catch((e) => setError(e.message))}>Re-run</Button></div>}>
          {lead.evidence.length === 0 ? <Empty icon="info" title={lead.research_status === "none" ? "Not researched yet" : "No usable evidence found"}>{lead.research_status === "insufficient" || lead.research_status === "failed" ? "The site had too little public text, blocked fetching, or none was listed. Nothing is guessed: drafts stay conservative and need manual review." : "Run research from a campaign or the leads list."}</Empty> : (
            <ul className="space-y-3 text-sm">{lead.evidence.filter((e) => e.finding !== "Homepage text sample").map((e) => (<li key={e.id}>
              <div className="flex flex-wrap items-center gap-2"><b>{e.finding}</b><Badge tone="success">{e.kind}</Badge><Badge>{e.confidence}</Badge></div>
              <blockquote className="mt-1 border-l-2 border-primary pl-2 text-muted-foreground">“{e.excerpt}”</blockquote>
              <a className="mt-1 inline-flex items-center gap-1 break-all text-xs text-primary underline" href={e.url} target="_blank" rel="noopener noreferrer"><Icon name="external" className="h-3 w-3" />{e.url}</a>
              {e.retrieved_at && <span className="ml-2 text-xs text-muted-foreground">retrieved {new Date(e.retrieved_at).toLocaleString()}</span>}</li>))}</ul>)}
        </Card>
        <Card title="ICP score">
          {!lead.icp_class ? <Empty icon="info" title="Not scored">Add this lead to a campaign and run "Score all".</Empty> : (<>
            <div className="mb-3 flex items-center gap-3"><span className="text-3xl font-semibold tabular-nums">{lead.icp_score ?? "n/a"}</span><Badge tone={lead.icp_class === "strong" ? "success" : lead.icp_class === "possible" ? "info" : "warning"}>{lead.icp_class}</Badge>
              <span className="text-xs text-muted-foreground">confidence {lead.icp_confidence}%</span></div>
            <ul className="space-y-2 text-sm">{lead.icp_breakdown.map((c) => (<li key={c.key} className="flex items-start justify-between gap-2"><span>{c.label}<span className="block text-xs text-muted-foreground">{c.detail}</span></span>
              <Badge tone={rtone(c.result)}>{c.result === "unknown" ? "unknown (not scored)" : c.result.replace("_", " ")}</Badge></li>))}</ul>
            <p className="mt-3 text-xs text-muted-foreground">Unknown facts are left out of the score and lower confidence instead of counting as a match or a miss. Latest campaign's criteria.</p></>)}
        </Card>
        <Card title="Outreach controls" className="lg:col-span-2">
          {stopped ? <p className="text-sm text-muted-foreground">This lead is permanently excluded from outreach.</p> : confirming ? (
            <Alert tone="info"><p className="mb-2">Mark this lead as <b>{pretty(confirming)}</b>? All outreach stops and the email is added to the suppression list. This cannot be undone from the UI.</p>
              <div className="flex gap-2"><Button variant="danger" onClick={() => apply(confirming)}>Confirm</Button><Button onClick={() => setConfirming(null)}>Cancel</Button></div></Alert>
          ) : (
            <div className="flex flex-wrap gap-2"><Button variant="danger" onClick={() => setConfirming("unsubscribed")}>Mark unsubscribed</Button>
              <Button variant="danger" onClick={() => setConfirming("suppressed")}>Suppress</Button></div>)}
        </Card>
      </div>
    </Shell>
  );
}
