from django import forms
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from .models import Match


class MatchForm(forms.ModelForm):
    """Shared 'express interest' form for gifts, skills, and volunteering.

    proposed_lat/proposed_lon are blank=True on the model, so Django already makes
    these form fields optional — no need to redeclare them.
    """

    # How much of an offer or wish with a quantity the request takes or brings
    quantity = forms.IntegerField(label=_("How much?"), required=False, min_value=1,
                                  widget=forms.NumberInput(attrs={"class": "form-input w-28", "min": "1"}))

    # From when until when a tool to lend (or to borrow) is borrowed: asked for with loan_of
    borrow_from = forms.DateField(label=_("Borrow from"), required=False,
                                  widget=forms.DateInput(attrs={"type": "date", "class": "form-input"}))
    borrow_to = forms.DateField(label=_("Borrow until"), required=False,
                                widget=forms.DateInput(attrs={"type": "date", "class": "form-input"}))

    def __init__(self, *args, loan_of=None, **kwargs):
        """loan_of: the tool to lend or to borrow the request is for; then it asks when."""
        super().__init__(*args, **kwargs)
        self.loan_of = loan_of
        if loan_of is not None:
            self.fields["borrow_from"].required = self.fields["borrow_to"].required = True

    def clean(self):
        cleaned = super().clean()
        if self.loan_of is None:
            return cleaned
        starts_on, ends_on = cleaned.get("borrow_from"), cleaned.get("borrow_to")
        if not (starts_on and ends_on):
            return cleaned
        if ends_on < starts_on:
            self.add_error("borrow_to", _("It can't come back before it is borrowed."))
        elif starts_on < timezone.localdate():
            self.add_error("borrow_from", _("Please choose a day from today on."))
        elif self.loan_of.lends_out and not self.loan_of.is_free(starts_on, ends_on):
            self.add_error("borrow_from", _("It is already lent then: %(days)s") % {"days": ", ".join(
                f"{date_format(loan.starts_on, 'SHORT_DATE_FORMAT')}–{date_format(loan.ends_on, 'SHORT_DATE_FORMAT')}"
                for loan in self.loan_of.upcoming_loans() if loan.overlaps(starts_on, ends_on)
            )})
        return cleaned

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
