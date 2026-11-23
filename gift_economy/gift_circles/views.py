from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
from django.utils.translation import get_language, gettext as _, ngettext
from django.views.decorators.http import require_POST

import bot_check
from events import kinds
from events.models import Event
from gift_economy.gifts.models import Listing
from gift_economy.matches.models import Match

from . import bringing, giftsheet as sheets, results, stories, video, wishes as wish_answers
from .emails import exact_place, send_guest_confirmation, send_guest_welcome, send_written
from .forms import EntryForm, GuestChangeForm, GuestForm, InviteForm, PhotoForm, WriteForm
from .guests import GUEST_SESSION_KEY, link_to_account
from .invitations import (
    EMAIL_LIMIT, answer, emails_left, invite as send_invitations, invite_who_came, may_invite, taken_users,
)
from .models import Attendee, Entry, Guest, Idea, Invitation, Scribe
from .timings import timings

# Empty lines on the printed Giftsheet's front (below its heading) and back: one sheet of
# A4, both sides
GIFTSHEET_ROWS = (24, 27)

# How long before the same link goes to the same address again
MAIL_AGAIN_AFTER = timedelta(minutes=10)


def _gift_circle(slug):
    return get_object_or_404(Event.objects.select_related("community", "host_user", "host_tour"), kind=kinds.GIFT_CIRCLE, slug=slug)


def print_giftsheet(request, slug, token=None):
    """The facilitator card and the Giftsheet, to print: empty for anyone (the title and
    the day are on the gift-circle's page too), filled in so far for who may see it, to
    take home on paper. Names only, no addresses."""
    if token is None:
        event = _gift_circle(slug)
        filled = sheets.may_see(event, request.user)
        giftsheet_url = reverse("gift_circles:giftsheet", args=[slug]) if filled else ""
    else:
        guest = _guest(slug, token)
        event, filled = guest.event, guest.confirmed_at is not None
        giftsheet_url = _guest_url(guest, "guest_giftsheet") if filled else ""
    if filled:
        sheets.sheet_of(event)
    entries = list(sheets.entries(event)) if filled else []
    return render(request, "gift_circles/print.html", {
        "event": event, "timings": timings(event), "pages": _pages(entries), "filled": bool(entries),
        "giftsheet_url": giftsheet_url,
    })


def _pages(rows):
    """The Giftsheet's lines over its pages: the front holds fewer (below its heading),
    every page after more; at least a front and a back, the rest of the last one empty
    lines to write on."""
    front, back = GIFTSHEET_ROWS
    pages = [rows[:front]]
    rest = rows[front:]
    while rest or len(pages) < 2:
        pages.append(rest[:back])
        rest = rest[back:]
    return [page + [None] * ((front if number == 0 else back) - len(page)) for number, page in enumerate(pages)]


# ── People with an account ──────────────────────────────────────────

@login_required
@require_POST
def attendee(request, slug):
    """Who comes, and its host, change whether their offers and wishes from it stay on
    ecobasa."""
    event = _gift_circle(slug)
    if bringing.is_in(event, request.user):
        Attendee.objects.update_or_create(
            event=event, user=request.user, defaults={"keep_on_ecobasa": bool(request.POST.get("keep_on_ecobasa"))},
        )
        messages.success(request, _("Saved."))
    if request.POST.get("next"):
        return _back(request, event)
    return redirect(event.get_absolute_url())


# ── What people bring ───────────────────────────────────────────────

def _back(request, event):
    """Where bringing or taking back leads: the page it was done on, else the gift-circle's."""
    target = request.POST.get("next", "")
    if target and url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(target)
    return redirect(f"{event.get_absolute_url()}#bring")


@login_required
@require_POST
def bring(request, slug):
    """Who comes or hosts brings an offer or a wish of their own."""
    event = _gift_circle(slug)
    listing = get_object_or_404(bringing.own_listings(request.user), pk=request.POST.get("listing", ""))
    if bringing.may_bring(event, request.user):
        bringing.bring(event, listing)
    return _back(request, event)


@login_required
@require_POST
def take_back(request, slug, pk):
    event = _gift_circle(slug)
    listing = get_object_or_404(Listing, pk=pk, owner=request.user)
    bringing.take_back(event, listing)
    return _back(request, event)


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


# Sign-ups from one connection, (at most, within): across all gift-circles, and for one.
# Loose, as people at one place often share a connection (a house Wi-Fi, a mobile network)
GUEST_LIMITS = [(40, timedelta(days=1))]
GUEST_LIMITS_PER_CIRCLE = [(15, timedelta(days=1))]


def guest_sign_up(request, slug):
    """Coming without an account: a name and an email, confirmed by a link in an email.
    Only an open gift-circle; who is logged in says "I'm coming". Through the bot check,
    so it can't be used to mail strangers."""
    event = _gift_circle(slug)
    if request.user.is_authenticated or not (event.is_open and event.takes_people()):
        return redirect(event.get_absolute_url())
    form = GuestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        check = bot_check.check(request, "guest", GUEST_LIMITS, scope=str(event.pk), scope_limits=GUEST_LIMITS_PER_CIRCLE)
        if check.trapped:
            return render(request, "gift_circles/guest_sent.html", {"event": event, "email": form.cleaned_data["email"]})
        if check.error:
            form.add_error(None, check.error)
        else:
            response = _sign_up(request, event, form)
            if response is not None:
                try:
                    bot_check.record(request, "guest", scope=str(event.pk))
                except IntegrityError:
                    pass
                return response
    return render(request, "gift_circles/guest_sign_up.html", {"event": event, "form": form})


def _sign_up(request, event, form, invitation=None):
    """The guest row of a valid sign-up and its email; the response, None when too many
    come. Through an invitation by email to the same address, it needs no confirming: the
    link in it proves the address."""
    error = _too_many(event, form.cleaned_data["people"])
    if error:
        form.add_error("people", error)
        return None
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
    if invitation is not None:
        # Answered: the guest row keeps the address now
        invitation.delete()
        if invitation.email.lower() == email.lower():
            if not guest.confirmed_at:
                _confirm(request, guest)
            return redirect(_guest_url(guest))
    # Already confirmed: the link to change it goes out again, nothing changes
    _mail_again(guest, send_guest_welcome if guest.confirmed_at else send_guest_confirmation)
    return render(request, "gift_circles/guest_sent.html", {"event": event, "email": email})


def _confirm(request, guest):
    """A guest counts from now on: the welcome email, and an invitation of their address
    is answered."""
    guest.confirmed_at = guest.mailed_at = timezone.now()
    guest.save(update_fields=["confirmed_at", "mailed_at"])
    guest.event.invitations.filter(email__iexact=guest.email).delete()
    transaction.on_commit(lambda: send_guest_welcome(guest))
    messages.success(request, _("You're in. See you on %(day)s!") % {"day": _day(guest.event)})


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
        _confirm(request, guest)
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


# ── Inviting ────────────────────────────────────────────────────────

@login_required
def invite(request, slug):
    """Its host and who comes invite members found by name and anyone by email. The host
    sees everyone invited so far, the others whom they invited."""
    event = _gift_circle(slug)
    if not may_invite(event, request.user):
        return redirect(event.get_absolute_url())
    form = InviteForm(event, request.POST or None)
    if request.method == "POST" and form.is_valid():
        made = send_invitations(
            event, request.user, form.cleaned_data["users"], form.cleaned_data["people"], form.cleaned_data["message"],
        )
        if made:
            messages.success(request, ngettext(
                "Your invitation has been sent.", "Your %(count)s invitations have been sent.", len(made),
            ) % {"count": len(made)})
        else:
            messages.info(request, _("They were invited already."))
        return redirect(event.get_absolute_url())
    invited = event.invitations.select_related("user").order_by("-created_at")
    if not event.can_edit(request.user):
        invited = invited.filter(invited_by=request.user)
    return render(request, "gift_circles/invite.html", {
        "event": event, "form": form, "invited": invited, "emails_left": emails_left(event),
        "email_limit": EMAIL_LIMIT,
        # Picked before the form came back with an error
        "chosen_people": [
            {"id": user.pk, "name": user.name or user.email} for user in form.cleaned_data.get("users", [])
        ] if form.is_bound else [],
    })


@login_required
def invite_people(request, slug):
    """Members whose name matches `q`, to invite: their name, picture and town. Not who
    comes or was invited already."""
    event = _gift_circle(slug)
    q = (request.GET.get("q") or "").strip()
    if not may_invite(event, request.user) or len(q) < 2:
        return JsonResponse({"results": []})
    from users.places import town

    taken = taken_users(event) | {request.user.pk}
    people = get_user_model().objects.filter(is_active=True, name__icontains=q).exclude(pk__in=taken).order_by("name")[:8]
    return JsonResponse({"results": [
        {"id": person.pk, "name": person.name, "image": person.image.url if person.image else "",
         "place": town(person.location_name) or ""}
        for person in people
    ]})


def invitation(request, slug, token):
    """The link in an invitation by email: coming as a guest, or with one's account, also
    when it isn't open; or "I'm not coming", which deletes the address."""
    invitation = get_object_or_404(
        Invitation.objects.select_related("event__community", "event__host_user", "event__host_tour", "invited_by"),
        token=token, user=None, event__kind=kinds.GIFT_CIRCLE, event__slug=slug,
    )
    event = invitation.event
    action = request.POST.get("action") if request.method == "POST" else None
    if action == "decline":
        invitation.delete()
        messages.success(request, _("We deleted your address. Thank you for letting us know."))
        return redirect(event.get_absolute_url())
    takes_people = event.takes_people()
    if action == "account" and request.user.is_authenticated:
        answer(invitation, request.user)
        return redirect(event.get_absolute_url())
    form = None
    if not request.user.is_authenticated and takes_people:
        form = GuestForm(request.POST or None, initial={"name": invitation.name, "email": invitation.email})
        if action == "guest" and form.is_valid():
            response = _sign_up(request, event, form, invitation)
            if response is not None:
                return response
    return render(request, "gift_circles/invitation.html", {
        "invitation": invitation, "event": event, "form": form, "takes_people": takes_people,
    })


# ── The Giftsheet ───────────────────────────────────────────────────

def giftsheet(request, slug):
    """The Giftsheet for who came, its host and scribes."""
    event = _gift_circle(slug)
    if not sheets.may_see(event, request.user):
        if not request.user.is_authenticated:
            return redirect(f"{reverse('users:login')}?{urlencode({'next': request.path})}")
        return redirect(event.get_absolute_url())
    return _giftsheet(request, event, here=reverse("gift_circles:giftsheet", args=[slug]))


def guest_giftsheet(request, slug, token):
    """The Giftsheet for a guest, through their link: they add lines of their own."""
    guest = _guest(slug, token)
    if not guest.confirmed_at:
        return redirect(_guest_url(guest, "guest_confirm"))
    return _giftsheet(request, guest.event, here=_guest_url(guest, "guest_giftsheet"), guest=guest)


def _giftsheet(request, event, here, guest=None):
    sheet = sheets.sheet_of(event)
    user = request.user
    writes = guest is None and sheets.may_write(event, user)
    adds_own = sheets.may_add_own(event, None if guest else user, guest, sheet)
    if request.method == "POST":
        if sheet.is_closed or not (writes or adds_own):
            return redirect(here)
        form = EntryForm(request.POST, people=sheets.people(event) if writes else None)
        if form.is_valid():
            try:
                _add_entry(request, event, form, writes, guest)
            except sheets.PickError as error:
                form.add_error("who", str(error))
        if form.is_valid():
            return redirect(f"{here}#new")
    else:
        form = EntryForm(people=sheets.people(event) if writes else None)
    entries = list(sheets.entries(event))
    for entry in entries:
        entry.is_own = _is_own(entry, user, guest)
    context = {
        "event": event, "sheet": sheet, "here": here, "guest": guest, "entries": entries,
        "writes": writes, "adds_own": adds_own, "people": sheets.people(event) if writes else [],
        "refreshes": sheets.refreshes(event, sheet),
    }
    if request.headers.get("HX-Request"):
        return render(request, "gift_circles/_giftsheet_entries.html", context)
    context.update({
        "form": form, "photos": event.giftsheet_photos.all(), "photo_form": PhotoForm(),
        "photo_limit": sheets.PHOTO_LIMIT, "can_edit": event.can_edit(user),
        "keeps": guest is None and Attendee.objects.filter(event=event, user=user, keep_on_ecobasa=True).exists(),
    })
    return render(request, "gift_circles/giftsheet.html", context)


def _add_entry(request, event, form, writes, guest):
    data = form.cleaned_data
    entry = Entry(event=event, type=data["type"], text=data["text"])
    if guest is not None:
        entry.from_guest = guest
    elif writes:
        entry.from_user, entry.from_guest, entry.from_name = sheets.pick(
            event, data["who"], data.get("name", ""), data.get("email", ""), by=request.user,
        )
        entry.created_by = request.user
    else:
        entry.from_user = entry.created_by = request.user
    entry.save()


@require_POST
def giftsheet_entry(request, slug, pk, token=None):
    """A line changed, answered ("Fulfilled by …", "Taken by …"), open again, given an
    idea how it could happen, or taken back. The host and scribes do anything; who wrote
    a line of their own changes it or takes it back while it is open."""
    if token is None:
        event = _gift_circle(slug)
        guest = None
        here = reverse("gift_circles:giftsheet", args=[slug])
    else:
        guest = _guest(slug, token)
        event = guest.event
        here = _guest_url(guest, "guest_giftsheet")
    entry = get_object_or_404(Entry, event=event, pk=pk)
    sheet = sheets.sheet_of(event)
    writes = guest is None and sheets.may_write(event, request.user)
    own = entry.state == Entry.STATE_OPEN and _is_own(entry, request.user, guest)
    action = request.POST.get("action")
    back = redirect(f"{here}#entry-{entry.pk}")
    if sheet.is_closed or entry.match_id:
        return back
    try:
        if action == "delete" and (writes or own):
            entry.delete()
            return redirect(here)
        if action == "edit" and (writes or own):
            _edit_entry(request, event, entry, writes)
        elif action == "open" and writes:
            entry.state = Entry.STATE_OPEN
            entry.for_user, entry.for_guest, entry.for_name = None, None, ""
            entry.lend, entry.borrow_from, entry.borrow_to = False, None, None
            entry.save()
        elif action == Entry.STATE_FULFILLED and writes:
            who = _picked(request, event)
            if sheets.same_person(entry, *who):
                raise sheets.PickError(_("That is who it is from. Please choose someone else."))
            entry.lend, entry.borrow_from, entry.borrow_to = _borrowing(request)
            entry.state = Entry.STATE_FULFILLED
            entry.for_user, entry.for_guest, entry.for_name = who
            entry.save()
        elif action == "idea" and writes:
            text = request.POST.get("idea", "").strip()
            if not text:
                raise sheets.PickError(_("Please write the idea."))
            from_user, from_guest, from_name = _picked(request, event)
            Idea.objects.create(
                entry=entry, text=text[:255], from_user=from_user, from_guest=from_guest, from_name=from_name,
                created_by=request.user,
            )
        elif action == "idea_delete" and writes:
            entry.ideas.filter(pk=request.POST.get("idea") or 0).delete()
    except sheets.PickError as error:
        messages.error(request, str(error))
    return back


def _borrowing(request):
    """(lends, from, until) of a tool to lend. The days may be left open, to propose them
    on the match afterwards; one day without an end."""
    if not request.POST.get("lends"):
        return False, None, None
    try:
        start = date.fromisoformat(request.POST.get("borrow_from", ""))
    except ValueError:
        return True, None, None
    try:
        end = date.fromisoformat(request.POST.get("borrow_to", "")) if request.POST.get("borrow_to") else start
    except ValueError:
        end = start
    if end < start:
        raise sheets.PickError(_("It can't come back before it is borrowed."))
    return True, start, end


def _picked(request, event):
    return sheets.pick(
        event, request.POST.get("who"), request.POST.get("name", ""), request.POST.get("email", ""), by=request.user,
    )


def _edit_entry(request, event, entry, writes):
    """Its words, and while it isn't an offer or wish on ecobasa already, whether it is a
    wish or an offer and (for the host and scribes) whom it is from."""
    text = request.POST.get("text", "").strip()
    if not text:
        raise sheets.PickError(_("Please write the wish or offer."))
    entry.text = text[:255]
    if entry.listing_id is None:
        if request.POST.get("type") in (Entry.TYPE_OFFER, Entry.TYPE_WISH):
            entry.type = request.POST["type"]
        if writes and request.POST.get("who") and request.POST["who"] != entry.from_choice:
            entry.from_user, entry.from_guest, entry.from_name = _picked(request, event)
    entry.save()


def _is_own(entry, user, guest):
    """A line someone wrote themselves: they may take it back while it is open."""
    if guest is not None:
        return entry.from_guest_id == guest.pk and entry.created_by_id is None
    return user.is_authenticated and entry.from_user_id == user.pk and entry.created_by_id == user.pk


@login_required
@require_POST
def giftsheet_close(request, slug):
    """The host closes the Giftsheet, or opens it again."""
    event = _gift_circle(slug)
    here = reverse("gift_circles:giftsheet", args=[slug])
    if not event.can_edit(request.user):
        return redirect(here)
    sheet = sheets.sheet_of(event)
    if request.POST.get("action") == "reopen" and sheet.is_closed:
        sheets.reopen(sheet)
    elif not sheet.is_closed:
        first = sheet.results_sent_at is None
        sheets.close(event, sheet, request.user)
        messages.success(request, _("The Giftsheet is closed.") + (
            " " + _("Everyone who came gets the results by email.") if first else ""
        ))
    return redirect(here)


@login_required
@require_POST
def giftsheet_photo(request, slug, pk=None):
    """The host and scribes add a photo of the paper Giftsheet, or delete one."""
    event = _gift_circle(slug)
    here = reverse("gift_circles:giftsheet", args=[slug])
    if not sheets.may_write(event, request.user):
        return redirect(here)
    if pk is not None:
        event.giftsheet_photos.filter(pk=pk).delete()
        return redirect(f"{here}#photos")
    if event.giftsheet_photos.count() >= sheets.PHOTO_LIMIT:
        return redirect(f"{here}#photos")
    form = PhotoForm(request.POST, request.FILES)
    if form.is_valid():
        photo = form.save(commit=False)
        photo.event = event
        photo.save()
    else:
        for error in form.errors.get("image", []):
            messages.error(request, error)
    return redirect(f"{here}#photos")


@login_required
@require_POST
def scribe(request, slug):
    """The host makes someone who comes a scribe, or no longer one. A scribe passes it on:
    makes someone else scribe, and steps down."""
    event = _gift_circle(slug)
    if sheets.may_hand_out_scribe(event, request.user):
        user_id = request.POST.get("user", "")
        hosts = event.can_edit(request.user)
        if user_id.isdigit() and int(user_id) in bringing.coming_ids(event):
            if request.POST.get("action") == "remove":
                if not hosts and int(user_id) != request.user.pk:
                    return redirect(f"{event.get_absolute_url()}#coming")
                Scribe.objects.filter(event=event, user_id=user_id).delete()
            else:
                Scribe.objects.get_or_create(event=event, user_id=user_id)
    return redirect(f"{event.get_absolute_url()}#coming")


# ── The video call ──────────────────────────────────────────────────

def video_call(request, slug):
    """An online gift-circle's video call, for who comes and its host: the room inside
    the page from an hour before, where the server allows it, else a link to it."""
    event = _gift_circle(slug)
    if not request.user.is_authenticated:
        return redirect(f"{reverse('users:login')}?{urlencode({'next': request.path})}")
    if not (event.is_online and video.may_join(event, request.user)):
        return redirect(event.get_absolute_url())
    return _video_call(request, event, request.user.name, reverse("gift_circles:giftsheet", args=[slug]))


def guest_video_call(request, slug, token):
    guest = _guest(slug, token)
    if not guest.confirmed_at:
        return redirect(_guest_url(guest, "guest_confirm"))
    if not guest.event.is_online:
        return redirect(_guest_url(guest))
    return _video_call(request, guest.event, guest.name, _guest_url(guest, "guest_giftsheet"), guest=guest)


def _video_call(request, event, name, giftsheet_url, guest=None):
    is_open = video.is_open(event)
    return render(request, "gift_circles/video_call.html", {
        "event": event, "guest": guest, "is_open": is_open, "opens": video.opens(event),
        "is_over": event.is_over or event.archived_at is not None,
        "room_url": video.room_url(event) if is_open else "",
        "embed_url": video.embed_url(event, name) if is_open and video.embeds(event) else "",
        "giftsheet_url": giftsheet_url,
        "back_url": _guest_url(guest) if guest else event.get_absolute_url(),
    })


# ── After the circle ────────────────────────────────────────────────

def _person_key(user_id, guest_id):
    if user_id:
        return f"user:{user_id}"
    return f"guest:{guest_id}" if guest_id else None


def _pairs(entry):
    """Who may write to whom about a line: its two sides, and its side and whoever had
    an idea for it."""
    origin = _person_key(entry.from_user_id, entry.from_guest_id)
    others = [_person_key(entry.for_user_id, entry.for_guest_id)] if entry.state == Entry.STATE_FULFILLED else []
    others += [_person_key(idea.from_user_id, idea.from_guest_id) for idea in entry.ideas.all()]
    return {frozenset((origin, other)) for other in others if origin and other and other != origin}


@login_required
def write(request, slug, pk):
    return _write(request, _gift_circle(slug), pk)


def guest_write(request, slug, token, pk):
    guest = _guest(slug, token)
    if not guest.confirmed_at:
        return redirect(_guest_url(guest, "guest_confirm"))
    return _write(request, guest.event, pk, guest)


def _write(request, event, pk, guest=None):
    """"Write to them": a few words by email to the other side of a line of a closed
    Giftsheet, without showing their address; answering goes to the sender."""
    if guest is None:
        me, sender_name, sender_email = f"user:{request.user.pk}", request.user.name or request.user.email, request.user.email
        giftsheet_url = reverse("gift_circles:giftsheet", args=[event.slug])
    else:
        me, sender_name, sender_email = f"guest:{guest.pk}", guest.name, guest.email
        giftsheet_url = _guest_url(guest, "guest_giftsheet")
    entry = get_object_or_404(Entry.objects.select_related("event"), event=event, pk=pk)
    sheet = sheets.sheet_of(event)
    to = request.GET.get("to", "")
    recipient = _addressee(event, to)
    if not sheet.is_closed or recipient is None or not recipient.email or frozenset((me, to)) not in _pairs(entry):
        return redirect(giftsheet_url)
    other_name = recipient.name or recipient.email
    form = WriteForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        send_written(entry, sender_name, sender_email, recipient, form.cleaned_data["message"])
        messages.success(request, _("Your message to %(name)s has been sent.") % {"name": other_name})
        return redirect(giftsheet_url)
    return render(request, "gift_circles/write.html", {
        "event": event, "entry": entry, "form": form, "other_name": other_name, "sender_email": sender_email,
        "giftsheet_url": giftsheet_url,
    })


def _addressee(event, to):
    kind, _sep, pk = to.partition(":")
    if not pk.isdigit():
        return None
    if kind == "user":
        return get_user_model().objects.filter(pk=pk, is_active=True).first()
    if kind == "guest":
        return event.guests.filter(pk=pk).first()
    return None


def wishes(request, slug, key):
    """"Did your wish come true?", behind the link in its email: one answer per wish.
    "Yes" marks it covered on ecobasa and asks for the story."""
    found = wish_answers.read_key(key)
    event = _gift_circle(slug)
    if found is None or found[0] != event.pk:
        messages.error(request, _("This link doesn't work any more."))
        return redirect(event.get_absolute_url())
    _event_pk, side, person_pk = found
    lines = list(wish_answers.wishes_of(event, side, person_pk))
    if not lines:
        return redirect(event.get_absolute_url())
    if request.method == "POST":
        entry = next((line for line in lines if str(line.pk) == request.POST.get("entry")), None)
        if entry is not None and request.POST.get("answer") in ("yes", "no"):
            wish_answers.answer(entry, request.POST["answer"] == "yes")
        return redirect(f"{request.path}#entry-{entry.pk if entry else ''}")
    guest = event.guests.filter(pk=person_pk).first() if side == "guest" else None
    user = get_user_model().objects.filter(pk=person_pk).first() if side == "user" else None
    stories_url = f"{event.get_absolute_url()}#references"
    for entry in lines:
        entry.contact = results.contact(event, entry, entry.for_user, entry.for_guest, user, guest)
        entry.story_url = reverse("matches:detail", args=[entry.match_id]) if entry.match_id else stories_url
    return render(request, "gift_circles/wishes.html", {"event": event, "entries": lines})


# Taken over from the last one by "Plan the next one": all but its day, host and video room
NEXT_FIELDS = (
    "title", "description", "starts_at", "ends_at", "is_open", "max_people", "potluck_note",
    "location_name", "location", "country", "is_online", "timezone", "languages",
)


@login_required
def plan_next(request, slug):
    """"Plan the next one": whoever came (or hosted) invites to the next gift-circle,
    with the form filled in from this one, and hosts it. Everyone who came is invited
    once it is saved."""
    from events.views import save_event

    event = _gift_circle(slug)
    if not (sheets.started(event) and bringing.is_in(event, request.user)):
        return redirect(event.get_absolute_url())
    following = Event(
        kind=event.kind, host_user=request.user, previous=event,
        **{field: getattr(event, field) for field in NEXT_FIELDS},
    )
    return save_event(
        request, following, event.get_absolute_url(),
        on_saved=lambda saved: invite_who_came(saved, event, request.user),
    )


@login_required
@require_POST
def story(request, slug):
    """Who came or hosted tells how it went, about something of it (stories.destinies);
    or takes their story back."""
    from gift_economy.references.forms import ReferenceForm
    from gift_economy.references.models import Reference
    from gift_economy.references.notifications import notify_reference_created

    event = _gift_circle(slug)
    back = redirect(f"{event.get_absolute_url()}#references")
    if not event.can_be_referenced_by(request.user):
        return back
    if request.POST.get("action") == "delete":
        reference = Reference.objects.filter(author=request.user, pk=request.POST.get("reference") or 0).first()
        if reference is not None and stories.is_story_of(reference, event):
            reference.delete()
        return back
    subject = stories.subject_for(event, request.user, request.POST.get("about", ""))
    if subject is None:
        messages.error(request, _("Please choose what it is about."))
        return back
    existing = stories.own_story(event, request.user, subject)
    form = ReferenceForm(request.POST, request.FILES, instance=existing, subject=subject, author=request.user)
    if not form.is_valid():
        messages.error(request, (form.errors.get("photo") or [_("Please choose an impression and describe your experience.")])[0])
        return back
    reference = form.save_reference(request.user, subject)
    if subject != event:
        reference.place = event
        reference.save(update_fields=["place_type", "place_id"])
    if existing is None:
        notify_reference_created(reference, http_request=request)
    messages.success(request, _("Thank you for sharing your experience."))
    return back
