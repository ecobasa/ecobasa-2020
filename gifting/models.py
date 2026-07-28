from django.contrib.contenttypes.fields import GenericRelation
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
    image = models.ImageField(_('image'), upload_to='gifting-images', null=True, blank=True)
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
    matches = GenericRelation("matches.Match")

    def __str__(self):
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("gifting:detail", kwargs={"pk": self.pk})

    # ── matches.Match target protocol ───────────────────────────────
    def get_match_owner(self):
        return self.owner

    def get_match_display_name(self):
        return self.title

    def get_match_location(self):
        owner = self.owner
        if not owner:
            return "", None, None
        label = f"{owner.name or owner.email}'s place"
        return label, owner.location_name, owner.location

    def get_match_icon(self):
        return "fa-hand-holding-heart" if self.type == "wish" else "fa-hand-point-up"

    def get_match_verb(self):
        return _("is interested in your offer") if self.type == "offer" else _("wants to fulfill your wish")

    class Meta:
        verbose_name = _("Ad")
        verbose_name_plural = _("Ads")
        ordering = ["-created_at"]
