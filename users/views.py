from django.contrib.auth.views import LoginView as DjangoLoginView
from django.utils.translation import gettext_lazy as _
from django.shortcuts import redirect, reverse, render
from django.contrib import messages
from django.contrib.auth import logout as auth_logout, login as auth_login, authenticate

from .forms import RegisterForm, LoginForm


class LoginView(DjangoLoginView):
    template_name = "users/login.html"
    form_class = LoginForm


def logout(request):
    """Logout user on POST requests only (more secure)"""
    if request.method == "POST":
        auth_logout(request)
        messages.success(request, _("You have been logged out."))
    return redirect(reverse("homepage:homepage"))


def register(request):
    """register a new user"""
    if request.user.is_authenticated:
        return redirect(reverse("homepage:homepage"))
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            form.save()
            email = form.cleaned_data.get("email")
            raw_password = form.cleaned_data.get("password")
            user = authenticate(username=email, password=raw_password)
            auth_login(request, user)
            messages.success(request, _("Account created and logged in."))
            return redirect("homepage:homepage")
    else:
        form = RegisterForm()
    return render(request, "users/register.html", {"form": form})
