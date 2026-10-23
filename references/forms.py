from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Reference


class ReferenceForm(forms.ModelForm):
    class Meta:
        model = Reference
        fields = ("tone", "text")
        widgets = {
            "tone": forms.RadioSelect,
            "text": forms.Textarea(attrs={
                "rows": 4, "class": "form-input",
                "placeholder": _("What was it like? What should others know?"),
            }),
        }
