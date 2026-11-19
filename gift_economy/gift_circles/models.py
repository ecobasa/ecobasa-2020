import secrets

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


def new_token():
    return secrets.token_urlsafe(24)


class GuestQuerySet(models.QuerySet):
    def coming(self):
        """Who comes as a guest: confirmed, and without an account yet (with one they
        come as everyone does)."""
        return self.filter(confirmed_at__isnull=False, user=None)


class Guest(models.Model):
    """Someone who comes to a gift-circle without an account: a name and an email. They
    count once they confirmed the email, and change or leave through the link in it
    (`token`). Nobody gets an account without asking for one; when they create one
    through their link, their rows are linked to it (`user`)."""

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="guests")
    name = models.CharField(_("Name"), max_length=100)
    email = models.EmailField(_("Email"))
    people = models.PositiveSmallIntegerField(
        _("How many are you?"), default=1, help_text=_("You and whoever comes with you, children too."),
    )
    token = models.CharField(max_length=64, unique=True, default=new_token)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    # When the confirmation link last went out: not again right away
    mailed_at = models.DateTimeField(null=True, blank=True)
    keep_on_ecobasa = models.BooleanField(_("Keep my offers and wishes from this gift-circle on ecobasa"), default=False)
    share_email = models.BooleanField(
        _("The people I make a match with at this gift-circle may get my email"), default=False,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="guest_rows",
    )
    language = models.CharField(max_length=10, blank=True)
    # Came without signing up, added to the Giftsheet with an email by its scribe: counts
    # as confirmed (they were there), and among the addresses the gift-circle may mail
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = GuestQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Guest")
        verbose_name_plural = _("Guests")
        constraints = [models.UniqueConstraint(fields=["event", "email"], name="one_guest_per_email_and_gift_circle")]

    def __str__(self):
        return f"{self.name} at {self.event}"


class Attendee(models.Model):
    """What someone with an account who comes to a gift-circle said yes to: whether their
    offers and wishes from it stay on ecobasa. Set when they come or ask to join,
    changeable on its page."""

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="attendees")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="gift_circles")
    keep_on_ecobasa = models.BooleanField(_("Keep my offers and wishes from this gift-circle on ecobasa"), default=False)

    class Meta:
        verbose_name = _("Attendee")
        verbose_name_plural = _("Attendees")
        constraints = [models.UniqueConstraint(fields=["event", "user"], name="one_attendee_per_gift_circle")]

    def __str__(self):
        return f"{self.user} at {self.event}"


class Invitation(models.Model):
    """Someone invited to a gift-circle by its host or by someone who comes: a member
    (`user`), or anyone by email (`email`, a `name` if it was given). Who was invited comes
    without asking, also when it isn't open. An address is kept for this gift-circle only,
    so the Giftsheet knows it, and deleted when they say they don't come (`token`, the link
    in their email) or sign up as a guest (then the guest row has it)."""

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="invitations")
    invited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="gift_circle_invitations",
    )
    name = models.CharField(_("Name"), max_length=100, blank=True)
    email = models.EmailField(_("Email"), blank=True)
    token = models.CharField(max_length=64, unique=True, default=new_token)
    # The inviter's, who writes the few words: an address has no language of its own
    language = models.CharField(max_length=10, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Invitation")
        verbose_name_plural = _("Invitations")
        constraints = [
            models.CheckConstraint(
                name="invitation_to_a_member_or_an_email",
                check=models.Q(user__isnull=False, email="") | models.Q(user=None) & ~models.Q(email=""),
            ),
            models.UniqueConstraint(
                fields=["event", "user"], condition=models.Q(user__isnull=False), name="one_invitation_per_member",
            ),
            models.UniqueConstraint(
                fields=["event", "email"], condition=~models.Q(email=""), name="one_invitation_per_email",
            ),
        ]

    def __str__(self):
        return f"{self.user or self.email} to {self.event}"

    def inviter_name(self):
        """Who invites, as the one invited reads it: never their email."""
        return (self.invited_by.name if self.invited_by else "") or self.event.host_name


class Brought(models.Model):
    """An offer or a wish of someone's own that they bring to a gift-circle they come to
    or host: linked, nothing copied, so it stays one listing on ecobasa. Its page lists
    what people bring while they still come."""

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="brought")
    listing = models.ForeignKey("gifts.Listing", on_delete=models.CASCADE, related_name="brought_to")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Brought offer or wish")
        verbose_name_plural = _("Brought offers and wishes")
        constraints = [models.UniqueConstraint(fields=["event", "listing"], name="bring_a_listing_once")]

    def __str__(self):
        return f"{self.listing} to {self.event}"


class Giftsheet(models.Model):
    """The table the scribe keeps at a gift-circle: its lines are its `entries`. Made when
    someone first opens it, with what people bring already on it. When the host closes
    it, its lines become offers, wishes and matches on ecobasa."""

    event = models.OneToOneField("events.Event", on_delete=models.CASCADE, related_name="giftsheet")
    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    # When everyone got the results: once, on the first closing
    results_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Giftsheet")
        verbose_name_plural = _("Giftsheets")

    def __str__(self):
        return f"Giftsheet of {self.event}"

    @property
    def is_closed(self):
        return self.closed_at is not None


class Scribe(models.Model):
    """Someone the host lets write the Giftsheet, besides themselves."""

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="scribes")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")

    class Meta:
        verbose_name = _("Scribe")
        verbose_name_plural = _("Scribes")
        constraints = [models.UniqueConstraint(fields=["event", "user"], name="one_scribe_per_gift_circle")]

    def __str__(self):
        return f"{self.user} at {self.event}"


class Entry(models.Model):
    """One line of the Giftsheet: an offer or a wish, from someone with an account, a
    guest, or someone known only by name; and who fulfilled the wish or took the offer
    (`for_…`). Ideas how it could happen are its `ideas`."""

    TYPE_OFFER = "offer"
    TYPE_WISH = "wish"
    TYPE_CHOICES = [(TYPE_OFFER, _("Offer")), (TYPE_WISH, _("Wish"))]

    STATE_OPEN = "open"
    STATE_FULFILLED = "fulfilled"
    STATE_CHOICES = [(STATE_OPEN, _("Still open")), (STATE_FULFILLED, _("Fulfilled"))]

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="entries")
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    text = models.CharField(max_length=255)
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="+",
    )
    from_guest = models.ForeignKey(Guest, on_delete=models.CASCADE, null=True, blank=True, related_name="entries")
    from_name = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=10, choices=STATE_CHOICES, default=STATE_OPEN)
    for_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="+",
    )
    for_guest = models.ForeignKey(Guest, on_delete=models.CASCADE, null=True, blank=True, related_name="answers")
    for_name = models.CharField(max_length=100, blank=True)
    # The offer or wish it is on ecobasa: brought to the circle, or made when it closed
    listing = models.ForeignKey("gifts.Listing", on_delete=models.SET_NULL, null=True, blank=True, related_name="entries")
    match = models.OneToOneField(
        "matches.Match", on_delete=models.SET_NULL, null=True, blank=True, related_name="giftsheet_entry",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    # A tool to lend, and from which day until which day it is borrowed, if they knew it
    # already: else they propose the days on the match afterwards
    lend = models.BooleanField(_("To lend"), default=False)
    borrow_from = models.DateField(_("Borrow from"), null=True, blank=True)
    borrow_to = models.DateField(_("Borrow until"), null=True, blank=True)
    # A fulfilled wish: when the one who wished was asked whether it came true, and what
    # they said (None: not yet answered)
    asked_at = models.DateTimeField(null=True, blank=True)
    came_true = models.BooleanField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("Entry")
        verbose_name_plural = _("Entries")
        constraints = [
            models.CheckConstraint(
                name="entry_from_one_person",
                check=(
                    models.Q(from_user__isnull=False, from_guest=None, from_name="")
                    | models.Q(from_user=None, from_guest__isnull=False, from_name="")
                    | models.Q(from_user=None, from_guest=None) & ~models.Q(from_name="")
                ),
            ),
        ]

    def __str__(self):
        return self.text

    @property
    def is_offer(self):
        return self.type == self.TYPE_OFFER

    @property
    def from_label(self):
        return _person_name(self.from_user, self.from_guest, self.from_name)

    @property
    def from_choice(self):
        """Whom it is from, as the person picker says it."""
        return _person_choice(self.from_user_id, self.from_guest_id, self.from_name)

    @property
    def for_label(self):
        return _person_name(self.for_user, self.for_guest, self.for_name)

    @property
    def lends(self):
        return self.lend

    # ── As what a match made on closing is attached to (gift_economy.matches) ──
    match_attachment_template = "gift_circles/_match_entry.html"


class Idea(models.Model):
    """An idea how a line of the Giftsheet could happen when nobody can do it right away,
    and whose it is. A line can have several, from several people."""

    entry = models.ForeignKey(Entry, on_delete=models.CASCADE, related_name="ideas")
    text = models.CharField(max_length=255)
    from_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="+",
    )
    from_guest = models.ForeignKey(Guest, on_delete=models.CASCADE, null=True, blank=True, related_name="ideas")
    from_name = models.CharField(max_length=100, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = _("Idea")
        verbose_name_plural = _("Ideas")
        constraints = [
            models.CheckConstraint(
                name="idea_from_one_person",
                check=(
                    models.Q(from_user__isnull=False, from_guest=None, from_name="")
                    | models.Q(from_user=None, from_guest__isnull=False, from_name="")
                    | models.Q(from_user=None, from_guest=None) & ~models.Q(from_name="")
                ),
            ),
        ]

    def __str__(self):
        return self.text

    @property
    def from_label(self):
        return _person_name(self.from_user, self.from_guest, self.from_name)

    # ── As what a story from its gift-circle is about (references) ──
    reference_subject = True

    def can_be_referenced_by(self, user):
        """Who came to its gift-circle, about someone else's idea."""
        return user.pk != self.from_user_id and self.entry.event.can_be_referenced_by(user)

    def get_reference_kind(self):
        return _("Idea"), "fa-lightbulb", "bg-yellow"

    def get_match_owner(self):
        return self.from_user

    def get_match_display_name(self):
        return self.text

    def get_match_icon(self):
        return "fa-lightbulb"

    def get_absolute_url(self):
        return f"{self.entry.event.get_absolute_url()}#references"


def _person_name(user, guest, name):
    if user is not None:
        return user.name or user.email
    if guest is not None:
        return guest.name
    return name


def _person_choice(user_id, guest_id, name):
    if user_id is not None:
        return f"user:{user_id}"
    if guest_id is not None:
        return f"guest:{guest_id}"
    return f"name:{name}"


class GiftsheetPhoto(models.Model):
    """A photo of the Giftsheet filled in on paper."""

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="giftsheet_photos")
    image = models.ImageField(_("Photo"), upload_to="giftsheet-photos/")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]
        verbose_name = _("Photo of the Giftsheet")
        verbose_name_plural = _("Photos of the Giftsheet")

    def __str__(self):
        return f"Photo of the Giftsheet of {self.event}"
