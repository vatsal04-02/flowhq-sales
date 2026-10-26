import { useId } from "react";

/** FlowHQ mark: an "F" whose top bar flows out of the stem, with a dot for the lead at the end of the middle bar. */
export function LogoMark({ size = 32, className }: { size?: number; className?: string }) {
  const id = "fhq" + useId().replace(/:/g, "");
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" role="img" aria-label="FlowHQ" className={className}>
      <defs>
        <linearGradient id={id} x1="2" y1="0" x2="30" y2="32" gradientUnits="userSpaceOnUse">
          <stop stopColor="#3B82F6" /><stop offset="1" stopColor="#7C3AED" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="9" fill={`url(#${id})`} />
      <path d="M11 24V14a6 6 0 0 1 6-6h5" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M11 16h6" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
      <circle cx="22.5" cy="16" r="2.25" fill="#fff" fillOpacity="0.92" />
    </svg>
  );
}

/** Mark + wordmark. `onDark` is for the always-dark sidebar and login hero. */
export function Logo({ size = 32, onDark = false, subtitle = "Outreach OS" }: { size?: number; onDark?: boolean; subtitle?: string | null }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={size} className="shrink-0 drop-shadow-[0_4px_10px_hsl(221_83%_50%/0.35)]" />
      <span className="leading-none">
        <span className={`block text-[17px] font-bold tracking-tight ${onDark ? "text-white" : "text-foreground"}`}>
          Flow<span className={onDark ? "text-blue-300" : "text-primary"}>HQ</span>
        </span>
        {subtitle && <span className={`mt-1 block text-xs font-medium uppercase tracking-[0.14em] ${onDark ? "text-sidebar-foreground/70" : "text-muted-foreground"}`}>{subtitle}</span>}
      </span>
    </span>
  );
}
