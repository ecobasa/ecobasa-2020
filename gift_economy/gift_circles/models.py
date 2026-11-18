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
