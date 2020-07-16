module.exports = {
  purge: [
    './templates/**/*.html',
    '**/templates/**/*.html',
    "./**/*.py",
    "./**/*.js"
  ],
  theme: {
    // https://github.com/tailwindcss/custom-forms/blob/master/src/defaultOptions.js
    customForms: theme => ({
      default: {
        checkbox: {
          color: theme('colors.orange.500'),
        },
        radio: {
          color: theme('colors.orange.500'),
        },
      },
    }),
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
  plugins: [require('@tailwindcss/ui')]
}
