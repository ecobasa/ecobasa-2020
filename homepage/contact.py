"""The contact form. Besides the bot check (bot_check.py), limits per sender and text,
and few links. No confirmation goes to the sender, so the form can't be used to mail
strangers."""

import re
from datetime import timedelta

from django import forms
from django.conf import settings
from django.core.mail import EmailMessage
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.translation import get_language, gettext_lazy as _

import bot_check
from bot_check import LINK

MAX_LINKS = 2
# (at most, within)
PER_ADDRESS = [(3, timedelta(hours=1)), (8, timedelta(days=1))]
PER_SENDER = (3, timedelta(days=1))
SAME_TEXT = timedelta(days=7)


def text_digest(text):
    return bot_check.digest(re.sub(r"\W+", "", text.lower()))


class ContactForm(forms.Form):
    name = forms.CharField(label=_("Name"), max_length=80)
    email = forms.EmailField(label=_("Your email"))
    subject = forms.CharField(label=_("Subject"), max_length=100)
    message = forms.CharField(label=_("Message"), min_length=15, max_length=4000, widget=forms.Textarea(attrs={"rows": 8}))

    def __init__(self, *args, request, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.member = request.user if request.user.is_authenticated else None
        self.trapped = False
        if self.member:
            del self.fields["name"], self.fields["email"]

    def clean_name(self):
        name = " ".join(self.cleaned_data["name"].split())
        if LINK.search(name):
            raise forms.ValidationError(_("Please leave links out of your name."))
        return name

    def clean_subject(self):
        subject = " ".join(self.cleaned_data["subject"].split())
        if LINK.search(subject):
            raise forms.ValidationError(_("Please leave links out of the subject."))
        return subject

    def clean_message(self):
        message = self.cleaned_data["message"].strip()
        if len(LINK.findall(message)) > MAX_LINKS:
            raise forms.ValidationError(_("Please send at most two links."))
        return message

    def clean(self):
        data = super().clean()
        if self.errors:
            return data
        check = bot_check.check(self.request, "contact", PER_ADDRESS, challenge_needed=not self.member)
        if check.error:
            raise forms.ValidationError(check.error)
        self.trapped = check.trapped
        if self.trapped:
            return data
        rows = bot_check.entries("contact")
        most, within = PER_SENDER
        sent = rows.filter(email_digest=bot_check.digest(self.sender()[1].lower()), created_at__gte=timezone.now() - within)
        if sent.count() >= most:
            raise forms.ValidationError(_("You have sent us several messages already. Please try again tomorrow."))
        if rows.filter(text_digest=text_digest(data["message"]), created_at__gte=timezone.now() - SAME_TEXT).exists():
            raise forms.ValidationError(_("We have received this message already."))
        return data

    def sender(self):
        if self.member:
            return self.member.name or self.member.email, self.member.email
        return self.cleaned_data["name"], self.cleaned_data["email"]

    def send(self):
        """Sends it to us, unless it was a bot in the trap. False if the mail server failed."""
        if self.trapped:
            return True
        name, email = self.sender()
        message = self.cleaned_data["message"]
        lines = [f"{name} <{email}> wrote through the contact page."]
        if self.member:
            lines.append(f"Member: {self.request.build_absolute_uri(self.member.get_absolute_url())}")
        lines += [f"Language: {get_language()}", "", message]
        mail = EmailMessage(
            subject=f"Contact: {self.cleaned_data['subject']} ({' '.join(name.split())})"[:150],
            body="\n".join(lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[settings.CONTACT_EMAIL],
            reply_to=[email],
        )
        try:
            with transaction.atomic():
                bot_check.record(
                    self.request, "contact", challenge_needed=not self.member,
                    email_digest=bot_check.digest(email.lower()), text_digest=text_digest(message),
                )
                mail.send()
        except IntegrityError:
            # The same challenge twice at once: the first one is on its way
            return True
        except OSError:
            return False
        return True
