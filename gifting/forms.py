from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.helper import FormHelper
from crispy_forms.bootstrap import InlineRadios, InlineCheckboxes
from crispy_forms.layout import Layout, Field, Fieldset as CrispyFieldset

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
                Field("description"),
                header_text=_("Describe your wish or offer here"),
            ),
        )

    class Meta:
        model = Ad
        fields = ("type", "title", "description", "categories")
        widgets = {
            "type": forms.RadioSelect,
            "categories": forms.CheckboxSelectMultiple,
        }

