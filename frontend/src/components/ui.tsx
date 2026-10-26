"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

const cx = (...a: (string | false | null | undefined)[]) => a.filter(Boolean).join(" ");

/* Icons: inline SVG (Lucide-style), decorative => aria-hidden. */
type IconName = "users" | "upload" | "activity" | "alert" | "check" | "info" | "download" | "ban" | "dashboard" | "megaphone" | "inbox" | "kanban" | "plug" | "history" | "send" | "edit" | "x" | "external" | "hand" | "copy" | "play" | "pause" | "file" | "sun" | "moon" | "mic" | "square" | "chevron";
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
  mic: "M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3zM19 10v2a7 7 0 0 1-14 0v-2M12 19v3M8 22h8",
  square: "M7 7h10v10H7z",
  chevron: "M6 9l6 6 6-6",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
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
    primary: "bg-gradient-to-b from-primary to-primary/85 text-primary-foreground shadow-card hover:shadow-glow hover:brightness-110 active:brightness-95",
    secondary: "border border-border bg-card shadow-card hover:bg-muted hover:shadow-lift",
    danger: "border border-destructive/50 bg-card text-destructive hover:bg-destructive/10",
    ghost: "text-primary hover:bg-muted",
  }[variant];
  return (
    <button {...p} className={cx(
      "inline-flex min-h-[44px] items-center justify-center gap-2 rounded-lg px-3.5 text-sm font-medium transition-all duration-200",
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
  "min-h-[44px] w-full rounded-lg border border-border bg-card px-3 text-sm shadow-card transition-shadow placeholder:text-muted-foreground focus:shadow-lift md:min-h-9";
export function Input(p: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...p} className={cx(inputCls, p.className)} />;
}

export function Card({ title, actions, children, className }: { title?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("page-in min-w-0 rounded-xl border border-border bg-card shadow-card", className)}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
          <h2 className="text-[15px] font-semibold">{title}</h2>{actions}
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
const DOT = { neutral: "bg-muted-foreground", info: "bg-primary", success: "bg-success", warning: "bg-accent", danger: "bg-destructive" };
export function Badge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-medium", TONES[tone])}>
      <span aria-hidden="true" className={cx("h-1.5 w-1.5 rounded-full", DOT[tone])} />{children}
    </span>
  );
}
export const statusTone = (s: string): Tone =>
  ["unsubscribed", "suppressed", "bounced"].includes(s) ? "danger"
  : ["qualified", "converted", "meeting_booked", "interested"].includes(s) ? "success"
  : s === "unqualified" || s === "not_interested" ? "warning" : "neutral";
export const pretty = (s: string) => s.replace(/_/g, " ");

export function Alert({ tone = "danger", children }: { tone?: "danger" | "info" | "success"; children: ReactNode }) {
  const cls = { danger: "border-destructive/40 bg-destructive/10", info: "border-primary/30 bg-primary/10", success: "border-success/40 bg-success/10" }[tone];
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cx("flex items-start gap-2.5 rounded-lg border p-3 text-sm shadow-card", cls)}>
      <Icon name={tone === "danger" ? "alert" : tone === "success" ? "check" : "info"} className="mt-0.5 h-4 w-4" />
      <div>{children}</div>
    </div>
  );
}

export function Empty({ icon, title, children }: { icon: IconName; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-2 px-4 py-12 text-center">
      <span className="grid h-14 w-14 place-items-center rounded-full bg-primary/10 text-primary ring-8 ring-primary/5"><Icon name={icon} className="h-6 w-6" /></span>
      <p className="mt-2 font-semibold">{title}</p>
      <div className="text-sm text-muted-foreground">{children}</div>
    </div>
  );
}

export function Skeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div aria-busy="true" aria-label="Loading" className="space-y-2 p-4">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="h-5 animate-pulse rounded-md bg-muted" style={{ animationDelay: `${i * 80}ms` }} />)}
    </div>
  );
}

export function PageHeader({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div><h1 className="text-2xl sm:text-[1.75rem]">{title}</h1>{subtitle && <p className="mt-1 text-sm text-muted-foreground">{subtitle}</p>}</div>
      <div className="flex flex-wrap items-center gap-2">{children}</div>
    </div>
  );
}

export const th = "sticky top-0 whitespace-nowrap bg-muted/70 px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground backdrop-blur";
export const td = "px-3 py-2.5 align-top";
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

/* ---------- visual components ---------- */
const PALETTE = ["--chart-1", "--chart-3", "--chart-4", "--chart-2", "--chart-5", "--chart-6"];
export const chartColor = (i: number) => `hsl(var(${PALETTE[i % PALETTE.length]}))`;

export function Avatar({ name, size = 32 }: { name: string; size?: number }) {
  const initials = (name || "?").split(/[\s@.]+/).filter(Boolean).slice(0, 2).map((p) => p[0]!.toUpperCase()).join("") || "?";
  let h = 0; for (const ch of name || "") h = (h * 31 + ch.charCodeAt(0)) % 360;
  return (
    <span aria-hidden="true" className="inline-grid shrink-0 place-items-center rounded-full font-semibold text-white"
      style={{ width: size, height: size, fontSize: size * 0.38, background: `linear-gradient(135deg, hsl(${h} 65% 46%), hsl(${(h + 40) % 360} 70% 38%))` }}>{initials}</span>
  );
}

export function Sparkline({ data, color = 0, width = 96, height = 30 }: { data: number[]; color?: number; width?: number; height?: number }) {
  const max = Math.max(...data, 1); const step = data.length > 1 ? width / (data.length - 1) : width;
  const pts = data.map((v, i) => [i * step, height - 3 - (v / max) * (height - 6)] as const);
  // smooth (Catmull-Rom -> cubic Bezier) so sparse daily counts read as a trend, not a seismograph
  const line = pts.map(([x, y], i) => {
    if (i === 0) return `M${x.toFixed(1)} ${y.toFixed(1)}`;
    const [x0, y0] = pts[i - 2] ?? pts[i - 1]; const [x1, y1] = pts[i - 1]; const [x3, y3] = pts[i + 1] ?? pts[i];
    const c1 = [x1 + (x - x0) / 6, y1 + (y - y0) / 6], c2 = [x - (x3 - x1) / 6, y - (y3 - y1) / 6];
    return `C${c1[0].toFixed(1)} ${Math.min(Math.max(c1[1], 1), height - 1).toFixed(1)} ${c2[0].toFixed(1)} ${Math.min(Math.max(c2[1], 1), height - 1).toFixed(1)} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const col = chartColor(color);
  return (
    <svg aria-hidden="true" width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
      <path d={`${line} L${width} ${height} L0 ${height} Z`} fill={col} opacity="0.12" />
      <path d={line} fill="none" stroke={col} strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" pathLength={1} className="draw" />
    </svg>
  );
}

export function StatCard({ label, value, caption, icon, spark, tone = "primary", title }: { label: string; value: ReactNode; caption?: ReactNode; icon: IconName; spark?: number[]; tone?: "primary" | "accent" | "success" | "danger"; title?: string }) {
  const chip = { primary: "bg-primary/10 text-primary", accent: "bg-accent/15 text-accent", success: "bg-success/15 text-success", danger: "bg-destructive/10 text-destructive" }[tone];
  return (
    <div title={title} className="page-in group rounded-xl border border-border bg-card p-4 shadow-card transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lift">
      <div className="flex items-start justify-between gap-2">
        <span className={cx("grid h-9 w-9 place-items-center rounded-lg", chip)}><Icon name={icon} className="h-[18px] w-[18px]" /></span>
        {spark && <Sparkline data={spark} color={tone === "accent" ? 3 : tone === "success" ? 1 : 0} />}
      </div>
      <div className="mt-3 text-sm font-medium text-muted-foreground">{label}</div>
      <div className="text-3xl font-semibold tabular-nums tracking-tight">{value}</div>
      {caption && <div className="mt-0.5 text-xs text-muted-foreground">{caption}</div>}
    </div>
  );
}

export function Ring({ value, label, caption, color = 0 }: { value: number | null; label: string; caption?: ReactNode; color?: number }) {
  const r = 28, c = 2 * Math.PI * r, v = Math.max(0, Math.min(100, value ?? 0));
  return (
    <div className="flex items-center gap-3">
      <svg width="72" height="72" viewBox="0 0 72 72" role="img" aria-label={`${label}: ${value == null ? "no data" : v + "%"}`}>
        <circle cx="36" cy="36" r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth="8" />
        {v > 0 && <circle cx="36" cy="36" r={r} fill="none" stroke={chartColor(color)} strokeWidth="8" strokeLinecap="round" strokeDasharray={`${(v / 100) * c} ${c}`} transform="rotate(-90 36 36)" />}
        <text x="36" y="41" textAnchor="middle" className="fill-foreground text-[15px] font-semibold">{value == null ? "—" : `${v}%`}</text>
      </svg>
      <div><div className="text-sm font-medium">{label}</div><div className="text-xs text-muted-foreground">{caption}</div></div>
    </div>
  );
}

export type Series = { key: string; label: string; color: number; dash?: string };
export function AreaChart({ data, series, height = 260 }: { data: Record<string, any>[]; series: Series[]; height?: number }) {
  const [hover, setHover] = useState<number | null>(null); const ref = useRef<HTMLDivElement>(null); const [W, setW] = useState(640);
  useEffect(() => { // measure so axis text stays a readable 11px at every screen width
    const el = ref.current; if (!el) return; const ro = new ResizeObserver(() => setW(Math.max(280, Math.round(el.clientWidth)))); ro.observe(el); setW(Math.max(280, Math.round(el.clientWidth))); return () => ro.disconnect();
  }, []);
  const H = height, L = 34, R = 12, T = 12, B = 26;
  const raw = Math.max(...data.flatMap((d) => series.map((s) => d[s.key] as number)), 0);
  const nice = Math.max(4, Math.ceil(raw / 4) * 4); // multiples of 4 => integer gridlines (0,2,4…)
  const x = (i: number) => L + (data.length > 1 ? (i * (W - L - R)) / (data.length - 1) : 0);
  const y = (v: number) => T + (1 - v / nice) * (H - T - B);
  const path = (k: string) => data.map((d, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(d[k]).toFixed(1)}`).join(" ");
  const empty = raw === 0;
  const fmt = (d: string) => new Date(d + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" });
  const hv = hover != null ? data[hover] : null;
  return (
    <div ref={ref} className="relative">
      <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="block max-w-full" role="img" aria-label={`Line chart of ${series.map((s) => s.label).join(", ")} per day`}
        onMouseLeave={() => setHover(null)} onMouseMove={(e) => { const r = e.currentTarget.getBoundingClientRect(); const px = e.clientX - r.left; setHover(Math.max(0, Math.min(data.length - 1, Math.round(((px - L) / (W - L - R)) * (data.length - 1))))); }}>
        {[0, 1, 2, 3, 4].map((g) => { const v = (nice / 4) * g; return (<g key={g}><line x1={L} x2={W - R} y1={y(v)} y2={y(v)} stroke="hsl(var(--border))" strokeDasharray={g ? "3 4" : undefined} />
          <text x={L - 6} y={y(v) + 4} textAnchor="end" fontSize="11" className="fill-muted-foreground">{v}</text></g>); })}
        {[0, Math.floor((data.length - 1) / 2), data.length - 1].map((i, k) => data[i] && <text key={k} x={x(i)} y={H - 6} fontSize="11" textAnchor={k === 0 ? "start" : k === 2 ? "end" : "middle"} className="fill-muted-foreground">{fmt(data[i].date)}</text>)}
        {series.map((s, si) => (<g key={s.key}>
          {si === 0 && <path d={`${path(s.key)} L${x(data.length - 1)} ${y(0)} L${x(0)} ${y(0)} Z`} fill={chartColor(s.color)} opacity="0.12" />}
          <path d={path(s.key)} fill="none" stroke={chartColor(s.color)} strokeWidth="2.25" strokeDasharray={s.dash} strokeLinecap="round" strokeLinejoin="round" pathLength={s.dash ? undefined : 1} className={s.dash ? undefined : "draw"} /></g>))}
        {hover != null && (<g><line x1={x(hover)} x2={x(hover)} y1={T} y2={H - B} stroke="hsl(var(--muted-foreground))" strokeDasharray="2 3" />
          {series.map((s) => <circle key={s.key} cx={x(hover)} cy={y(data[hover][s.key])} r="4" fill="hsl(var(--card))" stroke={chartColor(s.color)} strokeWidth="2" />)}</g>)}
      </svg>
      {empty && <div className="pointer-events-none absolute inset-0 grid place-items-center text-sm text-muted-foreground">No activity in this period yet</div>}
      {hv && (<div className="pointer-events-none absolute right-2 top-0 rounded-lg border border-border bg-card px-3 py-2 text-xs shadow-lift"><div className="mb-1 font-semibold">{fmt(hv.date)}</div>
        {series.map((s) => <div key={s.key} className="flex items-center gap-2"><svg width="16" height="4" aria-hidden="true"><line x1="0" x2="16" y1="2" y2="2" stroke={chartColor(s.color)} strokeWidth="2.5" strokeDasharray={s.dash} /></svg>{s.label}: <b className="tabular-nums">{hv[s.key]}</b></div>)}</div>)}
      <ul className="mt-1 flex flex-wrap gap-4 text-xs text-muted-foreground">{series.map((s) => <li key={s.key} className="flex items-center gap-1.5"><svg width="22" height="6" aria-hidden="true"><line x1="0" x2="22" y1="3" y2="3" stroke={chartColor(s.color)} strokeWidth="2.5" strokeDasharray={s.dash} /></svg>{s.label}</li>)}</ul>
    </div>
  );
}

export function Donut({ parts }: { parts: { label: string; value: number; color?: number }[] }) {
  const total = parts.reduce((a, p) => a + p.value, 0); const r = 40, c = 2 * Math.PI * r; let off = 0;
  return (
    <div className="flex flex-wrap items-center gap-5">
      <svg width="124" height="124" viewBox="0 0 100 100" role="img" aria-label={`Distribution of ${total} leads`}>
        <circle cx="50" cy="50" r={r} fill="none" stroke="hsl(var(--muted))" strokeWidth="14" />
        {total > 0 && parts.map((p, i) => { const len = (p.value / total) * c; const el = p.value > 0 && <circle key={p.label} cx="50" cy="50" r={r} fill="none" stroke={chartColor(p.color ?? i)} strokeWidth="14" strokeDasharray={`${len} ${c - len}`} strokeDashoffset={-off} transform="rotate(-90 50 50)" />; off += len; return el; })}
        <text x="50" y="48" textAnchor="middle" className="fill-foreground text-[16px] font-semibold">{total}</text><text x="50" y="60" textAnchor="middle" className="fill-muted-foreground text-[7px]">leads</text>
      </svg>
      <ul className="min-w-[140px] flex-1 space-y-1.5 text-sm">{parts.map((p, i) => (<li key={p.label} className="flex items-center justify-between gap-3"><span className="flex items-center gap-2 capitalize"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: chartColor(p.color ?? i) }} />{p.label}</span>
        <span className="tabular-nums text-muted-foreground">{p.value}{total ? ` · ${Math.round((100 * p.value) / total)}%` : ""}</span></li>))}</ul>
    </div>
  );
}

export function Funnel({ steps }: { steps: { stage: string; count: number }[] }) {
  const max = Math.max(...steps.map((s) => s.count), 1);
  return (
    <ol className="space-y-2">{steps.map((s, i) => { const prev = i ? steps[i - 1].count : null; const conv = prev ? Math.round((100 * s.count) / prev) : null;
      return (<li key={s.stage} className="grid grid-cols-[92px_1fr_auto] items-center gap-3 text-sm">
        <span className="text-muted-foreground">{s.stage}</span>
        <div className="h-7 overflow-hidden rounded-md bg-muted">{s.count > 0 && <div className="flex h-7 items-center rounded-md px-2 text-xs font-semibold text-primary-foreground transition-all duration-500" style={{ width: `${Math.max(8, (100 * s.count) / max)}%`, background: `linear-gradient(90deg, hsl(var(--chart-1)), hsl(var(--chart-4)))` }}>{s.count}</div>}</div>
        <span className="w-14 text-right text-xs tabular-nums text-muted-foreground">{conv != null ? `${conv}%` : "—"}</span></li>); })}</ol>
  );
}
