from django.contrib.gis.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from users.models import User
from .mixins import RandomIdMixin


class AdCategory(models.Model):
    """Category for Ads"""

    name = models.CharField(_("Name"), max_length=50)
    order = models.IntegerField(_("Order"), default="0")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Ad Category")
        verbose_name_plural = _("Ad Categories")
        ordering = ["order", "name"]


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
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="ads",
        verbose_name=_("Owner"),
        null=True,
    )
    categories = models.ManyToManyField(
        AdCategory, related_name="ads", verbose_name=_("Categories"), blank=True
    )
    location_name = models.CharField(
        _("Location"), null=True, blank=True, max_length=255
    )
    location = models.PointField(
        _("Geo Location"), null=True, blank=True, geography=True
    )

    def __str__(self):
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("gifting:detail", kwargs={"pk": self.pk})

    class Meta:
        verbose_name = _("Ad")
        verbose_name_plural = _("Ads")
        ordering = ["-created_at"]
