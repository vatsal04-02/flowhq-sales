"use client";
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, Avatar, Badge, Button, Card, Empty, Link, PageHeader, Skeleton, inputCls, pretty } from "@/components/ui";
import { api } from "@/lib/api";

type Conv = { id: string; channel: string; subject: string | null; last_message_at: string; lead: { id: string; name: string; email: string; title: string | null; company: string | null; status: string };
  last: { direction: string; preview: string; intent: string | null; simulated: boolean } | null };
type Msg = { id: string; direction: "in" | "out"; subject: string | null; body: string; state: string; simulated: boolean; manual: boolean; peer: string | null; at: string; intent: string | null; intent_confidence: number | null; intent_source: string | null; suggested_reply: string | null; error: string | null };
type Detail = Conv & { messages: Msg[]; intents: string[]; campaign: string | null };
const positive = ["interested", "meeting_request", "requesting_info"];

export default function Inbox() {
  const [list, setList] = useState<Conv[] | null>(null); const [intent, setIntent] = useState(""); const [d, setD] = useState<Detail | null>(null);
  const [reply, setReply] = useState(""); const [sim, setSim] = useState(""); const [unmatched, setUnmatched] = useState<{ id: string; kind: string; received_at: string; from: string | null; subject: string | null }[]>([]); const [error, setError] = useState<string | null>(null); const [note, setNote] = useState<string | null>(null);
  const load = useCallback(() => api<Conv[]>(`/conversations${intent ? `?intent=${intent}` : ""}`).then(setList).catch((e) => setError(e.message)), [intent]);
  useEffect(() => { load(); api<typeof unmatched>("/inbox/unmatched").then(setUnmatched).catch(() => {}); }, [load]);
  const open = async (id: string) => { setD(await api<Detail>(`/conversations/${id}`)); setReply(""); setError(null); setNote(null); };
  async function run(fn: () => Promise<unknown>, ok: string) { setError(null); setNote(null); try { await fn(); setNote(ok); await load(); if (d) await open(d.id); } catch (e: any) { setError(e.message); } }
  const lastIn = d ? [...d.messages].reverse().find((m) => m.direction === "in") : null;
  return (
    <Shell>
      <PageHeader title="Unified inbox">
        <select aria-label="Filter by intent" className={`${inputCls} !w-auto`} value={intent} onChange={(e) => setIntent(e.target.value)}><option value="">All conversations</option>
          {["interested", "meeting_request", "requesting_info", "objection", "not_interested", "wrong_person", "out_of_office", "unsubscribe", "unclear"].map((i) => <option key={i} value={i}>{pretty(i)}</option>)}</select>
      </PageHeader>
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}{note && <div className="mb-3"><Alert tone="success">{note}</Alert></div>}
      {unmatched.length > 0 && (
        <details className="mb-4 rounded-xl border border-border bg-card p-3 shadow-card"><summary className="cursor-pointer text-sm font-medium">{unmatched.length} message{unmatched.length === 1 ? "" : "s"} in your mailbox could not be matched to a lead</summary>
          <p className="mt-2 text-xs text-muted-foreground">Kept for you to check in your own mailbox. Nothing was changed on any lead.</p>
          <ul className="mt-2 divide-y divide-border text-sm">{unmatched.map((u) => (<li key={u.id} className="flex flex-wrap justify-between gap-2 py-1.5"><span>{u.from ?? "unknown sender"}{u.subject ? ` · ${u.subject}` : ""}</span><span className="text-xs text-muted-foreground">{u.kind === "bounce_unmatched" ? "bounce notice · " : ""}{new Date(u.received_at).toLocaleString()}</span></li>))}</ul></details>)}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[340px_1fr]">
        <div className="rounded-xl border border-border bg-card shadow-card">
          {!list ? <Skeleton /> : list.length === 0 ? <Empty icon="inbox" title="No conversations yet">Conversations appear after the first message is sent.</Empty> : (
            <ul className="max-h-[72vh] divide-y divide-border overflow-y-auto">{list.map((c) => (<li key={c.id}><button onClick={() => open(c.id)} aria-current={d?.id === c.id} className={`w-full cursor-pointer px-3 py-2 text-left hover:bg-muted/50 ${d?.id === c.id ? "bg-primary/10" : ""}`}>
              <div className="flex gap-2.5"><Avatar name={c.lead.name} size={36} /><div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-2"><span className="truncate text-sm font-medium">{c.lead.name}</span>
                {c.last?.intent && <Badge tone={positive.includes(c.last.intent) ? "success" : c.last.intent === "unsubscribe" ? "danger" : "neutral"}>{pretty(c.last.intent)}</Badge>}</div>
              <div className="truncate text-xs text-muted-foreground">{c.lead.company} · {c.channel}</div>
              <div className="truncate text-xs">{c.last?.direction === "in" ? "↩ " : "→ "}{c.last?.preview}</div></div></div></button></li>))}</ul>)}
        </div>
        <div className="min-w-0">{!d ? <div className="rounded-xl border border-border bg-card shadow-card"><Empty icon="inbox" title="Select a conversation">Replies are classified automatically. You can always correct the classification.</Empty></div> : (
          <div className="space-y-4">
            <Card title={`${d.lead.name} · ${d.lead.company ?? ""}`} actions={<div className="flex items-center gap-2"><Badge>{d.lead.status.replace(/_/g, " ")}</Badge><Link className="text-xs text-primary underline" href={`/leads/${d.lead.id}`}>Lead</Link></div>}>
              <ol className="space-y-3">{d.messages.map((m) => (<li key={m.id} className={`rounded-xl border p-3.5 text-sm ${m.direction === "in" ? "border-primary/30 bg-primary/5" : "border-border bg-muted/30"}`}>
                <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"><b className="text-foreground">{m.direction === "in" ? "Reply" : "Sent"}</b>
                  <time dateTime={m.at}>{new Date(m.at).toLocaleString()}</time>{m.direction === "in" && m.peer && m.peer.toLowerCase() !== d.lead.email?.toLowerCase() && <Badge tone="info">from {m.peer}</Badge>}{m.simulated && <Badge tone="warning">simulated</Badge>}{m.manual && <Badge tone="info">sent manually</Badge>}{m.state === "failed" && <Badge tone="danger">failed</Badge>}</div>
                <p className="whitespace-pre-wrap [overflow-wrap:anywhere]">{m.body}</p>
                {m.direction === "in" && (<div className="mt-2 flex flex-wrap items-center gap-2 border-t border-border pt-2 text-xs">
                  <span>Classified as</span><select aria-label="Intent" className={`${inputCls} !w-auto text-xs`} value={m.intent ?? "unclear"} onChange={(e) => run(() => api(`/conversations/${d.id}/classify`, { method: "POST", json: { message_id: m.id, intent: e.target.value } }), "Classification updated and rules re-applied.")}>
                    {d.intents.map((i) => <option key={i} value={i}>{pretty(i)}</option>)}</select>
                  <span className="text-muted-foreground">{m.intent_confidence}% · {m.intent_source}</span></div>)}</li>))}</ol>
            </Card>
            {d.channel === "email" && d.lead.status !== "unsubscribed" && d.lead.status !== "suppressed" && d.lead.status !== "bounced" ? (
              <Card title="Reply">
                {lastIn?.suggested_reply && <div className="mb-2 rounded bg-muted p-2 text-xs"><b>Suggested (edit before sending):</b> {lastIn.suggested_reply} <button className="ml-1 text-primary underline" onClick={() => setReply(lastIn.suggested_reply!)}>Use</button></div>}
                <textarea aria-label="Reply" className={`${inputCls} py-2`} rows={5} value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Write your reply. You review every word; nothing is auto-sent." />
                <div className="mt-2"><Button variant="primary" disabled={!reply.trim()} onClick={() => run(() => api(`/conversations/${d.id}/reply`, { method: "POST", json: { body: reply } }), "Reply sent.")}>Send reply</Button></div></Card>
            ) : <Alert tone="info">Replying is disabled: this lead opted out, bounced, or the channel is manual.</Alert>}
            {d.messages.some((m) => m.simulated) && (<Card title="Sandbox tools (simulated provider only)">
              <div className="flex flex-col gap-2 sm:flex-row"><input aria-label="Simulated reply text" className={inputCls} value={sim} onChange={(e) => setSim(e.target.value)} placeholder="Type a prospect reply, e.g. “Sounds interesting, can we talk Friday?”" />
                <Button disabled={!sim.trim()} onClick={() => run(() => api("/sandbox/simulate-reply", { method: "POST", json: { lead_id: d.lead.id, body: sim } }), "Simulated reply received and classified.")}>Simulate reply</Button>
                <Button variant="danger" onClick={() => run(() => api(`/sandbox/simulate-bounce?lead_id=${d.lead.id}`, { method: "POST" }), "Simulated bounce processed.")}>Simulate bounce</Button></div></Card>)}
          </div>)}</div>
      </div>
    </Shell>
  );
}
