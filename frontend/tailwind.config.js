/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        red:   { metro: '#E31E24' },
        blue:  { metro: '#007ABB' },
        green: { metro: '#009846' },
        metro: {
          dark:    '#0f172a',
          darker:  '#020617',
          surface: '#1e293b',
          border:  '#334155',
          text:    '#e2e8f0',
          muted:   '#94a3b8',
          accent:  '#38bdf8',
        },
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'pulse-fast': 'pulse 1s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
};
