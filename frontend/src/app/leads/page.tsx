"use client";
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, Badge, Button, Empty, Input, Link, PageHeader, Skeleton, inputCls, pretty, statusTone, td, th } from "@/components/ui";
import { api, Lead } from "@/lib/api";

const STATUSES = ["imported", "needs_research", "qualified", "unqualified", "ready_for_review", "approved",
  "active_outreach", "replied", "interested", "meeting_booked", "converted", "not_interested", "bounced",
  "unsubscribed", "suppressed"];

export default function Leads() {
  const [items, setItems] = useState<Lead[]>([]); const [cursor, setCursor] = useState<string | null>(null);
  const [q, setQ] = useState(""); const [status, setStatus] = useState(""); const [region, setRegion] = useState("");
  const [loading, setLoading] = useState(true); const [error, setError] = useState<string | null>(null);

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
      {error && <div className="mb-3"><Alert>Could not load leads: {error}. <button className="underline" onClick={() => load()}>Retry</button></Alert></div>}
      <div className="overflow-x-auto rounded border border-border bg-card">
        <table className="w-full min-w-[720px] text-sm">
          <caption className="sr-only">Leads</caption>
          <thead className="border-b border-border bg-muted/60"><tr>
            <th scope="col" className={th}>Name</th><th scope="col" className={th}>Email</th><th scope="col" className={th}>Phone</th>
            <th scope="col" className={th}>Region</th><th scope="col" className={th}>Status</th><th scope="col" className={th}>Flags</th></tr></thead>
          <tbody className="divide-y divide-border">
            {items.map((l) => (
              <tr key={l.id} className="hover:bg-muted/40">
                <td className={td}><Link className="font-medium text-primary underline-offset-2 hover:underline" href={`/leads/${l.id}`}>
                  {[l.first_name, l.last_name].filter(Boolean).join(" ") || "(no name)"}</Link>
                  {l.title && <div className="text-xs text-muted-foreground">{l.title}</div>}</td>
                <td className={`${td} mono text-xs`}>{l.email_norm ?? "—"}</td>
                <td className={`${td} mono text-xs`}>{l.phone_e164 ?? "—"}</td>
                <td className={td}>{l.region ?? "—"}</td>
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
