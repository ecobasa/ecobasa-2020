from django import template
from django.conf import settings

register = template.Library()


@register.simple_tag
def stadia_key():
    return getattr(settings, 'STADIA_MAPS_KEY', '')
