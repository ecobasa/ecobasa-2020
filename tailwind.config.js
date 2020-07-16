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
        input: {
          '&:focus': {
            boxShadow: "0 0 0 3px rgba(253, 186, 140, 0.45)",
            borderColor: theme('color.orange-500'),
          },
        },
        checkbox: {
          '&:focus': {
            boxShadow: "0 0 0 3px rgba(253, 186, 140, 0.45)",
            borderColor: theme('color.orange-500'),
          },
          color: theme('colors.orange.500'),
        },
        radio: {
          '&:focus': {
            boxShadow: "0 0 0 3px rgba(253, 186, 140, 0.45)",
            borderColor: theme('color.orange-500'),
          },
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
    },
  },
  variants: {},
  plugins: [require('@tailwindcss/ui')]
}
