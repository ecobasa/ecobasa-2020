"""The contact form and its spam protection, all on our own server: a trap field, a
signed single-use challenge the browser has to work on for about a second, a minimum
time to fill in, limits per address, sender and text, and few links. No confirmation
goes to the sender, so the form can't be used to mail strangers."""

import hashlib
import ipaddress
import re
import secrets
from datetime import timedelta

from django import forms
from django.conf import settings
from django.core import signing
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.translation import get_language, gettext_lazy as _

from .models import ContactSubmission

SALT = "homepage.contact"
# Leading zero bits of sha256(challenge:nonce): about 130,000 tries, a second or two in a browser
DIFFICULTY = 17
MIN_SECONDS = 4
MAX_AGE = timedelta(hours=3)
MAX_LINKS = 2
# (rows that count, over how long)
PER_ADDRESS = [(3, timedelta(hours=1)), (8, timedelta(days=1))]
PER_SENDER = [(3, timedelta(days=1))]
SAME_TEXT = timedelta(days=7)
KEEP = timedelta(days=8)

LINK = re.compile(r"https?://|www\.|\[url|<a\s|\]\(", re.IGNORECASE)


def challenge():
    return signing.TimestampSigner(salt=SALT).sign(secrets.token_hex(16))


def challenge_age(value):
    """Seconds since the challenge was made, or None if it isn't ours or too old."""
    signer = signing.TimestampSigner(salt=SALT)
    try:
        signer.unsign(value, max_age=MAX_AGE)
    except signing.BadSignature:
        return None
    issued = signing.b62_decode(value.split(signer.sep)[-2])
    return timezone.now().timestamp() - issued


def solved(value, nonce):
    if not nonce.isdigit() or len(nonce) > 12:
        return False
    digest = hashlib.sha256(f"{value}:{nonce}".encode()).digest()
    return int.from_bytes(digest, "big") >> (256 - DIFFICULTY) == 0


def client_address(request):
    """nginx appends the address it saw; earlier entries can be made up by the client.
    IPv6 by its /64, which one connection usually gets whole."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    address = forwarded.split(",")[-1].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if ip.version == 6:
        return str(ipaddress.ip_network(f"{ip}/64", strict=False))
    return str(ip)


def digest(value):
    return salted_hmac(SALT, value).hexdigest()


def text_digest(text):
    return digest(re.sub(r"\W+", "", text.lower()))


class ContactForm(forms.Form):
    name = forms.CharField(label=_("Name"), max_length=80)
    email = forms.EmailField(label=_("Email"))
    message = forms.CharField(label=_("Message"), min_length=15, max_length=4000, widget=forms.Textarea(attrs={"rows": 8}))
    # The trap: hidden from people, filled in by bots
    website = forms.CharField(required=False)
    challenge = forms.CharField(required=False, widget=forms.HiddenInput)
    nonce = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, *args, request, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.member = request.user if request.user.is_authenticated else None
        self.trapped = False
        if self.member:
            for name in ("name", "email", "website", "challenge", "nonce"):
                del self.fields[name]

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if LINK.search(name):
            raise forms.ValidationError(_("Please leave links out of your name."))
        return name

    def clean_message(self):
        message = self.cleaned_data["message"].strip()
        if len(LINK.findall(message)) > MAX_LINKS:
            raise forms.ValidationError(_("Please send at most two links."))
        return message

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        if not self.member:
            if data["website"]:
                self.trapped = True
                return data
            age = challenge_age(data["challenge"])
            if age is None or age < MIN_SECONDS or not solved(data["challenge"], data["nonce"]) or (
                ContactSubmission.objects.filter(token_digest=digest(data["challenge"])).exists()
            ):
                raise forms.ValidationError(_("That didn't work. Please send your message again."))
        email = self.sender()[1]
        now = timezone.now()
        rows = ContactSubmission.objects.all()
        limits = [(rows.filter(ip_digest=digest(client_address(self.request))), PER_ADDRESS),
                  (rows.filter(email_digest=digest(email.lower())), PER_SENDER)]
        if any(found.filter(created_at__gte=now - span).count() >= most for found, spans in limits for most, span in spans):
            raise forms.ValidationError(_("You have sent us several messages already. Please try again tomorrow."))
        if rows.filter(text_digest=text_digest(data["message"]), created_at__gte=now - SAME_TEXT).exists():
            raise forms.ValidationError(_("We have received this message already."))
        return data

    def sender(self):
        if self.member:
            return self.member.name or self.member.email, self.member.email
        return self.cleaned_data["name"], self.cleaned_data["email"]

    def send(self):
        """Sends it to us, unless it was a bot in the trap. False if the mail server failed."""
        if self.trapped:
            return True
        name, email = self.sender()
        message = self.cleaned_data["message"]
        lines = [f"{name} <{email}> wrote through the contact page."]
        if self.member:
            lines.append(f"Member: {self.request.build_absolute_uri(self.member.get_absolute_url())}")
        lines += [f"Language: {get_language()}", "", message]
        mail = EmailMessage(
            subject=" ".join(f"Contact: {name}".split())[:120],
            body="\n".join(lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.CONTACT_EMAIL],
            reply_to=[email],
        )
        ContactSubmission.objects.filter(created_at__lt=timezone.now() - KEEP).delete()
        try:
            with transaction.atomic():
                ContactSubmission.objects.create(
                    ip_digest=digest(client_address(self.request)),
                    email_digest=digest(email.lower()),
                    text_digest=text_digest(message),
                    token_digest=None if self.member else digest(self.cleaned_data["challenge"]),
                )
                mail.send()
        except IntegrityError:
            # The same challenge twice at once: the first one is on its way
            return True
        except OSError:
            return False
        return True
