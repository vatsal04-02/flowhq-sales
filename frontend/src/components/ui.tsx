import Link from "next/link";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(" ");

/* Icons: inline SVG (Lucide-style), decorative => aria-hidden. */
type IconName = "users" | "upload" | "activity" | "alert" | "check" | "info" | "download" | "ban";
const PATHS: Record<IconName, string> = {
  users: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75",
  upload: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M17 8l-5-5-5 5M12 3v12",
  activity: "M22 12h-4l-3 9L9 3l-3 9H2",
  alert: "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
  check: "M20 6 9 17l-5-5",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4M12 8h.01",
  download: "M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3",
  ban: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM4.9 4.9l14.2 14.2",
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
    <section className={cx("rounded border border-border bg-card", className)}>
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
