from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.gis.db import models
from django.contrib.gis.db.models.functions import SnapToGrid
from django.db.models import Case, Exists, OuterRef, Q, Subquery, Sum, When
from django.db.models.functions import Cast, Coalesce
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from users.places import CELL, approximate, town

from . import units
from .mixins import RandomIdMixin
# The skill vocabulary is part of this app (its models live in gifts/skills/)
from .skills.models import Skill, SkillTaxonomy  # noqa: F401


def public_spot():
    """Where a listing is, for sorting and filtering by place (as a flat geometry): its own
    place, else its community's or person's (Listing.place), only as the centre of its
    cell unless it's public (users.places), so no search finds out more than the map shows."""
    holder = Case(When(community__isnull=False, then="community__location"), default="owner__location")
    spot = Cast(Coalesce("location", holder), models.GeometryField(srid=4326))
    public = (
        Q(location__isnull=False, location_public=True) | Q(location__isnull=False, public_good=True)
        | Q(location__isnull=True, community__location_public=True)
    )
    return Case(
        When(public, then=spot),
        default=SnapToGrid(spot, CELL), output_field=models.GeometryField(srid=4326),
    )


class ListingCategory(models.Model):
    """The area of life a thing belongs to, in a theme. Whether it is a material or a tool
    is its kind (Listing.kind), so a category holds both: a scythe and seeds are both
    Garden & Farm. The curated list is in the load_listing_categories command."""

    THEME_LAND = "land"
    THEME_BUILDING = "building"
    THEME_HOME = "home"
    THEME_MOVE = "move"
    THEME_CULTURE = "culture"
    THEME_CHOICES = [
        (THEME_LAND, _("Land & Food")),
        (THEME_BUILDING, _("Building & Energy")),
        (THEME_HOME, _("Home & Living")),
        (THEME_MOVE, _("On the Move")),
        (THEME_CULTURE, _("Culture & Learning")),
    ]
    THEME_ICONS = {
        THEME_LAND: "fa-wheat-awn", THEME_BUILDING: "fa-house-chimney", THEME_HOME: "fa-mug-hot",
        THEME_MOVE: "fa-route", THEME_CULTURE: "fa-masks-theater",
    }

    slug = models.SlugField(_("Slug"), max_length=50, unique=True)
    name = models.CharField(_("Name"), max_length=50)
    # The name in other languages, e.g. {"de": "Garten & Hof"}; English is the name
    names = models.JSONField(_("Names"), default=dict, blank=True)
    theme = models.CharField(_("Theme"), max_length=20, choices=THEME_CHOICES, default=THEME_HOME)
    # A Font Awesome icon, e.g. "fa-seedling"
    icon = models.CharField(_("Icon"), max_length=40, default="fa-gift")
    # Across all themes, so a theme's categories stay together
    order = models.IntegerField(_("Order"), default="0")

    def __str__(self):
        return self.get_name()

    def get_name(self, lang=None):
        from django.utils.translation import get_language
        lang = (lang or get_language() or "en").split("-")[0]
        return self.names.get(lang) or self.name

    @property
    def theme_icon(self):
        return self.THEME_ICONS.get(self.theme, "fa-gift")

    class Meta:
        verbose_name = _("Listing Category")
        verbose_name_plural = _("Listing Categories")
        ordering = ["order", "name"]


def themed_choices(categories):
    """Categories as choices grouped by their themes, e.g. for a select's optgroups."""
    groups = {}
    for category in categories:
        groups.setdefault(category.get_theme_display(), []).append((category.pk, str(category)))
    return list(groups.items())


class ListingQuerySet(models.QuerySet):
    def skills(self):
        """Skills, knowledge and helping hands (with or without a known skill)."""
        return self.filter(kind__in=Listing.SKILL_KINDS)

    def things(self):
        return self.filter(kind__in=Listing.THING_KINDS)

    def current(self):
        """Not marked as covered, and not part of a project that is archived or over."""
        today = timezone.localdate()
        return self.filter(covered_at=None).filter(
            Q(project=None) | Q(project__archived_at=None) & (Q(project__ends_on=None) | Q(project__ends_on__gte=today))
        )

    def open(self):
        """Current, and not yet given or promised in full (see Listing.status)."""
        from gift_economy.matches.models import Contribution, Match
        accepted = Contribution.objects.filter(listing=OuterRef("pk"), match__status=Match.STATUS_ACCEPTED)
        promised = accepted.order_by().values("listing").annotate(total=Sum("quantity")).values("total")
        used_up = Exists(accepted) & (
            Q(quantity=None)
            | Exists(accepted.filter(quantity=None))
            | Q(quantity__lte=Coalesce(Subquery(promised), 0))
        )
        return self.current().exclude(Q(kind__in=Listing.USED_UP_KINDS) | Q(type=Listing.TYPE_WISH, kind__in=Listing.NEED_KINDS), used_up)

    def of(self, holder):
        """What a person or a community offers and wishes for (its projects' too)."""
        from communities.models import Community
        return self.filter(community=holder) if isinstance(holder, Community) else self.filter(owner=holder, community=None)


class Listing(RandomIdMixin, models.Model):
    """Everything someone offers or wishes for: things (material, tools, anything else),
    skills, knowledge and helping hands. A person's, or a community's (managed by its
    ambassador). A community's wish can belong to one of its projects: then it is a
    need of the project, and is listed only while the project runs.

    With a quantity ("200 kg", "3 people") a wish can be covered in parts, and an offer
    given away in parts: each exchange (Match) says how much of it it takes or brings
    (matches.Contribution)."""

    TYPE_OFFER = "offer"
    TYPE_WISH = "wish"
    TYPE_CHOICES = [(TYPE_OFFER, _("Offer")), (TYPE_WISH, _("Wish"))]
    TYPE_ICONS = {TYPE_OFFER: "fa-gift", TYPE_WISH: "fa-heart"}
    TYPE_COLOURS = {TYPE_OFFER: "bg-primary", TYPE_WISH: "bg-yellow"}

    KIND_MATERIAL = "material"
    KIND_TOOL = "tool"
    KIND_OTHER = "other"
    # Offered: a skill they share or teach. Wished for: a skill they want to learn by doing.
    KIND_SKILL = "skill"
    KIND_KNOWLEDGE = "knowledge"
    KIND_HANDS = "hands"
    KIND_CHOICES = [
        (KIND_MATERIAL, _("Material")),
        (KIND_TOOL, _("Tool")),
        (KIND_OTHER, _("Other")),
        (KIND_SKILL, _("Skill")),
        (KIND_KNOWLEDGE, _("Knowledge")),
        (KIND_HANDS, _("Helping hands")),
    ]
    THING_KINDS = (KIND_MATERIAL, KIND_TOOL, KIND_OTHER)
    SKILL_KINDS = (KIND_SKILL, KIND_KNOWLEDGE, KIND_HANDS)
    # Given away once (in parts, with a quantity); skills, knowledge and helping hands
    # can be shared again and again
    USED_UP_KINDS = THING_KINDS
    # Wishes for knowledge or helping hands are met once someone comes; wanting to learn
    # a skill stays until its owner says otherwise
    NEED_KINDS = (KIND_KNOWLEDGE, KIND_HANDS)
    KIND_ICONS = {
        KIND_MATERIAL: "fa-cubes", KIND_TOOL: "fa-screwdriver-wrench", KIND_OTHER: "fa-gift",
        KIND_SKILL: "fa-graduation-cap", KIND_KNOWLEDGE: "fa-lightbulb", KIND_HANDS: "fa-handshake-angle",
    }
    # Pill colour: skills purple, things in the primary colour
    KIND_COLOURS = {kind: "bg-purple" for kind in SKILL_KINDS}
    # Font Awesome code points for map markers: the kind, else a gift (offer) or heart (wish)
    KIND_GLYPHS = {
        KIND_MATERIAL: 0xF1B3, KIND_TOOL: 0xF7D9, KIND_SKILL: 0xF19D, KIND_KNOWLEDGE: 0xF0EB, KIND_HANDS: 0xF4C4,
    }

    LEVEL_BEGINNER = "beginner"
    LEVEL_INTERMEDIATE = "intermediate"
    LEVEL_ADVANCED = "advanced"
    LEVEL_EXPERT = "expert"
    LEVEL_CHOICES = [
        (LEVEL_BEGINNER, _("Beginner")),
        (LEVEL_INTERMEDIATE, _("Intermediate")),
        (LEVEL_ADVANCED, _("Advanced")),
        (LEVEL_EXPERT, _("Expert")),
    ]

    STATUS_OPEN = "open"
    STATUS_OFFERED = "offered"
    STATUS_PROMISED = "promised"
    STATUS_COVERED = "covered"

    random_id = models.CharField(
        _("Random Id"), max_length=8, primary_key=True, editable=False
    )
    type = models.CharField(
        _("Type"), choices=TYPE_CHOICES, max_length=5, default=TYPE_OFFER
    )
    kind = models.CharField(_("Kind"), max_length=10, choices=KIND_CHOICES, default=KIND_OTHER)
    # Set for a skill, and for knowledge or helping hands with a known skill (in any
    # language, see skills.models.get_or_create_skill): matched by it, not by the title
    skill = models.ForeignKey(
        "gifts.Skill", on_delete=models.CASCADE, null=True, blank=True, related_name="listings",
        verbose_name=_("Skill"),
    )
    title = models.CharField(_("Title"), max_length=255, blank=True)
    description = models.TextField(_("Description"), blank=True)
    image = models.ImageField(_('image'), upload_to='gifts-images', null=True, blank=True)
    quantity = models.PositiveIntegerField(_("How many / how much?"), null=True, blank=True)
    unit = models.CharField(_("Unit"), max_length=10, choices=units.UNIT_CHOICES, blank=True)
    # Skills: the level they have (offer) or have so far (wish); a community's: the
    # level it looks for
    level = models.CharField(_("Level"), max_length=20, choices=LEVEL_CHOICES, blank=True)
    available = models.BooleanField(_("Available to teach / share"), default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    # A person's listing. A community's has no owner: its ambassador manages it.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="listings",
        verbose_name=_("Owner"),
        null=True, blank=True,
    )
    community = models.ForeignKey(
        "communities.Community", on_delete=models.CASCADE, null=True, blank=True, related_name="listings",
        verbose_name=_("Community"),
    )
    # A community's need (or what you can learn) in one of its projects
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, null=True, blank=True, related_name="listings",
        verbose_name=_("Project"),
    )
    categories = models.ManyToManyField(
        ListingCategory, related_name="listings", verbose_name=_("Categories"), blank=True
    )
    location_name = models.CharField(
        _("Location"), null=True, blank=True, max_length=255
    )
    # Its own place, if it isn't where its person or community is
    location = models.PointField(
        _("Geo Location"), null=True, blank=True, geography=True
    )
    # Something found out there (a fruit tree, wood in the forest), offers of things only: nobody
    # needs to ask for it, everybody may edit and delete it, and its place is exact
    public_good = models.BooleanField(
        _("Public good"), default=False,
        help_text=_("For things found out there, like a fruit tree or wood in the forest. Doesn't need to be requested and accepted. Everybody can edit and delete it."),
    )
    # Its own place exactly for everyone. Otherwise others see only roughly where it is
    # (users.places).
    location_public = models.BooleanField(
        _("Show this place exactly — nobody lives here"), default=False,
        help_text=_("Otherwise others see only roughly where it is until a match is accepted."),
    )
    # Marked as covered (a wish) or given away (an offer) by its owner, however it was
    covered_at = models.DateTimeField(_("Covered"), null=True, blank=True)
    # Order among a project's needs
    order = models.PositiveSmallIntegerField(default=0)
    matches = GenericRelation("matches.Match")

    objects = ListingQuerySet.as_manager()

    class Meta:
        verbose_name = _("Listing")
        verbose_name_plural = _("Listings")
        ordering = ["-created_at"]
        constraints = [
            # A person or community has a skill (or wants it) once; projects list theirs apart
            models.UniqueConstraint(
                fields=["owner", "type", "skill"], name="one_skill_listing_per_person",
                condition=Q(kind="skill", community=None),
            ),
            models.UniqueConstraint(
                fields=["community", "type", "skill"], name="one_skill_listing_per_community",
                condition=Q(kind="skill", project=None, community__isnull=False),
            ),
        ]

    def __str__(self):
        return self.display_title

    def save(self, *args, **kwargs):
        if self.project_id:
            self.community_id = self.project.community_id
        if self.community_id:
            self.owner = None
        if self.skill_id and not self.title:
            self.title = self.skill.name
        super().save(*args, **kwargs)

    def get_absolute_url(self) -> str:
        return reverse("gifts:detail", kwargs={"pk": self.pk})

    def get_edit_url(self):
        return reverse("gifts:edit", kwargs={"pk": self.pk})

    # ── What it is ──────────────────────────────────────────────────
    @property
    def is_offer(self):
        return self.type == self.TYPE_OFFER

    @property
    def is_wish(self):
        return self.type == self.TYPE_WISH

    @property
    def is_skill(self):
        """Skills, knowledge and helping hands, as opposed to things."""
        return self.kind in self.SKILL_KINDS

    @property
    def is_thing(self):
        return self.kind in self.THING_KINDS

    @property
    def display_title(self):
        """The skill's name in the reader's language, else the title."""
        return self.skill.get_name() if self.skill_id else self.title

    @property
    def kind_icon(self):
        return self.KIND_ICONS.get(self.kind, "fa-gift")

    @property
    def kind_label(self):
        """The kind in words, by which side it is on: "Skill" offered, "Learn a skill" wished."""
        if self.kind == self.KIND_SKILL and self.is_wish:
            return _("Learn a skill") if self.owner_id else _("Skill")
        return self.get_kind_display()

    @property
    def colour(self):
        return self.KIND_COLOURS.get(self.kind, "bg-primary")

    @property
    def marker_glyph(self):
        return self.KIND_GLYPHS.get(self.kind) or (0xF004 if self.is_wish else 0xF06B)

    @property
    def amount(self):
        """"200 kg", "3 pieces", "" if no quantity is given."""
        return units.format_amount(self.quantity, self.unit)

    def format_amount(self, quantity):
        return units.format_amount(quantity, self.unit)

    # ── Whose it is ─────────────────────────────────────────────────
    @property
    def holder(self):
        """The person or community it belongs to."""
        return self.community if self.community_id else self.owner

    @property
    def manager(self):
        """The person who answers for it: its owner, or the community's ambassador."""
        return self.community.owner if self.community_id else self.owner

    def can_edit(self, user):
        """Its manager (and staff), and for a public good every member."""
        return user.is_authenticated and (self.public_good or self.is_managed_by(user))

    def is_managed_by(self, user):
        return user.is_authenticated and (user.is_staff or user == self.manager)

    @property
    def place(self):
        """(name, point) of where it is: its own place, else its person's or community's."""
        if self.location:
            return self.location_name, self.location
        holder = self.holder
        if holder is None:
            return "", None
        return holder.location_name, holder.location

    @property
    def point(self):
        return self.place[1]

    # ── Where it is, and who may know (users.places) ────────────────
    @property
    def place_seed(self):
        return self.community.place_seed if self.community_id else self.owner_id

    @property
    def place_is_public(self):
        if self.location:
            return self.location_public or self.public_good
        return self.community_id is not None and self.community.location_public

    @property
    def public_place(self):
        """(name, point) as everyone sees it: only roughly, unless it's public."""
        name, point = self.place
        if self.place_is_public:
            return name, point
        return town(name), approximate(point, self.place_seed)

    def place_for(self, user):
        """(name, point) as `user` sees it: exactly if they look after it, or it's their
        community's and they may know where that is."""
        if self.can_edit(user) or self.community_id and not self.location and self.community.shows_place_to(user):
            return self.place
        return self.public_place

    @property
    def country(self):
        holder = self.holder
        return str(holder.country or "") if holder is not None else ""

    @property
    def holder_name(self):
        holder = self.holder
        if holder is None:
            return ""
        return getattr(holder, "name", "") or getattr(holder, "username", "") or ""

    # ── How far it is covered ───────────────────────────────────────
    def _contributions_by_status(self):
        """(accepted, waiting) contributions to it, each with its match."""
        from gift_economy.matches.models import Match
        contributions = list(self.contributions.all())
        accepted = [c for c in contributions if c.match.status == Match.STATUS_ACCEPTED]
        waiting = [c for c in contributions if c.match.status in (Match.STATUS_PENDING, Match.STATUS_COUNTER)]
        return accepted, waiting

    @staticmethod
    def _sum(contributions):
        return sum(c.quantity for c in contributions if c.quantity)

    @property
    def can_run_out(self):
        """Whether exchanges use it up: things, and wishes for knowledge or helping hands.
        A skill can be shared again and again, and someone can keep learning one."""
        return self.kind in self.USED_UP_KINDS or (self.is_wish and self.kind in self.NEED_KINDS)

    @property
    def promised_quantity(self):
        return self._sum(self._contributions_by_status()[0])

    @property
    def offered_quantity(self):
        return self._sum(self._contributions_by_status()[1])

    @property
    def remaining(self):
        """How much is still left (an offer) or missing (a wish), if it has a quantity."""
        if self.quantity is None:
            return None
        return max(self.quantity - self.promised_quantity, 0)

    @property
    def status(self):
        """covered (marked by its owner) > promised (accepted exchanges take or bring all
        of it) > offered (an exchange waits for an answer, or accepted ones cover only a
        part) > open.

        With a quantity, accepted exchanges cover it once they add up to it; one that
        doesn't say how much covers it on its own. What can't run out (a skill) stays
        open, however often it is shared."""
        if self.covered_at:
            return self.STATUS_COVERED
        accepted, waiting = self._contributions_by_status()
        if self.can_run_out and accepted and (
            self.quantity is None
            or any(c.quantity is None for c in accepted)
            or self._sum(accepted) >= self.quantity
        ):
            return self.STATUS_PROMISED
        if waiting or accepted:
            return self.STATUS_OFFERED
        return self.STATUS_OPEN

    @property
    def is_done(self):
        return self.status in (self.STATUS_COVERED, self.STATUS_PROMISED)

    @property
    def is_current(self):
        """Still listed: not done, and its project (if any) still runs."""
        return not self.is_done and (self.project_id is None or self.project.is_current)

    @property
    def progress(self):
        """"120 of 200 kg promised" while accepted exchanges cover a part of a quantity."""
        if self.quantity is None or self.is_done:
            return ""
        promised = self.promised_quantity
        if not promised:
            return ""
        return _("%(promised)s of %(amount)s promised") % {
            "promised": promised, "amount": self.format_amount(self.quantity),
        }

    @property
    def promises(self):
        """The accepted contributions, each with its match (and so the person) and how much."""
        return self._contributions_by_status()[0]

    def promised_by(self):
        return [c.match.from_user for c in self.promises]

    # ── matches.Match target protocol ───────────────────────────────
    def get_match_owner(self):
        return self.manager

    def get_match_display_name(self):
        return self.display_title

    def get_match_location(self):
        holder = self.holder
        if holder is None:
            return "", None, None
        name, point = self.place
        if self.community_id:
            return holder.name, name, point
        return f"{holder.name or holder.email}'s place", name, point

    def get_match_icon(self):
        return self.kind_icon

    def get_match_verb(self):
        if self.is_wish:
            return _("offered to help with your wish") if self.is_skill else _("wants to fulfill your wish")
        return _("is interested in your skill") if self.is_skill else _("is interested in your offer")

    def get_match_request_text(self):
        if self.is_wish:
            if self.is_skill:
                return _("%(actor)s offered to help with: %(title)s")
            return _("%(actor)s wants to fulfill your wish: %(title)s")
        if self.is_skill:
            return _("%(actor)s is interested in your skill: %(title)s")
        return _("%(actor)s is interested in your offer: %(title)s")

    # ── references protocol ─────────────────────────────────────────
    def get_skill_holder(self):
        """Who a skill offer's references (and skills tagged on them) belong to."""
        return self.holder if self.skill_id and self.is_offer else None


# ── Skills of a person or community ─────────────────────────────────

def _holder_fields(holder):
    from communities.models import Community
    return {"community": holder} if isinstance(holder, Community) else {"owner": holder, "community": None}


def skill_offers(holder):
    """The skills a person or community offers (its projects' ones too)."""
    return Listing.objects.of(holder).filter(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL)


def add_skill_offer(holder, skill):
    """The holder's offer of the skill, created if needed."""
    return Listing.objects.get_or_create(
        type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL, skill=skill, project=None, **_holder_fields(holder),
    )[0]


def wish_kind_for(holder):
    """A person wants to learn a skill; a community looks for people with it."""
    from communities.models import Community
    return Listing.KIND_HANDS if isinstance(holder, Community) else Listing.KIND_SKILL


def sync_skill_listings(holder, type, names):
    """Make the holder's skills (type offer) or skill wishes (type wish) outside projects
    the ones named, in any language, keeping the ones that stay. Removing and re-adding
    them all on every save would make them look new each time (and be matched and
    announced again)."""
    from gift_economy.gifts.skills.models import get_or_create_skill
    kind = Listing.KIND_SKILL if type == Listing.TYPE_OFFER else wish_kind_for(holder)
    fields = {"type": type, "kind": kind, "project": None, **_holder_fields(holder)}
    wanted = {get_or_create_skill(name)[0].pk for name in names}
    listings = Listing.objects.filter(**fields).exclude(skill=None)
    listings.exclude(skill_id__in=wanted).delete()
    for skill_id in wanted - set(listings.values_list("skill_id", flat=True)):
        Listing.objects.create(skill_id=skill_id, **fields)
