/** @type {import('tailwindcss').Config} */
// NormaAI design tokens (see DESIGN.md). The colour values live in
// src/app/globals.css as RGB channels, light on :root and dark on .dark,
// so every colour here keeps Tailwind's opacity modifier: bg-union/10.
const rgb = (name) => `rgb(var(--${name}) / <alpha-value>)`

module.exports = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        canvas: rgb('canvas'),
        surface: { DEFAULT: rgb('surface'), 2: rgb('surface-2'), 3: rgb('surface-3') },
        ink: { DEFAULT: rgb('ink'), 2: rgb('ink-2'), 3: rgb('ink-3') },
        rule: { DEFAULT: rgb('rule'), 2: rgb('rule-2') },
        union: { DEFAULT: rgb('union'), deep: rgb('union-deep'), ink: rgb('union-ink') },
        mark: { DEFAULT: rgb('mark'), deep: rgb('mark-deep') },
        ok: rgb('ok'),
        warn: rgb('warn'),
        bad: rgb('bad'),
        // Framework hues: category labels only (dark text on a light tint).
        fw: {
          csrd: '#1F7A53',
          csddd: '#1D6FB8',
          aiact: '#6D4AB8',
          dora: '#B9541F',
          nis2: '#8A5A00',
          taxonomy: '#0F766E',
          gdpr: '#B42A45',
          cra: '#9A3D7A',
          esrs: '#5B5CA5',
        },
      },
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
        serif: ['var(--font-serif)', 'Georgia', 'Times New Roman', 'serif'],
        mono: ['var(--font-mono)', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: {
        caption: ['12px', { lineHeight: '1.4' }],
        small: ['13px', { lineHeight: '1.45' }],
        body: ['15px', { lineHeight: '1.5' }],
        read: ['16px', { lineHeight: '1.55' }],
        h4: ['17px', { lineHeight: '1.4' }],
        h3: ['20px', { lineHeight: '1.3' }],
        h2: ['24px', { lineHeight: '1.2' }],
        h1: ['32px', { lineHeight: '1.15' }],
        display: ['44px', { lineHeight: '1.1', letterSpacing: '-0.01em' }],
        'display-lg': ['56px', { lineHeight: '1.05', letterSpacing: '-0.015em' }],
      },
      borderRadius: {
        sm: '4px',
        md: '6px',
        lg: '10px',
        xl: '14px',
      },
      boxShadow: {
        // Two uses only: the document in the hero and dialogs.
        doc: '0 1px 2px rgba(12, 27, 51, 0.06), 0 12px 32px -12px rgba(12, 27, 51, 0.18)',
        pop: '0 2px 4px rgba(12, 27, 51, 0.08), 0 24px 48px -16px rgba(12, 27, 51, 0.35)',
      },
      maxWidth: {
        site: '1120px',
        app: '1200px',
        prose: '72ch',
      },
      spacing: {
        rail: '232px',
        'rail-collapsed': '64px',
      },
    },
  },
  plugins: [],
}
