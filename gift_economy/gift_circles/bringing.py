"""What people bring to a gift-circle: offers and wishes of their own on ecobasa, linked to
it (Brought). Who comes or hosts brings them, from the gift-circle's page or from the
offer or wish itself. Whatever is brought is matched with the offers and wishes of
everyone else who comes, however far apart they live: they meet there."""

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Q

from events import kinds
from events.filters import going_to
from events.models import Event
from gift_economy.gifts.models import Listing
from gift_economy.matches.matching import fit, side_of
from gift_economy.matches.models import Match, Suggestion

from .models import Brought


def coming_ids(event):
    """The people with an account who come: accepted."""
    return set(event.matches.filter(status=Match.STATUS_ACCEPTED).values_list("from_user_id", flat=True))


def is_in(event, user, coming=None):
    """Whether `user` comes to it or hosts it (may edit it)."""
    if not user.is_authenticated:
        return False
    coming = coming_ids(event) if coming is None else coming
    return user.pk in coming or event.can_edit(user)


def may_bring(event, user):
    return event.is_current and is_in(event, user)


def own_listings(user):
    """A person's own offers and wishes that can still be brought: current, not a
    community's or a tour's."""
    return Listing.objects.current().filter(owner=user, community=None, tour=None)


def gift_circles_of(user):
    """The gift-circles ahead that `user` comes to or hosts, the soonest first."""
    return Event.objects.current().filter(kind=kinds.GIFT_CIRCLE).filter(
        Q(pk__in=going_to(user)) | Q(host_user=user) | Q(host_tour__organiser=user) | Q(community__ambassador=user)
    ).distinct().order_by("starts_on", "starts_at")


def brought(event):
    """(offers, wishes) people bring who still come or host, oldest first. Each listing
    with `circle_promises`: what was promised between it and someone else who comes."""
    coming = coming_ids(event)
    rows = event.brought.select_related("listing__owner", "listing__skill").prefetch_related(
        "listing__contributions__match__from_user",
    )
    allowed = {}
    offers, wishes = [], []
    for row in rows:
        listing = row.listing
        owner = listing.owner
        if owner is None:
            continue
        if owner.pk not in allowed:
            allowed[owner.pk] = is_in(event, owner, coming)
        if not allowed[owner.pk]:
            continue
        listing.circle_promises = [
            contribution for contribution in listing.promises
            if contribution.match.from_user_id in coming or event.can_edit(contribution.match.from_user)
        ]
        (offers if listing.is_offer else wishes).append(listing)
    return offers, wishes


def bring(event, listing):
    """Bring `listing` to it, and suggest what fits it among who comes (and online, from
    afar, to anyone: skill_sharing). Once its Giftsheet is made, it goes on it too."""
    from .giftsheet import brought_now

    from .skill_sharing import share_online

    _, created = Brought.objects.get_or_create(event=event, listing=listing)
    if created:
        brought_now(event, listing)
        transaction.on_commit(lambda: suggest_at(event, listing))
        transaction.on_commit(lambda: share_online(event, listing))
    return created


def take_back(event, listing):
    from .giftsheet import taken_back

    Brought.objects.filter(event=event, listing=listing).delete()
    taken_back(event, listing)


def suggest_at(event, listing, notify=True):
    """Suggest `listing` and the offers and wishes of others who come that fit it to both
    sides, as coming to the same gift-circle. Returns the new suggestions."""
    side = side_of(listing)
    if side is None:
        return []
    people = coming_ids(event) | {event.manager.pk if event.manager else None}
    people.discard(None)
    people.discard(side.owner.pk)
    others = Listing.objects.current().filter(
        owner_id__in=people, community=None, tour=None,
        type=Listing.TYPE_OFFER if listing.is_wish else Listing.TYPE_WISH,
    ).select_related("owner", "skill").prefetch_related("contributions__match")
    created = []
    for other in others:
        other_side = side_of(other)
        if other_side is None or fit(side, other_side) is None:
            continue
        for recipient, shown in ((side, other_side), (other_side, side)):
            suggestion = _suggest(event, recipient, shown)
            if suggestion is not None:
                created.append(suggestion)
    if notify and created:
        from gift_economy.matches.emails import notify_new_suggestions
        notify_new_suggestions({suggestion.user for suggestion in created})
    return created


def suggest_for_newcomer(event, user):
    """Someone came: what others bring may fit their offers and wishes."""
    created = []
    for row in event.brought.exclude(listing__owner=user).select_related("listing__owner"):
        created += suggest_at(event, row.listing, notify=False)
    if created:
        from gift_economy.matches.emails import notify_new_suggestions
        notify_new_suggestions({suggestion.user for suggestion in created})
    return created


def _suggest(event, recipient, shown):
    """The suggestion for recipient's owner, with the gift-circle as its reason. One that
    was already found nearby takes it as its reason too: it is the better one. Returns it
    if it was created."""
    listing_type = ContentType.objects.get_for_model(Listing)
    circle = {
        "reason": Suggestion.REASON_GIFT_CIRCLE, "distance_km": None,
        "detail_type": ContentType.objects.get_for_model(Event), "detail_id": str(event.pk),
    }
    suggestion, created = Suggestion.objects.get_or_create(
        user=recipient.owner,
        own_type=listing_type, own_id=str(recipient.obj.pk), other_type=listing_type, other_id=str(shown.obj.pk),
        defaults={
            "other_user": shown.owner,
            "kind": Suggestion.KIND_GIFT if recipient.is_thing else Suggestion.KIND_SKILLS,
            **circle,
        },
    )
    if not created and suggestion.reason != Suggestion.REASON_GIFT_CIRCLE:
        for field, value in circle.items():
            setattr(suggestion, field, value)
        suggestion.save(update_fields=list(circle))
    return suggestion if created else None


def circle_suggestions(event, user):
    """`user`'s suggestions from this gift-circle that they haven't hidden."""
    return [
        suggestion for suggestion in user.suggestions.filter(
            reason=Suggestion.REASON_GIFT_CIRCLE, dismissed_at=None,
            detail_type=ContentType.objects.get_for_model(Event), detail_id=str(event.pk),
        ) if suggestion.other is not None and suggestion.own is not None
    ]
