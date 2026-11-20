"""Online skill-sharing: a skill or knowledge both sides can also share from afar
(Listing.from_afar) is suggested however far apart they live, and from that suggestion one
of them starts an online gift-circle for it, which invites the other and brings their own
offers and wishes that fit. Whatever is shared from afar at an online gift-circle is
suggested to everyone else who can share it from afar too, so they can join
(Suggestion.REASON_SHARED_ONLINE): when it is brought, and when they save theirs later."""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils.translation import gettext as _

from events import kinds
from events.models import Event
from gift_economy.gifts.models import Listing
from gift_economy.matches.matching import fit, side_of
from gift_economy.matches.models import Suggestion

from .bringing import bring, coming_ids
from .invitations import invite
from .models import Brought


def start(request, event):
    """A new gift-circle from `?suggestion=`, one of the reader's own that can start an
    online skill-sharing: online, named after the skills they share from afar with that
    person. Returns what runs once it is saved (bringing their offers and wishes, inviting
    the other person), or None."""
    suggestion = Suggestion.objects.filter(pk=request.GET.get("suggestion") or None, user=request.user).first()
    if suggestion is None or not suggestion.starts_skill_sharing:
        return None
    other_user = suggestion.other_user
    shared = [suggestion] + [
        other for other in request.user.suggestions.filter(other_user=other_user, dismissed_at=None).exclude(pk=suggestion.pk)
        if other.starts_skill_sharing
    ]
    names = list(dict.fromkeys(other.own.display_title for other in shared))
    event.is_online = True
    # From afar: the form asks for no town it is for people around
    event.skill_sharing = True
    event.title = (_("Online skill-sharing: %(skills)s") % {"skills": ", ".join(names)})[:255]

    def on_saved(saved):
        for other in shared:
            bring(saved, other.own)
        invite(saved, request.user, [other_user], [], "")

    return on_saved


def _shares(event):
    """Whether what is brought to it reaches people far away: an online gift-circle ahead."""
    return event.kind == kinds.GIFT_CIRCLE and event.is_online and event.is_current


def _inside(event):
    """Who needn't hear about it: who comes, its host, who was invited."""
    people = coming_ids(event) | set(event.invitations.exclude(user=None).values_list("user_id", flat=True))
    if event.manager is not None:
        people.add(event.manager.pk)
    return people


def _from_afar(listings):
    return listings.filter(from_afar=True, kind__in=Listing.FROM_AFAR_KINDS, community=None, tour=None, event=None)


def share_online(event, listing, notify=True):
    """`listing` was brought to `event`: if it is shared from afar at an online gift-circle,
    suggest it there to everyone else whose own offer or wish fits it from afar. Returns
    the new suggestions."""
    side = side_of(listing)
    if not _shares(event) or side is None or not side.from_afar:
        return []
    others = _from_afar(Listing.objects.current()).filter(
        type=Listing.TYPE_OFFER if listing.is_wish else Listing.TYPE_WISH,
    ).exclude(owner_id__in=_inside(event)).select_related("owner", "skill").prefetch_related("contributions__match")
    created = []
    for other in others:
        other_side = side_of(other)
        if other_side is not None and fit(other_side, side) is not None:
            suggestion = _suggest(event, other_side, side)
            if suggestion is not None:
                created.append(suggestion)
    _notify(created, notify)
    return created


def share_with(listing, notify=True):
    """`listing` was saved: suggest the online gift-circles ahead where something that fits
    it from afar is shared. Returns the new suggestions."""
    side = side_of(listing)
    if side is None or not side.from_afar or listing.community_id or listing.tour_id or listing.event_id:
        return []
    rows = Brought.objects.filter(
        event__kind=kinds.GIFT_CIRCLE, event__is_online=True,
        listing__in=_from_afar(Listing.objects.current()).filter(
            type=Listing.TYPE_OFFER if listing.is_wish else Listing.TYPE_WISH,
        ),
    ).exclude(listing__owner=listing.owner).select_related("event", "listing__owner", "listing__skill")
    created = []
    for row in rows:
        shown = side_of(row.listing)
        if shown is None or not _shares(row.event) or listing.owner_id in _inside(row.event) or fit(side, shown) is None:
            continue
        suggestion = _suggest(row.event, side, shown)
        if suggestion is not None:
            created.append(suggestion)
    _notify(created, notify)
    return created


def _suggest(event, recipient, shown):
    """The suggestion for recipient's owner, with sharing at the gift-circle as its reason;
    one found before takes it as its reason, unless they meet at a gift-circle already.
    Returns it if it was created."""
    listing_type = ContentType.objects.get_for_model(Listing)
    circle = {
        "reason": Suggestion.REASON_SHARED_ONLINE, "distance_km": None,
        "detail_type": ContentType.objects.get_for_model(Event), "detail_id": str(event.pk),
    }
    suggestion, created = Suggestion.objects.get_or_create(
        user=recipient.owner,
        own_type=listing_type, own_id=str(recipient.obj.pk), other_type=listing_type, other_id=str(shown.obj.pk),
        defaults={"other_user": shown.owner, "kind": Suggestion.KIND_SKILLS, **circle},
    )
    if not created and suggestion.reason not in (Suggestion.REASON_GIFT_CIRCLE, Suggestion.REASON_SHARED_ONLINE):
        for field, value in circle.items():
            setattr(suggestion, field, value)
        suggestion.save(update_fields=list(circle))
    return suggestion if created else None


def _notify(created, notify):
    if notify and created:
        from gift_economy.matches.emails import notify_new_suggestions
        notify_new_suggestions({suggestion.user for suggestion in created})


def schedule_share_with(listing):
    """share_with() once the request's transaction is committed."""
    pk = listing.pk

    def run():
        fresh = Listing.objects.filter(pk=pk).first()
        if fresh is not None:
            share_with(fresh)

    transaction.on_commit(run)
