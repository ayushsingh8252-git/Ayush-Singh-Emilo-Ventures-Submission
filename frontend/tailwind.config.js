/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['Fraunces', 'Georgia', 'serif'],
        sans: ['Inter', 'system-ui', 'sans-serif'],
      },
      colors: {
        ivory: '#FBF8F3',
        sand: { 50: '#F6F1E9', 100: '#EFE7DA', 200: '#E3D6C2', 300: '#CDB99B' },
        ink: { 900: '#1F1B16', 700: '#3D362E', 500: '#6B6157', 400: '#8C8177' },
        clay: { 50: '#FBEFE9', 100: '#F6DCCF', 500: '#C2643C', 600: '#A8522E', 700: '#8A4225' },
        sage: { 50: '#EEF3EC', 600: '#4F6F4A' },
      },
      boxShadow: {
        soft: '0 1px 2px rgba(31,27,22,0.04), 0 8px 24px -12px rgba(31,27,22,0.12)',
        lift: '0 2px 4px rgba(31,27,22,0.05), 0 22px 40px -18px rgba(31,27,22,0.28)',
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
