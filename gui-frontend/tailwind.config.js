/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Spec section 5: Color palette
        bg: "#0A0A0B",
        surface: "#131316",
        "surface-raised": "#1A1A1F",
        "border-default": "#25252B",
        "border-emphasis": "#3A3A42",
        "text-primary": "#F5F5F7",
        "text-secondary": "#8B8B95",
        "text-muted": "#565660",
        accent: "#FF4F1F",
        "accent-dim": "#B33815",

        // Chart colors
        "chart-power-ind": "#E5484D",
        "chart-power-brk": "#4493F8",
        "chart-ve": "#3DD68C",
        "chart-restrictor": "#C586E8",

        // Status colors
        "status-queued": "#565660",
        "status-running": "#FF4F1F",
        "status-converged": "#FFD15C",
        "status-done": "#3DD68C",
        "status-error": "#E5484D",
      },
      fontFamily: {
        ui: ["'Inter Tight'", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "monospace"],
      },
      borderRadius: {
        DEFAULT: "4px",
        md: "6px",
      },
    },
  },
  plugins: [],
};
