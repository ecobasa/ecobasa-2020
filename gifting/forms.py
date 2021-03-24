from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.bootstrap import InlineRadios, InlineCheckboxes
from crispy_forms.layout import Layout, Field, Fieldset as CrispyFieldset
from django.contrib.gis import forms

from .widgets import LocationWidget
from .models import Ad


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
            Fieldset(_("Location"), Field("location_name"), Field("location")),
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
            "location_name": LocationWidget,
            "location": forms.OSMWidget(attrs={'map_width': '100%', 'map_height': 400, 'default_zoom': 1}),
        }

