from django import template

register = template.Library()


@register.simple_tag
def event_url(event, name, *args):
    """The address of one of an event's pages: {% event_url event "edit" %}, wherever its
    pages live (Event.url)."""
    return event.url(name, *args)
