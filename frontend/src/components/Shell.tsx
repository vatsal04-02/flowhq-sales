"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Avatar, Icon } from "./ui";

type NavItem = { href: string; label: string; icon: any };
const NAV: { group: string; items: NavItem[] }[] = [
  { group: "Work", items: [
    { href: "/dashboard", label: "Dashboard", icon: "dashboard" }, { href: "/leads", label: "Leads", icon: "users" },
    { href: "/import", label: "Import", icon: "upload" }, { href: "/campaigns", label: "Campaigns", icon: "megaphone" }] },
  { group: "Outreach", items: [
    { href: "/review", label: "Draft review", icon: "edit" }, { href: "/inbox", label: "Inbox", icon: "inbox" },
    { href: "/manual", label: "Manual queue", icon: "hand" }, { href: "/pipeline", label: "Pipeline", icon: "kanban" }] },
  { group: "System", items: [
    { href: "/jobs", label: "Jobs & suppression", icon: "activity" }, { href: "/integrations", label: "Integrations", icon: "plug" },
    { href: "/activity", label: "Activity log", icon: "history" }] },
];

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-3 py-4">
      <span className="grid h-8 w-8 place-items-center rounded-lg bg-gradient-to-br from-primary to-[hsl(262_70%_55%)] shadow-glow" aria-hidden="true">
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M4 12h6l2-6 3 12 2-6h3" /></svg></span>
      <div className="leading-tight"><div className="font-display text-lg text-white">FlowHQ</div><div className="text-[11px] uppercase tracking-widest text-sidebar-foreground/70">Outreach OS</div></div>
    </div>
  );
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname(); const [me, setMe] = useState<{ email: string; role: string } | null>(null);
  useEffect(() => { api<{ email: string; role: string }>("/me").then(setMe).catch(() => {}); }, []);
  async function logout() { await api("/auth/logout", { method: "POST" }); location.href = "/login"; }
  const link = (n: NavItem, mobile = false) => {
    const active = path === n.href || path.startsWith(n.href + "/");
    return (
      <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
        className={`relative flex min-h-[44px] items-center gap-2.5 whitespace-nowrap rounded-lg px-3 text-sm transition-colors duration-200 md:min-h-9 ${mobile ? "" : "w-full"} ${active ? "bg-white/10 font-semibold text-white" : "text-sidebar-foreground hover:bg-white/5 hover:text-white"}`}>
        {active && !mobile && <span aria-hidden="true" className="absolute -left-3 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r bg-primary" />}
        <Icon name={n.icon} className={`h-[17px] w-[17px] ${active ? "text-primary-foreground" : ""}`} />{n.label}
      </Link>);
  };
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[236px_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:rounded focus:bg-card focus:p-2">Skip to content</a>
      <aside className="hidden bg-sidebar lg:block">
        <div className="sticky top-0 flex h-screen flex-col px-3 pb-3">
          <Brand />
          <nav aria-label="Main" className="flex-1 space-y-5 overflow-y-auto pt-2">
            {NAV.map((g) => (
              <div key={g.group}><div className="px-3 pb-1.5 text-[11px] font-semibold uppercase tracking-widest text-sidebar-foreground/50">{g.group}</div>
                <div className="space-y-0.5">{g.items.map((n) => link(n))}</div></div>))}
          </nav>
          <div className="mt-2 flex items-center gap-2.5 rounded-lg bg-white/5 p-2.5">
            <Avatar name={me?.email ?? "?"} size={32} />
            <div className="min-w-0 flex-1 leading-tight"><div className="truncate text-[13px] font-medium text-white">{me?.email ?? "…"}</div><div className="text-[11px] capitalize text-sidebar-foreground/70">{me?.role}</div></div>
            <button onClick={logout} aria-label="Sign out" title="Sign out" className="grid h-8 w-8 cursor-pointer place-items-center rounded-md text-sidebar-foreground hover:bg-white/10 hover:text-white"><Icon name="x" /></button>
          </div>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="bg-sidebar lg:hidden">
          <div className="flex items-center justify-between pr-2"><Brand /><button onClick={logout} className="min-h-[44px] cursor-pointer px-3 text-sm text-sidebar-foreground">Sign out</button></div>
          <nav aria-label="Main" className="flex items-center gap-1 overflow-x-auto px-2 pb-2">{NAV.flatMap((g) => g.items).map((n) => link(n, true))}</nav>
        </header>
        <main id="main" className="mx-auto max-w-7xl px-4 py-6 lg:px-8">{children}</main>
      </div>
    </div>
  );
}
