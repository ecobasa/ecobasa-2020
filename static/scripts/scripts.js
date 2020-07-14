document.querySelectorAll('.js-submit-on-input').forEach(function (form) {
    form.querySelectorAll('select, [type=checkbox]').forEach(function (input) {
        input.addEventListener('change', function () {
            form.submit();
        })

    })
})