import re
from django import template

register = template.Library()


@register.filter
def rough_location(location_name):
    """Return the last 2 meaningful parts of a Nominatim location string.

    'Hauptstraße 5, Potsdam, 14473, Brandenburg, Germany' → 'Brandenburg, Germany'
    'Potsdam, Brandenburg, Germany'                       → 'Brandenburg, Germany'
    'Bavaria, Germany'                                    → 'Bavaria, Germany'
    'Italy'                                               → 'Italy'
    """
    if not location_name:
        return ''
    parts = [p.strip() for p in location_name.split(',')]
    meaningful = [p for p in parts if p and not re.match(r'^\d[\d\s\-]*$', p)]
    return ', '.join(meaningful[-2:]) if len(meaningful) >= 2 else ', '.join(meaningful)


@register.simple_tag
def applications_visiting(match, viewer):
    """The membership applications a stay at a community is the visit for, as `viewer`
    may see them (Community.applications_visiting)."""
    community = match.target
    return community.applications_visiting(match, viewer) if community is not None else []


@register.filter
def visit_waits_for(membership, user):
    """Whether `user` is asked to accept the days proposed last for the visit."""
    return membership.visit_waits_for(user)


@register.filter
def can_propose_visit(membership, user):
    """Whether `user` may propose days for the visit."""
    return membership.can_propose_visit(user)
