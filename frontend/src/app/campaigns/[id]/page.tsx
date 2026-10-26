"use client";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import CampaignForm from "@/components/CampaignForm";
import Shell from "@/components/Shell";
import { Alert, Badge, Button, Card, Icon, Link, PageHeader, Skeleton, inputCls, pretty, th, td } from "@/components/ui";
import { Batch, Campaign, Criterion, Job, api } from "@/lib/api";

type CL = { lead_id: string; name: string | null; email: string | null; company: string | null; lead_status: string; research_status: string; state: string;
  stop_reason: string | null; icp_score: number | null; icp_class: string | null; icp_confidence: number | null; icp_breakdown: Criterion[] };
type Ready = { ready: boolean; checks: { key: string; label: string; ok: boolean }[] };
const classTone = (c: string | null) => (c === "strong" ? "success" : c === "possible" ? "info" : c === "insufficient" ? "warning" : c ? "neutral" : "neutral") as any;

export default function CampaignPage() {
  const { id } = useParams<{ id: string }>();
  const [c, setC] = useState<Campaign | null>(null); const [leads, setLeads] = useState<CL[]>([]); const [ready, setReady] = useState<Ready | null>(null);
  const [batches, setBatches] = useState<Batch[]>([]); const [batch, setBatch] = useState(""); const [busyJobs, setBusyJobs] = useState(0);
  const [error, setError] = useState<string | null>(null); const [note, setNote] = useState<string | null>(null); const [editing, setEditing] = useState(false);
  const [open, setOpen] = useState<string | null>(null); const [incl, setIncl] = useState(false);

  const load = useCallback(async () => {
    try {
      setC(await api<Campaign>(`/campaigns/${id}`)); setLeads(await api<CL[]>(`/campaigns/${id}/leads`)); setReady(await api<Ready>(`/campaigns/${id}/readiness`));
      const jobs = await api<Job[]>("/jobs"); setBusyJobs(jobs.filter((j) => ["pending", "running"].includes(j.state)).length);
    } catch (e) { setError((e as Error).message); }
  }, [id]);
  useEffect(() => { load(); api<Batch[]>("/imports").then(setBatches).catch(() => {}); }, [load]);
  useEffect(() => { if (!busyJobs) return; const t = setInterval(load, 2500); return () => clearInterval(t); }, [busyJobs, load]);

  async function act(path: string, body?: unknown, msg?: string) {
    setError(null); setNote(null);
    try { const r: any = await api(path, { method: "POST", json: body }); setNote(msg ?? (r.added !== undefined ? `Added ${r.added} lead(s), skipped ${r.skipped}.` : "Started. Progress updates below.")); await load(); }
    catch (e: any) { setError(e.message + (e.code === "not_ready" ? "" : "")); await load(); }
  }
  if (!c) return <Shell>{error ? <Alert>{error}</Alert> : <Skeleton />}</Shell>;
  const total = Object.values(c.lead_counts).reduce((a, b) => a + b, 0);
  const drafts = Object.values(c.message_counts).reduce((a, b) => a + b, 0);
  const researched = leads.filter((l) => l.research_status !== "none").length; const scored = leads.filter((l) => l.icp_class).length;
  return (
    <Shell>
      <p className="mb-2 text-sm"><Link href="/campaigns" className="text-primary underline">← Campaigns</Link></p>
      <PageHeader title={c.name}>
        <Badge tone={c.status === "active" ? "success" : c.status === "paused" ? "warning" : "neutral"}>{c.status}</Badge>
        {c.status === "active" && <Button onClick={() => act(`/campaigns/${id}/pause`, undefined, "Campaign paused. Queued sends are held, not lost.")}><Icon name="pause" />Pause</Button>}
        {c.status === "paused" && <Button variant="primary" onClick={() => act(`/campaigns/${id}/resume`, undefined, "Campaign resumed.")}><Icon name="play" />Resume</Button>}
        <Button onClick={() => setEditing(!editing)}><Icon name="edit" />{editing ? "Close settings" : "Settings"}</Button>
      </PageHeader>
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}
      {note && <div className="mb-3"><Alert tone="success">{note}</Alert></div>}
      {busyJobs > 0 && <div className="mb-3"><Alert tone="info">{busyJobs} background job{busyJobs === 1 ? "" : "s"} running. This page refreshes automatically.</Alert></div>}
      {editing && <div className="mb-4"><CampaignForm initial={c} onSaved={(x) => { setC(x); setEditing(false); setNote("Settings saved."); }} /></div>}

      <ol className="grid gap-4">
        <Card title={`1. Leads (${total})`} actions={<span className="text-xs text-muted-foreground">Suppressed or opted-out leads are never added</span>}>
          <div className="flex flex-wrap items-end gap-2">
            <label className="text-sm">Add all leads from an import
              <select className={`${inputCls} mt-1 min-w-64`} value={batch} onChange={(e) => setBatch(e.target.value)}><option value="">Choose an import…</option>
                {batches.map((b) => <option key={b.id} value={b.id}>{b.filename} — {b.created_count} leads</option>)}</select></label>
            <Button disabled={!batch} onClick={() => act(`/campaigns/${id}/leads`, { batch_id: batch })}>Add leads</Button>
            <Link href="/leads" className="text-sm text-primary underline">or pick leads individually in Leads</Link></div>
        </Card>
        <Card title={`2. Research & score (${researched}/${total} researched, ${scored} scored)`}
          actions={<div className="flex gap-2"><Button disabled={!total} onClick={() => act(`/campaigns/${id}/research`, undefined, "Research queued. Websites are fetched politely and robots.txt is respected.")}>Research all</Button>
            <Button disabled={!total} onClick={() => act(`/campaigns/${id}/qualify`)}>Score all</Button></div>}>
          {leads.length === 0 ? <p className="text-sm text-muted-foreground">Add leads first.</p> : (
            <div className="-m-4 overflow-x-auto"><table className="w-full min-w-[680px] text-sm"><thead className="border-b border-border bg-muted/60"><tr>
              <th className={th}>Lead</th><th className={th}>Research</th><th className={th}>Fit</th><th className={th}>Score</th><th className={th}>Confidence</th><th className={th}>Sequence</th></tr></thead>
              <tbody className="divide-y divide-border">{leads.map((l) => (<>
                <tr key={l.lead_id} className="hover:bg-muted/40">
                  <td className={td}><Link className="text-primary hover:underline" href={`/leads/${l.lead_id}`}>{l.name ?? l.email}</Link><div className="text-xs text-muted-foreground">{l.company}</div></td>
                  <td className={td}><Badge tone={l.research_status === "done" ? "success" : l.research_status === "none" ? "neutral" : "warning"}>{l.research_status === "none" ? "not yet" : l.research_status}</Badge></td>
                  <td className={td}>{l.icp_class ? <Badge tone={classTone(l.icp_class)}>{l.icp_class}</Badge> : "—"}</td>
                  <td className={td}>{l.icp_score ?? (l.icp_class ? "n/a" : "—")}{l.icp_breakdown.length > 0 && <button className="ml-2 text-xs text-primary underline" aria-expanded={open === l.lead_id} onClick={() => setOpen(open === l.lead_id ? null : l.lead_id)}>why</button>}</td>
                  <td className={td}>{l.icp_confidence != null ? `${l.icp_confidence}%` : "—"}</td>
                  <td className={td}>{l.state}{l.stop_reason ? <div className="text-xs text-muted-foreground">{l.stop_reason}</div> : null}</td></tr>
                {open === l.lead_id && <tr key={l.lead_id + "b"}><td colSpan={6} className="bg-muted/40 px-3 py-2"><ul className="grid gap-1 text-xs md:grid-cols-2">{l.icp_breakdown.map((b) => (
                  <li key={b.key} className="flex justify-between gap-2"><span>{b.label}: <i className="text-muted-foreground">{b.detail}</i></span>
                    <Badge tone={b.result === "match" ? "success" : b.result === "no_match" ? "danger" : "warning"}>{b.result === "unknown" ? "unknown (not scored)" : pretty(b.result)}</Badge></li>))}</ul></td></tr>}</>))}</tbody></table></div>)}
        </Card>
        <Card title={`3. Drafts (${drafts})`} actions={<Link href={`/review?campaign=${id}`} className="text-sm text-primary underline">Review drafts →</Link>}>
          <div className="flex flex-wrap items-center gap-3"><Button disabled={!scored} onClick={() => act(`/campaigns/${id}/generate-messages`, { include_insufficient: incl }, "Generating drafts…")}>Generate drafts</Button>
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={incl} onChange={(e) => setIncl(e.target.checked)} />Also draft conservative messages for leads with insufficient research</label></div>
          <p className="mt-2 text-sm text-muted-foreground">{Object.entries(c.message_counts).map(([k, v]) => `${v} ${pretty(k)}`).join(" · ") || "No drafts yet. Only strong/possible fits get drafts by default."}</p>
        </Card>
        <Card title="4. Launch">
          {ready && <ul className="mb-3 space-y-1 text-sm">{ready.checks.map((k) => (<li key={k.key} className="flex items-center gap-2"><Icon name={k.ok ? "check" : "alert"} className={`h-4 w-4 ${k.ok ? "text-success" : "text-warning"}`} />{k.label}<span className="sr-only">{k.ok ? "done" : "missing"}</span></li>))}</ul>}
          <Button variant="primary" disabled={!ready?.ready || c.status === "active"} onClick={() => act(`/campaigns/${id}/launch`, undefined, "Launched. The worker re-checks every safety rule before each send.")}><Icon name="send" />Launch campaign</Button>
          <p className="mt-2 text-xs text-muted-foreground">LinkedIn and Instagram drafts never send automatically; they appear in the <Link href="/manual" className="underline">Manual queue</Link> for you to send yourself.</p>
        </Card>
      </ol>
    </Shell>
  );
}
