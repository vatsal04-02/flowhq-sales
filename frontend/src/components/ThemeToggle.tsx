"use client";
import { useEffect, useState } from "react";
import { Icon } from "./ui";

const KEY = "flowhq-theme";
type Theme = "light" | "dark";

/** The initial theme is applied before paint by the script in layout.tsx; this just reads and flips it. */
function useTheme() {
  const [theme, setTheme] = useState<Theme>("light");
  useEffect(() => { setTheme(document.documentElement.dataset.theme === "dark" ? "dark" : "light"); }, []);
  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next; setTheme(next);
    try { localStorage.setItem(KEY, next); } catch { /* private mode: the choice just won't persist */ }
  };
  return { theme, toggle };
}

/** Both icons are always rendered and swapped with CSS, so server and client markup match. */
function Glyph({ className = "h-[18px] w-[18px]" }: { className?: string }) {
  return (<><Icon name="moon" className={`${className} dark:hidden`} /><Icon name="sun" className={`${className} hidden dark:block`} /></>);
}

export function ThemeToggle({ variant = "icon", className = "" }: { variant?: "icon" | "row"; className?: string }) {
  const { theme, toggle } = useTheme(); const dark = theme === "dark";
  if (variant === "row") {
    return (
      <button type="button" role="switch" aria-checked={dark} onClick={toggle} title="Toggle dark mode"
        className={`flex min-h-[44px] w-full cursor-pointer items-center gap-2.5 rounded-lg px-3 text-sm text-sidebar-foreground transition-colors hover:bg-white/5 hover:text-white md:min-h-9 ${className}`}>
        <Glyph className="h-[17px] w-[17px]" />
        <span className="flex-1 text-left">Dark mode</span>
        <span aria-hidden="true" className="relative h-5 w-9 rounded-full bg-white/15 transition-colors dark:bg-primary">
          <span className="absolute left-0.5 top-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform dark:translate-x-4" />
        </span>
      </button>);
  }
  return (
    <button type="button" onClick={toggle} aria-label={dark ? "Switch to light mode" : "Switch to dark mode"} title={dark ? "Light mode" : "Dark mode"}
      className={`grid h-11 w-11 cursor-pointer place-items-center rounded-lg transition-colors md:h-9 md:w-9 ${className}`}>
      <Glyph />
    </button>);
}
