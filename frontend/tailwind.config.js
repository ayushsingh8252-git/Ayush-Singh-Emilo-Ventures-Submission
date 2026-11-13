/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      // Black-and-white theme: every token is a neutral grey. The accent ("clay")
      // and positive ("sage") roles are carried by black and by weight, not hue.
      colors: {
        ivory: '#FFFFFF',
        sand: { 50: '#F5F5F5', 100: '#EBEBEB', 200: '#DEDEDE', 300: '#C2C2C2' },
        ink: { 900: '#0A0A0A', 700: '#2E2E2E', 500: '#595959', 400: '#737373' },
        clay: { 50: '#F2F2F2', 100: '#E3E3E3', 500: '#1A1A1A', 600: '#000000', 700: '#000000' },
        sage: { 50: '#EDEDED', 600: '#1A1A1A' },
      },
      boxShadow: {
        soft: '0 1px 2px rgba(0,0,0,0.04), 0 8px 24px -12px rgba(0,0,0,0.12)',
        lift: '0 2px 4px rgba(0,0,0,0.05), 0 22px 40px -18px rgba(0,0,0,0.28)',
      },
      keyframes: {
        rise: { '0%': { opacity: 0, transform: 'translateY(8px)' }, '100%': { opacity: 1, transform: 'none' } },
        fade: { '0%': { opacity: 0 }, '100%': { opacity: 1 } },
      },
      animation: { rise: 'rise 0.45s ease-out both', fade: 'fade 0.2s ease-out both' },
    },
  },
  plugins: [],
}
