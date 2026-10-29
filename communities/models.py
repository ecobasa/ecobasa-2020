from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.gis.db import models
from django.contrib.gis.db.models.functions import SnapToGrid
from django.db.models import Case, Q, When
from django.db.models.functions import Cast
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField

from users.models import User
from users.places import CELL, approximate, town

from embed_video.fields import EmbedVideoField
from taggit.managers import TaggableManager
from taggit.models import TaggedItemBase

from .mixins import UniqueSlugMixin

class TaggedSkills(TaggedItemBase):
    content_object = models.ForeignKey('Community', on_delete=models.CASCADE)

    class Meta:
        app_label = 'communities'

def public_location():
    """Where a community is, for sorting and filtering by place (as a flat geometry): only
    the centre of its cell unless it's public (users.places), so no search finds out more
    than the map shows."""
    location = Cast("location", models.GeometryField(srid=4326))
    return Case(
        When(location_public=True, then=location),
        default=SnapToGrid(location, CELL), output_field=models.GeometryField(srid=4326),
    )


class Community(UniqueSlugMixin, models.Model):
    name = models.CharField(_("Name"), max_length=255)
    slug = models.SlugField(_("Slug"), null=False, blank=True, unique=True) # populated by UniqueSlugMixin
    skills = TaggableManager(_('Skills'),
        through=TaggedSkills, related_name='_skills', blank=True,
        help_text=_('Skills that people can learn by volunteering or staying in your community'))
    description = models.TextField(_("Description"), blank=True)
    vision = models.TextField(_("What brings this community together?"), blank=True)
    accomodation = models.TextField(_("Accomodation for Guests"),  help_text=_('Where can your visitors sleep? Do you have space for a bus, tents? How is the indoor sleeping situation? Do you have mattresses, a couch? Donations or pricing model? Required daily work or experience?'), blank=True)
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
    inhabitants = models.PositiveIntegerField(
        _('How many people live in your community?'),
        null=True, blank=True)
    children = models.PositiveIntegerField(
        _('how many children live at your place?'), null=True, blank=True, default=0)
    max_guests = models.PositiveIntegerField(
        _('Maximum number of people you can host'), null=True, blank=True)
    has_workshop_space = models.TextField(
        _('Do you have workshop spaces where people can build/construct/manufacture things?'), blank=True,
        help_text=_('Describe your workshop spaces and what people can build/construct/manufacture.'))
    offers_seminars = models.TextField(
        _('Do you offer any seminars that visitors could attend?'), blank=True,
        help_text=_('List seminars, topics, and how visitors can join.'))
    visitor_requirements = models.TextField(
        _('Requirements for visitors'), blank=True,
        help_text=_('Anything guests must know before arriving: expectations, minimum length of stay, costs, working hours, house rules.'))
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
    country = CountryField(
        _("Country"), null=True, blank=True)
    location_name = models.CharField(
        _("Location"), null=True, blank=True, max_length=255
    )
    location = models.PointField(
        _("Geo Location"), null=True, blank=True, geography=True
    )
    # Most communities don't want visitors who didn't ask: unless public, others see only
    # roughly where it is (users.places), and its address and phone number once their
    # stay is accepted (shows_place_to)
    location_public = models.BooleanField(
        _("Public: show our exact place, address and phone number to everyone"), default=False,
        help_text=_("Otherwise people see only roughly where you are, and your address and phone number once you have accepted their visit."),
    )
    matches = GenericRelation("matches.Match")

    def __str__(self):
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("communities:detail", kwargs={"slug": self.slug})

    # Same icons as the community map markers
    TYPE_ICONS = {
        COMMUNITY_TYPE_ECOVILLAGE: "fa-people-roof",
        COMMUNITY_TYPE_COMUNE: "fa-house-chimney",
        COMMUNITY_TYPE_HOUSEPROJECT: "fa-house-chimney",
        COMMUNITY_TYPE_FARM: "fa-seedling",
        COMMUNITY_TYPE_PROJECT: "fa-hammer",
    }

    def get_type_icon(self):
        return self.TYPE_ICONS.get(self.type, "fa-house")

    # ── Where it is, and who may know ───────────────────────────────
    @property
    def place_seed(self):
        """Which spot in its cell others see it at (users.places.approximate)."""
        return f"community:{self.pk}"

    @property
    def place_is_public(self):
        return self.location_public

    def shows_place_to(self, user):
        """Whether `user` sees its exact place, address and phone number: everyone if
        it's public, else its members and those whose stay (also with one of its
        projects) was accepted."""
        if self.location_public:
            return True
        if not user.is_authenticated:
            return False
        if user.is_staff or user in self.members():
            return True
        from django.contrib.contenttypes.models import ContentType
        from gift_economy.matches.models import Match
        stays = Q(content_type=ContentType.objects.get_for_model(Community), object_id=str(self.pk)) | Q(
            content_type__app_label="projects", content_type__model="project",
            object_id__in=[str(pk) for pk in self.projects.values_list("pk", flat=True)],
        )
        return Match.objects.filter(stays, from_user=user, status=Match.STATUS_ACCEPTED).exists()

    def rough_place(self):
        """(name, point) as everyone sees it (users.places), unless it's public."""
        if self.location_public:
            return self.location_name, self.location
        return town(self.location_name), approximate(self.location, self.place_seed)

    def place_for(self, user):
        """(name, point) as `user` sees it."""
        return (self.location_name, self.location) if self.shows_place_to(user) else self.rough_place()

    def members(self):
        """Who belongs to the community. For now its ambassador; real membership can
        extend this."""
        return [self.owner] if self.owner_id else []

    def get_reference_subjects(self):
        """What references on this page can be about: the community and its offers and
        wishes (skills you can learn here, things)."""
        return [self, *self.listings.all()]

    def has_skill(self, skill):
        from gift_economy.gifts.models import skill_offers
        return skill_offers(self).filter(skill=skill).exists()

    def add_skill(self, skill):
        from gift_economy.gifts.models import add_skill_offer
        return add_skill_offer(self, skill)

    # ── matches.Match target protocol ───────────────────────────────
    def get_match_owner(self):
        return self.owner

    def get_match_display_name(self):
        return self.name

    def get_match_location(self):
        return self.name, self.location_name, self.location

    def get_match_icon(self):
        return "fa-campground"

    def get_match_verb(self):
        return _("requested to volunteer at")

    def get_match_request_text(self):
        return _("%(actor)s requested a volunteer stay at %(title)s")

    class Meta:
        verbose_name = _("Community")
        verbose_name_plural = _("Communities")
        ordering = ["name"]


class CommunityPhoto(models.Model):
    community = models.ForeignKey(
        Community,
        on_delete=models.CASCADE,
        related_name="photos",
    )
    image = models.ImageField(_('Image'), upload_to='community-images/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"Photo for {self.community.name}"
