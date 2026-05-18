from django.db import models
from django.utils.translation import gettext_lazy as _

from users.models import User


class Notification(models.Model):
    TAG_REQUESTED = "requested"
    TAG_ACCEPTED  = "accepted"
    TAG_DECLINED  = "declined"
    TAG_COUNTER   = "counter"
    TAG_MESSAGE   = "message"

    recipient   = models.ForeignKey(User, on_delete=models.CASCADE, related_name="notifications")
    actor       = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications_sent")
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
