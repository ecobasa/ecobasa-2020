from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.utils.translation import get_language, gettext as _, ngettext
from django.views.decorators.http import require_POST

from events import kinds
from events.models import Event
from gift_economy.matches.models import Match

from .emails import exact_place, send_guest_confirmation, send_guest_welcome
from .forms import GuestChangeForm, GuestForm
from .guests import GUEST_SESSION_KEY, link_to_account
from .models import Attendee, Guest
from .timings import timings

# Empty lines on the printed Giftsheet's front (below its heading) and back: one sheet of
# A4, both sides
GIFTSHEET_ROWS = (24, 27)

# How long before the same link goes to the same address again
MAIL_AGAIN_AFTER = timedelta(minutes=10)


def _gift_circle(slug):
    return get_object_or_404(Event.objects.select_related("community", "host_user", "host_tour"), kind=kinds.GIFT_CIRCLE, slug=slug)


def print_giftsheet(request, slug):
    """The facilitator card and an empty Giftsheet, to print. Nothing in it is private:
    the title and the day are on the gift-circle's page too."""
    event = _gift_circle(slug)
    return render(request, "gift_circles/print.html", {
        "event": event, "timings": timings(event), "pages": [range(rows) for rows in GIFTSHEET_ROWS],
    })


# ── People with an account ──────────────────────────────────────────

@login_required
@require_POST
def attendee(request, slug):
    """Who comes changes whether their offers and wishes from it stay on ecobasa."""
    event = _gift_circle(slug)
    if event.matches.filter(from_user=request.user, status=Match.STATUS_ACCEPTED).exists():
        Attendee.objects.update_or_create(
            event=event, user=request.user, defaults={"keep_on_ecobasa": bool(request.POST.get("keep_on_ecobasa"))},
        )
        messages.success(request, _("Saved."))
    return redirect(event.get_absolute_url())


# ── Guests ──────────────────────────────────────────────────────────

def _too_many(event, people, own=0):
    """Why `people` can't come (more than the free places, and the `own` places they
    have already), "" if they can."""
    free = event.free_places()
    if free is None:
        return ""
    free += own
    if people <= free:
        return ""
    return ngettext(
        "Only %(count)s more person can come.", "Only %(count)s more people can come.", free,
    ) % {"count": free}


def _mail_again(guest, send):
    """Send the guest's link again, but not right after the last one."""
    now = timezone.now()
    if guest.mailed_at and now - guest.mailed_at < MAIL_AGAIN_AFTER:
        return
    guest.mailed_at = now
    guest.save(update_fields=["mailed_at"])
    transaction.on_commit(lambda: send(guest))


def guest_sign_up(request, slug):
    """Coming without an account: a name and an email, confirmed by a link in an email.
    Only an open gift-circle; who is logged in says "I'm coming"."""
    event = _gift_circle(slug)
    if request.user.is_authenticated or not (event.is_open and event.takes_people()):
        return redirect(event.get_absolute_url())
    form = GuestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        error = _too_many(event, form.cleaned_data["people"])
        if error:
            form.add_error("people", error)
        else:
            email = form.cleaned_data["email"]
            guest = event.guests.filter(email__iexact=email).first()
            if guest is None:
                guest = form.save(commit=False)
                guest.event = event
                guest.language = get_language() or ""
                guest.save()
            elif not guest.confirmed_at:
                # Signed up before without confirming: what they say now counts
                for field in ("name", "people", "keep_on_ecobasa", "share_email"):
                    setattr(guest, field, form.cleaned_data[field])
                guest.save()
            # Already confirmed: the link to change it goes out again, nothing changes
            _mail_again(guest, send_guest_welcome if guest.confirmed_at else send_guest_confirmation)
            return render(request, "gift_circles/guest_sent.html", {"event": event, "email": email})
    return render(request, "gift_circles/guest_sign_up.html", {"event": event, "form": form})


def _guest(slug, token):
    guests = Guest.objects.select_related("event__community", "event__host_user", "event__host_tour")
    return get_object_or_404(guests, token=token, event__kind=kinds.GIFT_CIRCLE, event__slug=slug)


def _guest_url(guest, name="guest"):
    return reverse(f"gift_circles:{name}", args=[guest.event.slug, guest.token])


def guest_confirm(request, slug, token):
    """The link in the guest's email: confirming takes a click on the page, so mail
    programs that open links to check them don't confirm it."""
    guest = _guest(slug, token)
    event = guest.event
    if guest.confirmed_at:
        return redirect(_guest_url(guest))
    if request.method == "POST":
        error = _too_many(event, guest.people) if event.is_current else event.texts["no_offers"]
        if error:
            messages.error(request, error)
            return redirect(event.get_absolute_url())
        guest.confirmed_at = guest.mailed_at = timezone.now()
        guest.save(update_fields=["confirmed_at", "mailed_at"])
        transaction.on_commit(lambda: send_guest_welcome(guest))
        messages.success(request, _("You're in. See you on %(day)s!") % {"day": _day(event)})
        return redirect(_guest_url(guest))
    return render(request, "gift_circles/guest_confirm.html", {"guest": guest, "event": event})


def _day(event):
    from django.utils.formats import date_format

    return date_format(event.starts_on, "DATE_FORMAT") if event.starts_on else event.title


def guest(request, slug, token):
    """A guest's own page, through the link in their emails: their sign-up, its exact
    place, changing or leaving it, and why an account helps."""
    guest = _guest(slug, token)
    event = guest.event
    if not guest.confirmed_at:
        return redirect(_guest_url(guest, "guest_confirm"))
    if request.method == "POST" and request.POST.get("action") == "leave":
        guest.delete()
        messages.success(request, _("You are off the list."))
        return redirect(event.get_absolute_url())
    # Before the form puts the new number into it
    own = guest.people if guest.user_id is None else 0
    form = GuestChangeForm(request.POST or None, instance=guest)
    if request.method == "POST" and form.is_valid():
        people = form.cleaned_data["people"]
        error = _too_many(event, people, own) if people > own else ""
        if error:
            form.add_error("people", error)
        else:
            form.save()
            messages.success(request, _("Saved."))
            return redirect(_guest_url(guest))
    return render(request, "gift_circles/guest.html", {
        "guest": guest, "event": event, "form": form, "place_name": exact_place(event),
        "account_url": _guest_url(guest, "guest_account"),
    })


def guest_account(request, slug, token):
    """"Create an account" from a guest's link: the registration with their name and
    email filled in; once in, their sign-ups move to the account."""
    guest = _guest(slug, token)
    event_url = guest.event.get_absolute_url()
    if request.user.is_authenticated:
        link_to_account(token, request.user)
        return redirect(event_url)
    request.session[GUEST_SESSION_KEY] = token
    return redirect(f"{reverse('users:register')}?{urlencode({'name': guest.name, 'email': guest.email, 'next': event_url})}")
