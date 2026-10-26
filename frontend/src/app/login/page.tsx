"use client";
import { useState } from "react";
import { Alert, Button, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";

export default function Login() {
  const [email, setEmail] = useState(""); const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault(); setError(null); setBusy(true);
    try { await api("/auth/login", { method: "POST", json: { email, password } }); location.href = "/leads"; }
    catch (err) { setError((err as Error).message); setBusy(false); }
  }
  return (
    <main className="mx-auto mt-16 w-full max-w-sm px-4">
      <form onSubmit={submit} className="space-y-4 rounded border border-border bg-card p-6">
        <h1 className="text-lg font-semibold">Sign in to FlowHQ</h1>
        {error && <Alert>{error}</Alert>}
        <Field label="Email"><Input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
        <Field label="Password"><Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
        <Button variant="primary" className="w-full" disabled={busy}>{busy ? "Signing in…" : "Sign in"}</Button>
      </form>
    </main>
  );
}
