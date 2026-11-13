import calendar
import datetime

from django.conf import settings
from django.contrib.gis.db import models
from django.core.mail import send_mail
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _
from django_countries.fields import CountryField
from taggit.managers import TaggableManager


class UserManager(BaseUserManager):
    """Define a model manager for User model with no username field."""

    use_in_migrations = True

    def get_by_natural_key(self, username):
        """When trying to find the user try email first, then username (for legacy users)"""
        try:
            return self.get(email=username)
        except self.model.DoesNotExist:
            return self.get(username=username)

    def get_by_slug(self, slug):
        """Reverse of User.get_absolute_url(): username, then slugified name, then pk. None if no match.

        Names are compared slugified, so "bjorn-achterberg" finds "Björn Achterberg".
        """
        user = self.filter(username=slug).first()
        if user:
            return user
        if slug.isdigit():
            return self.filter(pk=slug).first()
        # Narrow by the slug's words (accented words won't match, the others will), then compare exactly
        query = models.Q()
        for word in slug.split("-"):
            if len(word) >= 3:
                query |= models.Q(name__icontains=word)
        names = self.exclude(name="").exclude(name__isnull=True)
        rows = list(names.filter(query).values_list("pk", "name")) if query else []
        if not rows:
            # every word is accented or short (e.g. "José", "Zoë"), so no narrowing is possible
            rows = names.values_list("pk", "name")
        for pk, name in rows:
            if slugify(name) == slug:
                return self.get(pk=pk)
        return None

    def _create_user(self, email, password, **extra_fields):
        """Create and save a User with the given email and password."""
        if not email:
            raise ValueError("The given email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular User with the given email and password."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        """Create and save a SuperUser with the given email and password."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """user model

     * email is used for logging in
     * username is only used for legacy users, so they can still log in like on the old site
     * name is used instead of first_name and last_name
    """

    # username is only for legacy users and None/null by default, but unique for non-null values
    username = models.CharField(_("username"), unique=True, default=None, max_length=150, blank=True, null=True)

    email = models.EmailField(_("email address"), unique=True)
    first_name = None
    last_name = None
    name = models.CharField(_("name"), blank=True, max_length=255)
    image = models.ImageField(_('image'), upload_to='user-images', null=True, blank=True)
    about = models.TextField(_('About you'),  blank=True, null=True)
    # simple skill tags for quick matching and display (requires django-taggit)
    skills = TaggableManager(blank=True)
    country = CountryField(_("Country"), null=True, blank=True)
    location_name = models.CharField(_("Location"), null=True, blank=True, max_length=255)
    location = models.PointField(_("Geo Location"), null=True, blank=True, geography=True)
    ecobasa_what = models.TextField(_('What would you like to use ecobasa mainly for?'), blank=True, null=True)
    world = models.TextField(_('What do you do to make the world a better place?'), blank=True, null=True)
    # Last language picked in the language switcher; emails to this user are sent in it.
    language = models.CharField(_("Language"), max_length=10, choices=settings.LANGUAGES, blank=True)
    # When they last used the site while logged in (LastSeenMiddleware, at most every few
    # minutes), shown as "last active" so visitors can tell who is likely to answer.
    last_seen = models.DateTimeField(_("Last active"), null=True, blank=True)
    # Matches (suggestions app): within this distance, and a weekly email about new ones
    match_emails = models.BooleanField(
        _("Email me weekly about new suggestions for my wishes, offers and skills"), default=True,
    )
    match_radius = models.PositiveSmallIntegerField(_("How far away (km)?"), default=150)
    match_global = models.BooleanField(_("Search worldwide"), default=False)
    # Suggestions of tours to travel along on: paused until this day, or off until they
    # turn them on again (PAUSED_FOREVER)
    tours_paused_until = models.DateField(_("Tour suggestions paused until"), null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["name"]

    objects = UserManager()

    def get_absolute_url(self) -> str:
        # Prefer username; otherwise slugified name; finally primary key
        slug = self.username or slugify(self.name) or str(self.pk)
        return reverse("users:detail", kwargs={"slug": slug})

    # ── Tour suggestions, on or paused ──────────────────────────────
    PAUSED_FOREVER = datetime.date.max
    TOUR_PAUSE_CHOICES = [
        ("on", _("On")),
        ("1", _("Pause for 1 month")),
        ("3", _("3 months")),
        ("6", _("6 months")),
        ("off", _("Off")),
    ]

    @property
    def tours_paused(self):
        """Whether they don't want to hear of tours to travel along on now."""
        return self.tours_paused_until is not None and self.tours_paused_until >= timezone.localdate()

    @property
    def tours_off(self):
        return self.tours_paused_until == self.PAUSED_FOREVER

    def pause_tours(self, choice):
        """Set the pause from one of TOUR_PAUSE_CHOICES (not saved)."""
        if choice == "on":
            self.tours_paused_until = None
        elif choice == "off":
            self.tours_paused_until = self.PAUSED_FOREVER
        elif choice in ("1", "3", "6"):
            self.tours_paused_until = add_months(timezone.localdate(), int(choice))

    @property
    def last_active(self):
        """Last time they were around: last_seen, or their last login before it existed."""
        return self.last_seen or self.last_login

    def member_communities(self):
        """The communities they belong to. For now the ones they're the ambassador of
        (as Community.members); real membership can extend this."""
        return list(self.communities.all())

    def get_reference_subjects(self):
        """What references on this profile can be about: the person and their offers and
        wishes (things and skills)."""
        return [self, *self.listings.filter(community=None)]

    def has_skill(self, skill):
        from gift_economy.gifts.models import skill_offers
        return skill_offers(self).filter(skill=skill).exists()

    def add_skill(self, skill):
        from gift_economy.gifts.models import add_skill_offer
        return add_skill_offer(self, skill)

    def email_user(self, subject, message, from_email=None, **kwargs):
        '''
        Sends an email to this User.
        '''
        send_mail(subject, message, from_email, [self.email], **kwargs)


def add_months(day, months):
    """The same day `months` later, or the month's last day if it is shorter."""
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    last = calendar.monthrange(year, month)[1]
    return day.replace(year=year, month=month, day=min(day.day, last))
