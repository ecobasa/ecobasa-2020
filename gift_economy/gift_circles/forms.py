from email.utils import parseaddr

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _, ngettext

from .invitations import emails_left, taken_emails
from .models import Entry, GiftsheetPhoto, Guest


class GuestChangeForm(forms.ModelForm):
    """What a guest changes through their link."""

    people = forms.IntegerField(
        label=Guest._meta.get_field("people").verbose_name, min_value=1, max_value=50, initial=1,
        widget=forms.NumberInput(attrs={"class": "form-input w-20", "min": "1", "max": "50"}),
    )

    class Meta:
        model = Guest
        fields = ["people", "keep_on_ecobasa", "share_email"]
        widgets = {
            "keep_on_ecobasa": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            "share_email": forms.CheckboxInput(attrs={"class": "form-checkbox"}),
        }


class GuestForm(GuestChangeForm):
    """Coming as a guest: a name and an email, and what they say yes to."""

    class Meta(GuestChangeForm.Meta):
        fields = ["name", "email", "people", "keep_on_ecobasa", "share_email"]
        widgets = {
            **GuestChangeForm.Meta.widgets,
            "name": forms.TextInput(attrs={"class": "form-input w-full", "autocomplete": "name"}),
            "email": forms.EmailInput(attrs={"class": "form-input w-full", "autocomplete": "email"}),
        }


def _person(line):
    """(name, email) of "Mila, mila@example.org", "Mila <mila@example.org>" or an
    address alone."""
    if "," in line:
        name, rest = line.rsplit(",", 1)
        return name.strip(), parseaddr(rest)[1].strip()
    name, email = parseaddr(line)
    return name.strip(), email.strip()


class InviteForm(forms.Form):
    """Inviting to a gift-circle: members found by name, and anyone by email, one person
    per line, with a few words to them."""

    users = forms.ModelMultipleChoiceField(
        get_user_model().objects.filter(is_active=True), required=False, widget=forms.MultipleHiddenInput,
    )
    people = forms.CharField(
        label=_("By email"), required=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-input w-full", "placeholder": "Mila, mila@example.org"}),
        help_text=_("One person per line: their name, a comma and their email. The name may be left out."),
    )
    message = forms.CharField(
        label=_("A few words to them"), required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-input w-full"}),
        help_text=_("They get it with the invitation."),
    )

    def __init__(self, event, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.event = event

    def clean_people(self):
        people, seen = [], set()
        for line in self.cleaned_data["people"].splitlines():
            if not line.strip():
                continue
            name, email = _person(line)
            try:
                validate_email(email)
            except ValidationError:
                raise ValidationError(_("This line has no email address: %(line)s") % {"line": line.strip()})
            if email.lower() not in seen:
                seen.add(email.lower())
                people.append((name[:100], email))
        new = len(seen - taken_emails(self.event))
        left = emails_left(self.event)
        if new > left:
            raise ValidationError(ngettext(
                "A gift-circle can invite %(count)s more person by email.",
                "A gift-circle can invite %(count)s more people by email.", left,
            ) % {"count": left})
        return people

    def clean(self):
        cleaned = super().clean()
        if not self.errors and not cleaned.get("users") and not cleaned.get("people"):
            raise ValidationError(_("Please choose someone, or write an email address."))
        return cleaned


class EntryForm(forms.Form):
    """A line of the Giftsheet: a wish or an offer in one line. The host and scribes pick
    whom it is from (`people`, see giftsheet.people), or write someone new."""

    type = forms.ChoiceField(choices=Entry.TYPE_CHOICES, initial=Entry.TYPE_WISH, widget=forms.RadioSelect)
    text = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-input w-full", "autocomplete": "off", "enterkeyhint": "done"}),
    )
    who = forms.ChoiceField(label=_("Who said it?"), required=False, widget=forms.Select(attrs={"class": "form-select w-full"}))
    name = forms.CharField(
        label=_("Name"), max_length=100, required=False,
        widget=forms.TextInput(attrs={"class": "form-input w-full", "autocomplete": "off"}),
    )
    email = forms.EmailField(
        label=_("Email (optional)"), required=False,
        widget=forms.EmailInput(attrs={"class": "form-input w-full", "autocomplete": "off"}),
    )

    def __init__(self, *args, people=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.picks = people is not None
        if self.picks:
            from .giftsheet import NEW

            self.fields["who"].required = True
            self.fields["who"].choices = [("", "")] + list(people) + [(NEW, _("Someone new"))]
        else:
            del self.fields["who"], self.fields["name"], self.fields["email"]


class PhotoForm(forms.ModelForm):
    class Meta:
        model = GiftsheetPhoto
        fields = ["image"]
        widgets = {"image": forms.ClearableFileInput(attrs={"accept": "image/*"})}

    def clean_image(self):
        from gift_economy.gifts.forms import shrunk

        return shrunk(self.cleaned_data.get("image"))
