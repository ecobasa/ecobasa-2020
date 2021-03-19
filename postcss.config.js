module.exports = (ctx) => ({
    map: ctx.env === 'development' ? ctx.map : false,
    plugins: {
        "postcss-import": {},
        "tailwindcss": {},
        "autoprefixer": {},
        "postcss-nested":{},
        "cssnano": ctx.env === 'production' ? {} : false
    }
})
