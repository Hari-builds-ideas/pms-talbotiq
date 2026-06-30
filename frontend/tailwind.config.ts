import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

/**
 * Talbotiq PMS — Admin Hub design system.
 *
 * Direction (from the V0 brief): a blend of Ashby (density + tables),
 * Rippling (admin workflows), Linear (polish + spacing), Lattice (PM patterns).
 * Slate/gray/white base, one confident "Modern Blue" primary, Purple for AI
 * states, Gold/Amber for premium-locked. Subtle, professional, data-dense.
 *
 * Colors are HSL CSS variables (see styles/globals.css) so the same component
 * code supports theming. Domain status colors are exposed as flat utilities.
 */
const config: Config = {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    container: {
      center: true,
      padding: "2rem",
      screens: { "2xl": "1400px" },
    },
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        // App shell (dark sidebar)
        sidebar: {
          DEFAULT: "hsl(var(--sidebar))",
          foreground: "hsl(var(--sidebar-foreground))",
          muted: "hsl(var(--sidebar-muted))",
          accent: "hsl(var(--sidebar-accent))",
          border: "hsl(var(--sidebar-border))",
        },
        // Domain semantic palette
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
          subtle: "hsl(var(--success-subtle))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
          subtle: "hsl(var(--warning-subtle))",
        },
        danger: {
          DEFAULT: "hsl(var(--danger))",
          foreground: "hsl(var(--danger-foreground))",
          subtle: "hsl(var(--danger-subtle))",
        },
        info: {
          DEFAULT: "hsl(var(--info))",
          foreground: "hsl(var(--info-foreground))",
          subtle: "hsl(var(--info-subtle))",
        },
        // AI states (purple) + premium-locked (gold)
        ai: {
          DEFAULT: "hsl(var(--ai))",
          foreground: "hsl(var(--ai-foreground))",
          subtle: "hsl(var(--ai-subtle))",
        },
        premium: {
          DEFAULT: "hsl(var(--premium))",
          foreground: "hsl(var(--premium-foreground))",
          subtle: "hsl(var(--premium-subtle))",
        },
        // Figma field tokens (filled inputs + switch track)
        "input-background": "hsl(var(--input-background))",
        "switch-background": "hsl(var(--switch-background))",
        // Chart palette (recharts data-viz)
        chart: {
          "1": "hsl(var(--chart-1))",
          "2": "hsl(var(--chart-2))",
          "3": "hsl(var(--chart-3))",
          "4": "hsl(var(--chart-4))",
          "5": "hsl(var(--chart-5))",
        },
      },
      borderRadius: {
        xl: "calc(var(--radius) + 4px)",
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      fontFamily: {
        sans: [
          "Inter",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      fontSize: {
        // Compact enterprise scale
        "2xs": ["0.6875rem", { lineHeight: "1rem" }],
        xs: ["0.75rem", { lineHeight: "1rem" }],
        sm: ["0.8125rem", { lineHeight: "1.25rem" }],
        base: ["0.875rem", { lineHeight: "1.375rem" }],
        md: ["0.9375rem", { lineHeight: "1.5rem" }],
        lg: ["1rem", { lineHeight: "1.5rem" }],
        xl: ["1.125rem", { lineHeight: "1.625rem" }],
        "2xl": ["1.375rem", { lineHeight: "1.875rem" }],
        "3xl": ["1.75rem", { lineHeight: "2.125rem" }],
      },
      // TalbotIQ soft shadow ladder (feather-soft card rest → md hover → xl modals)
      // + brand-green button-hover glows.
      boxShadow: {
        xs: "0 1px 2px 0 rgb(0 0 0 / 0.05)",
        sm: "0 1px 3px 0 rgb(0 0 0 / 0.08), 0 1px 2px -1px rgb(0 0 0 / 0.05)",
        DEFAULT: "0 2px 8px -1px rgb(0 0 0 / 0.08), 0 2px 4px -2px rgb(0 0 0 / 0.05)",
        md: "0 4px 12px -2px rgb(0 0 0 / 0.08), 0 2px 6px -2px rgb(0 0 0 / 0.05)",
        lg: "0 8px 24px -4px rgb(0 0 0 / 0.10), 0 4px 10px -4px rgb(0 0 0 / 0.06)",
        xl: "0 16px 40px -8px rgb(0 0 0 / 0.12), 0 8px 16px -8px rgb(0 0 0 / 0.08)",
        "primary-sm": "0 2px 8px -2px rgb(13 92 58 / 0.30)",
        "primary-md": "0 4px 16px -4px rgb(13 92 58 / 0.35)",
        focus: "0 0 0 3px hsl(var(--ring) / 0.35)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
        "fade-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
        shimmer: "shimmer 1.6s infinite",
        "fade-in": "fade-in 0.2s ease-out",
      },
    },
  },
  plugins: [animate],
};

export default config;
