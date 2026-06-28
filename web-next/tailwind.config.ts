import type { Config } from "tailwindcss";

// Aegis Refine design tokens (ported 1:1 from the static site's app.css).
const config: Config = {
  content: [
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        bg: "#0D0D0F",
        panel: "#16161A",
        "panel-2": "#0F1012",
        "panel-3": "#121316",
        text: "#F2F2F5",
        muted: "#A1A1AA",
        "muted-2": "#71717A",
        "muted-3": "#52525B",
        teal: "#00E5CC",
        amber: "#F59E0B",
        green: "#22C55E",
        red: "#ef4444",
      },
      borderColor: {
        line: "rgba(255,255,255,0.07)",
        "line-2": "rgba(255,255,255,0.1)",
        "teal-line": "rgba(0,229,204,0.3)",
      },
      backgroundColor: {
        "teal-dim": "rgba(0,229,204,0.1)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
export default config;
