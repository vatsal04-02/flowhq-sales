"use client";
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, Avatar, Badge, Button, Card, Empty, Field, Input, Link, PageHeader, Skeleton, inputCls, pretty } from "@/components/ui";
import { DictatedField } from "@/components/VoiceDictation";
import { api } from "@/lib/api";

type Opp = { id: string; stage: string; value: number | null; notes: string | null; next_action_at: string | null; lead: { id: string; name: string; email: string; company: string | null; outreach_status: string } };

export default function Pipeline() {
  const [data, setData] = useState<{ stages: string[]; items: Opp[] } | null>(null); const [sel, setSel] = useState<Opp | null>(null);
  const [error, setError] = useState<string | null>(null); const [drag, setDrag] = useState<string | null>(null);
  const [value, setValue] = useState(""); const [notes, setNotes] = useState(""); const [next, setNext] = useState("");
  const load = useCallback(() => api<typeof data>("/opportunities").then(setData as any).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  async function move(o: Opp, stage: string) {
    if (o.stage === stage) return; setError(null);
    try { await api(`/opportunities/${o.id}`, { method: "PATCH", json: { stage } }); await load(); } catch (e) { setError((e as Error).message); }
  }
  const pick = (o: Opp) => { setSel(o); setValue(o.value?.toString() ?? ""); setNotes(o.notes ?? ""); setNext(o.next_action_at ? o.next_action_at.slice(0, 16) : ""); };
  async function save() {
    if (!sel) return;
    try { await api(`/opportunities/${sel.id}`, { method: "PATCH", json: { value: value ? +value : null, notes, next_action_at: next ? new Date(next).toISOString() : null } }); setSel(null); await load(); } catch (e) { setError((e as Error).message); }
  }
  const total = (st: string) => data?.items.filter((i) => i.stage === st).reduce((a, b) => a + (b.value ?? 0), 0) ?? 0;
  return (
    <Shell>
      <PageHeader title="Pipeline" subtitle="Opportunity stage is separate from outreach status" />
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}
      <p className="mb-3 text-sm text-muted-foreground">Opportunity stage is separate from outreach status: a lead can stop receiving outreach and still be an active deal. Positive replies create an opportunity automatically. Drag a card, or use the stage menu.</p>
      {!data ? <Skeleton /> : data.items.length === 0 ? <div className="rounded-xl border border-border bg-card shadow-card"><Empty icon="kanban" title="No opportunities yet">Positive replies from the inbox appear here automatically.</Empty></div> : (
        <div className="grid auto-cols-[240px] grid-flow-col gap-3 overflow-x-auto pb-3" role="list">
          {data.stages.map((st) => (
            <section key={st} aria-label={pretty(st)} role="listitem" className="min-h-[220px] rounded-xl border border-border bg-muted/50"
              onDragOver={(e) => e.preventDefault()} onDrop={() => { const o = data.items.find((i) => i.id === drag); if (o) move(o, st); setDrag(null); }}>
              <header className="flex items-center justify-between border-b border-border px-3 py-2 text-sm font-semibold capitalize"><span>{pretty(st)} <span className="text-muted-foreground">({data.items.filter((i) => i.stage === st).length})</span></span>
                {total(st) > 0 && <span className="text-xs font-normal text-muted-foreground">{total(st).toLocaleString()}</span>}</header>
              <ul className="space-y-2 p-2">{data.items.filter((i) => i.stage === st).map((o) => (
                <li key={o.id} draggable onDragStart={() => setDrag(o.id)} className="cursor-grab rounded-lg border border-border bg-card p-2.5 text-sm shadow-card transition-shadow hover:shadow-lift active:cursor-grabbing">
                  <div className="flex items-center gap-2"><Avatar name={o.lead.name} size={28} /><div className="min-w-0"><button className="block max-w-full cursor-pointer truncate text-left font-medium text-primary hover:underline" onClick={() => pick(o)}>{o.lead.name}</button>
                  <div className="truncate text-xs text-muted-foreground">{o.lead.company}</div></div></div>
                  <div className="mt-1 flex flex-wrap items-center gap-1"><Badge>{pretty(o.lead.outreach_status)}</Badge>{o.value ? <Badge tone="success">{o.value.toLocaleString()}</Badge> : null}</div>
                  <select aria-label={`Move ${o.lead.name} to stage`} className={`${inputCls} mt-2 text-xs`} value={o.stage} onChange={(e) => move(o, e.target.value)}>{data.stages.map((s) => <option key={s} value={s}>{pretty(s)}</option>)}</select></li>))}</ul>
            </section>))}
        </div>)}
      {sel && (<div className="mt-4 max-w-xl"><Card title={`Deal: ${sel.lead.name}`} actions={<Link href={`/leads/${sel.lead.id}`} className="text-xs text-primary underline">Open lead</Link>}>
        <div className="grid gap-3"><Field label="Expected value"><Input type="number" min={0} value={value} onChange={(e) => setValue(e.target.value)} /></Field>
          <Field label="Next action"><Input type="datetime-local" value={next} onChange={(e) => setNext(e.target.value)} /></Field>
          <DictatedField label="Notes" speak="notes" value={notes} onChange={setNotes}><textarea className={`${inputCls} py-2`} rows={3} value={notes} onChange={(e) => setNotes(e.target.value)} /></DictatedField>
          <div className="flex gap-2"><Button variant="primary" onClick={save}>Save</Button><Button onClick={() => setSel(null)}>Cancel</Button></div></div></Card></div>)}
    </Shell>
  );
}
