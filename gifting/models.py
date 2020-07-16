from django.db import models
from django.urls import reverse
from django.utils.translation import ugettext_lazy as _

from .mixins import RandomIdMixin


class Ad(RandomIdMixin, models.Model):
    """An Ad for either an offer or a wish"""

    TYPE_CHOICES = [("offer", _("Offer")), ("wish", _("Wish"))]

    random_id = models.CharField(
        _("Random Id"), max_length=8, primary_key=True, editable=False
    )
    title = models.CharField(_("Title"), max_length=255)
    type = models.CharField(
        _("Type"), choices=TYPE_CHOICES, max_length=5, default="offer"
    )
    description = models.TextField(_("Description"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("gifting:detail", kwargs={"pk": self.pk})

    class Meta:
        verbose_name = _("Ad")
        verbose_name_plural = _("Ads")
        ordering = ["-created_at"]
