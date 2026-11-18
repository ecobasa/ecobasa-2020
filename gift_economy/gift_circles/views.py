from django.shortcuts import get_object_or_404, render

from events import kinds
from events.models import Event

from .timings import timings

# Empty lines on the printed Giftsheet's front (below its heading) and back: one sheet of
# A4, both sides
GIFTSHEET_ROWS = (24, 27)


def print_giftsheet(request, slug):
    """The facilitator card and an empty Giftsheet, to print. Nothing in it is private:
    the title and the day are on the gift-circle's page too."""
    event = get_object_or_404(Event, kind=kinds.GIFT_CIRCLE, slug=slug)
    return render(request, "gift_circles/print.html", {
        "event": event, "timings": timings(event), "pages": [range(rows) for rows in GIFTSHEET_ROWS],
    })
