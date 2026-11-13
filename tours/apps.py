from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ToursConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tours"
    verbose_name = _("Community-Tours")

    def ready(self):
        from . import signals  # noqa: F401
