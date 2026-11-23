"""Keeping bots out of public forms (contact, signup), all on our own server: a trap
field, a signed single-use challenge the browser has to work on for about a second
(static/js/bot-check.js), a minimum time to fill in, and limits per address. The form
renders its part with {% bot_check %}; the view calls check() and, once it goes through,
record(). Only keyed hashes are stored, never addresses or what was written."""

import hashlib
import ipaddress
import re
import secrets
from dataclasses import dataclass
from datetime import timedelta

from django.core import signing
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext_lazy as _

SALT = "bot-check"
# Leading zero bits of sha256(challenge:nonce): about 130,000 tries, under a second in a browser
DIFFICULTY = 17
MIN_SECONDS = 4
MAX_AGE = timedelta(hours=3)
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


def entries(form):
    from homepage.models import BotCheckEntry

    return BotCheckEntry.objects.filter(form=form)


@dataclass
class Check:
    trapped: bool = False
    error: str = ""


def check(request, form, limits, challenge_needed=True):
    """Whether this POST may go through. `limits`: [(at most, within)] per address.
    A bot in the trap gets `trapped`, so the view can pretend it worked."""
    data = request.POST
    if challenge_needed:
        if data.get("website"):
            return Check(trapped=True)
        value, age = data.get("challenge", ""), challenge_age(data.get("challenge", ""))
        if age is None or age < MIN_SECONDS or not solved(value, data.get("nonce", "")) or (
            entries(form).filter(token_digest=digest(value)).exists()
        ):
            return Check(error=_("That didn't work. Please send it again."))
    now = timezone.now()
    mine = entries(form).filter(ip_digest=digest(client_address(request)))
    if any(mine.filter(created_at__gte=now - span).count() >= most for most, span in limits):
        return Check(error=_("Too many tries from your connection. Please try again tomorrow."))
    return Check()


def record(request, form, challenge_needed=True, **fields):
    """Counts it towards the limits; raises IntegrityError if its challenge was used
    already (the same form sent twice at once)."""
    from homepage.models import BotCheckEntry

    BotCheckEntry.objects.filter(created_at__lt=timezone.now() - KEEP).delete()
    return BotCheckEntry.objects.create(
        form=form,
        ip_digest=digest(client_address(request)),
        token_digest=digest(request.POST.get("challenge", "")) if challenge_needed else None,
        **fields,
    )
