from django.contrib.auth import views as django_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.translation import gettext_lazy as _
from django.http import QueryDict
from django.shortcuts import redirect, reverse, render
from django.http import Http404
from django.urls import reverse_lazy
from django.contrib import messages
from django.contrib.auth import logout as auth_logout, login as auth_login, authenticate
from django.views.generic.detail import DetailView
from gift_economy.gifts.models import Listing
from .models import User
from .places import approximate, town

from .emails import read_email_change_token, send_email_change_link, send_email_changed_notice
from .forms import RegisterForm, LoginForm, ProfileUpdateForm, EmailChangeForm
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from django.db.models import Q


class LoginView(django_views.LoginView):
    template_name = "users/login.html"
    form_class = LoginForm

class DetailView(LoginRequiredMixin, DetailView):
    """A person's profile, for members only: visitors sign up to meet people, so that
    contact goes through the platform (and can get references)."""
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
            # Their skills and skill wishes as pills, everything else as cards
            listings = list(Listing.objects.of(user).current().select_related("skill"))
            with_skill = sorted((l for l in listings if l.skill_id), key=lambda l: l.display_title)
            ctx["listings"] = [l for l in listings if not l.skill_id]
            ctx["communities"] = user.member_communities_qs().prefetch_related("photos").order_by("name")
            ctx["user_skills"] = [l for l in with_skill if l.is_offer]
            ctx["skill_wishes"] = [l for l in with_skill if l.is_wish]
            # Others see only about where they live (users.places)
            own = ctx["own_place"] = user == self.request.user
            ctx["place_name"] = user.location_name if own else town(user.location_name)
            ctx["place_point"] = user.location if own else approximate(user.location, user.pk)
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


@login_required
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


def _next_url(request):
    """Where to go once registered: a page on this site they came from (e.g. an
    invitation's link), else the homepage."""
    from django.utils.http import url_has_allowed_host_and_scheme

    url = request.POST.get("next") or request.GET.get("next") or ""
    if url and url_has_allowed_host_and_scheme(url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return url
    return reverse("homepage:homepage")


def register(request):
    """register a new user"""
    if request.user.is_authenticated:
        return redirect(_next_url(request))
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
            return redirect(_next_url(request))
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

    def post(self, request, *args, **kwargs):
        # The account section is a form of its own, below the profile form
        if "new_email" not in request.POST:
            return super().post(request, *args, **kwargs)
        email_form = EmailChangeForm(request.POST, user=request.user)
        if not email_form.is_valid():
            return self.render_to_response(self.get_context_data(
                form=self.form_class(instance=request.user), email_form=email_form,
            ))
        new_email = email_form.cleaned_data["new_email"]
        send_email_change_link(request.user, new_email, request)
        messages.success(request, _("We sent a link to %(email)s. Your email address changes once you open it.") % {"email": new_email})
        return redirect(reverse("users:update") + "#account")

    def form_valid(self, form):
        self.object = form.save()
        # Whether their offers and skills show on each of their communities' pages, and
        # (for those they came to on a visit) that they found it through ecobasa
        for field in ("shows_offers", "shows_visit"):
            chosen = set(self.request.POST.getlist(field))
            for membership in self._memberships():
                if field == "shows_visit" and not membership.visit_id:
                    continue
                if getattr(membership, field) != (str(membership.pk) in chosen):
                    setattr(membership, field, not getattr(membership, field))
                    membership.save(update_fields=[field])
        return redirect(self.get_success_url())

    def _memberships(self):
        return self.request.user.memberships.counted().select_related("community")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["user_obj"] = self.request.user
        ctx["memberships"] = self._memberships()
        ctx.setdefault("email_form", EmailChangeForm(user=self.request.user))
        return ctx

    def get_success_url(self):
        return self.object.get_absolute_url() if hasattr(self, "object") else self.request.user.get_absolute_url()


def confirm_email(request, token):
    """The link sent to a new email address: changing it takes a click on the page, so
    mail programs that open links to check them don't change it."""
    data = read_email_change_token(token)
    user = User.objects.filter(pk=data[0]).first() if data else None
    old_email, new_email = data[1:] if data else ("", "")
    taken = User.objects.filter(email__iexact=new_email).exclude(pk=user.pk).exists() if user else False
    if user is None or user.email != old_email or taken:
        messages.error(request, _("This link doesn't work any more. You can ask for a new one on your profile page."))
        return redirect(reverse("users:update") if request.user.is_authenticated else reverse("users:login"))
    if request.method == "POST":
        user.email = new_email
        user.save(update_fields=["email"])
        send_email_changed_notice(user, old_email)
        messages.success(request, _("Your email address is now %(email)s. Use it to log in.") % {"email": new_email})
        return redirect(user.get_absolute_url() if request.user == user else reverse("users:login"))
    return render(request, "users/confirm_email.html", {"old_email": old_email, "new_email": new_email})


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
