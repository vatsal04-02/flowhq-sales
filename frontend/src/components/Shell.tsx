"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { Icon } from "./ui";

const NAV = [
  { href: "/leads", label: "Leads", icon: "users" },
  { href: "/import", label: "Import", icon: "upload" },
  { href: "/jobs", label: "Jobs & suppression", icon: "activity" },
] as const;

export default function Shell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  async function logout() { await api("/auth/logout", { method: "POST" }); location.href = "/login"; }
  return (
    <div className="min-h-screen">
      <a href="#main" className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-10 focus:rounded focus:bg-card focus:p-2">Skip to content</a>
      <header className="border-b border-border bg-card">
        <nav aria-label="Main" className="mx-auto flex max-w-7xl items-center gap-1 overflow-x-auto px-4">
          <span className="mr-4 whitespace-nowrap py-3 font-semibold">FlowHQ <span className="text-muted-foreground">Outreach OS</span></span>
          {NAV.map((n) => {
            const active = path.startsWith(n.href);
            return (
              <Link key={n.href} href={n.href} aria-current={active ? "page" : undefined}
                className={`flex min-h-[44px] items-center gap-2 whitespace-nowrap border-b-2 px-3 text-sm ${active ? "border-primary font-semibold text-primary" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
                <Icon name={n.icon} />{n.label}
              </Link>);
          })}
          <button onClick={logout} className="ml-auto min-h-[44px] cursor-pointer whitespace-nowrap px-3 text-sm text-muted-foreground hover:text-foreground">Sign out</button>
        </nav>
      </header>
      <main id="main" className="mx-auto max-w-7xl px-4 py-5">{children}</main>
    </div>
  );
}
