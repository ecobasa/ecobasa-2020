from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _

EMAIL_CHANGE_SALT = "users-email-change"
EMAIL_CHANGE_MAX_AGE = 60 * 60 * 24 * 3  # 3 days
SIGNUP_SALT = "users-signup-confirm"
SIGNUP_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def make_email_change_token(user, new_email):
    """The link only works while their address is still the one they asked from."""
    return signing.dumps({"user": user.pk, "old": user.email, "new": new_email}, salt=EMAIL_CHANGE_SALT)


def read_email_change_token(token):
    """(user pk, old email, new email), or None for a broken or old link."""
    try:
        data = signing.loads(token, salt=EMAIL_CHANGE_SALT, max_age=EMAIL_CHANGE_MAX_AGE)
    except signing.BadSignature:
        return None
    return data.get("user"), data.get("old", ""), data.get("new", "")


def make_signup_token(user):
    return signing.dumps({"user": user.pk, "email": user.email}, salt=SIGNUP_SALT)


def read_signup_token(token):
    """(user pk, email), or None for a broken or old link."""
    try:
        data = signing.loads(token, salt=SIGNUP_SALT, max_age=SIGNUP_MAX_AGE)
    except signing.BadSignature:
        return None
    return data.get("user"), data.get("email", "")


def _send(user, to, headline, paragraphs, button_url="", button_label=""):
    with translation.override(user.language or settings.LANGUAGE_CODE):
        context = {
            "user": user, "headline": headline, "paragraphs": [str(p) for p in paragraphs],
            "button_url": button_url, "button_label": str(button_label),
        }
        text_body = render_to_string("users/email/account.txt", context)
        html_body = render_to_string("users/email/account.html", context)
    message = EmailMultiAlternatives(subject=headline, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[to])
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=True)


def send_email_change_link(user, new_email, http_request):
    """To the new address: the link that makes it theirs."""
    path = reverse("users:confirm_email", args=[make_email_change_token(user, new_email)])
    with translation.override(user.language or settings.LANGUAGE_CODE):
        headline = _("Confirm your new email address for ecobasa")
        paragraphs = [
            _("You'd like to use this address for ecobasa from now on. Until you confirm it, you keep logging in with %(email)s.") % {"email": user.email},
            _("The link works for 3 days. If you didn't ask for this, you can ignore this email."),
        ]
        label = _("Confirm email address")
    _send(user, new_email, headline, paragraphs, http_request.build_absolute_uri(path), label)


def send_email_changed_notice(user, old_email):
    """To the old address, once the change is done, so a change they didn't make doesn't go unnoticed."""
    with translation.override(user.language or settings.LANGUAGE_CODE):
        headline = _("Your ecobasa email address was changed")
        paragraphs = [
            _("Your ecobasa email address is now %(email)s. Use it to log in from now on.") % {"email": user.email},
            _("If you didn't change it, please answer this email right away."),
        ]
    _send(user, old_email, headline, paragraphs)


def send_signup_confirmation(user, http_request):
    """After signing up: the link that confirms their address, so they can start sharing."""
    path = reverse("users:confirm_signup", args=[make_signup_token(user)])
    with translation.override(user.language or settings.LANGUAGE_CODE):
        headline = _("Confirm your email address for ecobasa")
        paragraphs = [
            _("Welcome to ecobasa! Please confirm that this is your address. Then you can share gifts and skills, write to people and visit communities."),
            _("The link works for 7 days. If you didn't sign up, you can ignore this email."),
        ]
        label = _("Confirm email address")
    _send(user, user.email, headline, paragraphs, http_request.build_absolute_uri(path), label)
