/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // White/grey theme, built on the dataviz skill's validated light-mode
        // reference palette (chart surface #fcfcfb, page plane #f9f9f7,
        // primary ink #0b0b0b, secondary #52514e, muted #898781, gridline
        // #e1e0d9) so text-on-surface contrast is already checked, not eyeballed.
        surface: { DEFAULT: '#f4f5f3', panel: '#ffffff', raised: '#ffffff', overlay: '#fcfcfb' },
        ink: { primary: '#0b0b0b', secondary: '#52514e', muted: '#898781' },
        hairline: '#e1e0d9',
        accent: {
          blue: '#2a78d6',
          orange: '#eb6834',
          aqua: '#1baf7a',
          yellow: '#eda100',
          magenta: '#e87ba4',
          green: '#008300',
          violet: '#4a3aa7',
          red: '#e34948',
        },
        status: {
          good: '#0ca30c',
          warning: '#fab219',
          serious: '#ec835a',
          critical: '#d03b3b',
        },
      },
      fontFamily: {
        sans: ['"IBM Plex Sans"', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        serif: ['"IBM Plex Serif"', 'Georgia', 'Cambria', 'serif'],
        mono: ['"IBM Plex Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace'],
      },
      boxShadow: {
        glow: '0 0 48px -14px rgba(42,120,214,0.35)',
        'glow-violet': '0 0 48px -16px rgba(74,58,167,0.32)',
        panel: '0 1px 0 rgba(255,255,255,0.6) inset, 0 1px 2px rgba(11,11,11,0.04), 0 16px 32px -20px rgba(11,11,11,0.12)',
        'panel-hover': '0 1px 0 rgba(255,255,255,0.6) inset, 0 20px 40px -20px rgba(42,120,214,0.18)',
      },
      backgroundSize: { grid: '34px 34px' },
      backgroundImage: {
        'aurora-blue': 'radial-gradient(circle, rgba(42,120,214,0.14), transparent 70%)',
        'aurora-violet': 'radial-gradient(circle, rgba(74,58,167,0.12), transparent 70%)',
        'aurora-aqua': 'radial-gradient(circle, rgba(27,175,122,0.10), transparent 70%)',
        'sheen': 'linear-gradient(115deg, transparent 20%, rgba(255,255,255,0.6) 40%, transparent 60%)',
      },
      keyframes: {
        pulseGlow: { '0%,100%': { opacity: 1 }, '50%': { opacity: 0.5 } },
        floatUp: { '0%': { opacity: 0, transform: 'translateY(6px)' }, '100%': { opacity: 1, transform: 'translateY(0)' } },
        auroraDriftA: {
          '0%, 100%': { transform: 'translate(-6%, -4%) scale(1)' },
          '50%': { transform: 'translate(4%, 6%) scale(1.15)' },
        },
        auroraDriftB: {
          '0%, 100%': { transform: 'translate(5%, 3%) scale(1.05)' },
          '50%': { transform: 'translate(-5%, -6%) scale(0.95)' },
        },
        gridPan: {
          '0%': { backgroundPosition: '0 0' },
          '100%': { backgroundPosition: '34px 34px' },
        },
        sheenSweep: {
          '0%': { backgroundPosition: '-150% 0' },
          '100%': { backgroundPosition: '250% 0' },
        },
        radarSweep: {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' },
        },
      },
      animation: {
        'pulse-glow': 'pulseGlow 1.8s ease-in-out infinite',
        'float-up': 'floatUp 0.4s ease-out both',
        'aurora-a': 'auroraDriftA 22s ease-in-out infinite',
        'aurora-b': 'auroraDriftB 26s ease-in-out infinite',
        'grid-pan': 'gridPan 6s linear infinite',
        'sheen-sweep': 'sheenSweep 2.6s ease-in-out infinite',
        'radar-sweep': 'radarSweep 1.6s linear infinite',
      },
    },
  },
  plugins: [],
}
