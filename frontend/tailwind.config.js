const c = (n) => `hsl(var(--${n}) / <alpha-value>)`;
module.exports = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        background: c("background"), foreground: c("foreground"), card: c("card"), muted: c("muted"),
        "muted-foreground": c("muted-foreground"), border: c("border"), primary: c("primary"),
        "primary-foreground": c("primary-foreground"), accent: c("accent"), destructive: c("destructive"),
        success: c("success"), warning: c("warning"), ring: c("ring"),
      },
      borderRadius: { DEFAULT: "6px" },
    },
  },
  plugins: [],
};
