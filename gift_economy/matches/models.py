from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.html import escape, format_html
from django.utils.translation import gettext_lazy as _

from users.places import approximate, town


# Matches whose target is in one of these apps are volunteer stays: at a community, or
# helping with one of its projects.
STAY_APP_LABELS = ("communities", "projects")


class Match(models.Model):
    """A negotiation between two users over something one of them offers or wishes for
    (a gift listing: a thing, a skill, knowledge, helping hands), a stay at a community or
    help with one of its projects. `target` is whatever is being negotiated over — a
    Listing, Community or Project — via a generic reference, so this app never has to
    import gifts/communities/projects models to work with it.
    """

    LOC_MY_PLACE = "my_place"
    LOC_YOUR_PLACE = "your_place"
    LOC_CUSTOM = "custom"
    LOC_CHOICES = [
        (LOC_MY_PLACE, _("My place — come visit me")),
        (LOC_YOUR_PLACE, _("Your place — I will visit you")),
        (LOC_CUSTOM, _("Somewhere else")),
    ]

    STATUS_PENDING = "pending"
    STATUS_ACCEPTED = "accepted"
    STATUS_DECLINED = "declined"
    STATUS_COUNTER = "counter"
    STATUS_CHOICES = [
        (STATUS_PENDING, _("Pending")),
        (STATUS_ACCEPTED, _("Accepted")),
        (STATUS_DECLINED, _("Declined")),
        (STATUS_COUNTER, _("Counter-proposed")),
    ]

    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="matches_sent"
    )
    # Denormalized at creation time: who this match was directed at. Needed because a
    # GenericForeignKey can't be filtered/joined generically across heterogeneous target
    # types ("show me matches sent to me" would otherwise require a different lookup path
    # per target model). Mirrors the existing Notification.recipient pattern.
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="matches_received",
    )

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    # CharField, not PositiveIntegerField: gifts.Listing uses a random string primary key
    # (RandomIdMixin), so object_id has to accommodate non-numeric PKs too.
    object_id = models.CharField(max_length=255)
    target = GenericForeignKey("content_type", "object_id")

    message = models.TextField(_("Message"))
    location_type = models.CharField(
        _("Meeting location"), max_length=20, choices=LOC_CHOICES, default=LOC_YOUR_PLACE
    )
    proposed_location = models.CharField(_("Custom location"), max_length=255, blank=True)
    proposed_lat = models.FloatField(null=True, blank=True)
    proposed_lon = models.FloatField(null=True, blank=True)
    proposed_date = models.DateTimeField(_("Proposed date"), null=True, blank=True)
    status = models.CharField(
        _("Status"), max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    responded_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # The offers and wishes this exchange takes or brings, with how much of each
    # (Contribution): the target listing itself, a project's needs a helper brings, a
    # community's wishes a volunteer brings along, or another of the other side's offers
    # asked for while talking it over. They cover wishes in parts, are named in the
    # references and shown with the match.
    listings = models.ManyToManyField(
        "gifts.Listing", through="Contribution", blank=True, related_name="exchanges",
        verbose_name=_("Part of this exchange"),
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Match")
        verbose_name_plural = _("Matches")

    def __str__(self):
        return f"Match from {self.from_user} → {self.target}"

    def get_absolute_url(self):
        return reverse("matches:detail", args=[self.pk])

    @property
    def is_community_stay(self):
        """A volunteer stay happens at the community itself (also when helping with one
        of its projects), so only its dates are open to a counter-proposal, never the place."""
        return self.content_type.app_label in STAY_APP_LABELS

    @property
    def community(self):
        """The community a stay is at: the target, or the project's community."""
        if not self.is_community_stay:
            return None
        target = self.target
        return getattr(target, "community", target)

    @property
    def kind(self):
        """What the match is about, as a pill: (label, icon, colour). Skills, knowledge and
        helping hands purple, things in the primary colour (by their kind), stays green."""
        model = self.content_type.model
        if model == "listing":
            listing = self.target
            if listing is not None and listing.kind != listing.KIND_OTHER:
                return listing.kind_label, listing.kind_icon, listing.colour
            return _("Gift"), "fa-gift", "bg-primary"
        if model == "project":
            return _("Project"), "fa-person-digging", "bg-green"
        if model == "community":
            return _("Volunteer stay"), "fa-campground", "bg-green"
        return _("Match"), "fa-handshake", "bg-primary"

    def _extras(self):
        """The contributions beyond what the match is about (its target listing)."""
        target_id = self.object_id if self.content_type.model == "listing" else None
        return [c for c in self.contributions.all() if c.listing_id != target_id]

    def brings(self):
        """The wishes it helps with besides its target: a project's needs a helper or
        volunteer brings, a community's wishes brought along. Each with how much."""
        return [c for c in self._extras() if c.listing.is_wish]

    def asks_for(self):
        """The offers asked for too while talking it over."""
        return [c for c in self._extras() if c.listing.is_offer]

    def _counter_period(self):
        """The latest counter-proposed period (stay or loan), or None."""
        return (
            self.thread.filter(status_to=self.STATUS_COUNTER)
            .exclude(counter_stay_from=None, counter_stay_to=None)
            .last()
        )

    def stay_period(self):
        """(from, to) of a stay as currently proposed: the latest counter-proposed period,
        else what the volunteer asked for. (None, None) without dates."""
        counter = self._counter_period()
        if counter:
            return counter.counter_stay_from, counter.counter_stay_to
        details = getattr(self, "volunteer_details", None)
        if details:
            return details.stay_from, details.stay_to
        return None, None

    # ── Places: exactly only once accepted ─────────────────────────
    # Until then both see each other's place only roughly (users.places), so that asking
    # never gives anyone an address; places that are public anyway stay exact.
    @property
    def places_shown(self):
        return self.status == self.STATUS_ACCEPTED

    def person_place(self, user):
        """(name, point) of where `user` lives, as this match shows it."""
        if self.places_shown:
            return user.location_name, user.location
        return town(user.location_name), approximate(user.location, user.pk)

    def target_location(self):
        """(label, name, point) of what it is about, as this match shows it."""
        label, name, point = self.target.get_match_location()
        if not self.places_shown and not self.target.place_is_public:
            name, point = town(name), approximate(point, self.target.place_seed)
        return label, name, point

    @property
    def is_loan(self):
        """About a tool to lend or to borrow: it has dates it is lent from and until (Loan)."""
        return hasattr(self, "loan")

    @property
    def lender(self):
        """Who lends the tool: the owner of a tool to lend, the one who answers a wish to borrow."""
        if not self.is_loan:
            return None
        target = self.target
        return self.recipient if target is not None and target.is_offer else self.from_user

    @property
    def borrower(self):
        if not self.is_loan:
            return None
        return self.from_user if self.lender == self.recipient else self.recipient

    def loan_period(self):
        """(start, end) of a loan as currently proposed: the latest counter-proposed one,
        else the agreed or asked for one. (None, None) if it isn't a loan."""
        if not self.is_loan:
            return None, None
        counter = self._counter_period()
        if counter and counter.counter_stay_from and counter.counter_stay_to:
            return counter.counter_stay_from, counter.counter_stay_to
        return self.loan.starts_at, self.loan.ends_at

    def resolved_location(self):
        """Human-readable meeting location, resolving my/your place from profiles."""
        if self.location_type == self.LOC_MY_PLACE:
            loc = self.person_place(self.from_user)[0] or self.proposed_location or ""
            name = self.from_user.name or self.from_user.email
            return f"{name}'s place — {loc}" if loc else f"{name}'s place"
        if self.location_type == self.LOC_YOUR_PLACE and self.target is not None:
            label, loc_name, _point = self.target_location()
            if label:
                return f"{label} — {loc_name}" if loc_name else label
        return self.proposed_location or ""

    def place_of(self, user, viewer=None):
        """(name, point) of where one side is: for the side it belongs to, where the thing
        is (its own place, its person's or community's), else the person's place. Exactly
        to the viewer it belongs to, to others only roughly until accepted."""
        if user is None:
            return "", None
        own = viewer is not None and viewer == user
        if user == self.recipient and self.target is not None:
            _label, name, point = self.target.get_match_location() if own else self.target_location()
            if point:
                return name, point
        if own:
            return user.location_name or "", user.location
        name, point = self.person_place(user)
        return name or "", point

    def place_is_rough(self, user):
        """Whether place_of(user) shows others only roughly where it is."""
        if user is None or self.places_shown:
            return False
        if user == self.recipient and self.target is not None and self.target.get_match_location()[2]:
            return not self.target.place_is_public
        return True

    def location_coords(self):
        """Best coordinates for this match's proposed meeting point."""
        if self.proposed_lat and self.proposed_lon:
            return self.proposed_lat, self.proposed_lon
        if self.location_type == self.LOC_MY_PLACE and self.from_user.location:
            point = self.person_place(self.from_user)[1]
            return point.y, point.x
        if self.location_type == self.LOC_YOUR_PLACE and self.target is not None:
            _label, _loc_name, point = self.target_location()
            if point:
                return point.y, point.x
        return None, None

    def location_is_rough(self):
        """Whether location_coords is only roughly where it is."""
        if self.places_shown or self.proposed_lat and self.proposed_lon:
            return False
        if self.location_type == self.LOC_YOUR_PLACE and self.target is not None:
            return not self.target.place_is_public
        return self.location_type == self.LOC_MY_PLACE


class MatchMessage(models.Model):
    """One entry in a Match conversation thread — a plain message or a status decision."""

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="thread")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    body = models.TextField(_("Message"), blank=True)
    status_to = models.CharField(
        _("Decision"), max_length=20, blank=True, choices=Match.STATUS_CHOICES
    )
    counter_location_type = models.CharField(max_length=20, blank=True, choices=Match.LOC_CHOICES)
    counter_location = models.CharField(max_length=255, blank=True)
    counter_lat = models.FloatField(null=True, blank=True)
    counter_lon = models.FloatField(null=True, blank=True)
    counter_date = models.DateTimeField(null=True, blank=True)
    # Counter-proposed stay period, for community stays (see VolunteerDetails.stay_from/to)
    counter_stay_from = models.DateTimeField(null=True, blank=True)
    counter_stay_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Match Message")
        verbose_name_plural = _("Match Messages")

    def __str__(self):
        return f"{self.sender} → {self.match} ({self.status_to or 'message'})"

    def resolved_counter_location(self):
        """Human-readable counter-proposed meeting location, resolving my/your place."""
        if self.counter_location:
            return self.counter_location
        match = self.match
        if self.counter_location_type == Match.LOC_MY_PLACE and match.target is not None:
            label, loc_name, _point = match.target_location()
            if label:
                return f"{label} — {loc_name}" if loc_name else label
        if self.counter_location_type == Match.LOC_YOUR_PLACE:
            loc = match.person_place(match.from_user)[0] or ""
            name = match.from_user.name or match.from_user.email
            return f"{name}'s place — {loc}" if loc else f"{name}'s place"
        return ""

    @property
    def counter_loan_period(self):
        """The counter-proposed time of a loan, in words."""
        return period_text(self.counter_stay_from, self.counter_stay_to)

    def counter_location_coords(self):
        if self.counter_lat and self.counter_lon:
            return self.counter_lat, self.counter_lon
        # "My place" is the place of whoever proposed it, "your place" the other side's
        match = self.match
        _name, point = match.place_of(self._counter_side())
        return (point.y, point.x) if point else (None, None)

    def _counter_side(self):
        match = self.match
        other = match.recipient if self.sender_id == match.from_user_id else match.from_user
        return {Match.LOC_MY_PLACE: self.sender, Match.LOC_YOUR_PLACE: other}.get(self.counter_location_type)

    def counter_location_is_rough(self):
        """Whether counter_location_coords is only roughly where it is."""
        if self.counter_lat and self.counter_lon:
            return False
        return self.match.place_is_rough(self._counter_side())


class VolunteerDetails(models.Model):
    """Volunteer-only extra fields that don't generalize to gifts/skills matches."""

    match = models.OneToOneField(Match, on_delete=models.CASCADE, related_name="volunteer_details")
    volunteer_mode = models.CharField(max_length=20, blank=True)  # 'offer' | 'wish'
    stay_from = models.DateTimeField(null=True, blank=True)
    stay_to = models.DateTimeField(null=True, blank=True)
    practice_skills = models.TextField(blank=True)
    practice_skill_level = models.CharField(max_length=20, blank=True)
    sender_skills = models.TextField(blank=True)

    class Meta:
        verbose_name = _("Volunteer Details")
        verbose_name_plural = _("Volunteer Details")

    def __str__(self):
        return f"Volunteer details for {self.match}"

    @property
    def practice_skills_list(self):
        return [s.strip() for s in self.practice_skills.split(",") if s.strip()] if self.practice_skills else []

    @property
    def sender_skills_list(self):
        return [s.strip() for s in self.sender_skills.split(",") if s.strip()] if self.sender_skills else []

    def _skill_pills(self, names):
        """(name, level, url of the volunteer's skill page) for skill names: the level and
        page if they have that skill on their profile."""
        from gift_economy.gifts.models import Listing
        from gift_economy.gifts.skills.models import skill_slug_for_name
        if not names:
            return []
        own = {
            us.skill.slug: us for us in Listing.objects.of(self.match.from_user)
            .filter(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL).select_related("skill")
        }
        pills = []
        for name in names:
            us = own.get(skill_slug_for_name(name))
            pills.append((name, us.get_level_display() if us and us.level else "", us.get_absolute_url() if us else ""))
        return pills

    @property
    def practice_skill_pills(self):
        return self._skill_pills(self.practice_skills_list)

    @property
    def sender_skill_pills(self):
        return self._skill_pills(self.sender_skills_list)


def loan_span(first_day, last_day, from_time=None, until_time=None):
    """(start, end) as aware datetimes of borrowing from first_day until last_day: whole
    days without times (until the start of the day after last_day), else from and until
    the times given ("Sat 14:00–18:00")."""
    from datetime import datetime, time, timedelta
    from django.utils import timezone
    last_day = last_day or first_day
    if from_time is None or until_time is None:
        start = datetime.combine(first_day, time())
        end = datetime.combine(last_day + timedelta(days=1), time())
    else:
        start = datetime.combine(first_day, from_time)
        end = datetime.combine(last_day, until_time)
    return timezone.make_aware(start), timezone.make_aware(end)


def _whole_days(start, end):
    return start.time() == end.time() and start.hour == start.minute == 0


def period_text(start, end):
    """"Sat 31 Oct", "Sat 31 Oct – Mon 2 Nov" (whole days), "Sat 31 Oct, 14:00–18:00",
    "Sat 31 Oct 18:00 – Sun 1 Nov 10:00"."""
    from datetime import timedelta
    from django.utils import timezone
    from django.utils.formats import date_format
    if start is None or end is None:
        return ""
    start, end = timezone.localtime(start), timezone.localtime(end)
    day = lambda value: date_format(value, "D j M")
    if _whole_days(start, end):
        last = end - timedelta(days=1)
        return day(start) if last.date() == start.date() else f"{day(start)} – {day(last)}"
    if start.date() == end.date():
        return f"{day(start)}, {date_format(start, 'H:i')}–{date_format(end, 'H:i')}"
    return f"{day(start)} {date_format(start, 'H:i')} – {day(end)} {date_format(end, 'H:i')}"


def until_text(start, end):
    """When it comes back: "Mon 2 Nov" (whole days, the last one), "Sat 31 Oct, 18:00"."""
    from datetime import timedelta
    from django.utils import timezone
    from django.utils.formats import date_format
    start, end = timezone.localtime(start), timezone.localtime(end)
    if _whole_days(start, end):
        return date_format(end - timedelta(days=1), "D j M")
    return f"{date_format(end, 'D j M')}, {date_format(end, 'H:i')}"


class Loan(models.Model):
    """When a tool or vehicle is lent: from a day (and maybe an hour) until another, as
    asked for, and as agreed once the match is accepted (a counter-proposal's, if that is
    what was accepted). Whole days run from midnight to the midnight after the last day
    (loan_span). Shown in the lending calendar of both sides."""

    match = models.OneToOneField(Match, on_delete=models.CASCADE, related_name="loan")
    starts_at = models.DateTimeField(_("Borrow from"))
    ends_at = models.DateTimeField(_("Borrow until"))

    class Meta:
        ordering = ["starts_at"]
        verbose_name = _("Loan")
        verbose_name_plural = _("Loans")

    def __str__(self):
        return f"Loan {self.starts_at}–{self.ends_at} of {self.match}"

    def overlaps(self, starts_at, ends_at):
        return self.starts_at < ends_at and self.ends_at > starts_at

    @property
    def period(self):
        return period_text(self.starts_at, self.ends_at)

    # As a form asks for it: the first and last day, and the hours unless whole days
    @property
    def first_day(self):
        from django.utils import timezone
        return timezone.localdate(self.starts_at)

    @property
    def last_day(self):
        from datetime import timedelta
        from django.utils import timezone
        return timezone.localdate(self.ends_at - timedelta(microseconds=1) if self.whole_days else self.ends_at)

    @property
    def whole_days(self):
        from django.utils import timezone
        return _whole_days(timezone.localtime(self.starts_at), timezone.localtime(self.ends_at))

    @property
    def from_time(self):
        from django.utils import timezone
        return None if self.whole_days else timezone.localtime(self.starts_at).time()

    @property
    def until_time(self):
        from django.utils import timezone
        return None if self.whole_days else timezone.localtime(self.ends_at).time()

    @property
    def until(self):
        return until_text(self.starts_at, self.ends_at)


class Contribution(models.Model):
    """An offer or wish that is part of an exchange, with how much of it the exchange
    takes or brings: "120 kg of the 200 kg clay", "1 of 2 people". Without a quantity it
    is the whole of it. Covers wishes (and gives offers away) in parts, see
    gifts.Listing.status."""

    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name="contributions")
    listing = models.ForeignKey("gifts.Listing", on_delete=models.CASCADE, related_name="contributions")
    quantity = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["match", "listing"], name="one_contribution_per_listing")]
        verbose_name = _("Contribution")
        verbose_name_plural = _("Contributions")

    def __str__(self):
        return f"{self.match} → {self.listing}"

    @property
    def amount(self):
        return self.listing.format_amount(self.quantity)


def _name(user):
    return (user.name or user.email) if user else ""


class Suggestion(models.Model):
    """Something of someone else's that fits something of yours, found by the matching
    (matching.py) as soon as either was saved: their gift offer for your wish, their wish
    for your offer, a project that needs your skill, a person with the skill your project
    or your wish asks for. Each pair is suggested to both sides, each within their own
    distance (User.match_radius)."""

    REASON_SKILL = "skill"
    REASON_WORDS = "words"
    REASON_THING = "thing"
    REASON_CHOICES = [
        (REASON_SKILL, _("Same skill")),
        (REASON_WORDS, _("Similar title")),
        (REASON_THING, _("Same kind of thing")),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="suggestions")
    # Their own thing it fits: a gift listing, skill, skill wish or project need
    own_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="+")
    own_id = models.CharField(max_length=255)
    own = GenericForeignKey("own_type", "own_id")
    # Someone else's thing
    other_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, related_name="+")
    other_id = models.CharField(max_length=255)
    other = GenericForeignKey("other_type", "other_id")
    other_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="+",
    )
    KIND_GIFT = "gift"
    KIND_SKILLS = "skills"
    # Things (gifts, and materials and tools for projects) or skills (and knowledge)
    KIND_CHOICES = [(KIND_GIFT, _("Gifts")), (KIND_SKILLS, _("Skills"))]

    kind = models.CharField(max_length=10, choices=KIND_CHOICES, default=KIND_GIFT)
    reason = models.CharField(max_length=20, choices=REASON_CHOICES)
    distance_km = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    seen_at = models.DateTimeField(null=True, blank=True)
    emailed_at = models.DateTimeField(null=True, blank=True)
    dismissed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "own_type", "own_id", "other_type", "other_id"], name="one_suggestion_per_pair",
            ),
        ]
        indexes = [models.Index(fields=["other_type", "other_id"]), models.Index(fields=["own_type", "own_id"])]
        verbose_name = _("Suggestion")
        verbose_name_plural = _("Suggestions")

    def __str__(self):
        return f"{self.user} ← {self.other}"

    @property
    def other_model(self):
        return self.other_type.model

    @property
    def icon(self):
        other = self.other
        if other is None or self.other_model != "listing":
            return "fa-handshake-angle"
        if other.project_id and other.is_wish:
            return "fa-person-digging"
        if other.kind == other.KIND_OTHER:
            return "fa-gift" if other.is_offer else "fa-heart"
        return other.kind_icon

    @property
    def text(self):
        """What the other side has or needs, in the reader's language."""
        other = self.other
        if other is None:
            return ""
        if self.other_model != "listing":
            return str(other)
        title = f"{other.display_title} ({other.amount})" if other.amount else other.display_title
        if other.project_id and other.is_wish:
            return _("%(project)s at %(community)s needs: %(title)s") % {
                "project": other.project.title, "community": other.community.name, "title": title,
            }
        if other.community_id:
            if other.is_offer:
                if other.kind == other.KIND_SKILL:
                    return _("You can learn %(skill)s at %(community)s") % {"skill": title, "community": other.community.name}
                return _("%(name)s offers: %(title)s") % {"name": other.community.name, "title": title}
            return _("%(community)s is looking for: %(skill)s") % {"community": other.community.name, "skill": title}
        name = _name(other.owner)
        if other.kind == other.KIND_SKILL:
            if other.is_offer:
                return _("%(name)s offers the skill: %(skill)s") % {"name": name, "skill": title}
            return _("%(name)s wants to learn: %(skill)s") % {"name": name, "skill": title}
        if other.is_offer:
            if other.is_skill:
                return _("%(name)s offers: %(title)s") % {"name": name, "title": title}
            return _("%(name)s gives away: %(title)s") % {"name": name, "title": title}
        return _("%(name)s is looking for: %(title)s") % {"name": name, "title": title}

    @property
    def title_html(self):
        """The text with links: a project need's project to its page and its community to
        its profile, a community's wish to the community, anything else to the thing."""
        other = self.other
        if other is None:
            return ""
        link = '<a href="{}" class="font-semibold hover:underline">{}</a>'
        if self.other_model == "listing" and other.project_id and other.is_wish:
            project = other.project
            title = f"{other.display_title} ({other.amount})" if other.amount else other.display_title
            return format_html(
                escape(_("%(project)s at %(community)s needs: %(title)s")).replace("%(project)s", "{project}")
                .replace("%(community)s", "{community}").replace("%(title)s", "{title}"),
                project=format_html(link, project.get_absolute_url(), project.title),
                community=format_html(link, project.community.get_absolute_url(), project.community.name),
                title=title,
            )
        if self.other_model == "listing" and other.community_id and other.is_wish:
            # The community links to its profile; the button opens its volunteer form
            community = other.community
            return format_html(
                escape(_("%(community)s is looking for: %(skill)s")).replace("%(community)s", "{community}")
                .replace("%(skill)s", "{skill}"),
                community=format_html(link, community.get_absolute_url(), community.name),
                skill=other.display_title,
            )
        return format_html(link, self.url, self.text)

    @property
    def own_text(self):
        """Which of their own things it fits."""
        own = self.own
        if own is None:
            return ""
        if self.own_type.model != "listing":
            return str(own)
        if own.project_id:
            return _("your project %(project)s: %(title)s") % {"project": own.project.title, "title": own.display_title}
        if own.is_offer and own.kind == own.KIND_SKILL:
            return _("your skill: %(skill)s") % {"skill": own.display_title}
        template = _("your offer: %(title)s") if own.is_offer else _("your wish: %(title)s")
        return template % {"title": own.display_title}

    @property
    def url(self):
        """The thing's page: a project need on its project's page."""
        other = self.other
        if other is None:
            return ""
        if self.other_model == "listing" and other.project_id and other.is_wish:
            return f"{other.project.get_absolute_url()}#need-{other.pk}"
        return other.get_absolute_url()

    @property
    def helps(self):
        """Whether the other side needs something, so the reader can help with it."""
        return getattr(self.other, "type", "") == "wish"

    @property
    def action_url(self):
        """Where to act on it: the offer form for a project need, the volunteer form for a
        community's wish for a skill, else the thing's page (where it can be asked for or
        offered)."""
        other = self.other
        if self.other_model == "listing" and other is not None and other.is_wish:
            if other.project_id:
                return f"{reverse('projects:offer_help', args=[other.project_id])}?need={other.pk}"
            if other.community_id and other.skill_id:
                return f"{other.community.get_absolute_url()}?help={other.skill.slug}"
        return self.url
