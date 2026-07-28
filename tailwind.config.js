module.exports = {
  content: [
    './templates/**/*.html',
    './**/templates/**/*.html',
    './**/*.py',
    './static_src/**/*.{js,css}',
    './static/**/*.{js,css}',
  ],
  theme: {
    fontFamily: {
      sans: ['Lato', 'sans-serif'],
      serif: ['Bree Serif', 'serif'],
    },
    extend: {
      colors: {
        primary: '#da6137',
        brown: '#452912',
        secondary: '#fcf3e5',
        third: '#b4502c',
        yellow: '#de7a08',
        orange: '#ff7800',
        red: '#e34a26',
        dark_brown: '#0e0700',
        purple: '#80143b',
        green: '#5A5527',
      },
    },
  },
  plugins: [require('@tailwindcss/forms')],
}
