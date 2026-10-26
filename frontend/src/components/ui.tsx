import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(" ");

/* Icons: inline SVG (Lucide-style), decorative => aria-hidden. */
type IconName = "users" | "upload" | "activity" | "alert" | "check" | "info" | "download" | "ban" | "dashboard" | "megaphone" | "inbox" | "kanban" | "plug" | "history" | "send" | "edit" | "x" | "external" | "hand" | "copy" | "play" | "pause" | "file";
const PATHS: Record<IconName, string> = {
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  activity: "M22 12h-4l-3 9L9 3l-3 9H2",
  alert: "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
  check: "M20 6 9 17l-5-5",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  ban: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM4.9 4.9l14.2 14.2",
  dashboard: "M3 3h7v9H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z",
  megaphone: "M3 11v2a1 1 0 0 0 1 1h2l5 4V6L6 10H4a1 1 0 0 0-1 1zM15.5 8.5a5 5 0 0 1 0 7M18.5 5.5a9 9 0 0 1 0 13",
  inbox: "M22 12h-6l-2 3h-4l-2-3H2M5.5 5h13l3.5 7v6a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-6z",
  kanban: "M6 3v18M12 3v10M18 3v14",
  plug: "M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4",
  history: "M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2",
  send: "M22 2 11 13M22 2l-7 20-4-9-9-4z",
  edit: "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z",
  x: "M18 6 6 18M6 6l12 12",
  external: "M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14 21 3",
  hand: "M18 11V6a2 2 0 0 0-4 0M14 10V4a2 2 0 0 0-4 0v6M10 10.5V6a2 2 0 0 0-4 0v8M18 8a2 2 0 0 1 4 0v6a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.9-5.9-2.4L3.4 16a2 2 0 0 1 3-2.7L8 15",
  copy: "M9 9h11v11H9zM5 15H4a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v1",
  play: "M6 4l14 8-14 8z",
  pause: "M6 4h4v16H6zM14 4h4v16h-4z",
  file: "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h8",
};
export function Icon({ name, className = "h-4 w-4" }: { name: IconName; className?: string }) {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" className={cx("shrink-0", className)}>
      <path d={PATHS[name]} />
    </svg>
  );
}

type BtnProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost" };
export function Button({ variant = "secondary", className, ...p }: BtnProps) {
  const v = {
    primary: "bg-primary text-primary-foreground hover:opacity-90",
    secondary: "border border-border bg-card hover:bg-muted",
    danger: "border border-destructive/50 bg-card text-destructive hover:bg-destructive/10",
    ghost: "text-primary hover:bg-muted",
  }[variant];
  return (
    <button {...p} className={cx(
      "inline-flex min-h-[44px] items-center justify-center gap-2 rounded px-3 text-sm font-medium transition-colors",
      "cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 md:min-h-9", v, className)} />
  );
}

export function Field({ label, hint, error, children }: { label: string; hint?: string; error?: string | null; children: ReactNode }) {
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-xs text-muted-foreground">{hint}</span>}
      {error && <span role="alert" className="mt-1 block text-xs text-destructive">{error}</span>}
    </label>
  );
}
export const inputCls =
  "min-h-[44px] w-full rounded border border-border bg-card px-3 text-sm placeholder:text-muted-foreground md:min-h-9";
export function Input(p: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={cx(inputCls, p.className)} />;
}

export function Card({ title, actions, children, className }: { title?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("min-w-0 rounded border border-border bg-card", className)}>
      {(title || actions) && (
        <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-2.5">
          <h2 className="text-sm font-semibold">{title}</h2>{actions}
        </header>)}
      <div className="p-4">{children}</div>
    </section>
  );
}

const TONES = {
  neutral: "bg-muted text-foreground", info: "bg-primary/10 text-primary",
  success: "bg-success/15 text-success", warning: "bg-accent/15 text-warning", danger: "bg-destructive/10 text-destructive",
};
export type Tone = keyof typeof TONES;
/** Status is always conveyed by text (and optional icon), never colour alone. */
export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return <span className={cx("inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs font-medium", TONES[tone])}>{children}</span>;
}
export const statusTone = (s: string): Tone =>
  ["unsubscribed", "suppressed", "bounced"].includes(s) ? "danger"
  : ["qualified", "converted", "meeting_booked", "interested"].includes(s) ? "success"
  : s === "unqualified" || s === "not_interested" ? "warning" : "neutral";
export const pretty = (s: string) => s.replace(/_/g, " ");

export function Alert({ tone = "danger", children }: { tone?: "danger" | "info" | "success"; children: ReactNode }) {
  const cls = { danger: "border-destructive/40 bg-destructive/10", info: "border-primary/30 bg-primary/10", success: "border-success/40 bg-success/10" }[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("flex items-start gap-2 rounded border p-3 text-sm", cls)}>
      <Icon name={tone === "danger" ? "alert" : tone === "success" ? "check" : "info"} className="mt-0.5 h-4 w-4" />
      <div>{children}</div>
    </div>
  );
}

export function Empty({ icon, title, children }: { icon: IconName; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
      <Icon name={icon} className="h-8 w-8 text-muted-foreground" />
      <p className="font-medium">{title}</p>
      <div className="text-sm text-muted-foreground">{children}</div>
    </div>
  );
}

export function Skeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading" className="space-y-2 p-4">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="h-5 animate-pulse rounded bg-muted" />)}
    </div>
  );
}

export function PageHeader({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

export const th = "whitespace-nowrap px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground";
export const td = "px-3 py-2 align-top";
export { Link, cx };

export function Kpi({ label, value, caption, title, tone }: { label: string; value: ReactNode; caption?: ReactNode; title?: string; tone?: Tone }) {
  return (
    <div className="rounded border border-border bg-card p-3" title={title}>
      <div className="text-xs font-medium text-muted-foreground">{label}</div>
      <div className={cx("mt-1 text-2xl font-semibold tabular-nums", tone === "danger" && "text-destructive")}>{value}</div>
      {caption && <div className="mt-0.5 text-xs text-muted-foreground">{caption}</div>}
    </div>
  );
}

/** Horizontal bar row: value is always printed as text, so colour is never the only signal. */
export function BarRow({ label, value, max, suffix }: { label: string; value: number; max: number; suffix?: string }) {
  const pct = max > 0 ? Math.max(2, Math.round((100 * value) / max)) : 0;
  return (
    <div className="grid grid-cols-[110px_1fr_64px] items-center gap-2 text-sm">
      <span className="truncate text-muted-foreground">{label}</span>
      <div className="h-3 rounded bg-muted"><div className="h-3 rounded bg-primary" style={{ width: `${value ? pct : 0}%` }} /></div>
      <span className="text-right tabular-nums">{value.toLocaleString()}{suffix}</span>
    </div>
  );
}
