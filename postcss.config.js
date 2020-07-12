module.exports = (ctx) => ({
    map: ctx.env === 'development' ? ctx.map : false,
    plugins: {
        "postcss-import": {},
        "tailwindcss": {},
        "autoprefixer": ctx.env === 'production' ? {} : false,
        "cssnano": ctx.env === 'production' ? {} : false
    }
})
