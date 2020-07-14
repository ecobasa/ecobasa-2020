from django import forms

from .models import Ad


class AdForm(forms.ModelForm):
    class Meta:
        model = Ad
        fields = ("type", "title", "description")
        widgets = {"type": forms.RadioSelect}
