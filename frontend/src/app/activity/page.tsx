"use client";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, Empty, PageHeader, Skeleton, th, td } from "@/components/ui";
import { api } from "@/lib/api";

type Row = { id: number; action: string; target: string | null; data: Record<string, unknown>; at: string };
export default function Activity() {
  const [rows, setRows] = useState<Row[] | null>(null); const [q, setQ] = useState(""); const [error, setError] = useState<string | null>(null);
  useEffect(() => { api<Row[]>("/audit?limit=300").then(setRows).catch((e) => setError(e.message)); }, []);
  const shown = rows?.filter((r) => !q || JSON.stringify(r).toLowerCase().includes(q.toLowerCase()));
  return (
    <Shell>
      <PageHeader title="Activity & audit log"><input aria-label="Search log" placeholder="Search" className="min-h-[44px] rounded border border-border bg-card px-3 text-sm md:min-h-9" value={q} onChange={(e) => setQ(e.target.value)} /></PageHeader>
      <p className="mb-3 text-sm text-muted-foreground">Append-only record of approvals, sends, suppression changes and admin actions.</p>
      {error && <Alert>{error}</Alert>}
      {!shown ? <Skeleton /> : shown.length === 0 ? <div className="rounded border border-border bg-card"><Empty icon="history" title="Nothing matches" /></div> : (
        <div className="overflow-x-auto rounded border border-border bg-card"><table className="w-full min-w-[640px] text-sm"><thead className="border-b border-border bg-muted/60"><tr><th className={th}>When</th><th className={th}>Action</th><th className={th}>Target</th><th className={th}>Details</th></tr></thead>
          <tbody className="divide-y divide-border">{shown.map((r) => (<tr key={r.id}><td className={`${td} whitespace-nowrap text-xs`}>{new Date(r.at).toLocaleString()}</td><td className={`${td} font-medium`}>{r.action}</td>
            <td className={`${td} mono break-all text-xs`}>{r.target}</td><td className={`${td} mono break-all text-xs text-muted-foreground`}>{JSON.stringify(r.data)}</td></tr>))}</tbody></table></div>)}
    </Shell>
  );
}
