from django.contrib.gis.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from users.models import User

from embed_video.fields import EmbedVideoField
from taggit.managers import TaggableManager
from taggit.models import TaggedItemBase

from .mixins import UniqueSlugMixin

class TaggedCommunity(TaggedItemBase):
    content_object = models.ForeignKey('Community', on_delete=models.CASCADE)

    class Meta:
        app_label = 'communities'

class TaggedSkills(TaggedItemBase):
    content_object = models.ForeignKey('Community', on_delete=models.CASCADE)

    class Meta:
        app_label = 'communities'

class Community(UniqueSlugMixin, models.Model):
    name = models.CharField(_("Name"), max_length=255)
    slug = models.SlugField(_("Slug"), null=False, blank=True, unique=True) # populated by UniqueSlugMixin
    tags = TaggableManager(_('Tags'),
        through=TaggedCommunity, related_name='_tags', blank=True,
        help_text=_('Add some keywords that define your community. This way your profile can be found by in the search. People might be interested in your technologies, structures or experiences.'))
    skills = TaggableManager(_('Skills'),
        through=TaggedSkills, related_name='_skills', blank=True,
        help_text=_('Skills that people can learn by volunteering or staying in your community'))
    description = models.TextField(_("Description"), blank=True)
    vision = models.TextField(_("What brings this community together?"), blank=True)
    accomodation = models.TextField(_("Accomodation for Guests"),  help_text=_('Where can your visitors sleep? Do you have space for a bus, tents? How is the indoor sleeping situation? Do you have matresses, a couch? Do you have a donations or a pricing model? Required daily working amount or epxeriences?'), blank=True)
    website = models.URLField(_('link of your communities website'), max_length=250,
        blank=True, null=True)
    telephone = models.CharField(_('telephone'),
        max_length=255, 
        blank=True, 
        null=True)
    video = EmbedVideoField(
        verbose_name=_('Video'),
        help_text=_('Link to a video showing your community'),
        max_length=255,
        blank=True,
        null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    owner = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="communities",
        verbose_name=_("Owner"),
        null=True,
    )
    inhabitants = models.CharField(
        _('how many people live in your community?'),
        max_length=255, null=True, blank=True)
    children = models.PositiveIntegerField(
        _('how many children live at your place?'), null=True, blank=True, default=0)
    COMMUNITY_STATUS_PLANNING = 'p'
    COMMUNITY_STATUS_STARTING = 's'
    COMMUNITY_STATUS_ESTABLISHED = 'e'
    COMMUNITY_STATUS_LAND = 'l'
    COMMUNITY_STATUS_CHOICES = (
        (COMMUNITY_STATUS_PLANNING, _('Future Project (looking for co-founders)')),
        (COMMUNITY_STATUS_STARTING, _('Starting Project (first years)')),
        (COMMUNITY_STATUS_ESTABLISHED, _('Established (+4 years)')),
    )
    status = models.CharField(_('Project status'),
        max_length=2,
        blank=True,
        choices=COMMUNITY_STATUS_CHOICES,
        default=COMMUNITY_STATUS_ESTABLISHED)

    COMMUNITY_TYPE_ECOVILLAGE = 'e'
    COMMUNITY_TYPE_COMUNE = 'c'
    COMMUNITY_TYPE_HOUSEPROJECT = 'h'
    COMMUNITY_TYPE_FARM = 'f'
    COMMUNITY_TYPE_PROJECT = 'p'
    COMMUNITY_TYPE_CHOICES = (
        (COMMUNITY_TYPE_ECOVILLAGE, _('Ecovillage')),
        (COMMUNITY_TYPE_COMUNE, _('Commune')),
        (COMMUNITY_TYPE_HOUSEPROJECT, _('Houseproject')),
        (COMMUNITY_TYPE_FARM, _('Permaculture Farm')),
        (COMMUNITY_TYPE_PROJECT, _('Place for Projects')),
    )
    type = models.CharField(_('Type of community'),
        max_length=2,
        blank=True,
        choices=COMMUNITY_TYPE_CHOICES,
        default=COMMUNITY_TYPE_ECOVILLAGE)
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
