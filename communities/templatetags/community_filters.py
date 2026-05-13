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
