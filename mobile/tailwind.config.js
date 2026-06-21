/** Talbotiq PMS mobile — the SAME brand tokens as web (indigo primary, slate base,
 *  violet=AI, amber=premium), as flat NativeWind colors. */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}"],
  presets: [require("nativewind/preset")],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: "#5B5BD6", foreground: "#FFFFFF" },
        background: "#F1F1F6",
        foreground: "#0C0C14",
        card: { DEFAULT: "#FFFFFF", foreground: "#0C0C14" },
        muted: { DEFAULT: "#EDEDF5", foreground: "#71718A" },
        border: "#E2E2EC",
        sidebar: "#0C0C14",
        success: { DEFAULT: "#00B87C", subtle: "#E1F7EF" },
        warning: { DEFAULT: "#F59E0B", subtle: "#FCEFD6" },
        danger: { DEFAULT: "#EF4444", subtle: "#FBE3E3" },
        ai: "#8B5CF6",
      },
    },
  },
  plugins: [],
};
