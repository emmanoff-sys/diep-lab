import type { Config } from 'tailwindcss';

const config: Config = {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: '#0f1419',
        panel: '#161b22',
        edge: '#232a33',
        muted: '#8b95a1',
      },
    },
  },
  plugins: [],
};

export default config;
