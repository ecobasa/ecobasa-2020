"""The Giftsheet: the table a gift-circle's scribe keeps, line by line, on a phone or
laptop. It starts with what people bring; the host and scribes write every line, who
comes adds their own. When the host closes it, the lines of people with an account
become offers and wishes on ecobasa (if they said yes to that), and what one of them
fulfilled for another an accepted match."""

from datetime import datetime, time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone, translation
from django.utils.translation import gettext as _

from gift_economy.gifts.models import Listing
from gift_economy.gifts.things import recognize
from gift_economy.matches.models import Contribution, Loan, Match, loan_span

from .bringing import coming_ids, is_in
from .models import Attendee, Entry, Giftsheet, Guest, Idea, Scribe

# Photos of the paper Giftsheet: its front and its back
PHOTO_LIMIT = 2

# What the person picker sends for someone not on the list yet
NEW = "new"


# ── Who does what ───────────────────────────────────────────────────

def is_scribe(event, user):
    return user.is_authenticated and Scribe.objects.filter(event=event, user=user).exists()


def may_hand_out_scribe(event, user):
    """The host, and a scribe, who can pass it on to someone else who comes."""
    return user.is_authenticated and (event.can_edit(user) or is_scribe(event, user))


def may_write(event, user):
    """Its host and its scribes write every line."""
    return user.is_authenticated and (event.can_edit(user) or is_scribe(event, user))


def may_see(event, user):
    """Who came (or comes), the host and scribes. Guests see it through their link."""
    return is_in(event, user) or is_scribe(event, user)


def may_add_own(event, user=None, guest=None, sheet=None):
    """Who comes adds lines of their own while it is open; guests through their link."""
    if sheet is not None and sheet.is_closed:
        return False
    if guest is not None:
        return guest.confirmed_at is not None and guest.event_id == event.pk
    return user is not None and user.is_authenticated and user.pk in coming_ids(event)


def started(event):
    """Whether it has begun: from then on the page refreshes for whoever has it open."""
    if event.starts_on is None:
        return False
    start = timezone.make_aware(datetime.combine(event.starts_on, event.starts_at or time.min))
    return timezone.now() >= start


def refreshes(event, sheet):
    """Running over is common, so it keeps refreshing until the host closes it."""
    return started(event) and not sheet.is_closed


# ── The sheet ───────────────────────────────────────────────────────

def sheet_of(event):
    """Its Giftsheet, made the first time with what people bring on it."""
    sheet, created = Giftsheet.objects.get_or_create(event=event)
    if created:
        from .bringing import brought

        offers, wishes = brought(event)
        for listing in sorted(offers + wishes, key=lambda listing: listing.created_at):
            add_brought(event, listing)
    return sheet


def add_brought(event, listing):
    """A brought offer or wish as a line of the Giftsheet, once."""
    if listing.owner_id is None or event.entries.filter(listing=listing).exists():
        return None
    return Entry.objects.create(
        event=event, type=listing.type, text=listing.display_title[:255], from_user=listing.owner, listing=listing,
    )


def brought_now(event, listing):
    """Brought after the Giftsheet was made: it goes on it too."""
    if Giftsheet.objects.filter(event=event, closed_at=None).exists():
        add_brought(event, listing)


def taken_back(event, listing):
    """Taken back: off the Giftsheet too, unless it has been answered there."""
    event.entries.filter(listing=listing, state=Entry.STATE_OPEN, match=None).delete()


def entries(event):
    return event.entries.select_related("from_user", "from_guest", "for_user", "for_guest", "listing").prefetch_related(
        "ideas__from_user", "ideas__from_guest",
    )


# ── The person picker ───────────────────────────────────────────────

def people(event):
    """Whom a line can be from or for, as (value, name) pairs: who comes with an account,
    the host and scribes; guests; who was invited and hasn't answered yet; and who came
    without signing up and is on the Giftsheet by name already. An invited address shows
    its name, or the part before the @, never the whole address."""
    users = get_user_model().objects.filter(pk__in=_user_ids(event))
    choices = [(f"user:{user.pk}", user.name or user.email) for user in users]
    choices += [(f"guest:{guest.pk}", guest.name) for guest in event.guests.coming()]
    choices += [
        (f"invitation:{invitation.pk}", invitation.name or invitation.email.split("@")[0])
        for invitation in event.invitations.filter(user=None)
    ]
    names = {}
    for name in (
        list(event.entries.exclude(from_name="").values_list("from_name", flat=True))
        + list(event.entries.exclude(for_name="").values_list("for_name", flat=True))
        + list(Idea.objects.filter(entry__event=event).exclude(from_name="").values_list("from_name", flat=True))
    ):
        names.setdefault(name.lower(), name)
    choices += [(f"name:{name}", name) for name in names.values()]
    return sorted(choices, key=lambda choice: choice[1].lower())


def _user_ids(event):
    ids = coming_ids(event) | set(event.scribes.values_list("user_id", flat=True))
    ids.update(event.invitations.exclude(user=None).values_list("user_id", flat=True))
    if event.manager is not None:
        ids.add(event.manager.pk)
    return ids


class PickError(ValueError):
    pass


def pick(event, value, name="", email="", by=None):
    """(user, guest, name) for what the picker sent. Someone new with an email comes as
    a guest added by the scribe (`by`), and so does an invited address picked: they were
    there. Raises PickError with what to tell the scribe."""
    kind, _sep, pk = (value or "").partition(":")
    if kind == "user" and pk.isdigit() and int(pk) in _user_ids(event):
        return get_user_model().objects.get(pk=pk), None, ""
    if kind == "guest" and pk.isdigit():
        guest = event.guests.coming().filter(pk=pk).first()
        if guest is not None:
            return None, guest, ""
    if kind == "invitation" and pk.isdigit():
        invitation = event.invitations.filter(user=None, pk=pk).first()
        if invitation is not None:
            return None, _walk_in(event, invitation.name or invitation.email.split("@")[0], invitation.email, by), ""
    if kind == "name" and pk.strip():
        return None, None, pk.strip()[:100]
    if value == NEW:
        name, email = name.strip(), email.strip()
        if not name:
            raise PickError(_("Please write their name."))
        if email:
            return None, _walk_in(event, name, email, by), ""
        return None, None, name[:100]
    raise PickError(_("Please choose who it is."))


def _walk_in(event, name, email, by):
    """A guest for someone who came with an email: theirs if they signed up, else a new
    one that counts as confirmed. An invitation of the address is answered by it."""
    from .invitations import emails_left

    guest = event.guests.filter(email__iexact=email).first()
    if guest is not None:
        if guest.confirmed_at is None:
            guest.confirmed_at = timezone.now()
            guest.save(update_fields=["confirmed_at"])
        return guest
    invited = event.invitations.filter(user=None, email__iexact=email)
    if not invited.exists() and not emails_left(event):
        raise PickError(_("This gift-circle can't add more email addresses. Add them by name only."))
    with transaction.atomic():
        invitation = invited.first()
        invited.delete()
        return Guest.objects.create(
            event=event, name=name[:100], email=email, confirmed_at=timezone.now(), added_by=by,
            language=(invitation.language if invitation else "") or translation.get_language() or "",
        )


def same_person(entry, user, guest, name):
    return (
        (user is not None and entry.from_user_id == user.pk)
        or (guest is not None and entry.from_guest_id == guest.pk)
        or (name and not entry.from_user_id and not entry.from_guest_id and entry.from_name.lower() == name.lower())
    )


# ── Closing ─────────────────────────────────────────────────────────

def close(event, sheet, user=None):
    """The host closes it (or the morning-after job, without `user`): lines of people
    with an account who said yes become offers and wishes, and what one of them fulfilled
    for another an accepted match. Nobody is mailed about those: the results email, sent
    on the first closing, says it all. Closing again after opening it again only adds what
    is new."""
    from .results import send_results

    with transaction.atomic():
        sheet.closed_at = timezone.now()
        sheet.closed_by = user
        fields = ["closed_at", "closed_by"]
        first = sheet.results_sent_at is None
        if first:
            sheet.results_sent_at = sheet.closed_at
            fields.append("results_sent_at")
        sheet.save(update_fields=fields)
        settle(event, entries(event).filter(match=None))
    if first:
        transaction.on_commit(lambda: send_results(event))


def settle(event, lines):
    """Offers, wishes and matches on ecobasa for `lines` of a closed Giftsheet, as far as
    their people have an account and said yes."""
    keeps = set(Attendee.objects.filter(event=event, keep_on_ecobasa=True).values_list("user_id", flat=True))
    for entry in lines:
        if entry.listing is None:
            entry.listing = _listing(entry, keeps)
        if entry.match_id is None and _matches(entry):
            entry.match = _match(event, entry)
        if entry.listing_id or entry.match_id:
            entry.save(update_fields=["listing", "match"])
        _cover(entry)


def reopen(sheet):
    sheet.closed_at = None
    sheet.closed_by = None
    sheet.save(update_fields=["closed_at", "closed_by"])


def _listing(entry, keeps):
    """Its offer or wish on ecobasa, if its person said yes to that. A wish fulfilled by
    lending something is the lender's offer to lend instead, if they said yes: the tool
    stays there for others to borrow, the wish is met."""
    if entry.lends and not entry.is_offer and entry.state == Entry.STATE_FULFILLED and entry.for_user_id in keeps:
        return _new_listing(entry.for_user, Entry.TYPE_OFFER, entry.text, lend=True)
    if entry.from_user_id in keeps:
        return _new_listing(entry.from_user, entry.type, entry.text, lend=entry.lends)
    return None


def _new_listing(owner, type, title, lend=False):
    """An offer or wish of its own on ecobasa, at its person's place, with what it names
    recognized as any listing's title."""
    thing_id = recognize(title, Listing.KIND_OTHER)
    listing = Listing.objects.create(
        owner=owner, type=type, kind=Listing.KIND_OTHER, title=title, thing_id=thing_id, lend=lend,
    )
    if thing_id is not None:
        listing.categories.set(Listing.thing_categories(listing.thing, Listing.KIND_OTHER))
    return listing


def _matches(entry):
    """Fulfilled (a wish) or taken (an offer) between two people with an account, and on
    ecobasa as one of theirs."""
    listing = entry.listing
    return (
        entry.state == Entry.STATE_FULFILLED and listing is not None and entry.from_user_id and entry.for_user_id
        and entry.from_user_id != entry.for_user_id and listing.owner_id in (entry.from_user_id, entry.for_user_id)
    )


def _cover(entry):
    """A fulfilled wish is met: no longer current on ecobasa. If it comes up again, its
    person wishes for it anew."""
    listing = entry.listing
    if entry.state == Entry.STATE_FULFILLED and not entry.is_offer and listing is not None and listing.is_wish and listing.covered_at is None:
        listing.covered_at = timezone.now()
        listing.save(update_fields=["covered_at"])


def _match(event, entry):
    """The exchange between the two, accepted at once, as "I'm coming" is."""
    listing = entry.listing
    owner = listing.owner
    asking = entry.from_user if owner.pk == entry.for_user_id else entry.for_user
    # The giver: who fulfilled a wish, whose offer was taken
    giver_id = entry.from_user_id if entry.is_offer else entry.for_user_id
    with translation.override(owner.language or settings.LANGUAGE_CODE):
        message = _("At the gift-circle %(title)s.") % {"title": event.title}
    match = Match(
        from_user=asking, recipient=owner, message=message,
        status=Match.STATUS_ACCEPTED, responded_at=timezone.now(),
        # At the giver's place
        location_type=Match.LOC_YOUR_PLACE if giver_id == owner.pk else Match.LOC_MY_PLACE,
    )
    match.target = listing
    match.save()
    Contribution.objects.create(match=match, listing=listing)
    if entry.lends:
        if not listing.lend:
            listing.lend = True
            listing.save(update_fields=["lend"])
        # Without days yet they propose them on the match (Match.lends_later)
        if entry.borrow_from is not None:
            starts_at, ends_at = loan_span(entry.borrow_from, entry.borrow_to)
            Loan.objects.create(match=match, starts_at=starts_at, ends_at=ends_at)
    return match
