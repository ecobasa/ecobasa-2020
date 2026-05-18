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

    def __str__(self):
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("gifting:detail", kwargs={"pk": self.pk})

    class Meta:
        verbose_name = _("Ad")
        verbose_name_plural = _("Ads")
        ordering = ["-created_at"]


class AdRequest(models.Model):
    LOC_MY_PLACE   = "my_place"
    LOC_YOUR_PLACE = "your_place"
    LOC_CUSTOM     = "custom"
    LOC_CHOICES = [
        (LOC_MY_PLACE,   _("My place — come pick up / visit me")),
        (LOC_YOUR_PLACE, _("Your place — I will bring it / visit you")),
        (LOC_CUSTOM,     _("Somewhere else")),
    ]

    STATUS_PENDING  = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_COUNTER  = "counter"
    STATUS_CHOICES = [
        (STATUS_PENDING,  _("Pending")),
        (STATUS_ACCEPTED, _("Accepted")),
        (STATUS_DECLINED, _("Declined")),
        (STATUS_COUNTER,  _("Counter-proposed")),
    ]

    ad                = models.ForeignKey(
        Ad, on_delete=models.CASCADE, related_name="requests"
    )
    from_user         = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="ad_requests_sent"
    )
    message           = models.TextField(_("Message"))
    location_type     = models.CharField(
        _("Meeting location"), max_length=20, choices=LOC_CHOICES, default=LOC_YOUR_PLACE
    )
    proposed_location = models.CharField(_("Custom location"), max_length=255, blank=True)
    proposed_lat      = models.FloatField(null=True, blank=True)
    proposed_lon      = models.FloatField(null=True, blank=True)
    proposed_date     = models.DateTimeField(_("Proposed date"), null=True, blank=True)
    status            = models.CharField(
        _("Status"), max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    responded_at      = models.DateTimeField(null=True, blank=True)
    created_at        = models.DateTimeField(auto_now_add=True)

    def get_absolute_url(self):
        return reverse("gifting:adrequest_detail", kwargs={"pk": self.pk})

    def resolved_location(self):
        if self.location_type == self.LOC_MY_PLACE:
            loc = self.from_user.location_name or self.proposed_location or ""
            name = self.from_user.name or self.from_user.email
            return f"{name}'s place — {loc}" if loc else f"{name}'s place"
        if self.location_type == self.LOC_YOUR_PLACE:
            owner = self.ad.owner
            if owner:
                loc = owner.location_name or ""
                name = owner.name or owner.email
                return f"{name}'s place — {loc}" if loc else f"{name}'s place"
        return self.proposed_location or ""

    def location_coords(self):
        if self.proposed_lat and self.proposed_lon:
            return self.proposed_lat, self.proposed_lon
        if self.location_type == self.LOC_MY_PLACE and self.from_user.location:
            return self.from_user.location.y, self.from_user.location.x
        if self.location_type == self.LOC_YOUR_PLACE:
            owner = self.ad.owner
            if owner and owner.location:
                return owner.location.y, owner.location.x
        return None, None

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Ad Request")
        verbose_name_plural = _("Ad Requests")

    def __str__(self):
        return f"Request from {self.from_user} → {self.ad}"


class AdRequestMessage(models.Model):
    """One entry in an AdRequest conversation thread."""
    request      = models.ForeignKey(AdRequest, on_delete=models.CASCADE, related_name="thread")
    sender       = models.ForeignKey(User, on_delete=models.CASCADE, related_name="ad_request_messages")
    body         = models.TextField(_("Message"), blank=True)
    status_to    = models.CharField(
        _("Decision"), max_length=20, blank=True, choices=AdRequest.STATUS_CHOICES
    )
    counter_location_type = models.CharField(max_length=20, blank=True, choices=AdRequest.LOC_CHOICES)
    counter_location      = models.CharField(max_length=255, blank=True)
    counter_lat           = models.FloatField(null=True, blank=True)
    counter_lon           = models.FloatField(null=True, blank=True)
    counter_date          = models.DateTimeField(null=True, blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Ad Request Message")
        verbose_name_plural = _("Ad Request Messages")

    def __str__(self):
        return f"{self.sender} → {self.request} ({self.status_to or 'message'})"

    def resolved_counter_location(self):
        if self.counter_location:
            return self.counter_location
        ar = self.request
        if self.counter_location_type == AdRequest.LOC_MY_PLACE:
            owner = ar.ad.owner
            if owner:
                loc = owner.location_name or ""
                name = owner.name or owner.email
                return f"{name}'s place — {loc}" if loc else f"{name}'s place"
        if self.counter_location_type == AdRequest.LOC_YOUR_PLACE:
            loc = ar.from_user.location_name or ""
            name = ar.from_user.name or ar.from_user.email
            return f"{name}'s place — {loc}" if loc else f"{name}'s place"
        return ""

    def counter_location_coords(self):
        if self.counter_lat and self.counter_lon:
            return self.counter_lat, self.counter_lon
        ar = self.request
        if self.counter_location_type == AdRequest.LOC_MY_PLACE:
            owner = ar.ad.owner
            if owner and owner.location:
                return owner.location.y, owner.location.x
        if self.counter_location_type == AdRequest.LOC_YOUR_PLACE and ar.from_user.location:
            return ar.from_user.location.y, ar.from_user.location.x
        return None, None
