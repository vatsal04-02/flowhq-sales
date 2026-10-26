"use client";
import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, Badge, Empty, Link, PageHeader, Skeleton, th, td } from "@/components/ui";
import { Campaign, api } from "@/lib/api";

export default function Campaigns() {
  const [items, setItems] = useState<Campaign[] | null>(null); const [error, setError] = useState<string | null>(null);
  useEffect(() => { api<Campaign[]>("/campaigns").then(setItems).catch((e) => setError(e.message)); }, []);
  return (
    <Shell>
      <PageHeader title="Campaigns"><Link href="/campaigns/new" className="inline-flex min-h-[44px] items-center rounded bg-primary px-3 text-sm font-medium text-primary-foreground md:min-h-9">New campaign</Link></PageHeader>
      {error && <Alert>{error}</Alert>}
      {!items ? <Skeleton /> : items.length === 0 ? <div className="rounded border border-border bg-card"><Empty icon="megaphone" title="No campaigns yet">A campaign holds your offer, target profile, channels and follow-up sequence.</Empty></div> : (
        <div className="overflow-x-auto rounded border border-border bg-card"><table className="w-full min-w-[640px] text-sm"><thead className="border-b border-border bg-muted/60"><tr>
          <th className={th}>Name</th><th className={th}>Status</th><th className={th}>Leads</th><th className={th}>Drafts</th><th className={th}>Channels</th></tr></thead>
          <tbody className="divide-y divide-border">{items.map((c) => (<tr key={c.id} className="hover:bg-muted/40">
            <td className={td}><Link className="font-medium text-primary hover:underline" href={`/campaigns/${c.id}`}>{c.name}</Link></td>
            <td className={td}><Badge tone={c.status === "active" ? "success" : c.status === "paused" ? "warning" : "neutral"}>{c.status}</Badge></td>
            <td className={td}>{Object.values(c.lead_counts).reduce((a, b) => a + b, 0)}</td>
            <td className={td}>{Object.entries(c.message_counts).map(([k, v]) => `${v} ${k}`).join(", ") || "—"}</td>
            <td className={td}>{c.channels.join(", ")}</td></tr>))}</tbody></table></div>)}
    </Shell>
  );
}
