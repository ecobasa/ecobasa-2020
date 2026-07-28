from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Match


class MatchForm(forms.ModelForm):
    """Shared 'express interest' form for gifts, skills, and volunteering.

    proposed_lat/proposed_lon are blank=True on the model, so Django already makes
    these form fields optional — no need to redeclare them.
    """

    class Meta:
        model = Match
        fields = ("message", "location_type", "proposed_location", "proposed_lat", "proposed_lon", "proposed_date")
        widgets = {
            "message": forms.Textarea(attrs={
                "rows": 4, "class": "form-input",
                "placeholder": _("Write a short message about why you're interested…"),
            }),
            "location_type": forms.RadioSelect,
            "proposed_location": forms.TextInput(attrs={
                "placeholder": _("City, region, address…"),
                "class": "form-input",
            }),
            "proposed_lat": forms.HiddenInput,
            "proposed_lon": forms.HiddenInput,
            "proposed_date": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-input"}),
        }


class MatchMessageForm(forms.Form):
    body = forms.CharField(
        label=_("Message"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-input", "placeholder": _("Write a message…")}),
    )
