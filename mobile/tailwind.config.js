/** Talbotiq PMS mobile — the SAME TalbotIQ design language as web (brand green
 *  primary #0d5c3a, light green-tinted canvas, AI quiet/on-brand), as flat
 *  NativeWind colors. */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: "#0d5c3a", foreground: "#FFFFFF" },
        background: "#eff5f0",
        foreground: "#0f172a",
        card: { DEFAULT: "#FFFFFF", foreground: "#0f172a" },
        muted: { DEFAULT: "#f0f5f1", foreground: "#64748b" },
        border: "#dde8e0",
        sidebar: "#FFFFFF",
        success: { DEFAULT: "#16a34a", subtle: "#f0fdf4" },
        warning: { DEFAULT: "#d97706", subtle: "#fffbeb" },
        danger: { DEFAULT: "#dc2626", subtle: "#fef2f2" },
        // AI is quiet / on-brand (both docs: AI is invisible) — not a loud violet.
        ai: "#0d5c3a",
      },
    },
  },
  plugins: [],
};
