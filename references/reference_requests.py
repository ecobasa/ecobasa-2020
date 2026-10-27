"""Reference requests: after a match, both sides are asked by email for a reference, framed
for them as their story. They answer on a small form (no login, the link carries the key)
or by replying to the email, with a photo if they like. Shared ones can be featured."""

import io
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.core.files.base import ContentFile
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from PIL import Image, ImageOps, UnidentifiedImageError

from matches.models import Match

from .models import Reference, ReferenceSkill, ReferenceRequest, match_gift_names, match_reference_subject, subject_owner
from .notifications import notify_reference_created

# How long the link in a story email keeps working
LINK_MAX_AGE = timedelta(days=60)
PHOTO_MAX_SIZE = (1600, 1600)
# Replies are cut here: everything below is the quoted email
REPLY_MARKER = "## ecobasa: write above this line ##"


def exchange_dates(match):
    """(start, end) of what happened: the stay, or the agreed date (a counter-proposal's if
    that is what was accepted) with no end. (None, None) if there was no date."""
    try:
        details = match.volunteer_details
    except ObjectDoesNotExist:
        details = None
    if details and details.stay_to:
        if not details.stay_from:
            return details.stay_to, None
        return details.stay_from, details.stay_to
    counter = match.thread.filter(status_to=Match.STATUS_COUNTER).exclude(counter_date=None).last()
    return (counter.counter_date if counter else match.proposed_date), None


def reference_due_at(match):
    """When to ask for the reference: after the stay ended or the agreed date, or a while
    after acceptance if there was no date."""
    start, end = exchange_dates(match)
    if end or start:
        return (end or start) + timedelta(days=settings.REFERENCE_REQUEST_DELAY_DAYS)
    if match.responded_at:
        return match.responded_at + timedelta(days=settings.REFERENCE_REQUEST_UNDATED_DELAY_DAYS)
    return None


def exchange_text(match, user):
    """What the reference is for, from `user`'s side, in the active language — they may
    have had several exchanges with the same person."""
    target = match.target
    is_requester = user == match.from_user
    subject, _gift, _skill = match_reference_subject(match, user)
    model = match.content_type.model
    if model == "community":
        text = _("Your stay at %(title)s") if is_requester else _("%(name)s's stay at %(title)s")
    elif model == "project":
        text = _("Your help with %(title)s at %(name)s") if is_requester else _("%(name)s's help with %(title)s")
    elif model == "listing":
        # On an offer the owner gives; on a wish whoever answered it does
        gave = (target.type == "wish") == is_requester
        text = _("%(title)s, your gift to %(name)s") if gave else _("%(title)s, a gift from %(name)s")
    elif model == "skillwish":
        text = _("Your help with %(title)s for %(name)s") if is_requester else _("%(name)s's help with %(title)s")
    elif hasattr(target, "get_skill_holder"):
        text = _("Learning %(title)s with %(name)s") if is_requester else _("Sharing %(title)s with %(name)s")
    else:
        text = "%(title)s"
    return text % {"title": target.get_match_display_name(), "name": subject_name(subject)}


def exchange_context(match, user):
    """Template context reminding `user` of the exchange: what, when, and the request."""
    start, end = exchange_dates(match)
    return {
        "exchange": exchange_text(match, user),
        "exchange_start": start,
        "exchange_end": end,
        "match_message": match.message,
        # Who sent the request: None if it was them
        "match_message_author": None if user == match.from_user else (match.from_user.name or match.from_user.email),
    }


def send_reference_requests(now=None):
    """Email both sides of every accepted match whose reference is due and who weren't asked
    yet. Returns how many emails were sent."""
    now = now or timezone.now()
    oldest = now - timedelta(days=settings.REFERENCE_REQUEST_MAX_AGE_DAYS)
    sent = 0
    matches = (
        Match.objects.filter(status=Match.STATUS_ACCEPTED)
        .select_related("content_type", "from_user", "recipient")
        .prefetch_related("target", "reference_requests", "references")
    )
    for match in matches:
        due = reference_due_at(match)
        if due is None or not oldest <= due <= now:
            continue
        asked = {r.user_id for r in match.reference_requests.all()}
        written = {r.author_id for r in match.references.all()}
        for user in (match.from_user, match.recipient):
            if user is None or not user.email or user.pk in asked or user.pk in written:
                continue
            if match_reference_subject(match, user) is None:
                continue
            reference_request = ReferenceRequest.objects.create(match=match, user=user)
            send_reference_request_email(reference_request)
            sent += 1
    return sent


def find_reference_request(key):
    """The reference request for a key, unless its link has expired or the match is gone."""
    reference_request = (
        ReferenceRequest.objects.select_related("match", "user", "reference").filter(key=key).first()
    )
    if reference_request is None or reference_request.sent_at < timezone.now() - LINK_MAX_AGE:
        return None
    if match_reference_subject(reference_request.match, reference_request.user) is None:
        return None
    return reference_request


def existing_reference(reference_request):
    """The reference the user already wrote about this match's subject, if any: the request
    form edits it rather than adding a second one (one reference per subject)."""
    subject, _gift, _skill = match_reference_subject(reference_request.match, reference_request.user)
    return Reference.objects.filter(
        author=reference_request.user,
        content_type=ContentType.objects.get_for_model(subject),
        object_id=str(subject.pk),
    ).first()


def save_requested_reference(reference_request, *, text, impression=Reference.IMPRESSION_POSITIVE, photo=None,
               share_publicly=None, http_request=None):
    """Save the answer as the user's reference about the match's subject. `photo` is a
    ContentFile from shrink_photo(). `share_publicly` None keeps what was set before."""
    match, user = reference_request.match, reference_request.user
    subject, gift, skill = match_reference_subject(match, user)
    holder = subject_owner(subject)
    if holder == user:
        return None
    reference = existing_reference(reference_request) or Reference(author=user)
    created = reference.pk is None
    reference.subject = subject
    reference.recipient = holder
    reference.match = match
    reference.text = text
    reference.impression = impression
    if share_publicly is not None:
        reference.share_publicly = share_publicly
    if photo is not None:
        reference.photo.save(photo.name, photo, save=False)
    for name in [gift, *match_gift_names(match, user)]:
        if name and name not in reference.gift_names:
            reference.gift_names = [*reference.gift_names, name]
    reference.save()

    if skill and hasattr(subject, "add_skill"):
        from skills.models import get_or_create_skill

        skill_obj = get_or_create_skill(name=skill)[0]
        if not reference.skill_tags.filter(skill=skill_obj).exists():
            status = ReferenceSkill.STATUS_CONFIRMED if subject.has_skill(skill_obj) else ReferenceSkill.STATUS_PENDING
            ReferenceSkill.objects.create(reference=reference, skill=skill_obj, status=status)

    reference_request.reference = reference
    reference_request.save(update_fields=["reference"])
    if created:
        notify_reference_created(reference, http_request=http_request, base_url=settings.SITE_URL)
    return reference


def shrink_photo(file):
    """A phone photo as a JPEG of at most PHOTO_MAX_SIZE, turned upright. Raises
    ValueError if it isn't an image."""
    try:
        image = Image.open(file)
        image = ImageOps.exif_transpose(image)
    except (UnidentifiedImageError, OSError) as error:
        raise ValueError("not an image") from error
    image.thumbnail(PHOTO_MAX_SIZE)
    if image.mode != "RGB":
        image = image.convert("RGB")
    out = io.BytesIO()
    image.save(out, "JPEG", quality=85, optimize=True)
    return ContentFile(out.getvalue(), name=f"{uuid.uuid4().hex}.jpg")


# ── Emails ──────────────────────────────────────────────────────────────────────

def reply_address(reference_request):
    """<mailbox>+<key>@domain, or "" when replying by email isn't set up."""
    address = settings.REFERENCE_REPLY_ADDRESS
    if not address or "@" not in address:
        return ""
    local, domain = address.split("@", 1)
    return f"{local}+{reference_request.key}@{domain}"


def _request_url(reference_request, query=""):
    return settings.SITE_URL.rstrip("/") + reverse("references:request", args=[reference_request.key]) + query


def subject_name(subject):
    if hasattr(subject, "get_match_display_name"):
        return subject.get_match_display_name()
    return subject.name or subject.email


def _send(reference_request, template_base, subject_line, extra_context):
    user = reference_request.user
    subject, _gift, _skill = match_reference_subject(reference_request.match, user)
    reply_to = reply_address(reference_request)
    context = {
        "recipient": user,
        "headline": subject_line,
        "subject_name": subject_name(subject),
        **exchange_context(reference_request.match, user),
        "request_url": _request_url(reference_request),
        "can_reply": bool(reply_to),
        "reply_marker": REPLY_MARKER,
        **extra_context,
    }
    text_body = render_to_string(f"{template_base}.txt", context)
    html_body = render_to_string(f"{template_base}.html", context)
    msg = EmailMultiAlternatives(
        # The key in the subject finds the story again when the reply address lost it
        subject=f"{subject_line} [#{reference_request.key}]",
        body=text_body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[user.email],
        reply_to=[reply_to] if reply_to else None,
    )
    msg.attach_alternative(html_body, "text/html")
    msg.send(fail_silently=True)


def send_reference_request_email(reference_request):
    user = reference_request.user
    with translation.override(user.language or settings.LANGUAGE_CODE):
        headline = _("%(exchange)s: how was it?") % {
            "exchange": exchange_text(reference_request.match, user),
        }
        _send(reference_request, "references/email/reference_request", headline, {})


def send_reference_received_email(reference_request):
    """After a reference came in by email: thanks, and a link to add a photo or allow sharing
    it, which a reply can't ask for."""
    user = reference_request.user
    with translation.override(user.language or settings.LANGUAGE_CODE):
        headline = _("Thank you for your story")
        _send(reference_request, "references/email/reference_received", headline, {
            "reference": reference_request.reference,
            "share_url": _request_url(reference_request, "?share=1"),
        })
