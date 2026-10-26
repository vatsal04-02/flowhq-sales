"use client";
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, Badge, Button, Empty, Input, Link, PageHeader, Skeleton, inputCls, pretty, statusTone, td, th } from "@/components/ui";
import { api, Campaign, Lead } from "@/lib/api";

const STATUSES = ["imported", "needs_research", "qualified", "unqualified", "ready_for_review", "approved",
  "active_outreach", "replied", "interested", "meeting_booked", "converted", "not_interested", "bounced",
  "unsubscribed", "suppressed"];

export default function Leads() {
  const [items, setItems] = useState<Lead[]>([]); const [cursor, setCursor] = useState<string | null>(null);
  const [q, setQ] = useState(""); const [status, setStatus] = useState(""); const [region, setRegion] = useState("");
  const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set()); const [camps, setCamps] = useState<Campaign[]>([]); const [camp, setCamp] = useState(""); const [note, setNote] = useState<string | null>(null);
  useEffect(() => { api<Campaign[]>("/campaigns").then(setCamps).catch(() => {}); }, []);
  const toggle = (id: string) => setPicked((p) => { const n = new Set(p); n.has(id) ? n.delete(id) : n.add(id); return n; });
  async function bulk(kind: "research" | "campaign") {
    setError(null); setNote(null);
    try {
      if (kind === "research") { const r = await api<{ queued: number }>("/leads/research", { method: "POST", json: { lead_ids: [...picked] } }); setNote(`Research queued for ${r.queued} lead(s).`); }
      else { const r = await api<{ added: number; skipped: number }>(`/campaigns/${camp}/leads`, { method: "POST", json: { lead_ids: [...picked] } }); setNote(`Added ${r.added} to the campaign (${r.skipped} skipped: already in it or suppressed).`); }
      setPicked(new Set());
    } catch (e) { setError((e as Error).message); }
  }

  const load = useCallback(async (next?: string | null) => {
    setLoading(true); setError(null);
    const p = new URLSearchParams({ limit: "50" });
    if (q) p.set("q", q); if (status) p.set("status", status); if (region) p.set("region", region);
    if (next) p.set("cursor", next);
    try {
      const page = await api<{ items: Lead[]; next_cursor: string | null }>(`/leads?${p}`);
      setItems((prev) => (next ? [...prev, ...page.items] : page.items)); setCursor(page.next_cursor);
    } catch (e) { setError((e as Error).message); } finally { setLoading(false); }
  }, [q, status, region]);
  useEffect(() => { const t = setTimeout(() => load(), 250); return () => clearTimeout(t); }, [load]);

  const filtered = q || status || region;
  return (
    <Shell>
      <PageHeader title="Leads">
        <Link href="/import" className="inline-flex min-h-[44px] items-center rounded bg-primary px-3 text-sm font-medium text-primary-foreground md:min-h-9">Import CSV</Link>
      </PageHeader>
      <div className="mb-3 grid gap-2 sm:grid-cols-[1fr_200px_110px]" role="search">
        <Input aria-label="Search leads" placeholder="Search name, email, company, domain" value={q} onChange={(e) => setQ(e.target.value)} />
        <select aria-label="Filter by status" className={inputCls} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">All statuses</option>{STATUSES.map((s) => <option key={s} value={s}>{pretty(s)}</option>)}</select>
        <Input aria-label="Filter by region (ISO code)" placeholder="Region, e.g. IN" maxLength={2} value={region} onChange={(e) => setRegion(e.target.value)} />
      </div>
      {error && <div className="mb-3"><Alert>{error} <button className="underline" onClick={() => load()}>Reload</button></Alert></div>}
      {note && <div className="mb-3"><Alert tone="success">{note}</Alert></div>}
      {picked.size > 0 && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded border border-primary/30 bg-primary/10 p-2 text-sm" role="region" aria-label="Bulk actions">
          <b>{picked.size} selected</b><Button onClick={() => bulk("research")}>Research</Button>
          <select aria-label="Campaign" className={`${inputCls} !w-auto`} value={camp} onChange={(e) => setCamp(e.target.value)}><option value="">Add to campaign…</option>{camps.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select>
          <Button disabled={!camp} onClick={() => bulk("campaign")}>Add</Button><Button variant="ghost" onClick={() => setPicked(new Set())}>Clear</Button></div>)}
      <div className="overflow-x-auto rounded border border-border bg-card">
        <table className="w-full min-w-[900px] text-sm">
          <caption className="sr-only">Leads</caption>
          <thead className="border-b border-border bg-muted/60"><tr>
            <th scope="col" className="w-8 px-3 py-2"><span className="sr-only">Select</span></th><th scope="col" className={th}>Name</th><th scope="col" className={th}>Email</th><th scope="col" className={th}>Phone</th>
            <th scope="col" className={th}>Region</th><th scope="col" className={th}>Research</th><th scope="col" className={th}>Fit</th><th scope="col" className={th}>Status</th><th scope="col" className={th}>Flags</th></tr></thead>
          <tbody className="divide-y divide-border">
            {items.map((l) => (
              <tr key={l.id} className="hover:bg-muted/40">
                <td className="px-3 py-2"><input type="checkbox" aria-label={`Select ${l.email_norm ?? l.id}`} checked={picked.has(l.id)} onChange={() => toggle(l.id)} /></td>
                <td className={td}><Link className="font-medium text-primary underline-offset-2 hover:underline" href={`/leads/${l.id}`}>
                  {[l.first_name, l.last_name].filter(Boolean).join(" ") || "(no name)"}</Link>
                  {l.title && <div className="text-xs text-muted-foreground">{l.title}</div>}</td>
                <td className={`${td} mono text-xs`}>{l.email_norm ?? "—"}</td>
                <td className={`${td} mono text-xs`}>{l.phone_e164 ?? "—"}</td>
                <td className={td}>{l.region ?? "—"}</td>
                <td className={td}><Badge tone={l.research_status === "done" ? "success" : l.research_status === "none" ? "neutral" : "warning"}>{l.research_status === "none" ? "not yet" : l.research_status}</Badge></td>
                <td className={td}>{l.icp_class ? <><Badge tone={l.icp_class === "strong" ? "success" : l.icp_class === "possible" ? "info" : l.icp_class === "insufficient" ? "warning" : "neutral"}>{l.icp_class}</Badge>{l.icp_score != null && <span className="ml-1 text-xs tabular-nums">{l.icp_score}</span>}</> : "—"}</td>
                <td className={td}><Badge tone={statusTone(l.status)}>{pretty(l.status)}</Badge></td>
                <td className={td}>{l.possible_duplicate_of && <Badge tone="warning">possible duplicate</Badge>}</td>
              </tr>))}
          </tbody>
        </table>
        {loading && <Skeleton />}
        {!loading && !error && items.length === 0 && (filtered
          ? <Empty icon="users" title="No leads match these filters"><button className="underline" onClick={() => { setQ(""); setStatus(""); setRegion(""); }}>Clear filters</button></Empty>
          : <Empty icon="upload" title="No leads yet">Start by <Link className="text-primary underline" href="/import">importing a CSV</Link>.</Empty>)}
      </div>
      {cursor && !loading && <div className="mt-3 text-center"><Button onClick={() => load(cursor)}>Load more</Button></div>}
    </Shell>
  );
}
