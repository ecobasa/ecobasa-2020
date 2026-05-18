from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.bootstrap import InlineRadios, InlineCheckboxes
from crispy_forms.layout import Layout, Field, Fieldset as CrispyFieldset
from django.contrib.gis import forms

from .widgets import LocationWidget
from .models import Ad, AdRequest, AdRequestMessage


class Fieldset(CrispyFieldset):
    def __init__(self, *args, **kwargs):
        self.text = kwargs.pop("header_text", "")
        super().__init__(*args, **kwargs)


class AdForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Fieldset("", InlineRadios("type"), InlineCheckboxes("categories")),
            Fieldset(
                _("Content"),
                Field("title"),
                Field("image"),
                Field("description"),
                header_text=_("Describe your wish or offer here"),
            ),
        )

    class Meta:
        model = Ad
        fields = (
            "type",
            "title",
            "description",
            "image",
            "categories",
            "location_name",
            "location",
        )
        widgets = {
            "type": forms.RadioSelect,
            "categories": forms.CheckboxSelectMultiple,
            "location_name": forms.HiddenInput,
            "location": forms.HiddenInput,
        }


class AdRequestForm(forms.ModelForm):
    class Meta:
        model = AdRequest
        fields = ("message", "location_type", "proposed_location", "proposed_lat", "proposed_lon", "proposed_date")
        widgets = {
            "message": forms.Textarea(attrs={"rows": 4, "class": "form-textarea w-full", "placeholder": "Write a short message about why you're interested…"}),
            "location_type": forms.RadioSelect,
            "proposed_location": forms.HiddenInput,
            "proposed_lat": forms.HiddenInput,
            "proposed_lon": forms.HiddenInput,
            "proposed_date": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-input"}),
        }


class AdRequestMessageForm(forms.ModelForm):
    class Meta:
        model = AdRequestMessage
        fields = ("body",)
        widgets = {
            "body": forms.Textarea(attrs={"rows": 3, "class": "form-textarea w-full", "placeholder": "Add a message (optional)…"}),
        }

