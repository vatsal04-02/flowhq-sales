"use client";
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, Badge, Button, Card, Empty, Input, PageHeader, Tone, inputCls, td, th } from "@/components/ui";
import { api, Job, Suppression } from "@/lib/api";

const jobTone = (s: string): Tone => (s === "dead" ? "danger" : s === "done" ? "success" : s === "running" ? "info" : "warning");

export default function Jobs() {
  const [jobs, setJobs] = useState<Job[]>([]); const [sup, setSup] = useState<Suppression[]>([]);
  const [kind, setKind] = useState("email"); const [value, setValue] = useState(""); const [error, setError] = useState<string | null>(null);
  const load = useCallback(() => {
    api<Job[]>("/jobs").then(setJobs).catch((e) => setError(e.message));
    api<Suppression[]>("/suppressions").then(setSup).catch((e) => setError(e.message));
  }, []);
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t); }, [load]);
  async function add(e: React.FormEvent) {
    e.preventDefault(); setError(null);
    try { setSup(await api<Suppression[]>("/suppressions", { method: "POST", json: { kind, value, reason: "manual" } })); setValue(""); }
    catch (err) { setError((err as Error).message); }
  }
  return (
    <Shell>
      <PageHeader title="Jobs & suppression" />
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}
      <div className="space-y-4">
        <Card title="Background jobs">
          {jobs.length === 0 ? <Empty icon="activity" title="No jobs yet">Imports and other background work appear here, including failures you can retry.</Empty> : (
            <div className="-m-4 overflow-x-auto"><table className="w-full min-w-[560px] text-sm"><thead className="border-b border-border bg-muted/60"><tr>
              <th className={th}>Type</th><th className={th}>State</th><th className={th}>Attempts</th><th className={th}>Last error</th><th className={th}><span className="sr-only">Actions</span></th></tr></thead>
              <tbody className="divide-y divide-border">{jobs.map((j) => (<tr key={j.id}><td className={td}>{j.type}</td>
                <td className={td}><Badge tone={jobTone(j.state)}>{j.state}</Badge></td><td className={td}>{j.attempts}/{j.max_attempts}</td>
                <td className={`${td} mono max-w-xs break-words text-xs text-destructive`}>{j.last_error}</td>
                <td className={td}>{j.state === "dead" && <Button variant="ghost" onClick={() => api(`/jobs/${j.id}/retry`, { method: "POST" }).then(load).catch((e) => setError(e.message))}>Retry</Button>}</td></tr>))}</tbody></table></div>)}
        </Card>
        <Card title="Suppression list">
          <form onSubmit={add} className="mb-4 grid gap-2 sm:grid-cols-[120px_1fr_auto]">
            <select aria-label="Kind" className={inputCls} value={kind} onChange={(e) => setKind(e.target.value)}><option>email</option><option>domain</option><option>phone</option></select>
            <Input aria-label="Value to suppress" placeholder="person@example.com, example.com or +919876543210" value={value} onChange={(e) => setValue(e.target.value)} required />
            <Button variant="danger">Suppress</Button></form>
          {sup.length === 0 ? <Empty icon="ban" title="Nothing suppressed">Opt-outs and bounces will be listed here and are never contacted again.</Empty> : (
            <ul className="divide-y divide-border text-sm">{sup.map((s) => (<li key={s.id} className="flex items-center justify-between gap-3 py-2">
              <span className="flex items-center gap-2"><Badge>{s.kind}</Badge><span className="mono break-all text-xs">{s.value_norm}</span></span>
              <span className="text-muted-foreground">{s.reason.replace(/_/g, " ")}</span></li>))}</ul>)}
        </Card>
      </div>
    </Shell>
  );
}
