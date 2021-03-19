module.exports = {
  purge: [
    './templates/**/*.html',
    '**/templates/**/*.html',
    "./**/*.py",
    "./**/*.js"
  ],
  theme: {

    fontFamily: {
      sans: ["Lato", "sans-serif"],
      serif: ["Bree Serif", "serif"]
    },
    // https://github.com/tailwindcss/custom-forms/blob/master/src/defaultOptions.js
    customForms: theme => ({
      default: {
        input: {
          '&:focus': {
            boxShadow: "0 0 0 3px rgba(218, 97, 55)",
            borderColor: theme('color.primary'),
          },
        },
        checkbox: {
          '&:focus': {
            boxShadow: "0 0 0 3px rgba(218, 97, 55)",
            borderColor: theme('color.primary'),
          },
          color: theme('colors.primary'),
        },
        radio: {
          '&:focus': {
            boxShadow: "0 0 0 3px rgba(218, 97, 55)",
            borderColor: theme('color.primary'),
          },
          color: theme('colors.primary'),
        },
      },
    }),
    extend: {
      colors: {
        "primary": "#da6137",
        "brown": "#452912",
        "secondary" : "#fcf3e5",
        "third" : "#b4502c",
        "yellow" : "#de7a08",
        "orange" : "#ff7800",
        "red" : "#e34a26",
        "brown" : "#452912",
        "dark-brown" : "#0e0700",
        "purple" : "#80143b",
        "green" : "#5A5527"
      },
    },
  },
  variants: {},
  plugins: [require('@tailwindcss/ui')]
}
