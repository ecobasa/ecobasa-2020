from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class GiftCirclesConfig(AppConfig):
    """What only gift-circles have, beside the events they are: the emails with the
    instructions, the facilitator card and the Giftsheet."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "gift_economy.gift_circles"
    label = "gift_circles"
    verbose_name = _("Gift-circles")

    def ready(self):
        from . import receivers  # noqa: F401
