const c = (n) => `hsl(var(--${n}) / <alpha-value>)`;
module.exports = {
  // Theme is driven by <html data-theme="light|dark"> (set before paint by the script in layout.tsx).
  darkMode: ["selector", '[data-theme="dark"]'],
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      colors: {
        background: c("background"), foreground: c("foreground"), card: c("card"), muted: c("muted"),
        "muted-foreground": c("muted-foreground"), border: c("border"), primary: c("primary"),
        "primary-foreground": c("primary-foreground"), accent: c("accent"), destructive: c("destructive"),
        success: c("success"), warning: c("warning"), ring: c("ring"), sidebar: c("sidebar"), "sidebar-foreground": c("sidebar-foreground"),
      },
      borderRadius: { DEFAULT: "8px", lg: "12px", xl: "16px" },
      boxShadow: {
        card: "0 1px 2px hsl(222 47% 11% / 0.04), 0 1px 3px hsl(222 47% 11% / 0.06)",
        lift: "0 4px 12px hsl(222 47% 11% / 0.08), 0 1px 3px hsl(222 47% 11% / 0.06)",
        glow: "0 6px 18px hsl(221 83% 50% / 0.35)",
      },
    },
  },
  plugins: [],
};
