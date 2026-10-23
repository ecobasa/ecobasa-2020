from django.contrib.auth import views as django_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext_lazy as _
from django.http import QueryDict
from django.shortcuts import redirect, reverse, render
from django.http import Http404
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth import logout as auth_logout, login as auth_login, authenticate
from django.views.generic.detail import DetailView
from .models import User

from .forms import RegisterForm, LoginForm, ProfileUpdateForm
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.db.models import Q


class LoginView(django_views.LoginView):
    template_name = "users/login.html"
    form_class = LoginForm

class DetailView(DetailView):
    model = User
    template_name = "users/detail.html"
    slug_field = "username"
    slug_url_kwarg = "slug"

    def get_object(self, queryset=None):
        slug = self.kwargs.get(self.slug_url_kwarg)
        if not slug:
            raise Http404("No user found matching the query")
        if queryset is None:
            queryset = self.get_queryset()

        user = User.objects.get_by_slug(slug)
        if user is None or not queryset.filter(pk=user.pk).exists():
            raise Http404("No user found matching the query")
        return user

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        try:
            user = self.get_object()
            ctx["listings"] = user.listings.all()
            ctx["communities"] = user.communities.order_by("name")
            ctx["user_skills"] = (
                user.user_skills.select_related("skill").order_by("skill__name")
            )
            ctx["skill_wishes"] = (
                user.skill_wishes.select_related("skill").order_by("skill__name")
            )
        except Exception:
            ctx["listings"] = []
            ctx["communities"] = []
            ctx["user_skills"] = []
            ctx["skill_wishes"] = []
        return ctx


def logout(request):
    """Logout user on POST requests only (more secure)"""
    if request.method == "POST":
        auth_logout(request)
        messages.success(request, _("You have been logged out."))
    return redirect(reverse("homepage:homepage"))


@require_GET
def autocomplete(request):
    """Simple user autocomplete for recipients (returns JSON). `value` is the user id, which
    is what postman looks recipients up by; `?id=` returns that one user (prefilled recipient)."""
    q = request.GET.get("q", "").strip()
    user_id = request.GET.get("id", "").strip()
    results = []
    if q or user_id.isdigit():
        if user_id.isdigit():
            qs = User.objects.filter(pk=user_id)
        else:
            qs = User.objects.filter(
                Q(name__icontains=q) | Q(username__istartswith=q)
            ).order_by('name')[:20]
        for u in qs:
            results.append({
                "value": str(u.pk),
                "name": u.name or u.username,
                "username": u.username,
                "image_url": u.image.url if u.image else None,
            })
    return JsonResponse(results, safe=False)


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


class UpdateView(LoginRequiredMixin, django_views.FormView):
    template_name = "users/update.html"
    form_class = ProfileUpdateForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["instance"] = self.request.user
        return kwargs

    def form_valid(self, form):
        self.object = form.save()
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["user_obj"] = self.request.user
        return ctx

    def get_success_url(self):
        return self.object.get_absolute_url() if hasattr(self, "object") else self.request.user.get_absolute_url()



def set_language(request):
    """Django's set_language (stores the choice in a cookie), plus remembering it on the
    profile so emails to this user go out in that language too."""
    from django.utils.translation import check_for_language
    from django.views.i18n import set_language as django_set_language

    response = django_set_language(request)
    code = request.POST.get("language")
    if (request.method == "POST" and request.user.is_authenticated and code
            and check_for_language(code) and request.user.language != code):
        request.user.language = code
        request.user.save(update_fields=["language"])
    return response
