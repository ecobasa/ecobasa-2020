from django.contrib.auth.views import LoginView as DjangoLoginView
from django.utils.translation import gettext_lazy as _
from django.shortcuts import redirect, reverse
from django.contrib import messages
from django.contrib.auth import logout as auth_logout


class LoginView(DjangoLoginView):
    template_name = "users/login.html"


def logout(request):
    """Logout user on POST requests (more secure)"""
    if request.method == "POST":
        auth_logout(request)
        messages.success(request, _("You have been logged out."))
    return redirect(reverse("homepage:homepage"))
