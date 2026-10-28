from django import forms
from django.utils.translation import gettext_lazy as _

from crispy_forms.layout import Fieldset as CrispyFieldset
from django.contrib.gis import forms

from skills.models import get_or_create_skill
from .models import Listing


class Fieldset(CrispyFieldset):
    def __init__(self, *args, **kwargs):
        self.text = kwargs.pop("header_text", "")
        super().__init__(*args, **kwargs)


def shrunk(image):
    """A newly uploaded photo as a JPEG of a sensible size, turned upright; anything
    else (nothing, the photo already saved) as it is."""
    from django.core.files.uploadedfile import UploadedFile
    from references.reference_requests import shrink_photo

    if not isinstance(image, UploadedFile):
        return image
    try:
        return shrink_photo(image)
    except ValueError:
        raise forms.ValidationError(_("Please upload a photo."))


class ListingForm(forms.ModelForm):
    """An offer or a wish of any kind: a thing (material, tool, anything else), a skill,
    knowledge or helping hands. A skill names a skill in any language ("Zimmerei" is
    Carpentry); knowledge and helping hands can name one, so people with it are found."""

    skill_name = forms.CharField(
        label=_("Skill"), max_length=100, required=False,
        widget=forms.TextInput(attrs={
            "autocomplete": "off", "list": "skill-suggestions", "data-skill-name": "",
            "placeholder": _("e.g. Carpentry, Solar energy, Cooking"),
        }),
    )

    class Meta:
        model = Listing
        fields = (
            "type", "kind", "skill_name", "title", "quantity", "unit", "level", "available",
            "description", "image", "categories", "location_name", "location",
        )
        widgets = {
            "type": forms.RadioSelect,
            "kind": forms.RadioSelect,
            "categories": forms.CheckboxSelectMultiple,
            "description": forms.Textarea(attrs={"rows": 4}),
            "location_name": forms.HiddenInput,
            "location": forms.HiddenInput,
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["type"].choices = Listing.TYPE_CHOICES
        self.fields["kind"].required = False
        self.fields["kind"].choices = Listing.KIND_CHOICES
        self.fields["title"].help_text = _("For knowledge or helping hands: what for, if no skill says it.")
        self.fields["quantity"].help_text = _("Optional: how many or how much you offer or wish for.")
        self.fields["quantity"].widget.attrs["min"] = "1"
        self.fields["unit"].choices = [("", _("no unit"))] + list(self.fields["unit"].choices)[1:]
        self.fields["level"].choices = [("", "—")] + Listing.LEVEL_CHOICES
        self.fields["image"].label = _("Photo")
        if self.instance.pk and self.instance.skill_id:
            self.initial["skill_name"] = self.instance.skill.get_name()

    def clean_kind(self):
        return self.cleaned_data.get("kind") or Listing.KIND_OTHER

    def clean_image(self):
        return shrunk(self.cleaned_data.get("image"))

    def clean(self):
        cleaned = super().clean()
        kind = cleaned.get("kind") or Listing.KIND_OTHER
        skill_name = (cleaned.get("skill_name") or "").strip()
        title = (cleaned.get("title") or "").strip()
        if kind == Listing.KIND_SKILL and not skill_name:
            self.add_error("skill_name", _("Which skill?"))
        elif kind in Listing.SKILL_KINDS and not (skill_name or title):
            self.add_error("title", _("Name a skill or say what for."))
        elif kind in Listing.THING_KINDS and not title:
            self.add_error("title", _("What is it?"))
        if kind in Listing.THING_KINDS:
            cleaned["skill_name"] = ""
            cleaned["level"] = ""
        else:
            cleaned["categories"] = []
        return cleaned

    def save(self, commit=True):
        listing = super().save(commit=False)
        skill_name = self.cleaned_data.get("skill_name", "").strip()
        listing.skill = get_or_create_skill(skill_name)[0] if skill_name else None
        if listing.kind == Listing.KIND_SKILL:
            listing.title = listing.skill.name
        if commit:
            listing.save()
            self.save_m2m()
        return listing
