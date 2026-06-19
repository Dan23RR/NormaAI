/** @type {import('tailwindcss').Config} */
// NormaAI brand tokens - mirrors dashboard/styles.css :root variables.
// Updated 2026-04-28 (G4.3): aligned to dashboard mockup design system.
// Aliases bg/surface/text/text-muted/accent/accent2 mantenuti per
// backward-compat con le 31 pagine dashboard esistenti.

module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        // Surface scale (dark backend stack)
        bg: '#0a0d12',
        'bg-2': '#0e1218',
        surface: '#11161e',
        'surface-2': '#161c26',
        'surface-3': '#1d2531',
        // Backward-compat alias
        surface2: '#161c26',

        // Borders
        border: 'rgba(255, 255, 255, 0.06)',
        'border-2': 'rgba(255, 255, 255, 0.10)',
        'border-3': 'rgba(255, 255, 255, 0.16)',

        // Ink (typography)
        ink: '#e6ebf2',
        'ink-2': '#aab3c0',
        'ink-3': '#6f7a8a',
        'ink-4': '#4b5566',
        // Backward-compat aliases
        text: '#e6ebf2',
        'text-muted': '#aab3c0',

        // Brand (NormaAI blue, not indigo)
        accent: '#5b8cff',
        accent2: '#3a6cff',
        'accent-soft': 'rgba(91, 140, 255, 0.10)',

        // Semantic
        good: '#34d399',
        'good-soft': 'rgba(52, 211, 153, 0.10)',
        warn: '#f4b740',
        'warn-soft': 'rgba(244, 183, 64, 0.10)',
        bad: '#ef4f63',
        'bad-soft': 'rgba(239, 79, 99, 0.10)',
        info: '#67c8ff',

        // Per-framework hue
        'fw-csrd': '#34d399',
        'fw-csddd': '#5fbcff',
        'fw-ai_act': '#b08bff',
        'fw-dora': '#ff8c5a',
        'fw-nis2': '#f4b740',
        'fw-taxonomy': '#4ad6c2',
        'fw-gdpr': '#ef4f63',

        // ── "Warm paper" palette (public pages: landing, legali, codex) ──
        // Editoriale su carta calda, ispirata alla grammatica visiva
        // Anthropic (#FAF9F5 / #141413 / clay #D97757). La dashboard
        // continua a usare la scala dark qui sopra: token additivi,
        // nessuna collisione di nome.
        paper: '#FAF9F5',
        'paper-2': '#F0EEE6',
        'paper-3': '#E8E4D9',
        night: '#141413',
        'night-2': '#5E5D59',
        'night-3': '#87867F',
        coal: '#0F0F0E',
        'coal-2': '#1B1B19',
        clay: '#D97757',
        'clay-deep': '#C2613F',
        'clay-soft': 'rgba(217, 119, 87, 0.10)',
        line: '#E3DFD3',
        'line-2': '#D2CCBC',
      },
      fontFamily: {
        sans: [
          'var(--font-sans)',
          'system-ui',
          '-apple-system',
          'Segoe UI',
          'Roboto',
          'sans-serif',
        ],
        serif: [
          'var(--font-serif)',
          'Georgia',
          'Times New Roman',
          'serif',
        ],
        mono: [
          'var(--font-mono)',
          'JetBrains Mono',
          'Menlo',
          'Consolas',
          'monospace',
        ],
      },
      borderRadius: {
        xs: '4px',
        sm: '6px',
        md: '10px',
        lg: '14px',
        xl: '20px',
      },
      boxShadow: {
        soft: '0 1px 0 rgba(255,255,255,0.03) inset, 0 8px 24px rgba(0,0,0,0.20)',
        pop: '0 24px 48px rgba(0,0,0,0.45), 0 2px 0 rgba(255,255,255,0.04) inset',
      },
      backgroundImage: {
        'app-radial':
          'radial-gradient(1200px 600px at 20% -10%, rgba(91,140,255,0.06), transparent 60%), radial-gradient(900px 500px at 100% 110%, rgba(176,139,255,0.04), transparent 60%)',
      },
      spacing: {
        sidebar: '240px',
        'sidebar-collapsed': '64px',
        topbar: '56px',
      },
    },
  },
  plugins: [],
}
