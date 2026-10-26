from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.gis.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from users.models import User
from . import units
from .mixins import RandomIdMixin


class ListingCategory(models.Model):
    """Category for Listings"""

    name = models.CharField(_("Name"), max_length=50)
    order = models.IntegerField(_("Order"), default="0")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Listing Category")
        verbose_name_plural = _("Listing Categories")
        ordering = ["order", "name"]


class Listing(RandomIdMixin, models.Model):
    """A Listing for either an offer or a wish"""

    TYPE_CHOICES = [("offer", _("Offer")), ("wish", _("Wish"))]

    random_id = models.CharField(
        _("Random Id"), max_length=8, primary_key=True, editable=False
    )
    title = models.CharField(_("Title"), max_length=255)
    type = models.CharField(
        _("Type"), choices=TYPE_CHOICES, max_length=5, default="offer"
    )
    description = models.TextField(_("Description"), blank=True)
    image = models.ImageField(_('image'), upload_to='gifts-images', null=True, blank=True)
    quantity = models.PositiveIntegerField(_("How many / how much?"), null=True, blank=True)
    unit = models.CharField(_("Unit"), max_length=10, choices=units.UNIT_CHOICES, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="listings",
        verbose_name=_("Owner"),
        null=True,
    )
    categories = models.ManyToManyField(
        ListingCategory, related_name="listings", verbose_name=_("Categories"), blank=True
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
        return reverse("gifts:detail", kwargs={"pk": self.pk})

    @property
    def amount(self):
        """"200 kg", "3 pieces", "" if no quantity is given."""
        return units.format_amount(self.quantity, self.unit)

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

    def get_match_request_text(self):
        if self.type == "offer":
            return _("%(actor)s is interested in your offer: %(title)s")
        return _("%(actor)s wants to fulfill your wish: %(title)s")

    class Meta:
        verbose_name = _("Listing")
        verbose_name_plural = _("Listings")
        ordering = ["-created_at"]
