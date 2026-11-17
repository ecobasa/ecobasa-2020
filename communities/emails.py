from django.conf import settings
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _

from users.models import User

FAMILY_SALT = "communities-family"
FAMILY_MAX_AGE = 60 * 60 * 24 * 90  # 90 days


def make_family_token(family, email):
    return signing.dumps({"family": family.pk, "email": email}, salt=FAMILY_SALT)


def read_family_token(token):
    """(family pk, invited email), or None for a broken or old link."""
    try:
        data = signing.loads(token, salt=FAMILY_SALT, max_age=FAMILY_MAX_AGE)
    except signing.BadSignature:
        return None
    return data.get("family"), data.get("email", "")


def send_family_invitations(family, applicant, emails, http_request):
    """Ask the people someone applies together with to send their own application: a
    link to the apply page that puts them in the same family. In their language, or for
    who isn't on ecobasa yet, in the applicant's."""
    community = family.community
    users = {user.email.lower(): user for user in User.objects.filter(email__in=emails)}
    for email in emails:
        recipient = users.get(email)
        path = reverse("communities:apply", args=[community.slug]) + "?together=" + make_family_token(family, email)
        with translation.override((recipient and recipient.language) or applicant.language or settings.LANGUAGE_CODE):
            headline = _("%(name)s would like to apply together with you to become members of %(community)s") % {
                "name": applicant.name, "community": community.name,
            }
            context = {
                "recipient": recipient, "email": email, "applicant": applicant, "community": community,
                "headline": headline, "apply_url": http_request.build_absolute_uri(path),
                "detail_url": http_request.build_absolute_uri(community.get_absolute_url()),
            }
            text_body = render_to_string("communities/email/family_invitation.txt", context)
            html_body = render_to_string("communities/email/family_invitation.html", context)
        message = EmailMultiAlternatives(subject=headline, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[email])
        message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=True)
