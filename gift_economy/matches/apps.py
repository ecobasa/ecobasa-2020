from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MatchesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gift_economy.matches"
    label = "matches"
    verbose_name = _("Matches")

    def ready(self):
        import gift_economy.matches.signals  # noqa: F401
