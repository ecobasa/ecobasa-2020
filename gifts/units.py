"""Units for amounts, shared by gift listings and project needs, so "200 kg" means the
same everywhere and gifts can be matched to needs."""

from django.utils.translation import gettext_lazy as _, ngettext_lazy

PEOPLE = "people"

UNIT_CHOICES = [
    (PEOPLE, _("people")),
    ("pieces", _("pieces")),
    ("kg", "kg"),
    ("m", "m"),
    ("m2", "m²"),
    ("m3", "m³"),
    ("l", _("litres")),
    ("days", _("days")),
]

# Units that read as a count of something, in the right singular or plural
_COUNTED = {
    PEOPLE: ngettext_lazy("%(count)s person", "%(count)s people", "count"),
    "pieces": ngettext_lazy("%(count)s piece", "%(count)s pieces", "count"),
    "l": ngettext_lazy("%(count)s litre", "%(count)s litres", "count"),
    "days": ngettext_lazy("%(count)s day", "%(count)s days", "count"),
}


def format_amount(quantity, unit):
    """"1 person", "3 people", "200 kg", "4" (no unit); "" without a quantity."""
    if quantity is None:
        return ""
    if unit in _COUNTED:
        return _COUNTED[unit] % {"count": quantity}
    return f"{quantity} {dict(UNIT_CHOICES)[unit]}" if unit else str(quantity)
