"use client";
import { useEffect, useRef, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, Button, Card, Field, Icon, Input, PageHeader, inputCls, th, td } from "@/components/ui";
import { api, Batch } from "@/lib/api";

type Upload = { batch: Batch; preview: Record<string, string>[]; target_fields: string[] };
const ACTIVE = ["queued", "running"];

export default function ImportPage() {
  const [up, setUp] = useState<Upload | null>(null); const [mapping, setMapping] = useState<Record<string, string>>({});
  const [batch, setBatch] = useState<Batch | null>(null); const [error, setError] = useState<string | null>(null);
  const [region, setRegion] = useState(""); const [busy, setBusy] = useState(false); const file = useRef<HTMLInputElement>(null);

  async function upload(e: React.FormEvent) {
    e.preventDefault(); setError(null);
    const f = file.current?.files?.[0]; if (!f) return;
    const fd = new FormData(); fd.append("file", f); if (region) fd.append("default_region", region);
    setBusy(true);
    try { const r = await api<Upload>("/imports", { method: "POST", body: fd }); setUp(r); setMapping(r.batch.mapping); setBatch(r.batch); }
    catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  async function start() {
    if (!up) return; setError(null); setBusy(true);
    try {
      await api(`/imports/${up.batch.id}/mapping`, { method: "PUT", json: { mapping, default_region: region || null } });
      setBatch(await api<Batch>(`/imports/${up.batch.id}/start`, { method: "POST" }));
    } catch (err) { setError((err as Error).message); } finally { setBusy(false); }
  }
  const polling = !!batch && ACTIVE.includes(batch.status);
  useEffect(() => {
    if (!polling || !batch) return;
    const t = setInterval(() => api<Batch>(`/imports/${batch.id}`).then(setBatch).catch(() => {}), 1500);
    return () => clearInterval(t);
  }, [polling, batch?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const configuring = !!up && !!batch && ["uploaded", "mapped"].includes(batch.status);
  const started = !!batch && !["uploaded", "mapped"].includes(batch.status);
  return (
    <Shell>
      <PageHeader title="Import leads" subtitle="Upload a CSV, map columns, review, import" />
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}
      {!up && (
        <Card title="1. Upload a CSV">
          <form onSubmit={upload} className="max-w-xl space-y-3">
            <p className="text-sm text-muted-foreground">UTF-8 CSV, up to 10 MB or 50,000 rows. Original values are preserved and unmapped columns are kept as custom fields.</p>
            <Field label="CSV file"><input ref={file} type="file" accept=".csv,text/csv" required className="block w-full text-sm" /></Field>
            <Field label="Default country for phone numbers (optional)" hint="Two-letter code, e.g. IN or US"><Input maxLength={2} className="max-w-[120px]" value={region} onChange={(e) => setRegion(e.target.value)} /></Field>
            <Button variant="primary" disabled={busy}><Icon name="upload" />{busy ? "Uploading…" : "Upload and preview"}</Button>
          </form>
        </Card>)}
      {configuring && up && (
        <div className="space-y-4">
          <Card title={`2. Map columns — ${up.batch.total_rows.toLocaleString()} rows`}>
            <div className="grid gap-3 md:grid-cols-2">{up.target_fields.map((t) => (
              <Field key={t} label={t.replace(/_/g, " ")}>
                <select className={inputCls} value={mapping[t] ?? ""} onChange={(e) => setMapping((m) => { const n = { ...m }; if (e.target.value) n[t] = e.target.value; else delete n[t]; return n; })}>
                  <option value="">Not mapped</option>{up.batch.headers.map((h) => <option key={h}>{h}</option>)}</select></Field>))}</div>
          </Card>
          <Card title="Preview (first 20 rows)"><div className="overflow-x-auto"><table className="w-full text-xs"><thead><tr>{up.batch.headers.map((h) => <th key={h} className={th}>{h}</th>)}</tr></thead>
            <tbody className="divide-y divide-border">{up.preview.map((r, i) => <tr key={i}>{up.batch.headers.map((h) => <td key={h} className={td}>{r[h]}</td>)}</tr>)}</tbody></table></div></Card>
          <Button variant="primary" onClick={start} disabled={busy}>Start import</Button>
        </div>)}
      {started && batch && (
        <Card title={polling ? "Importing…" : `Import ${batch.status}`}>
          <div aria-live="polite">
            <progress className="mb-3 h-2 w-full" max={batch.total_rows} value={Math.min(batch.next_row - 1, batch.total_rows)} aria-label="Import progress" />
            <dl className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
              {([["Created", batch.created_count], ["Duplicates skipped", batch.duplicate_count], ["Invalid rows", batch.invalid_count], ["Suppressed", batch.suppressed_count]] as const).map(([k, v]) => (
                <div key={k}><dt className="text-muted-foreground">{k}</dt><dd className="text-2xl font-semibold">{v.toLocaleString()}</dd></div>))}</dl>
            <p className="mt-2 text-xs text-muted-foreground">Rows processed: {Math.min(batch.next_row - 1, batch.total_rows).toLocaleString()} of {batch.total_rows.toLocaleString()}</p>
            {batch.status === "failed" && batch.error && <div className="mt-3"><Alert>{batch.error}</Alert></div>}
          </div>
          {batch.status === "completed" && (
            <div className="mt-4 flex flex-wrap gap-2">
              <a href="/leads" className="inline-flex min-h-[44px] items-center rounded bg-primary px-3 text-sm font-medium text-primary-foreground md:min-h-9">View leads</a>
              {(batch.invalid_count + batch.duplicate_count) > 0 && <a href={`/api/v1/imports/${batch.id}/errors.csv`} className="inline-flex min-h-[44px] items-center gap-2 rounded border border-border px-3 text-sm md:min-h-9"><Icon name="download" />Download error report</a>}
              {batch.invalid_count > 0 && <Button onClick={async () => setBatch(await api<Batch>(`/imports/${batch.id}/retry-failed`, { method: "POST" }))}>Retry failed rows</Button>}
            </div>)}
        </Card>)}
    </Shell>
  );
}
