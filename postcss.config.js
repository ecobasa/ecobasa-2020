module.exports = (ctx) => ({
    map: ctx.env === 'development' ? ctx.map : false,
    plugins: {
        "postcss-import": {},
        "tailwindcss": {},
        "autoprefixer": {},
        "cssnano": ctx.env === 'production' ? {} : false
    }
})
