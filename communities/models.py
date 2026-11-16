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

from . import declines, onboarding
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
    # The rest of its onboarding process, handled locally: trial period, plenum, buying in
    after_visit = models.TextField(
        _("Our process after the visit"), blank=True,
        help_text=_("Trial period, plenum, buying in: what comes after the visit you handle yourselves. Describe it here, so people know what's coming."),
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

    def onboarding(self):
        """Its onboarding process as the applicant meets it: the must-matches first, then
        what it asks, then what it'd like to talk about at the visit. Each question with
        its wording for now (`shown_text`); a statement whose fact isn't filled in is left
        out."""
        from . import onboarding

        order = {onboarding.MUST_MATCH: 0, onboarding.INFO: 1, onboarding.DISCUSSION: 2}
        shown = []
        for question in self.onboarding_questions.all():
            question.shown_text = question.text_for()
            if question.shown_text:
                shown.append(question)
        # The library's in its order (so new library questions fall into place), its own after them
        shown.sort(key=lambda question: (
            order[question.type], not question.key, onboarding.POSITIONS.get(question.key, 0) if question.key else question.position,
        ))
        return shown

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

    def get_match_summary_template(self):
        return "communities/_stay_application.html"

    def match_redirect(self, match):
        """While someone is invited to visit, their visit's stay is talked over in their
        membership application: its page leads there."""
        membership = self.memberships.filter(visit=match, stage=Membership.STAGE_VISIT, ended_at=None).select_related("match").first()
        return membership.match.get_absolute_url() + "#compose" if membership is not None and membership.is_visiting else ""

    def applications_visiting(self, match, viewer):
        """The membership applications a stay (or tour visit) here is the visit for: asked
        for as part of one, or someone on it is invited to visit. The ambassador sees all
        of them, everyone else only their own."""
        from gift_economy.matches.models import Match

        details = getattr(match, "stay_details", None)
        people = [match.from_user_id, *(details.companions.values_list("pk", flat=True) if details else [])]
        found = self.memberships.filter(ended_at=None, match__status=Match.STATUS_ACCEPTED).filter(
            Q(visit=match) | Q(stage=Membership.STAGE_VISIT, visit=None, user_id__in=people),
        ).select_related("user", "match", "application")
        if not self.is_ambassador(viewer):
            found = found.filter(user_id=viewer.pk)
        return list(found)

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


def _day(raw):
    """A day from a date input, as an aware datetime at its start; None if blank or invalid."""
    from datetime import date, datetime, time
    from django.utils import timezone

    try:
        day = date.fromisoformat(raw) if raw else None
    except ValueError:
        return None
    return timezone.make_aware(datetime.combine(day, time())) if day else None


def _day_of(value):
    """The start of the (local) day of a datetime, None for None."""
    from django.utils import timezone

    return _day(timezone.localdate(value).isoformat()) if value else None


def agreed_text(start, end):
    """The message saying the days for a visit are agreed."""
    from datetime import timedelta
    from gift_economy.matches.models import period_text

    days = period_text(start or end, (end or start) + timedelta(days=1)) if start or end else ""
    return str(_("Agreed on the days for the visit: %(days)s") % {"days": days})


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
        """Members: at the member stage, without a match (the ambassador, or added in the
        admin) or with it accepted."""
        from gift_economy.matches.models import Match

        return self.filter(ended_at=None, stage=Membership.STAGE_MEMBER).filter(
            Q(match=None) | Q(match__status=Match.STATUS_ACCEPTED)
        )


class Membership(models.Model):
    """Someone belonging to a community, also a planned one nobody lives in yet. Others
    than the ambassador ask for it with a match that has the membership as target, and
    count once they reach the member stage. An accepted application goes on to the
    visit, and may stay there: what comes after it the community handles itself. Leaving
    keeps the row (ended_at), so the match keeps its target."""

    STAGE_APPLICATION = "application"
    STAGE_VISIT = "visit"
    STAGE_MEMBER = "member"
    STAGE_CHOICES = (
        (STAGE_APPLICATION, _("Application")),
        (STAGE_VISIT, _("Visit")),
        (STAGE_MEMBER, _("Member")),
    )

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    match = models.OneToOneField(
        "matches.Match", on_delete=models.SET_NULL, null=True, blank=True, related_name="membership",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    stage = models.CharField(_("Stage"), max_length=12, choices=STAGE_CHOICES, default=STAGE_MEMBER)
    # The stay or tour visit at the community it came from, if that went through ecobasa
    visit = models.ForeignKey(
        "matches.Match", on_delete=models.SET_NULL, null=True, blank=True, related_name="visit_memberships",
    )
    # Their offers and skills show on the community page only if they want
    shows_offers = models.BooleanField(_("Show my offers and skills on the community page"), default=False)
    # And that they became a member after a tour visit, on the tour's page
    shows_visit = models.BooleanField(_("Show that I found this community through ecobasa"), default=False)
    # How the ambassador said no to the application, if they did
    declined_as = models.CharField(_("Declined as"), max_length=8, blank=True, choices=declines.KIND_CHOICES)

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

        return self.ended_at is None and self.stage == self.STAGE_MEMBER and (
            self.match_id is None or self.match.status == Match.STATUS_ACCEPTED
        )

    @property
    def is_visiting(self):
        """Their application was accepted: they are invited to visit."""
        from gift_economy.matches.models import Match

        return self.ended_at is None and self.stage == self.STAGE_VISIT and self.match_id is not None and (
            self.match.status == Match.STATUS_ACCEPTED
        )

    def make_member(self):
        """They are a member now, remembering the visit they came from: the stay asked for
        as part of the application, else their latest accepted stay or tour visit here that
        has begun."""
        from django.utils import timezone

        if self.visit_id is None:
            begun = [stay for stay in self.stays_here() if (stay.stay_details.stay_from or stay.created_at) <= timezone.now()]
            self.visit = begun[0] if begun else None
        self.stage = self.STAGE_MEMBER
        self.save(update_fields=["stage", "visit"])

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

    # A membership is a yes or a no, there is nothing to counter-propose, and no gifts
    # to ask for along with it
    match_counter = False
    match_extras = False

    def has_application(self):
        try:
            return self.application is not None
        except MembershipApplication.DoesNotExist:
            return False

    def match_accept_choices(self):
        """How the ambassador accepts an application: inviting to visit (with days they
        suggest for it, the fields' template), or making them a member right away. One
        plain "Accept" for the rest."""
        if self.is_invitation or not self.has_application():
            return []
        return [
            (self.STAGE_VISIT, _("Invite to visit"), "fa-campground", "communities/_visit_days.html"),
            (self.STAGE_MEMBER, _("Make member"), "fa-user-check", ""),
        ]

    def match_accepted(self, match, data=None):
        """Accepted: an invitation, or who lives there already, makes a member; an
        application goes to the visit unless the ambassador chose to make them a member.
        The days they suggest for the visit stay with their answer."""
        data = data or {}
        if self.declined_as:
            # A no changed into a yes
            self.declined_as = ""
            self.save(update_fields=["declined_as"])
        if not self.match_accept_choices() or data.get("accept_as") == self.STAGE_MEMBER:
            self.make_member()
            return
        self.stage = self.STAGE_VISIT
        self.save(update_fields=["stage"])
        visit_from, visit_to = _day(data.get("visit_from")), _day(data.get("visit_to"))
        if visit_from and visit_to and visit_to < visit_from:
            visit_to = None
        answer = match.thread.filter(status_to=match.STATUS_ACCEPTED).last()
        if answer is not None and (visit_from or visit_to):
            answer.counter_stay_from, answer.counter_stay_to = visit_from, visit_to
            answer.save(update_fields=["counter_stay_from", "counter_stay_to"])

    # ── Saying no to an application ──
    # It hurts to be turned down by a community. The ambassador starts from a text for
    # "not now" or "no" at the stage it is at, fills in what it's about, and the
    # applicant sees no red "Declined", only the community's answer.
    def match_decline_fields(self):
        """The fields that come with declining: only an application has them."""
        if self.is_invitation or not self.has_application():
            return ""
        return "communities/_decline_fields.html"

    def decline_texts(self):
        """(kind, label, text) to start from, for the stage the application is at."""
        stage = self.STAGE_VISIT if self.stage == self.STAGE_VISIT else self.STAGE_APPLICATION
        ambassador = self.community.ambassador
        names = {
            "name": self.user.name or self.user.email.split("@")[0],
            "community": self.community.name,
            "ambassador": (ambassador.name or "") if ambassador else "",
        }
        return [(kind, label, declines.text(stage, kind, **names)) for kind, label in declines.KIND_CHOICES]

    @property
    def decline_guidance(self):
        return declines.GUIDANCE

    def match_decline_error(self, match, data):
        if self.match_decline_fields() and declines.is_unfilled(data.get("body", "")):
            return _("Please fill in or delete the part in brackets first.")
        return ""

    def match_declined(self, match, data):
        if not self.match_decline_fields():
            return
        kind = data.get("decline_as", "")
        self.declined_as = kind if kind in dict(declines.KIND_CHOICES) else declines.NO
        self.save(update_fields=["declined_as"])

    def match_declined_label(self):
        """What a declined application shows instead of a red "Declined"."""
        if not self.match_decline_fields():
            return None
        if self.declined_as == declines.NOT_NOW:
            return _("Not now")
        return _("Not this time")

    def get_match_declined_text(self):
        if not self.match_decline_fields():
            return None
        return _("%(actor)s answered your membership application: %(title)s")

    # ── The visit, agreed in the application's conversation ──
    # The days are messages with them (`counter_stay_from/to`): the invitation to visit
    # may bring the first ones, then each proposal from either side (the ambassador
    # first) is a counter-proposal, and accepting the latest is an "accepted" message
    # with the agreed days, so they always stand in the latest word. Accepting makes the
    # stay (or moves it), accepted, as the membership's visit. A volunteer stay the
    # applicant asks for at the community meanwhile is the visit too, its days their
    # proposal; while they are invited to visit, its own page leads here.

    def _days_messages(self):
        if not hasattr(self, "_days"):
            self._days = list(self.match.thread.exclude(
                counter_stay_from=None, counter_stay_to=None,
            ).select_related("sender")) if self.match_id else []
        return self._days

    def visit_proposal(self):
        """The latest word on the days: a proposal, or their agreement. None if none."""
        days = self._days_messages()
        return days[-1] if days else None

    def visit_answer(self):
        """Where the conversation shows the visit: with the latest word on the days, else
        with the invitation to visit."""
        from gift_economy.matches.models import Match

        return self.visit_proposal() or (
            self.match.thread.filter(status_to=Match.STATUS_ACCEPTED).last() if self.match_id else None
        )

    def suggested_visit(self):
        """(from, to) proposed or agreed last for the visit, else (None, None)."""
        proposal = self.visit_proposal()
        return (proposal.counter_stay_from, proposal.counter_stay_to) if proposal else (None, None)

    @property
    def visit_is_own(self):
        """Its visit is a stay of the applicant's at the community, its days agreed here
        (not a tour visit, which the membership only remembers)."""
        visit = self.visit if self.visit_id else None
        return (
            visit is not None and visit.from_user_id == self.user_id and visit.is_community_stay
            and getattr(visit, "stay_details", None) is not None and not hasattr(visit, "tour_stop")
        )

    def visit_agreed(self):
        """Whether the latest word on the days is their agreement (accepting days proposed
        before; the invitation's own days are only proposed)."""
        from gift_economy.matches.models import Match

        days = self._days_messages()
        return len(days) > 1 and days[-1].status_to == Match.STATUS_ACCEPTED

    def visit_waits_for(self, user):
        """Whether `user` is asked to accept the days proposed last (the other side is)."""
        proposal = self.visit_proposal()
        return bool(proposal and proposal.sender_id != user.pk and not self.visit_agreed())

    def can_propose_visit(self, user):
        """Both sides propose days while invited to visit; the ambassador first."""
        if not self.is_visiting:
            return False
        if user.pk == self.community.ambassador_id or self.community.is_ambassador(user):
            return True
        return user.pk == self.user_id and self.visit_proposal() is not None

    def agree_on_visit(self, user):
        """`user` accepted the days proposed last: the stay is made, or moved to them and
        accepted (its own conversation says so too)."""
        from django.utils import timezone
        from gift_economy.matches.models import Match, MatchMessage, StayDetails, create_stay

        stay_from, stay_to = self.suggested_visit()
        if self.visit_is_own:
            stay = self.visit
            stay.stay_details.stay_from, stay.stay_details.stay_to = stay_from, stay_to
            stay.stay_details.save(update_fields=["stay_from", "stay_to"])
            stay.status, stay.responded_at = Match.STATUS_ACCEPTED, timezone.now()
            stay.save(update_fields=["status", "responded_at"])
            MatchMessage.objects.create(
                match=stay, sender=user, status_to=Match.STATUS_ACCEPTED,
                counter_stay_from=stay_from, counter_stay_to=stay_to,
            )
            return stay
        stay = create_stay(
            self.user, self.community, message=self.match.message, stay_from=stay_from, stay_to=stay_to,
            status=Match.STATUS_ACCEPTED, volunteer_mode=StayDetails.MODE_APPLICATION,
        )
        MatchMessage.objects.create(
            match=stay, sender=user, status_to=Match.STATUS_ACCEPTED, counter_stay_from=stay_from, counter_stay_to=stay_to,
        )
        self.visit = stay
        self.save(update_fields=["visit"])
        return stay

    def propose_visit(self, sender, stay_from, stay_to, body="", agreed=False):
        """Days in the conversation (whole days): proposed, or `agreed` to."""
        from gift_economy.matches.models import Match, MatchMessage

        message = MatchMessage.objects.create(
            match=self.match, sender=sender, body=body,
            status_to=Match.STATUS_ACCEPTED if agreed else Match.STATUS_COUNTER,
            counter_stay_from=_day_of(stay_from), counter_stay_to=_day_of(stay_to),
        )
        self.__dict__.pop("_days", None)
        return message

    def adopt_stay(self, stay):
        """They asked for a volunteer stay at the community while invited to visit: it is
        the visit, and its days their proposal in the conversation."""
        self.visit = stay
        self.save(update_fields=["visit"])
        details = stay.stay_details
        return self.propose_visit(
            stay.from_user, details.stay_from, details.stay_to,
            # Their own words, else a line saying what it is
            body=stay.message.strip() or str(_("I asked for a volunteer stay on these days.")),
        )

    # Shown with the latest word on the visit: its days, and accepting or proposing others
    match_answer_template = "communities/_visit_answer.html"

    def match_person(self, user, match):
        """The ambassador sees what someone asking to become a member has to offer and
        where else they are a member; the one asking doesn't need that of the ambassador."""
        return not self.is_invitation and user.pk == self.community.ambassador_id

    # ── What the ambassador sees with an application, without asking ──
    def references_count(self):
        from gift_economy.references.models import references_about

        return references_about(self.user).count()

    def stays_here(self):
        """Their accepted stays at the community, tour visits included (they came along)."""
        from gift_economy.matches.models import Match

        return self.community.matches.filter(status=Match.STATUS_ACCEPTED).filter(
            Q(from_user=self.user) | Q(stay_details__companions=self.user),
        ).distinct().select_related("stay_details").order_by("-stay_details__stay_from")

    def wished_skills(self):
        """Their skill offers the community looks for."""
        from gift_economy.gifts.models import Listing, skill_offers

        wished = Listing.objects.of(self.community).filter(type=Listing.TYPE_WISH).exclude(skill=None).values("skill_id")
        return list(skill_offers(self.user).filter(skill_id__in=wished).select_related("skill"))

    def get_match_summary_template(self):
        return "communities/_application_summary.html"


class MembershipApplication(models.Model):
    """What someone answered when they asked to become a member, each question frozen
    with its wording at the time, so later changes to the onboarding process don't
    change what they answered. Only the ambassador and the applicant see it. Someone
    who already lives there asks without one."""

    membership = models.OneToOneField(Membership, on_delete=models.CASCADE, related_name="application")
    # [{"key", "type", "kind", "text", "sensitive", "answer"}], in the order asked
    answers = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    # When they agreed that the community may see their answers, and, apart from that,
    # that the ambassador sees their answers to the sensitive questions
    consented_at = models.DateTimeField(null=True, blank=True)
    sensitive_consented_at = models.DateTimeField(null=True, blank=True)
    # Applying together with others, each with an application of their own
    family = models.ForeignKey("Family", on_delete=models.SET_NULL, null=True, blank=True, related_name="applications")

    class Meta:
        verbose_name = _("Membership application")
        verbose_name_plural = _("Membership applications")

    def __str__(self):
        return str(self.membership)

    def of_type(self, type):
        return [answer for answer in self.answers if answer["type"] == type]

    def agreed(self):
        return self.of_type(onboarding.MUST_MATCH)

    def answered(self):
        return self.of_type(onboarding.INFO)

    def talks(self):
        return self.of_type(onboarding.DISCUSSION)

    def together(self):
        """The others in its family: (person, their match) for who applied too, and
        (person or address, None) for who is still to."""
        if self.family_id is None:
            return []
        others = self.family.applications.exclude(pk=self.pk).select_related("membership__user", "membership__match")
        return [(other.membership.user, other.membership.match) for other in others] + [
            (waiting, None) for waiting in self.family.waiting()
        ]


class Family(models.Model):
    """People who apply together to become members of a community. Every adult applies
    on their own; the family keeps the children coming along, by age, and the email
    addresses of those asked to apply too who haven't yet."""

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="families")
    children = ArrayField(models.PositiveSmallIntegerField(), default=list, blank=True)
    invited = ArrayField(models.EmailField(), default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Family")
        verbose_name_plural = _("Families")

    def __str__(self):
        return ", ".join(str(application.membership.user) for application in self.applications.all()) or str(self.pk)

    def applicants(self):
        return [application.membership.user for application in self.applications.select_related("membership__user")]

    def waiting(self):
        """Those asked to apply too who haven't yet: their account, or only the address."""
        users = {user.email.lower(): user for user in User.objects.filter(email__in=self.invited)}
        return [users.get(email.lower()) or email for email in self.invited]

    def joined(self, application, email=""):
        """Someone asked applied too (`email`: the address they were asked at, if their
        account has another one): no longer waited for."""
        gone = {application.membership.user.email.lower(), email.lower()}
        self.invited = [invited for invited in self.invited if invited.lower() not in gone]
        self.save(update_fields=["invited"])
        application.family = self
        application.save(update_fields=["family"])


class OnboardingQuestion(models.Model):
    """One question of a community's onboarding process: a library question it switched
    on (`key`, see communities.onboarding), or one of its own (`text`)."""

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="onboarding_questions")
    key = models.CharField(max_length=40, blank=True)
    type = models.CharField(_("Type"), max_length=10, choices=onboarding.TYPE_CHOICES, default=onboarding.INFO)
    required = models.BooleanField(_("Required"), default=False)
    position = models.PositiveSmallIntegerField(default=0)
    note = models.TextField(_("Note"), blank=True, help_text=_("Shown under the question"))
    # Its own questions
    text = models.CharField(_("Question"), max_length=500, blank=True)
    answer_kind = models.CharField(
        _("Answered as"), max_length=8, choices=onboarding.OWN_KIND_CHOICES, default=onboarding.TEXT, blank=True,
    )

    class Meta:
        ordering = ["position", "pk"]
        verbose_name = _("Onboarding question")
        verbose_name_plural = _("Onboarding questions")
        constraints = [
            models.UniqueConstraint(fields=["community", "key"], condition=~Q(key=""), name="one_library_question_each"),
        ]

    def __str__(self):
        return self.key or self.text

    @property
    def library(self):
        """Its library question (None for its own, or for a key the library dropped)."""
        return onboarding.QUESTIONS.get(self.key) if self.key else None

    @property
    def module(self):
        return onboarding.MODULE_OF.get(self.key)

    @property
    def kind(self):
        if self.type == onboarding.MUST_MATCH:
            return onboarding.AGREE
        return self.library.kind if self.library else self.answer_kind or onboarding.TEXT

    @property
    def sensitive(self):
        return bool(self.library and self.library.sensitive)

    @property
    def is_required(self):
        """Whether the applicant has to answer it: a must-match always, a sensitive
        question or a discussion topic never."""
        if self.type == onboarding.MUST_MATCH:
            return True
        return self.type == onboarding.INFO and self.required and not self.sensitive

    def text_for(self):
        """Its wording for its community now ("" for a statement whose fact isn't filled in)."""
        if self.key:
            return self.library.text_for(self.community) if self.library else ""
        return self.text
