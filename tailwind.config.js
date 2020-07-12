module.exports = {
  purge: [
    './templates/**/*.html',
    '**/templates/**/*.html',
    "./**/*.py",
    "./**/*.js"
  ],
  theme: {
    extend: {
      fontFamily: {
        "bree": ["Bree Serif", "serif"]
      },
      color: {
        "orange-500": "#da6136"
      }
    },
  },
  variants: {},
  plugins: [],
}
