from django import forms

from .models import Guest


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
