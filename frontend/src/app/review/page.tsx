"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, Avatar, Badge, Button, Card, Empty, Icon, Link, PageHeader, Skeleton, inputCls, pretty } from "@/components/ui";
import { Campaign, Draft, api } from "@/lib/api";

const tone = (s: string) => (s === "approved" || s === "sent" ? "success" : s === "needs_review" ? "warning" : s === "rejected" ? "danger" : "neutral") as any;

function Review() {
  const qs = useSearchParams(); const [campaign, setCampaign] = useState(qs.get("campaign") ?? ""); const [status, setStatus] = useState("");
  const [camps, setCamps] = useState<Campaign[]>([]); const [items, setItems] = useState<Draft[] | null>(null); const [sel, setSel] = useState<Draft | null>(null);
  const [subject, setSubject] = useState(""); const [body, setBody] = useState(""); const [error, setError] = useState<string | null>(null); const [note, setNote] = useState<string | null>(null);

  const load = useCallback(async () => {
    const p = new URLSearchParams(); if (campaign) p.set("campaign_id", campaign); if (status) p.set("status", status);
    try { const d = await api<Draft[]>(`/messages?${p}`); setItems(d); } catch (e) { setError((e as Error).message); }
  }, [campaign, status]);
  useEffect(() => { api<Campaign[]>("/campaigns").then(setCamps).catch(() => {}); }, []);
  useEffect(() => { load(); }, [load]);
  const open = async (id: string) => { const d = await api<Draft>(`/messages/${id}`); setSel(d); setSubject(d.subject ?? ""); setBody(d.body); setError(null); setNote(null); };

  async function run(fn: () => Promise<unknown>, ok: string) {
    setError(null); setNote(null);
    try { await fn(); setNote(ok); await load(); if (sel) await open(sel.id); } catch (e: any) { setError(e.message + (e.details?.errors ? ": " + e.details.errors.join("; ") : "")); }
  }
  const dirty = !!sel && (body !== sel.body || subject !== (sel.subject ?? ""));
  const locked = sel?.status === "sent";
  return (
    <Shell>
      <PageHeader title="Draft review" subtitle="Check the evidence, edit if needed, approve. Nothing sends without approval.">
        <select aria-label="Campaign" className={`${inputCls} !w-auto`} value={campaign} onChange={(e) => { setCampaign(e.target.value); setSel(null); }}><option value="">All campaigns</option>{camps.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
        <select aria-label="Status" className={`${inputCls} !w-auto`} value={status} onChange={(e) => setStatus(e.target.value)}><option value="">All statuses</option>{["draft", "needs_review", "approved", "rejected", "sent"].map((s) => <option key={s} value={s}>{pretty(s)}</option>)}</select>
        {campaign && <Button variant="primary" onClick={() => run(() => api(`/campaigns/${campaign}/approve`, { method: "POST", json: { all_clean: true } }), "Approved every clean draft. Drafts with errors or no evidence were left for you.")}>Approve all clean drafts</Button>}
      </PageHeader>
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}{note && <div className="mb-3"><Alert tone="success">{note}</Alert></div>}
      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        <div className="rounded-xl border border-border bg-card shadow-card">
          {!items ? <Skeleton /> : items.length === 0 ? <Empty icon="edit" title="No drafts">Generate drafts from a <Link className="text-primary underline" href="/campaigns">campaign</Link>.</Empty> : (
            <ul className="max-h-[70vh] divide-y divide-border overflow-y-auto">{items.map((d) => (<li key={d.id}>
              <button onClick={() => open(d.id)} aria-current={sel?.id === d.id} className={`w-full cursor-pointer px-3 py-2 text-left hover:bg-muted/50 ${sel?.id === d.id ? "bg-primary/10" : ""}`}>
                <div className="flex gap-2.5"><Avatar name={d.lead?.name ?? d.lead?.email ?? "?"} size={34} /><div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2"><span className="truncate text-sm font-medium">{d.lead?.name ?? d.lead?.email}</span><Badge tone={tone(d.status)}>{pretty(d.status)}</Badge></div>
                <div className="truncate text-xs text-muted-foreground">{d.lead?.company} · {d.channel} · {d.step === 0 ? "first message" : `follow-up ${d.step}`}</div>
                {d.quality.errors.length > 0 && <div className="mt-0.5 text-xs text-destructive">{d.quality.errors.length} problem(s)</div>}</div></div></button></li>))}</ul>)}
        </div>
        <div>{!sel ? <div className="rounded-xl border border-border bg-card shadow-card"><Empty icon="edit" title="Select a draft to review">Check the evidence, edit if needed, then approve. Nothing is sent without approval.</Empty></div> : (
          <div className="space-y-4">
            <Card title={`${sel.lead?.name ?? sel.lead?.email} · ${sel.lead?.company ?? ""}`} actions={<div className="flex items-center gap-2"><Badge tone={tone(sel.status)}>{pretty(sel.status)}</Badge><Badge>{sel.source === "llm" ? "local model" : "template"}</Badge></div>}>
              {sel.edited_since_approval && <div className="mb-3"><Alert tone="info">Edited after approval. It must be approved again before it can send.</Alert></div>}
              {sel.channel === "email" && <label className="mb-3 block text-sm font-medium">Subject<input className={`${inputCls} mt-1 font-normal`} value={subject} disabled={locked} onChange={(e) => setSubject(e.target.value)} /></label>}
              <label className="block text-sm font-medium">{sel.channel === "email" ? "Body" : `${sel.channel} message (manual send)`}<textarea className={`${inputCls} mt-1 py-2 font-normal`} rows={sel.channel === "email" ? 10 : 5} value={body} disabled={locked} onChange={(e) => setBody(e.target.value)} /></label>
              <div className="mt-1 text-xs text-muted-foreground">{sel.channel === "email" ? `${body.split(/\s+/).filter(Boolean).length} words` : `${body.length}/300 characters`}. {sel.channel === "email" ? "The unsubscribe link and postal address are added automatically when sending." : ""}</div>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button disabled={!dirty || locked} onClick={() => run(() => api(`/messages/${sel.id}`, { method: "PATCH", json: { subject: sel.channel === "email" ? subject : null, body } }), "Saved and re-checked. Approval was cleared.")}>Save edits</Button>
                <Button variant="primary" disabled={dirty || locked || sel.status === "approved" || sel.status === "rejected"} onClick={() => run(() => api(`/messages/${sel.id}/approve`, { method: "POST" }), "Approved.")}><Icon name="check" />Approve</Button>
                <Button variant="danger" disabled={locked || sel.status === "rejected"} onClick={() => run(() => api(`/messages/${sel.id}/reject`, { method: "POST" }), "Rejected. Any queued send was cancelled.")}><Icon name="x" />Reject</Button></div>
              {dirty && <p className="mt-2 text-xs text-muted-foreground">Save your edits before approving.</p>}
            </Card>
            <Card title="Quality checks">
              {sel.quality.errors.length === 0 && sel.quality.warnings.length === 0 && <p className="flex items-center gap-2 text-sm"><Icon name="check" className="h-4 w-4 text-success" />All checks passed. {sel.quality.verified_claims} verified claim(s).</p>}
              <ul className="space-y-1 text-sm">{sel.quality.errors.map((e) => <li key={e} className="flex gap-2 text-destructive"><Icon name="alert" className="mt-0.5 h-4 w-4" />Blocks approval: {e}</li>)}
                {sel.quality.warnings.map((e) => <li key={e} className="flex gap-2 text-warning"><Icon name="info" className="mt-0.5 h-4 w-4" />{e}</li>)}
                {sel.quality.llm_note && <li className="flex gap-2 text-muted-foreground"><Icon name="info" className="mt-0.5 h-4 w-4" />{sel.quality.llm_note}</li>}</ul>
            </Card>
            <Card title="Evidence behind the personalization">
              {sel.claims.length === 0 ? <p className="text-sm text-muted-foreground">No evidence-backed claims. This is a conservative message with no specific facts about the company. {sel.rationale}</p> : (
                <ul className="space-y-3 text-sm">{sel.claims.map((c, i) => { const ev = sel.evidence?.find((e) => e.id === c.evidence_id); return (<li key={i} className="rounded-lg border border-border bg-muted/30 p-2.5">
                  <div>Claim: <b>{c.text}</b></div>
                  <blockquote className="mt-1 border-l-2 border-primary pl-2 text-muted-foreground">“{ev?.excerpt ?? c.quote}”</blockquote>
                  {ev && <a className="mt-1 inline-flex items-center gap-1 text-xs text-primary underline" href={ev.url} target="_blank" rel="noopener noreferrer"><Icon name="external" className="h-3 w-3" />{ev.url}</a>}
                  {ev && <div className="mt-1 flex gap-2"><Badge tone="success">{ev.kind}</Badge><Badge>{ev.confidence} confidence</Badge></div>}</li>); })}</ul>)}
            </Card>
          </div>)}</div>
      </div>
    </Shell>
  );
}
export default function Page() { return <Suspense fallback={null}><Review /></Suspense>; }
