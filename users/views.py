from django.contrib.auth import views as django_views
from django.utils.translation import gettext_lazy as _
from django.http import QueryDict
from django.shortcuts import redirect, reverse, render
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth import logout as auth_logout, login as auth_login, authenticate
from django.views.generic.detail import DetailView
from .models import User

from .forms import RegisterForm, LoginForm


class LoginView(django_views.LoginView):
    template_name = "users/login.html"
    form_class = LoginForm

class DetailView(DetailView):
    model = User
    template_name = "users/detail.html"
    slug_field = "username"
    slug_url_kwarg = "slug"


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
        data = request.POST
        # allow legacy payloads with first_name/last_name by mapping to name
        if not data.get("name") and (data.get("first_name") or data.get("last_name")):
            mutable = QueryDict(mutable=True)
            mutable.update(data)
            full_name = " ".join(filter(None, [data.get("first_name"), data.get("last_name")])).strip()
            mutable["name"] = full_name
            data = mutable
        form = RegisterForm(data, request.FILES)
        if form.is_valid():
            form.save()
            email = form.cleaned_data.get("email")
            name = form.cleaned_data.get("name")
            image = form.cleaned_data.get("image")
            raw_password = form.cleaned_data.get("password")
            user = authenticate(username=email, password=raw_password)
            auth_login(request, user)
            messages.success(request, _("Account created and logged in."))
            return redirect("homepage:homepage")
    else:
        form = RegisterForm()
    return render(request, "users/register.html", {"form": form})


class PasswordResetView(django_views.PasswordResetView):
    email_template_name = "users/password_reset/email.html"
    template_name = "users/password_reset/form.html"
    success_url = reverse_lazy("users:password_reset_done")


class PasswordResetDoneView(django_views.PasswordResetDoneView):
    template_name = "users/password_reset/done.html"


class PasswordResetConfirmView(django_views.PasswordResetConfirmView):
    success_url = reverse_lazy("users:password_reset_complete")
    template_name = "users/password_reset/confirm.html"


class PasswordResetCompleteView(django_views.PasswordResetCompleteView):
    template_name = "users/password_reset/complete.html"

