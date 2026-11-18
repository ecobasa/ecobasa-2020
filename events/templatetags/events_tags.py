from django import template
from django.db.models import F, Q
from django.utils import timezone

from events import kinds
from events.filters import going_to
from events.models import Event

register = template.Library()

# Past events on a profile: the latest few, the rest stays at their addresses
PAST_ON_PROFILE = 5


@register.simple_tag
def event_url(event, name, *args):
    """The address of one of an event's pages: {% event_url event "edit" %}, wherever its
    pages live (Event.url)."""
    return event.url(name, *args)


@register.inclusion_tag("events/_profile_events.html")
def events_of(person):
    """The events of the kinds profiles list that someone hosts (themselves or with their
    tour) or comes to, for their profile: those ahead, the soonest first, then the latest
    past ones, archived too. Each with `hosted`."""
    events = Event.objects.filter(kind__in=kinds.ON_PROFILES).filter(
        Q(pk__in=going_to(person)) | Q(host_user=person) | Q(host_tour__organiser=person)
    ).select_related("community", "host_user", "host_tour__organiser").distinct()
    today = timezone.localdate()
    ahead = events.filter(archived_at=None).filter(Q(ends_on=None) | Q(ends_on__gte=today))
    upcoming = list(ahead.order_by(F("starts_on").asc(nulls_first=True)))
    past = list(events.exclude(pk__in=ahead.values("pk")).order_by(
        F("ends_on").desc(nulls_last=True), "-starts_on"
    )[:PAST_ON_PROFILE])
    for event in upcoming + past:
        event.hosted = event.manager == person
    return {"events": upcoming + past}
