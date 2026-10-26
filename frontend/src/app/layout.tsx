import { Inter, JetBrains_Mono } from "next/font/google";
import "./globals.css";

const sans = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata = {
  title: { default: "FlowHQ Outreach OS", template: "%s · FlowHQ" },
  description: "Approval-first outreach: research, personalize and follow up, with a human approving every message.",
};
export const viewport = { width: "device-width", initialScale: 1 };

// Runs before first paint so a saved (or OS-preferred) dark theme never flashes light.
const THEME_SCRIPT = `try{var t=localStorage.getItem("flowhq-theme");if(t!=="light"&&t!=="dark")t=matchMedia("(prefers-color-scheme: dark)").matches?"dark":"light";document.documentElement.dataset.theme=t}catch(e){document.documentElement.dataset.theme="light"}`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${sans.variable} ${mono.variable}`} suppressHydrationWarning>
      <head><script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} /></head>
      <body>{children}</body>
    </html>
  );
}
