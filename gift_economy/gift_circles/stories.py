"""How a gift-circle went: stories by who came or hosted, each about something, its
destiny: the gift-circle, someone who was there, an offer or wish from its Giftsheet, or
an idea. A story is a reference about that, with the gift-circle as where it happened
(`Reference.place`), so it shows on the gift-circle's page and on the person's, the offer's
or the wish's page too."""

from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.utils.translation import gettext as _

from gift_economy.gifts.models import Listing
from gift_economy.references.models import Reference, with_card_data

from .bringing import coming_ids
from .models import Idea

EVENT = "event"


def destinies(event, user):
    """What `user` can write about, as (value, label) pairs: the gift-circle, the people
    who came and the host, the offers and wishes on its Giftsheet and its ideas, all but
    their own."""
    choices = [(EVENT, _("The gift-circle"))]
    manager = event.manager
    people = get_user_model().objects.filter(pk__in=coming_ids(event) - {user.pk}).order_by("name")
    if manager is not None and manager != user:
        choices.append((f"user:{manager.pk}", _("%(name)s, the host") % {"name": manager.name or manager.email}))
    choices += [(f"user:{person.pk}", person.name or person.email) for person in people if person != manager]
    lines = event.entries.exclude(listing=None).exclude(listing__owner=user).select_related("listing__owner", "from_user", "from_guest")
    for entry in lines:
        listing = entry.listing
        text = _("Offer: %(text)s (%(from)s)") if listing.is_offer else _("Wish: %(text)s (%(from)s)")
        # A wish fulfilled by lending is the lender's offer
        name = entry.from_label if listing.owner_id == entry.from_user_id else listing.owner.name or listing.owner.email
        choices.append((f"listing:{listing.pk}", text % {"text": listing.title, "from": name}))
    for idea in Idea.objects.filter(entry__event=event).exclude(from_user=user).select_related("from_user", "from_guest"):
        choices.append((f"idea:{idea.pk}", _("An idea from %(name)s: %(text)s") % {"name": idea.from_label, "text": idea.text}))
    return choices


def subject_for(event, user, value):
    """What `value` (one of `destinies`) names, or None."""
    if value not in dict(destinies(event, user)):
        return None
    if value == EVENT:
        return event
    kind, _sep, pk = value.partition(":")
    if kind == "user":
        return get_user_model().objects.filter(pk=pk).first()
    if kind == "listing":
        return Listing.objects.filter(pk=pk).first()
    if kind == "idea":
        return Idea.objects.filter(pk=pk).first()
    return None


def _event_q(event, prefix=""):
    event_type = ContentType.objects.get_for_model(event)
    return Q(**{f"{prefix}content_type": event_type, f"{prefix}object_id": str(event.pk)}) | Q(
        **{f"{prefix}place_type": event_type, f"{prefix}place_id": str(event.pk)}
    )


def stories(event):
    """Its stories, the newest first, each saying what it is about unless the gift-circle."""
    found = list(with_card_data(Reference.objects.filter(_event_q(event))))
    event_type = ContentType.objects.get_for_model(event)
    for story in found:
        story.about_other = (story.content_type_id, story.object_id) != (event_type.pk, str(event.pk))
        story.visible_skill_tags = []
    return found


def own_story(event, user, subject):
    """`user`'s story from it about `subject`, to change rather than write twice."""
    subject_type = ContentType.objects.get_for_model(subject)
    own = Reference.objects.filter(author=user, content_type=subject_type, object_id=str(subject.pk))
    if subject == event:
        return own.filter(place_id="").first()
    return own.filter(place_type=ContentType.objects.get_for_model(event), place_id=str(event.pk)).first()


def is_story_of(reference, event):
    return Reference.objects.filter(_event_q(event), pk=reference.pk).exists()
