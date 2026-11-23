from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.shortcuts import redirect
from django.utils import timezone, translation
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _


class UserLanguageMiddleware:
    """Logged-in users see the site in their saved language on every device.

    Runs after AuthenticationMiddleware (LocaleMiddleware has already picked a language
    from the cookie or browser by then) and switches to the user's saved language. On
    the way out it brings the language cookie in line, which also covers the login
    request itself, where the user only becomes known inside the view.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        language = self._saved_language(request)
        if language and language != translation.get_language():
            translation.activate(language)
            request.LANGUAGE_CODE = language

        response = self.get_response(request)

        language = self._saved_language(request)
        if language and request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME) != language:
            response.set_cookie(
                settings.LANGUAGE_COOKIE_NAME, language,
                max_age=settings.LANGUAGE_COOKIE_AGE, path=settings.LANGUAGE_COOKIE_PATH,
                domain=settings.LANGUAGE_COOKIE_DOMAIN, secure=settings.LANGUAGE_COOKIE_SECURE,
                httponly=settings.LANGUAGE_COOKIE_HTTPONLY, samesite=settings.LANGUAGE_COOKIE_SAMESITE,
            )
        return response

    @staticmethod
    def _saved_language(request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated or not user.language:
            return None
        return user.language if translation.check_for_language(user.language) else None


class LastSeenMiddleware:
    """Keeps User.last_seen up to date for "last active" on profiles and community pages.

    Writes at most once per LAST_SEEN_INTERVAL per user, with an update query so it
    doesn't touch other fields or send signals.
    """

    LAST_SEEN_INTERVAL = timedelta(minutes=10)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated:
            now = timezone.now()
            if user.last_seen is None or now - user.last_seen > self.LAST_SEEN_INTERVAL:
                get_user_model().objects.filter(pk=user.pk).update(last_seen=now)
                user.last_seen = now
        return response


class UnconfirmedEmailMiddleware:
    """Until a new account has confirmed its email address, it can look around but not
    post: no listings, messages or requests from addresses nobody reads, and from bots.
    Logging out, the language, the profile (its texts only show once confirmed), the
    contact page (as for visitors) and the confirmation itself stay open."""

    OPEN = {
        "users:logout", "set_language", "users:update", "users:confirm_email",
        "users:confirm_signup", "users:resend_confirmation", "homepage:contact",
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        user = getattr(request, "user", None)
        if (request.method in ("GET", "HEAD", "OPTIONS") or user is None or not user.is_authenticated
                or user.email_confirmed or request.resolver_match.view_name in self.OPEN):
            return None
        messages.error(request, _("Please confirm your email address first: open the link we sent to %(email)s.") % {"email": user.email})
        if request.headers.get("HX-Request"):
            response = HttpResponse(status=403)
            response["HX-Refresh"] = "true"
            return response
        back = request.META.get("HTTP_REFERER")
        if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
            back = "/"
        return redirect(back)
