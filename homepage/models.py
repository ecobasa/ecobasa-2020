from django.db import models


class ContactSubmission(models.Model):
    """One message sent through the contact page, only for the spam limits. Keyed hashes,
    never the address, name or text: the mail itself is the record."""

    ip_digest = models.CharField(max_length=64, db_index=True)
    email_digest = models.CharField(max_length=64, db_index=True)
    text_digest = models.CharField(max_length=64, db_index=True)
    # The form's challenge: each one sends once
    token_digest = models.CharField(max_length=64, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
