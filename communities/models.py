from django.contrib.gis.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from users.models import User

from .mixins import UniqueSlugMixin


class Community(UniqueSlugMixin, models.Model):
    name = models.CharField(_("Name"), max_length=255)
    slug = models.SlugField(_("Slug"), null=False, blank=True, unique=True) # populated by UniqueSlugMixin

    description = models.TextField(_("Description"), blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="communities",
        verbose_name=_("Owner"),
        null=True,
    )
    # location_name = models.CharField(
    #     _("Location"), null=True, blank=True, max_length=255
    # )
    # location = models.PointField(
    #     _("Geo Location"), null=True, blank=True, geography=True
    # )

    def __str__(self):
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("communities:detail", kwargs={"slug": self.slug})

    class Meta:
        verbose_name = _("Community")
        verbose_name_plural = _("Communities")
        ordering = ["name"]
