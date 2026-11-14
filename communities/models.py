from django.conf.locale import LANG_INFO
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.gis.db import models
from django.contrib.gis.db.models.functions import SnapToGrid
from django.contrib.postgres.fields import ArrayField
from django.core.validators import FileExtensionValidator
from django.db.models import Case, Q, When
from django.db.models.functions import Cast
from django.urls import reverse
from django.utils.translation import gettext, gettext_lazy as _, ngettext
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

def language_name(code):
    """A language's name in the current language ("" for an unknown code)."""
    info = LANG_INFO.get(code, {})
    return gettext(info["name"]) if "name" in info else ""


def language_choices():
    """(code, name) for every language Django knows, by name in the current language."""
    return sorted(
        ((code, language_name(code)) for code, info in LANG_INFO.items() if "name" in info),
        key=lambda choice: choice[1].lower(),
    )


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
    # Represents the community to the network and the network to the community: matches
    # on the community, its events and listings are addressed to them
    ambassador = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="ambassador_of",
        verbose_name=_("Ambassador"),
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
    # ── How we live: what seekers filter on before they ask to become a member ──
    looking_for_members = models.BooleanField(_("Looking for new members"), default=False)
    # What the shared kitchen cooks, as many as fit (eating anything rules out vegetarian and vegan)
    KITCHEN_ANY = "any"
    KITCHEN_VEGETARIAN = "vegetarian"
    KITCHEN_VEGAN = "vegan"
    KITCHEN_GLUTEN_FREE = "gluten_free"
    KITCHEN_LACTOSE_FREE = "lactose_free"
    KITCHEN_SUGAR_FREE = "sugar_free"
    KITCHEN_RAW = "raw"
    KITCHEN_AYURVEDIC = "ayurvedic"
    KITCHEN_HALAL = "halal"
    KITCHEN_KOSHER = "kosher"
    KITCHEN_CHOICES = (
        (KITCHEN_ANY, _("Eats anything")),
        (KITCHEN_VEGETARIAN, _("Vegetarian")),
        (KITCHEN_VEGAN, _("Vegan")),
        (KITCHEN_GLUTEN_FREE, _("Gluten-free")),
        (KITCHEN_LACTOSE_FREE, _("Lactose-free")),
        (KITCHEN_SUGAR_FREE, _("Sugar-free")),
        (KITCHEN_RAW, _("Raw food")),
        (KITCHEN_AYURVEDIC, _("Ayurvedic")),
        (KITCHEN_HALAL, _("Halal")),
        (KITCHEN_KOSHER, _("Kosher")),
    )
    kitchen = ArrayField(
        models.CharField(max_length=12, choices=KITCHEN_CHOICES), verbose_name=_("Shared kitchen"), default=list, blank=True,
    )
    private_kitchens = models.BooleanField(_("Private kitchens too"), default=False)
    CHILDREN_WELCOME = "welcome"
    CHILDREN_NO_ROOM = "no_room"
    CHILDREN_ADULTS_ONLY = "adults"
    CHILDREN_CHOICES = (
        (CHILDREN_WELCOME, _("Welcome")),
        (CHILDREN_NO_ROOM, _("No room for more right now")),
        (CHILDREN_ADULTS_ONLY, _("Adults-only")),
    )
    children_welcome = models.CharField(_("Children"), max_length=8, blank=True, choices=CHILDREN_CHOICES)
    PETS_WELCOME = "welcome"
    PETS_ASK = "ask"
    PETS_NONE = "none"
    PETS_CHOICES = (
        (PETS_WELCOME, _("Welcome")),
        (PETS_ASK, _("Ask us first")),
        (PETS_NONE, _("None")),
    )
    pets = models.CharField(_("Pets"), max_length=8, blank=True, choices=PETS_CHOICES)
    # Vegetarian or vegan is more than the kitchen, and communities are often strict about it
    animals = models.TextField(
        _("Animals and animal products"), blank=True,
        help_text=_("Do you keep animals, and what for? Which animal products are used here (milk, eggs, honey, meat, leather, wool)? Do you slaughter?"),
    )
    currency = models.CharField(
        _("Currency"), max_length=3, default="EUR", help_text=_("For the buy-in and the monthly contribution, e.g. EUR"),
    )
    buy_in = models.PositiveIntegerField(_("Buy-in"), null=True, blank=True)
    # What the buy-in is also says who owns the place and how you get your money out
    BUY_IN_SHARES = "shares"
    BUY_IN_STOCK = "stock"
    BUY_IN_FOUNDATION = "foundation"
    BUY_IN_RENT_TO_OWN = "rent_to_own"
    BUY_IN_LOAN = "loan"
    BUY_IN_DONATION = "donation"
    BUY_IN_KIND_CHOICES = (
        (BUY_IN_SHARES, _("Cooperative shares")),
        (BUY_IN_STOCK, _("Shares in a stock corporation")),
        (BUY_IN_FOUNDATION, _("A contribution to a foundation")),
        (BUY_IN_RENT_TO_OWN, _("Rent-to-own")),
        (BUY_IN_LOAN, _("A loan")),
        (BUY_IN_DONATION, _("A donation")),
    )
    buy_in_kind = models.CharField(
        _("What the buy-in is"), max_length=12, blank=True, choices=BUY_IN_KIND_CHOICES,
        help_text=_("Other ways communities do it: a direct loan, a share of the property, a one-off fee, or work instead of money."),
    )
    monthly_contribution = models.PositiveIntegerField(_("Monthly contribution"), null=True, blank=True)
    work_hours = models.PositiveSmallIntegerField(
        _("Work commitment"), null=True, blank=True, help_text=_("Hours per week"),
    )
    DECISIONS_CONSENSUS = "consensus"
    DECISIONS_CONSENT = "consent"
    DECISIONS_SYSTEMIC = "systemic"
    DECISIONS_COUNCIL = "council"
    DECISIONS_MAJORITY = "majority"
    DECISIONS_COMPETENCE = "competence"
    DECISIONS_DOOCRACY = "doocracy"
    DECISIONS_HOLACRACY = "holacracy"
    DECISIONS_ELECTED_LEADER = "elected"
    DECISIONS_LEADER = "leader"
    DECISIONS_OTHER = "other"
    DECISION_CHOICES = (
        (DECISIONS_CONSENSUS, _("Consensus")),
        (DECISIONS_CONSENT, _("Consent (sociocracy)")),
        (DECISIONS_SYSTEMIC, _("Systemic consensing")),
        (DECISIONS_COUNCIL, _("Council (talking circle)")),
        (DECISIONS_MAJORITY, _("Majority vote")),
        (DECISIONS_COMPETENCE, _("Competence hierarchy")),
        (DECISIONS_DOOCRACY, _("Do-ocracy (who does it decides)")),
        (DECISIONS_HOLACRACY, _("Holacracy")),
        (DECISIONS_ELECTED_LEADER, _("An elected leader decides")),
        (DECISIONS_LEADER, _("A leader decides")),
        (DECISIONS_OTHER, _("Other")),
    )
    decision_making = models.CharField(_("Decision making"), max_length=10, blank=True, choices=DECISION_CHOICES)
    INCOME_SHARING_NONE = "none"
    INCOME_SHARING_PARTLY = "partly"
    INCOME_SHARING_FULLY = "fully"
    INCOME_SHARING_CHOICES = (
        (INCOME_SHARING_NONE, _("None")),
        (INCOME_SHARING_PARTLY, _("Partly")),
        (INCOME_SHARING_FULLY, _("Fully")),
    )
    income_sharing = models.CharField(_("Income sharing"), max_length=8, blank=True, choices=INCOME_SHARING_CHOICES)
    trial_months = models.PositiveSmallIntegerField(
        _("Trial period"), null=True, blank=True, help_text=_("Months"),
    )
    # Codes from Django's LANG_INFO (language_choices)
    languages = ArrayField(models.CharField(max_length=12), verbose_name=_("Languages"), default=list, blank=True)
    exit_terms = models.TextField(
        _("Exit terms"), blank=True,
        help_text=_("What happens to the buy-in when someone leaves, and how long the payout takes."),
    )
    house_agreements = models.TextField(
        _("House agreements"), blank=True,
        help_text=_("Alcohol, smoking, drugs, cars, flying, guests and partners staying over, noise, cleanliness, phone and wifi zones, rituals and spiritual practice …"),
    )
    statutes_url = models.URLField(_("Vision and statutes"), max_length=250, blank=True, help_text=_("A link"))
    statutes_file = models.FileField(
        _("Vision and statutes (PDF)"), upload_to="community-statutes/", blank=True,
        validators=[FileExtensionValidator(["pdf"])],
    )
    matches = GenericRelation("matches.Match")

    def __str__(self):
        return self.name

    def lives(self):
        """Its "How we live" facts that are filled in, as (icon, label, value) for its page
        (whether children are welcome goes with how many live there)."""
        def money(amount):
            return f"{amount:,} {self.currency}".replace(",", " ") if amount is not None else ""

        kitchen = ", ".join(str(label) for code, label in self.KITCHEN_CHOICES if code in self.kitchen)
        if kitchen and self.private_kitchens:
            kitchen = f"{kitchen} · {_('Private kitchens too')}"
        buy_in = money(self.buy_in)
        if buy_in and self.buy_in_kind:
            buy_in = f"{buy_in} ({self.get_buy_in_kind_display()})"
        facts = [
            ("fa-utensils", _("Shared kitchen"), kitchen),
            ("fa-paw", _("Pets"), self.get_pets_display()),
            ("fa-coins", _("Buy-in"), buy_in),
            ("fa-calendar", _("Monthly contribution"), money(self.monthly_contribution)),
            ("fa-person-digging", _("Work commitment"),
             ngettext("%(n)s hour per week", "%(n)s hours per week", self.work_hours) % {"n": self.work_hours}
             if self.work_hours else ""),
            ("fa-people-arrows", _("Decision making"), self.get_decision_making_display()),
            ("fa-hand-holding-heart", _("Income sharing"), self.get_income_sharing_display()),
            ("fa-hourglass-half", _("Trial period"),
             ngettext("%(n)s month", "%(n)s months", self.trial_months) % {"n": self.trial_months}
             if self.trial_months else ""),
            ("fa-language", _("Languages"), ", ".join(language_name(code) for code in self.languages)),
        ]
        return [fact for fact in facts if fact[2]]

    def get_absolute_url(self) -> str:
        return reverse("communities:detail", kwargs={"slug": self.slug})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # The ambassador is a member too
        update_fields = kwargs.get("update_fields")
        if self.ambassador_id and (update_fields is None or "ambassador" in update_fields):
            if not self.memberships.counted().filter(user_id=self.ambassador_id).exists():
                Membership.objects.create(community=self, user_id=self.ambassador_id)

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
        events) was accepted, with whoever came along on it (a tour visit's group)."""
        if self.location_public:
            return True
        if not user.is_authenticated:
            return False
        if user.is_staff or user in self.members():
            return True
        from django.contrib.contenttypes.models import ContentType
        from gift_economy.matches.models import Match
        stays = Q(content_type=ContentType.objects.get_for_model(Community), object_id=str(self.pk)) | Q(
            content_type__app_label="events", content_type__model="event",
            object_id__in=[str(pk) for pk in self.events.values_list("pk", flat=True)],
        )
        # Who asked, and the companions of an accepted stay (a tour visit's group)
        return Match.objects.filter(stays, Q(from_user=user) | Q(stay_details__companions=user),
                                    status=Match.STATUS_ACCEPTED).exists()

    def rough_place(self):
        """(name, point) as everyone sees it (users.places), unless it's public."""
        if self.location_public:
            return self.location_name, self.location
        return town(self.location_name), approximate(self.location, self.place_seed)

    def place_for(self, user):
        """(name, point) as `user` sees it."""
        return (self.location_name, self.location) if self.shows_place_to(user) else self.rough_place()

    def members(self):
        """Who belongs to the community, its ambassador first."""
        return [membership.user for membership in self.member_list()]

    def member_list(self):
        """Its memberships that count, the ambassador's first."""
        memberships = self.memberships.counted().select_related("user")
        return sorted(memberships, key=lambda membership: membership.user_id != self.ambassador_id)

    def showing_offers(self):
        """The members whose offers and skills show with the community."""
        return User.objects.filter(pk__in=self.memberships.counted().filter(shows_offers=True).values("user_id"))

    def is_member(self, user):
        return user.is_authenticated and self.memberships.counted().filter(user=user).exists()

    def membership_of(self, user):
        """`user`'s membership, also one still asked for, or None."""
        if not user.is_authenticated:
            return None
        return self.memberships.current().filter(user=user).select_related("match").first()

    def can_edit(self, user):
        """Its members edit its page and its offers and wishes (and staff)."""
        return user.is_authenticated and (user.is_staff or self.is_member(user))

    def is_ambassador(self, user):
        return user.is_authenticated and (user.is_staff or user.pk == self.ambassador_id)

    def hand_over(self, user):
        """Make a member the ambassador. The open and accepted matches addressed to the
        one before (stays, its events', offers' and wishes', membership applications)
        move to them; the one before stays a member."""
        from django.contrib.contenttypes.models import ContentType
        from django.db import transaction
        from gift_economy.matches.models import Match

        before = self.ambassador
        with transaction.atomic():
            self.ambassador = user
            self.save(update_fields=["ambassador"])
            if before is None:
                return
            def of(model, pks):
                return Q(content_type=ContentType.objects.get_by_natural_key(*model), object_id__in=[str(pk) for pk in pks])
            ours = (
                of(("communities", "community"), [self.pk])
                | of(("events", "event"), self.events.values_list("pk", flat=True))
                | of(("gifts", "listing"), self.listings.values_list("pk", flat=True))
                | of(("communities", "membership"), self.memberships.values_list("pk", flat=True))
            )
            Match.objects.filter(
                ours, recipient=before, status__in=[Match.STATUS_PENDING, Match.STATUS_COUNTER, Match.STATUS_ACCEPTED],
            ).exclude(from_user=user).update(recipient=user)

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
        return self.ambassador

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


def with_member_communities(path=""):
    """A prefetch of the communities people belong to, for User.member_communities():
    `path` leads from the queryset to the people (e.g. "owner__")."""
    from django.db.models import Prefetch

    return Prefetch(
        f"{path}memberships", to_attr="counted_memberships",
        queryset=Membership.objects.counted().select_related("community").prefetch_related("community__photos"),
    )


class MembershipQuerySet(models.QuerySet):
    def current(self):
        """Not left nor removed: members, and those who asked and wait for an answer."""
        from gift_economy.matches.models import Match

        return self.filter(ended_at=None).filter(
            Q(match=None) | Q(match__status__in=[Match.STATUS_PENDING, Match.STATUS_ACCEPTED, Match.STATUS_COUNTER])
        )

    def counted(self):
        """Members: without a match (the ambassador, or added in the admin), or accepted."""
        from gift_economy.matches.models import Match

        return self.filter(ended_at=None).filter(Q(match=None) | Q(match__status=Match.STATUS_ACCEPTED))


class Membership(models.Model):
    """Someone belonging to a community, also a planned one nobody lives in yet. Others
    than the ambassador ask for it with a match that has the membership as target, and
    count once it is accepted. Leaving keeps the row (ended_at), so the match keeps its
    target."""

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    match = models.OneToOneField(
        "matches.Match", on_delete=models.SET_NULL, null=True, blank=True, related_name="membership",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    # Their offers and skills show on the community page only if they want
    shows_offers = models.BooleanField(_("Show my offers and skills on the community page"), default=False)

    objects = MembershipQuerySet.as_manager()

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("Membership")
        verbose_name_plural = _("Memberships")

    def __str__(self):
        return f"{self.user} in {self.community}"

    @property
    def is_counted(self):
        from gift_economy.matches.models import Match

        return self.ended_at is None and (self.match_id is None or self.match.status == Match.STATUS_ACCEPTED)

    def end(self):
        from django.utils import timezone

        self.ended_at = timezone.now()
        self.save(update_fields=["ended_at"])

    def get_absolute_url(self):
        return self.community.get_absolute_url()

    # ── As what a membership application is about (gift_economy.matches) ──
    def get_match_owner(self):
        return self.community.ambassador

    def get_match_display_name(self):
        return self.community.name

    def get_match_location(self):
        return self.community.get_match_location()

    @property
    def place_seed(self):
        return self.community.place_seed

    @property
    def place_is_public(self):
        return self.community.place_is_public

    def get_match_icon(self):
        return self.community.get_type_icon()

    @property
    def is_invitation(self):
        """The ambassador invited them, rather than they asked to become a member."""
        return self.match_id is not None and self.match.recipient_id == self.user_id

    def get_match_kind(self):
        if self.is_invitation:
            return _("Invitation"), "fa-envelope-open-text", "bg-purple"
        return _("Membership application"), "fa-people-group", "bg-green"

    def get_match_verb(self, own=True):
        if self.is_invitation:
            return _("invited you to become a member of")
        return _("asked to become a member of")

    def get_match_request_text(self):
        if self.is_invitation:
            return _("%(actor)s invited you to become a member of %(title)s")
        return _("%(actor)s asked to become a member of %(title)s")

    # A membership is a yes or a no, there is nothing to counter-propose
    match_counter = False
