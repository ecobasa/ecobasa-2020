from django.db import models
from django.utils.translation import gettext_lazy as _, ngettext

from users.models import User


SKILL_NUDGE_TEXT = _(
    "Your profile has no skills yet — add what you can offer and "
    "what you want to learn or need help with so communities and "
    "people can find you."
)

MATCH_AREA_TEXT = _(
    "You get suggestions from everywhere, because your profile has no place yet. "
    "Add your place or country in the settings to see what's near you."
)

# Icon per kind of match, keyed by the target's app label (same approach as
# matches.views._TAB_APP_LABELS, so this app never imports gifts/skills/communities).
_MATCH_TYPE_ICONS = {
    "gifts":       "fa-gift",
    "skills":      "fa-graduation-cap",
    "communities": "fa-campground",
    "projects":    "fa-person-digging",
}


class Notification(models.Model):
    TAG_REQUESTED   = "requested"
    TAG_ACCEPTED    = "accepted"
    TAG_DECLINED    = "declined"
    TAG_COUNTER     = "counter"
    TAG_MESSAGE     = "message"
    TAG_SKILL_NUDGE = "skill_nudge"
    TAG_REFERENCE   = "reference"
    TAG_SUGGESTION  = "suggestion"
    TAG_MATCH_AREA  = "match_area"

    recipient   = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    actor       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications_sent")
    # The match this notification is about. Its text is built from tag + match at display
    # time, so it shows in the reader's language rather than the actor's.
    match       = models.ForeignKey(
        "matches.Match", on_delete=models.CASCADE, null=True, blank=True, related_name="notifications",
    )
    # Same for a new reference about you (or something you hold, or your community)
    reference   = models.ForeignKey(
        "references.Reference", on_delete=models.CASCADE, null=True, blank=True, related_name="notifications",
    )
    # Fallback text, rendered at creation time: used for notifications without a match
    # (or whose match target has since been deleted) and in the admin.
    verb        = models.CharField(_("Message"), max_length=255)
    link        = models.CharField(_("Link"), max_length=500, blank=True)
    tag         = models.CharField(max_length=20, blank=True)
    is_read     = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = _("Notification")
        verbose_name_plural = _("Notifications")

    def __str__(self):
        return f"→ {self.recipient}: {self.verb}"

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.save(update_fields=["is_read"])

    def _target(self):
        return self.match.target if self.match_id else None

    @property
    def text(self):
        """The notification sentence in the currently active language."""
        if self.tag == self.TAG_SKILL_NUDGE:
            return str(SKILL_NUDGE_TEXT)
        if self.tag == self.TAG_REFERENCE:
            return self._reference_text()
        if self.tag == self.TAG_SUGGESTION:
            return self._suggestion_text()
        if self.tag == self.TAG_MATCH_AREA:
            return str(MATCH_AREA_TEXT)
        target = self._target()
        if target is None:
            return self.verb

        if self.tag == self.TAG_REQUESTED:
            template = target.get_match_request_text()
        elif self.tag == self.TAG_ACCEPTED:
            # The requester can only accept/decline a counter-proposal from the owner.
            template = (_("%(actor)s accepted your counter-proposal for: %(title)s")
                        if self.actor_id == self.match.from_user_id
                        else _("%(actor)s accepted your request: %(title)s"))
        elif self.tag == self.TAG_DECLINED:
            template = (_("%(actor)s declined your counter-proposal for: %(title)s")
                        if self.actor_id == self.match.from_user_id
                        else _("%(actor)s declined your request: %(title)s"))
        elif self.tag == self.TAG_COUNTER:
            template = (_("%(actor)s suggested other dates for your stay at: %(title)s")
                        if self.match.is_community_stay
                        else _("%(actor)s suggested another time or place for: %(title)s"))
        elif self.tag == self.TAG_MESSAGE:
            template = _("%(actor)s sent you a message about: %(title)s")
        else:
            return self.verb

        actor = (self.actor.name or self.actor.email) if self.actor else _("Someone")
        return str(template) % {"actor": actor, "title": target.get_match_display_name()}

    def _suggestion_text(self):
        """Counts what is new for them, so the one notification stays true."""
        new = self.recipient.suggestions.filter(seen_at=None, dismissed_at=None).count()
        if not new:
            return str(_("Suggestions near you: what fits your wishes, offers and skills."))
        return ngettext(
            "%(count)s new suggestion near you: something fits your wishes, offers or skills.",
            "%(count)s new suggestions near you: things fit your wishes, offers or skills.",
            new,
        ) % {"count": new}

    def _reference_text(self):
        subject = self.reference.subject if self.reference_id else None
        if subject is None:
            return self.verb
        actor = (self.actor.name or self.actor.email) if self.actor else _("Someone")
        if subject == self.recipient:
            text = _("%(actor)s wrote a reference about you.") % {"actor": actor}
        else:
            title = getattr(subject, "get_match_display_name", lambda: str(subject))()
            text = _("%(actor)s wrote a reference about %(title)s.") % {"actor": actor, "title": title}
        if self.reference.skill_tags.filter(status="pending").exists():
            text = "%s %s" % (text, _("It mentions skills that wait for your confirmation."))
        return str(text)

    @property
    def icon(self):
        """Font Awesome (solid) icon class for this notification."""
        if self.tag == self.TAG_REQUESTED:
            target = self._target()
            if target is None:
                return "fa-bell"
            if getattr(target, "type", None) == "wish":
                return "fa-hand-holding-heart"
            return _MATCH_TYPE_ICONS.get(self.match.content_type.app_label, "fa-bell")
        return {
            self.TAG_ACCEPTED:    "fa-handshake-simple",
            self.TAG_DECLINED:    "fa-handshake-simple-slash",
            self.TAG_COUNTER:     "fa-hand-holding-hand",
            self.TAG_MESSAGE:     "fa-comment",
            self.TAG_SKILL_NUDGE: "fa-graduation-cap",
            self.TAG_REFERENCE:   "fa-comments",
            self.TAG_SUGGESTION:  "fa-handshake-angle",
            self.TAG_MATCH_AREA:  "fa-location-dot",
        }.get(self.tag, "fa-bell")
