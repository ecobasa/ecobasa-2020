from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.bootstrap import InlineRadios, InlineCheckboxes
from crispy_forms.layout import Div, Layout, Field, Fieldset as CrispyFieldset
from django.contrib.gis import forms

from .widgets import LocationWidget
from .models import Listing


class Fieldset(CrispyFieldset):
    def __init__(self, *args, **kwargs):
        self.text = kwargs.pop("header_text", "")
        super().__init__(*args, **kwargs)


class ListingForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["quantity"].help_text = _("Optional: how many or how much you offer or wish for.")
        self.fields["quantity"].widget.attrs["min"] = "1"
        self.fields["unit"].choices = [("", _("no unit"))] + list(self.fields["unit"].choices)[1:]
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Fieldset("", InlineRadios("type"), InlineCheckboxes("categories")),
            Fieldset(
                _("Content"),
                Field("title"),
                Div(
                    Div(Field("quantity"), css_class="w-1/2 sm:w-1/3"),
                    Div(Field("unit"), css_class="w-1/2 sm:w-1/3"),
                    css_class="flex gap-4",
                ),
                Field("image"),
                Field("description"),
                header_text=_("Describe your wish or offer here"),
            ),
        )

    class Meta:
        model = Listing
        fields = (
            "type",
            "title",
            "quantity",
            "unit",
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



