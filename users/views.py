from django.shortcuts import render
from django.contrib.auth.views import (
    LoginView as DjangoLoginView,
    LogoutView as DjangoLogoutView,
)


class LoginView(DjangoLoginView):
    template_name = "users/login.html"


class LogoutView(DjangoLogoutView):
    pass
