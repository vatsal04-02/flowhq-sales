"use client";
import { useCallback, useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { Alert, Badge, Button, Card, Field, Icon, Input, PageHeader, Skeleton, inputCls } from "@/components/ui";
import { Account, api } from "@/lib/api";

type Data = { accounts: Account[]; llm: Record<string, any>; llm_usage: { calls: number; avg_latency_ms: number; failures: number }; manual_channels: { channel: string; mode: string; note: string }[]; kill_switch: boolean };

export default function Integrations() {
  const [d, setD] = useState<Data | null>(null); const [error, setError] = useState<string | null>(null); const [note, setNote] = useState<string | null>(null);
  const [f, setF] = useState({ name: "", from_email: "", host: "", port: "587", username: "", password: "", security: "starttls", daily_limit: "30" }); const [show, setShow] = useState(false);
  const load = useCallback(() => api<Data>("/integrations").then(setD).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  async function run(fn: () => Promise<unknown>, ok?: string) { setError(null); setNote(null); try { await fn(); if (ok) setNote(ok); await load(); } catch (e: any) { setError(e.message); } }
  const llmTone = (s: string) => (s === "ok" ? "success" : s === "templates_only" ? "info" : "warning") as any;
  return (
    <Shell>
      <PageHeader title="Integrations & safety" subtitle="Sending accounts, local AI model and the global kill switch" />
      {error && <div className="mb-3"><Alert>{error}</Alert></div>}{note && <div className="mb-3"><Alert tone="success">{note}</Alert></div>}
      {!d ? <Skeleton /> : (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Global kill switch">
            <p className="mb-3 text-sm">{d.kill_switch ? <b className="text-destructive">ALL sending is stopped.</b> : "Sending is enabled."} The switch overrides every campaign and takes effect before the next send.</p>
            <Button variant={d.kill_switch ? "primary" : "danger"} onClick={() => run(() => api("/workspace/kill-switch", { method: "POST", json: { on: !d.kill_switch } }), d.kill_switch ? "Sending re-enabled." : "All sending stopped.")}>{d.kill_switch ? "Re-enable sending" : "Stop all sending now"}</Button>
          </Card>
          <Card title="Local AI model">
            <div className="flex flex-wrap items-center gap-2 text-sm"><Badge tone={llmTone(d.llm.status)}>{String(d.llm.status).replace(/_/g, " ")}</Badge><span>{d.llm.provider}{d.llm.model ? ` · ${d.llm.model}` : ""}</span></div>
            {d.llm.hint && <p className="mt-2 text-sm text-muted-foreground">{d.llm.hint}</p>}
            {d.llm.status === "templates_only" && <p className="mt-2 text-sm text-muted-foreground">No model configured. Drafts use evidence-based templates (instant). Set LLM_PROVIDER=ollama to let a local model write the opening line.</p>}
            <p className="mt-2 text-xs text-muted-foreground">{d.llm_usage.calls} calls · avg {d.llm_usage.avg_latency_ms} ms · {d.llm_usage.failures} failures. If the model is down the system keeps working with templates.</p>
          </Card>
          <Card title="Email sending accounts" actions={<div className="flex gap-2"><Button onClick={() => run(() => api("/integrations/mock", { method: "POST" }), "Sandbox account added.")}>Add sandbox</Button><Button onClick={() => setShow(!show)}>Add SMTP</Button></div>}>
            {d.accounts.length === 0 ? <p className="text-sm text-muted-foreground">No account yet. Add the sandbox to try the full flow without sending real email.</p> : (
              <ul className="divide-y divide-border text-sm">{d.accounts.map((a) => (<li key={a.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <div><div className="font-medium">{a.name} {a.simulated && <Badge tone="warning">simulated: no real email</Badge>}</div>
                  <div className="text-xs text-muted-foreground">{a.from_email} · {a.daily_limit}/day · {a.capabilities.can_send ? "can send" : "cannot send"}</div>
                  {a.health?.ok !== undefined && <div className={`text-xs ${a.health.ok ? "text-success" : "text-destructive"}`}>{a.health.ok ? "Connection OK" : `Connection failed: ${a.health.error}`}</div>}</div>
                <div className="flex gap-2"><Badge tone={a.status === "active" ? "success" : "neutral"}>{a.status}</Badge>
                  {a.status === "active" && <><Button variant="ghost" onClick={() => run(() => api(`/integrations/${a.id}/test`, { method: "POST" }))}>Test</Button><Button variant="ghost" onClick={() => { if (confirm("Disable this account and delete its stored credentials?")) run(() => api(`/integrations/${a.id}`, { method: "DELETE" })); }}>Remove</Button></>}</div></li>))}</ul>)}
            {show && (<form className="mt-4 grid gap-3 border-t border-border pt-4 md:grid-cols-2" onSubmit={(e) => { e.preventDefault(); run(async () => { await api("/integrations/smtp", { method: "POST", json: { ...f, port: +f.port, daily_limit: +f.daily_limit } }); setShow(false); setF({ ...f, password: "" }); }, "SMTP account saved. Credentials are encrypted and never shown again."); }}>
              <Field label="Name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></Field>
              <Field label="From address"><Input type="email" value={f.from_email} onChange={(e) => setF({ ...f, from_email: e.target.value })} required /></Field>
              <Field label="SMTP host"><Input value={f.host} onChange={(e) => setF({ ...f, host: e.target.value })} required /></Field>
              <Field label="Port"><Input type="number" value={f.port} onChange={(e) => setF({ ...f, port: e.target.value })} /></Field>
              <Field label="Username"><Input autoComplete="off" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value })} /></Field>
              <Field label="Password / app password"><Input type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} /></Field>
              <Field label="Security"><select className={inputCls} value={f.security} onChange={(e) => setF({ ...f, security: e.target.value })}><option value="starttls">STARTTLS</option><option value="ssl">SSL/TLS</option><option value="none">None (local testing only)</option></select></Field>
              <Field label="Daily limit" hint="Start at 20–30 per mailbox and ramp slowly."><Input type="number" value={f.daily_limit} onChange={(e) => setF({ ...f, daily_limit: e.target.value })} /></Field>
              <div className="md:col-span-2"><Button variant="primary">Save account</Button></div></form>)}
          </Card>
          <Card title="LinkedIn & Instagram">
            <ul className="space-y-2 text-sm">{d.manual_channels.map((m) => (<li key={m.channel} className="flex gap-2"><Icon name="hand" className="mt-0.5 h-4 w-4" /><div><b className="capitalize">{m.channel}</b> <Badge tone="info">{m.mode}</Badge><div className="text-muted-foreground">{m.note}</div></div></li>))}</ul>
            <p className="mt-3 text-xs text-muted-foreground">These channels have no compliant automated route for cold messages. FlowHQ prepares evidence-based drafts; you paste and send in your own browser. It never logs in to or controls these accounts.</p>
          </Card>
        </div>)}
    </Shell>
  );
}
