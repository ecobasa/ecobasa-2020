from django import template

from ..models import Attendee

register = template.Library()


@register.simple_tag
def keeps_on_ecobasa(event, user):
    """Whether `user` said yes to keeping their offers and wishes from it on ecobasa."""
    if not user.is_authenticated:
        return False
    return Attendee.objects.filter(event=event, user=user, keep_on_ecobasa=True).exists()
