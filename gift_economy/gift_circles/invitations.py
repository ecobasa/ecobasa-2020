"""Inviting to a gift-circle: its host and who comes invite members by name and anyone by
email. Who was invited comes without asking."""

from django.conf import settings
from django.db import transaction
from django.utils import translation
from django.utils.translation import get_language, gettext as _

from gift_economy.matches.models import Match

from .emails import send_email_invitation, send_member_invitation
from .models import Invitation

# How many addresses one gift-circle invites by email, all inviters together: anyone
# can host one, so ecobasa's mail doesn't become a way to write to strangers in bulk
EMAIL_LIMIT = 50


def may_invite(event, user):
    """Its host and who comes, while it is ahead."""
    if not (event.is_current and user.is_authenticated):
        return False
    return event.can_edit(user) or event.matches.filter(from_user=user, status=Match.STATUS_ACCEPTED).exists()


def emails_left(event):
    return max(0, EMAIL_LIMIT - event.invitations.exclude(email="").count())


def taken_users(event):
    """Members who needn't be invited: the host, who comes or asked, who was invited."""
    taken = set(event.matches.exclude(status__in=Match.CLOSED_STATUSES).values_list("from_user_id", flat=True))
    taken.update(event.invitations.exclude(user=None).values_list("user_id", flat=True))
    if event.manager is not None:
        taken.add(event.manager.pk)
    return taken


def taken_emails(event):
    """Addresses invited already, or signed up as a guest, in lower case."""
    taken = {email.lower() for email in event.invitations.exclude(email="").values_list("email", flat=True)}
    taken.update(email.lower() for email in event.guests.values_list("email", flat=True))
    return taken


def invite(event, inviter, users, people, message):
    """Invite `users` (members) and `people` ((name, email) pairs) with the few words
    `message`: a notification and an email to each member, an email to each address.
    Whoever was invited or comes already is left out. Returns the invitations made."""
    language = get_language() or ""
    made = []
    with transaction.atomic():
        taken = taken_users(event) | {inviter.pk}
        for user in users:
            if user.pk not in taken:
                taken.add(user.pk)
                made.append(Invitation.objects.create(event=event, invited_by=inviter, user=user, language=language))
        taken = taken_emails(event)
        for name, email in people:
            if email.lower() not in taken:
                taken.add(email.lower())
                made.append(Invitation.objects.create(
                    event=event, invited_by=inviter, name=name, email=email.lower(), language=language,
                ))
    transaction.on_commit(lambda: _send(made, message))
    return made


def _send(invitations, message):
    from notifications.models import Notification

    for invitation in invitations:
        user = invitation.user
        if user is None:
            send_email_invitation(invitation, message)
            continue
        with translation.override(user.language or settings.LANGUAGE_CODE):
            verb = _("%(name)s invites you to a gift-circle: %(title)s") % {
                "name": invitation.inviter_name(), "title": invitation.event.title,
            }
        Notification.objects.create(
            recipient=user, actor=invitation.invited_by, verb=verb[:255], link=invitation.event.get_absolute_url(),
            tag=Notification.TAG_INVITATION,
        )
        if user.email:
            send_member_invitation(invitation, message)


def answer(invitation, user):
    """Someone invited by email says they come with their account: the invitation is
    theirs from now on, and their address no longer kept with it."""
    event = invitation.event
    if event.invitations.filter(user=user).exists():
        invitation.delete()
    else:
        invitation.user = user
        invitation.name = invitation.email = ""
        invitation.save(update_fields=["user", "name", "email"])
