from django import template

from .. import bringing, giftsheet
from ..models import Attendee, Scribe

register = template.Library()


@register.simple_tag
def keeps_on_ecobasa(event, user):
    """Whether `user` said yes to keeping their offers and wishes from it on ecobasa."""
    if not user.is_authenticated:
        return False
    return Attendee.objects.filter(event=event, user=user, keep_on_ecobasa=True).exists()


@register.simple_tag
def sees_giftsheet(event, user):
    """Whether `user` may open its Giftsheet: who comes, its host and scribes."""
    return giftsheet.may_see(event, user)


@register.simple_tag
def is_scribe(event, user):
    return Scribe.objects.filter(event=event, user=user).exists()


@register.simple_tag
def brought_to(event, user):
    """What its page shows of what people bring: the offers and wishes, whether `user`
    sees who brings them (logged in) and what was promised among who comes (who comes
    and the host), and what of theirs they could still bring."""
    offers, wishes = bringing.brought(event)
    is_in = bringing.is_in(event, user)
    may_bring = event.is_current and is_in
    own = []
    if may_bring:
        taken = {listing.pk for listing in offers + wishes}
        own = [listing for listing in bringing.own_listings(user).select_related("skill") if listing.pk not in taken]
    return {
        "offers": offers, "wishes": wishes, "names": user.is_authenticated, "promises": is_in,
        "may_bring": may_bring, "own": own,
    }


@register.inclusion_tag("gift_circles/_bring_to.html", takes_context=True)
def bring_to_gift_circles(context, listing):
    """On an offer or wish of one's own: bring it to the gift-circles ahead one comes to
    or hosts, or take it back."""
    request = context["request"]
    user = request.user
    circles = []
    if user.is_authenticated and listing.owner_id == user.pk and not listing.community_id and not listing.tour_id and listing.is_current:
        circles = list(bringing.gift_circles_of(user))
        brought = set(listing.brought_to.filter(event__in=circles).values_list("event_id", flat=True))
        for circle in circles:
            circle.has_it = circle.pk in brought
    return {"circles": circles, "listing": listing, "request": request, "csrf_token": context.get("csrf_token")}
