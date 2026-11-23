from django.db import models


class BotCheckEntry(models.Model):
    """One message or signup that went through a bot check (bot_check.py), only for its
    limits. Keyed hashes, never the address, name or text: the mail or the account itself
    is the record."""

    FORM_CHOICES = [("contact", "Contact"), ("signup", "Signup"), ("guest", "Gift-circle guest"),
                    ("password_reset", "Password reset")]

    form = models.CharField(max_length=20, choices=FORM_CHOICES)
    ip_digest = models.CharField(max_length=64, db_index=True)
    email_digest = models.CharField(max_length=64, blank=True, db_index=True)
    text_digest = models.CharField(max_length=64, blank=True, db_index=True)
    # What it was for, when limits count per thing too (a guest: the gift-circle)
    scope = models.CharField(max_length=64, blank=True)
    # The form's challenge: each one goes through once
    token_digest = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name_plural = "bot check entries"
