from datetime import datetime, time, timedelta

from django import template
from django.conf import settings
from django.contrib.humanize.templatetags.humanize import NaturalTimeFormatter
from django.utils import timezone
from django.utils.timesince import timesince
from django.utils.translation import gettext as _

register = template.Library()


@register.simple_tag
def stadia_key():
    return getattr(settings, 'STADIA_MAPS_KEY', '')


@register.filter
def ago(value):
    """When something happened, roughly and in words: "today", "yesterday", "3 days ago",
    "2 months ago". For "last active" and "updated", where days are precise enough."""
    if not value:
        return ""
    now = timezone.now()
    if not isinstance(value, datetime):
        value = timezone.make_aware(datetime.combine(value, time.min))
    days = (timezone.localdate(now) - timezone.localdate(value)).days
    if days <= 0:
        return _("today")
    if days == 1:
        return _("yesterday")
    # humanize's phrases decline properly ("vor 3 Tagen", "hace 3 días")
    delta = timesince(value, now, time_strings=NaturalTimeFormatter.past_substrings, depth=1)
    return NaturalTimeFormatter.time_strings["past-day"] % {"delta": delta}


@register.filter
def freshness(value):
    """"fresh" (up to two weeks), "recent" (until it counts as stale) or "stale", for
    styling how current something is."""
    if not value:
        return "stale"
    age = timezone.now() - value
    if age <= timedelta(days=14):
        return "fresh"
    if age <= timedelta(days=settings.PROJECT_STALE_DAYS):
        return "recent"
    return "stale"
