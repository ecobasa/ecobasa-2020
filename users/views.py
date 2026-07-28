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

        # Try username match first (legacy behavior)
        try:
            return queryset.get(username=slug)
        except self.model.DoesNotExist:
            pass

        # Try matching slugified name
        try:
            return queryset.get(name__isnull=False, name__iexact=slug.replace("-", " "))
        except self.model.DoesNotExist:
            pass

        # Fallback to primary key for users without a username
        try:
            return queryset.get(pk=slug)
        except (self.model.DoesNotExist, ValueError, TypeError):
            pass

        raise Http404("No user found matching the query")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        # Provide the user's gifting ads (if any) to the template
        try:
            user = self.get_object()
            ctx["ads"] = user.ads.all()
        except Exception:
            ctx["ads"] = []
        return ctx


def logout(request):
    """Logout user on POST requests only (more secure)"""
    if request.method == "POST":
        auth_logout(request)
        messages.success(request, _("You have been logged out."))
    return redirect(reverse("homepage:homepage"))


@require_GET
def autocomplete(request):
    """Simple user autocomplete for recipients (returns JSON)."""
    q = request.GET.get("q", "").strip()
    results = []
    if q:
        # Match by username or email (helps when users type an email address)
        qs = User.objects.filter(Q(username__istartswith=q) | Q(email__istartswith=q)).order_by('username', 'email')[:20]
        for u in qs:
            # return the user's email as the canonical value (matches USERNAME_FIELD)
            results.append({"value": u.email, "name": u.name or u.username, "username": u.username})
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

