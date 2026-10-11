import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Shared Perseus XR tokens; names remain compatible with local vault views.
        bg:            'var(--bg)',
        sidebar:       'var(--sidebar)',
        surface:       'var(--surface)',
        raised:        'var(--raised)',
        border:        'var(--border)',
        accent:        'var(--accent)',
        'accent-light':'var(--accent-light)',
        muted:         'var(--muted)',
        faint:         'var(--faint)',
      },
      fontFamily: {
        sans: ['"Inter"', 'Arial', 'sans-serif'],
        display: ['"Outfit"', '"Inter"', 'Arial', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
      },
      keyframes: {
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition:  '200% 0' },
        },
      },
      animation: {
        shimmer: 'shimmer 1.5s infinite',
      },
    },
  },
  plugins: [],
} satisfies Config
