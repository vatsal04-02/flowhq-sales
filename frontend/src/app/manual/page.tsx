"use client";
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, Badge, Button, Card, Empty, Icon, PageHeader, Skeleton } from "@/components/ui";
import { Draft, api } from "@/lib/api";

type Q = { items: Draft[]; sent_last_24h: number; suggested_daily_cap: number; note: string };

export default function Manual() {
  const [q, setQ] = useState<Q | null>(null); const [error, setError] = useState<string | null>(null); const [copied, setCopied] = useState<string | null>(null);
  const load = useCallback(() => api<Q>("/manual-queue").then(setQ).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  async function copy(d: Draft) { try { await navigator.clipboard.writeText(d.body); setCopied(d.id); setTimeout(() => setCopied(null), 2000); } catch { setError("Copy failed: select the text and copy it manually."); } }
  return (
    <Shell>
      <PageHeader title="Manual queue" subtitle="LinkedIn & Instagram: you send, we keep track" />
      <div className="mb-4"><Alert tone="info">{q?.note ?? "You send these yourself in your own browser."} Open the profile, paste the message, send it, then mark it as sent so replies and follow-ups stay tracked.</Alert></div>
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}
      {q && <p className="mb-3 text-sm text-muted-foreground">Sent in the last 24 hours: <b className="text-foreground">{q.sent_last_24h}</b> · suggested cap {q.suggested_daily_cap}/day. Going slower protects your account.{q.sent_last_24h >= q.suggested_daily_cap && <b className="text-warning"> You have reached the suggested cap for today.</b>}</p>}
      {!q ? <Skeleton /> : q.items.length === 0 ? <div className="rounded-xl border border-border bg-card shadow-card"><Empty icon="hand" title="Nothing to send">Approve LinkedIn or Instagram drafts in Draft review and they appear here.</Empty></div> : (
        <ul className="grid gap-3 md:grid-cols-2">{q.items.map((d) => { const url = d.channel === "linkedin" ? d.lead?.linkedin_url : d.lead?.instagram_url; return (<li key={d.id}>
          <Card title={`${d.lead?.name ?? "Lead"} · ${d.lead?.company ?? ""}`} actions={<Badge tone="info">{d.channel}</Badge>}>
            <p className="whitespace-pre-wrap rounded bg-muted p-2 text-sm">{d.body}</p>
            <p className="mt-1 text-xs text-muted-foreground">{d.body.length}/300 characters</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {url ? <a href={url} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-[44px] items-center gap-2 rounded border border-border px-3 text-sm hover:bg-muted md:min-h-9"><Icon name="external" />Open profile</a> : <span className="text-xs text-muted-foreground">No {d.channel} URL on this lead</span>}
              <Button onClick={() => copy(d)}><Icon name="copy" />{copied === d.id ? "Copied" : "Copy message"}</Button>
              <Button variant="primary" onClick={async () => { try { await api(`/messages/${d.id}/mark-sent`, { method: "POST" }); load(); } catch (e) { setError((e as Error).message); } }}><Icon name="check" />I sent it</Button></div></Card></li>); })}</ul>)}
    </Shell>
  );
}
