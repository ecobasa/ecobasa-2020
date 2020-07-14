module.exports = {
  purge: [
    './templates/**/*.html',
    '**/templates/**/*.html',
    "./**/*.py",
    "./**/*.js"
  ],
  theme: {
    customForms: function (theme) {
      return ({

      })
    },
    extend: {
      fontFamily: {
        "bree": ["Bree Serif", "serif"]
      },
      color: {
        "orange-500": "#da6136"
      },
      boxShadow: {
        outline: '0 0 0 3px #da6136',
      }
    },
  },
  variants: {},
  plugins: [require("@tailwindcss/custom-forms")],
}
