from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SuggestionsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "suggestions"
    verbose_name = _("Suggestions")

    def ready(self):
        from . import signals  # noqa: F401
