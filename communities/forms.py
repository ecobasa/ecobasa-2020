import re

from django import forms
from django.forms.widgets import ClearableFileInput
from django.utils.translation import gettext_lazy as _
from taggit.forms import TagWidget

from .models import Community


class MultiFileInput(ClearableFileInput):
    allow_multiple_selected = True


class MultiImageField(forms.ImageField):
    def clean(self, data, initial=None):
        if not data:
            return []
        if not isinstance(data, (list, tuple)):
            data = [data]
        cleaned = []
        errors = []
        for item in data:
            try:
                cleaned.append(super().clean(item, initial))
            except forms.ValidationError as exc:
                errors.extend(exc.error_list)
        if errors:
            raise forms.ValidationError(errors)
        return cleaned


class CommunityForm(forms.ModelForm):
    PEOPLE_COUNT_PATTERN = re.compile(r"^\d+(?:-\d+)?$")
    gallery = MultiImageField(
        required=False,
        widget=MultiFileInput(attrs={"multiple": True}),
        help_text=_("Upload one or more additional images."),
    )
    _gallery_validator = forms.ImageField(required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} community-field".strip()
        if "people_count" in self.fields:
            self.fields["people_count"].widget.attrs.setdefault(
                "placeholder", _("e.g. 25 or 25-30")
            )
        if "gallery" in self.fields:
            css = self.fields["gallery"].widget.attrs.get("class", "")
            self.fields["gallery"].widget.attrs["class"] = f"{css} community-field".strip()

    def clean_people_count(self):
        value = self.cleaned_data.get("people_count")
        if not value:
            return value
        text = str(value).strip()
        if not self.PEOPLE_COUNT_PATTERN.match(text):
            raise forms.ValidationError(_("Use a whole number or a range like 25-30."))
        return text

    def clean_gallery(self):
        files = self.cleaned_data.get("gallery") or []
        return files

    class Meta:
        model = Community
        fields = [
            "name",
            "type",
            "status",
            "location_name",
            "location",
            "people_count",
            "minors_count",
            "max_guests",
            "has_workshop_space",
            "offers_seminars",
            "visitor_requirements",
            "description",
            "vision",
            "accomodation",
            "website",
            "telephone",
            "skills",
        ]
        widgets = {
            "location": forms.HiddenInput(),
            "has_workshop_space": forms.Textarea(attrs={"rows": 2}),
            "offers_seminars": forms.Textarea(attrs={"rows": 2}),
            "visitor_requirements": forms.Textarea(attrs={"rows": 3}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "vision": forms.Textarea(attrs={"rows": 3}),
            "accomodation": forms.Textarea(attrs={"rows": 3}),
            "skills": TagWidget(attrs={"placeholder": _("Add skills, comma separated")}),
        }
        labels = {
            "location_name": _("Location"),
            "location": _("Geo location"),
            "people_count": _("How many people live in your community?"),
            "minors_count": _("How many of them are under 18?"),
            "max_guests": _("Maximum number of people you can host"),
            "has_workshop_space": _("Do you have workshop spaces where people can build/construct/manufacture things?"),
            "offers_seminars": _("Do you offer any seminars that visitors could attend?"),
            "visitor_requirements": _("Requirements for visitors"),
        }
