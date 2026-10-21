/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        claude: {
          bg: "#FAF9F5",
          subtle: "#F5F3ED",
          card: "#FFFFFF",
          muted: "#FBF9F4",
          border: "#E8E4DA",
          "border-subtle": "#F0ECE1",
          "border-strong": "#D5CFC2",
          text: "#1F1E1D",
          "text-secondary": "#6E6961",
          "text-muted": "#9B9488",
          clay: "#D97757",
          "clay-hover": "#C15F3C",
          "clay-light": "#FBF2ED",
          "clay-subtle": "#FAF0EB",
          "clay-border": "#EACBBF",
          sand: "#EAE5D9",
          amber: "#B8860B",
          forest: "#2D6A4F",
          sage: "#588157",
        },
      },
      fontFamily: {
        serif: [
          '"Newsreader"',
          '"Source Han Serif SC"',
          '"Noto Serif SC"',
          'Georgia',
          'Cambria',
          'serif',
        ],
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          '"Inter"',
          '"PingFang SC"',
          '"Hiragino Sans GB"',
          '"Microsoft YaHei"',
          'sans-serif',
        ],
        mono: [
          '"SF Mono"',
          'Menlo',
          'Monaco',
          'Consolas',
          'monospace',
        ],
      },
      boxShadow: {
        'claude-card': '0 1px 3px rgba(40, 30, 20, 0.04), 0 6px 16px rgba(40, 30, 20, 0.03)',
        'claude-hover': '0 4px 20px rgba(40, 30, 20, 0.08), 0 1px 4px rgba(40, 30, 20, 0.04)',
        'claude-modal': '0 20px 48px -12px rgba(40, 30, 20, 0.18)',
      },
    },
  },
  plugins: [],
};
