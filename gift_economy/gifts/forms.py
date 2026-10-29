from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from crispy_forms.layout import Fieldset as CrispyFieldset
from django.contrib.gis import forms

from gift_economy.gifts.skills.models import get_or_create_skill
from gift_economy.gifts.things import WHITELISTED_KINDS, thing_named
from .models import Listing


class Fieldset(CrispyFieldset):
    def __init__(self, *args, **kwargs):
        self.text = kwargs.pop("header_text", "")
        super().__init__(*args, **kwargs)


def shrunk(image):
    """A newly uploaded photo as a JPEG of a sensible size, turned upright; anything
    else (nothing, the photo already saved) as it is."""
    from django.core.files.uploadedfile import UploadedFile
    from gift_economy.references.reference_requests import shrink_photo

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
            "autocomplete": "off", "data-skill-name": "",
            "placeholder": _("e.g. Carpentry, Solar energy, Cooking"),
        }),
    )

    class Meta:
        model = Listing
        fields = (
            "type", "kind", "skill_name", "title", "variety", "harvest_year", "open_pollinated", "lend",
            "quantity", "unit", "level", "available",
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
        self.fields["quantity"].help_text = _("Optional: how many or how much you offer or wish for.")
        self.fields["quantity"].widget.attrs["min"] = "1"
        self.fields["unit"].choices = [("", _("no unit"))] + list(self.fields["unit"].choices)[1:]
        self.fields["level"].choices = [("", "—")] + Listing.LEVEL_CHOICES
        self.fields["image"].label = _("Photo")
        self.fields["title"].widget.attrs.update({"class": "textinput form-input", "data-thing-title": "", "autocomplete": "off"})
        self.fields["variety"].widget.attrs["placeholder"] = _("e.g. Ochsenherz, Golden Bantam, Lange Rote")
        self.fields["harvest_year"].widget.attrs.update({"min": "1990", "placeholder": str(timezone.now().year)})
        self.fields["open_pollinated"].help_text = _("Its seeds can be saved again and come true (not an F1 hybrid).")
        if self.instance.pk and self.instance.skill_id:
            self.initial["skill_name"] = self.instance.skill.get_name()

    # The text colour going with a pill colour, for an icon on a light background
    TEXT_COLOURS = {"bg-primary": "text-primary", "bg-purple": "text-purple", "bg-yellow": "text-yellow"}

    def _radios(self, name, icons, colours):
        """(radio, icon, pill colour, text colour) for each choice of a radio field."""
        return [
            (radio, icons.get(radio.data["value"], ""), colours.get(radio.data["value"], "bg-primary"),
             self.TEXT_COLOURS.get(colours.get(radio.data["value"], "bg-primary"), "text-primary"))
            for radio in self[name]
        ]

    def type_radios(self):
        return self._radios("type", Listing.TYPE_ICONS, Listing.TYPE_COLOURS)

    def kind_radios(self):
        return self._radios("kind", Listing.KIND_ICONS, Listing.KIND_COLOURS)

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
        elif kind in Listing.SKILL_KINDS and skill_name and not self._known_skill(skill_name):
            # Skills from the list only, as everywhere, so people with the same one meet
            self.add_error("skill_name", _("Please choose one from the suggestions, so others with the same can find it."))
        elif kind in Listing.SKILL_KINDS and not (skill_name or title):
            self.add_error("title", _("Name a skill or say what for."))
        elif kind in Listing.THING_KINDS and not title:
            self.add_error("title", _("What is it?"))
        elif kind in WHITELISTED_KINDS and thing_named(title, kind) is None:
            # Matched by what exactly it is: a crop or a vehicle from the list
            self.add_error("title", _("Please choose one from the suggestions, so others with the same can find it."))
        if kind not in Listing.LEND_KINDS:
            cleaned["lend"] = False
        if kind in Listing.PIECE_KINDS:
            cleaned["unit"] = ""
        if kind in Listing.CATEGORY_KINDS and title and not self.has_error("title"):
            # What it is decides its categories: a seed or vehicle always; a tool or a
            # material once recognized, else the categories chosen
            from .models import Thing
            from .things import recognize
            if kind in WHITELISTED_KINDS:
                thing_id = thing_named(title, kind)
            else:
                thing_id = recognize(title, kind)
            thing = Thing.objects.filter(pk=thing_id).select_related("category").first()
            if thing is not None or kind in WHITELISTED_KINDS:
                cleaned["categories"] = Listing.thing_categories(thing, kind)
        if kind != Listing.KIND_SEEDS:
            cleaned["variety"], cleaned["harvest_year"], cleaned["open_pollinated"] = "", None, False
        if kind in Listing.THING_KINDS:
            cleaned["skill_name"] = ""
            cleaned["level"] = ""
        else:
            cleaned["categories"] = []
            # An amount only for things, and for a project's needs ("2 people")
            if not self.instance.project_id:
                cleaned["quantity"], cleaned["unit"] = None, ""
        return cleaned

    def _known_skill(self, name):
        """A skill of the taxonomy (in any language), or the one it already has."""
        from gift_economy.gifts.skills.models import _taxonomy
        if name.strip().lower() in _taxonomy()[1]:
            return True
        skill = self.instance.skill if self.instance.pk and self.instance.skill_id else None
        return skill is not None and name.strip().lower() in (skill.name.lower(), skill.get_name().lower())

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
