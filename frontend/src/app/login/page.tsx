"use client";
import { useState } from "react";
import { Alert, Button, Field, Icon, Input } from "@/components/ui";
import { api } from "@/lib/api";

const POINTS = [
  { icon: "file", title: "Evidence, not guesswork", text: "Every personalized line quotes a source from the prospect's own website." },
  { icon: "check", title: "Approval first", text: "Nothing is sent until you approve the exact words." },
  { icon: "ban", title: "Safety built in", text: "Opt-outs, bounces and limits are enforced before every single send." },
] as const;

export default function Login() {
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(null); setBusy(true);
    try { await api("/auth/login", { method: "POST", json: { email, password } }); location.href = "/dashboard"; }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <main className="grid min-h-screen lg:grid-cols-[1.1fr_1fr]">
      <section className="relative hidden overflow-hidden bg-sidebar p-12 text-white lg:flex lg:flex-col lg:justify-between">
        <div aria-hidden="true" className="absolute -right-24 -top-24 h-96 w-96 rounded-full bg-primary/30 blur-3xl" />
        <div aria-hidden="true" className="absolute -bottom-32 -left-16 h-96 w-96 rounded-full bg-[hsl(262_70%_55%)]/25 blur-3xl" />
        <div className="relative flex items-center gap-2.5">
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-gradient-to-br from-primary to-[hsl(262_70%_55%)] shadow-glow"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M4 12h6l2-6 3 12 2-6h3" /></svg></span>
          <span className="font-display text-xl">FlowHQ Outreach OS</span></div>
        <div className="relative max-w-lg">
          <h1 className="text-5xl leading-[1.08]">Turn a lead list into real conversations.</h1>
          <p className="mt-4 text-lg text-sidebar-foreground">Research, personalize and follow up, with a human approving every message.</p>
          <ul className="mt-10 space-y-5">{POINTS.map((p) => (
            <li key={p.title} className="flex gap-4"><span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/10 ring-1 ring-white/10"><Icon name={p.icon} className="h-5 w-5" /></span>
              <div><div className="font-semibold">{p.title}</div><div className="text-sm text-sidebar-foreground">{p.text}</div></div></li>))}</ul>
        </div>
        <p className="relative text-xs text-sidebar-foreground/60">LinkedIn and Instagram messages are always sent by you, never automated.</p>
      </section>
      <section className="grid place-items-center px-4 py-12">
        <form onSubmit={submit} className="page-in w-full max-w-sm space-y-5 rounded-2xl border border-border bg-card p-7 shadow-lift">
          <div><h2 className="font-display text-2xl">Welcome back</h2><p className="mt-1 text-sm text-muted-foreground">Sign in to your workspace.</p></div>
          {error && <Alert>{error}</Alert>}
          <Field label="Email"><Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
          <Field label="Password"><Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
          <Button variant="primary" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
        </form>
      </section>
    </main>
  );
}
