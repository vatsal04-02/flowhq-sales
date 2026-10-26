"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { Icon } from "./ui";

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

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  async function logout() { await api("/auth/logout", { method: "POST" }); location.href = "/login"; }
  const link = (n: NavItem, mobile = false) => {
    const active = path === n.href || path.startsWith(n.href + "/");
    return (
      <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
        className={`flex min-h-[44px] items-center gap-2 whitespace-nowrap rounded px-3 text-sm md:min-h-9 ${mobile ? "" : "w-full"} ${active ? "bg-primary/10 font-semibold text-primary" : "text-muted-foreground hover:bg-muted hover:text-foreground"}`}>
        <Icon name={n.icon} />{n.label}
      </Link>);
  };
  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[220px_1fr]">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:rounded focus:bg-card focus:p-2">Skip to content</a>
      <aside className="hidden border-r border-border bg-card lg:block">
        <div className="sticky top-0 flex h-screen flex-col p-3">
          <div className="px-3 py-3 font-semibold">FlowHQ <span className="text-muted-foreground">Outreach OS</span></div>
          <nav aria-label="Main" className="flex-1 space-y-4 overflow-y-auto">
            {NAV.map((g) => (
              <div key={g.group}><div className="px-3 pb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{g.group}</div>
                <div className="space-y-0.5">{g.items.map((n) => link(n))}</div></div>))}
          </nav>
          <button onClick={logout} className="min-h-9 cursor-pointer rounded px-3 text-left text-sm text-muted-foreground hover:bg-muted hover:text-foreground">Sign out</button>
        </div>
      </aside>
      <div className="min-w-0">
        <header className="border-b border-border bg-card lg:hidden">
          <nav aria-label="Main" className="flex items-center gap-1 overflow-x-auto px-2">
            {NAV.flatMap((g) => g.items).map((n) => link(n, true))}
            <button onClick={logout} className="ml-auto min-h-[44px] cursor-pointer whitespace-nowrap px-3 text-sm text-muted-foreground">Sign out</button>
          </nav>
        </header>
        <main id="main" className="mx-auto max-w-7xl px-4 py-5">{children}</main>
      </div>
    </div>
  );
}
