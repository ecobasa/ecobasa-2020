import json

from django import forms
from django.contrib.auth import get_user_model
from django.forms.widgets import ClearableFileInput
from django.utils.translation import gettext_lazy as _
from taggit.forms import TagWidget

from .models import Community, language_choices


# The "How we live" fields, in the order of their section on the form
HOW_WE_LIVE_FIELDS = [
    "looking_for_members", "kitchen", "private_kitchens", "pets", "animals",
    "currency", "buy_in", "buy_in_kind", "exit_terms", "monthly_contribution", "work_hours",
    "decision_making", "income_sharing", "trial_months", "languages", "house_agreements",
    "statutes_url", "statutes_file",
]
CHECKBOX_FIELDS = ["location_public", "looking_for_members", "private_kitchens"]


class LanguagesField(forms.Field):
    """Language codes, picked by name with Tagify (only languages Django knows); the
    input holds the codes, comma separated."""

    widget = forms.TextInput

    def prepare_value(self, value):
        if isinstance(value, str):
            return value
        return ",".join(value or [])

    def to_python(self, value):
        known = dict(language_choices())
        codes = [code.strip() for code in (value or "").split(",") if code.strip()]
        unknown = [code for code in codes if code not in known]
        if unknown:
            raise forms.ValidationError(_("Unknown language: %(code)s") % {"code": ", ".join(unknown)})
        return list(dict.fromkeys(codes))


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
    gallery = MultiImageField(
        required=False,
        widget=MultiFileInput(attrs={"multiple": True}),
        help_text=_("Upload one or more additional images."),
    )
    _gallery_validator = forms.ImageField(required=False)
    skill_wishes = forms.CharField(
        required=False,
        label=_("Skills we're looking for"),
        widget=forms.TextInput(attrs={
            "placeholder": _("Add skills, comma separated"), "data-skill-tags": _("Skills communities always need"),
        }),
    )

    kitchen = forms.MultipleChoiceField(
        label=_("Shared kitchen"), choices=Community.KITCHEN_CHOICES, required=False,
        widget=forms.CheckboxSelectMultiple, help_text=_("What the shared kitchen cooks. Tick all that fit."),
    )
    languages = LanguagesField(required=False, label=_("Languages"), help_text=_("The languages you speak together."))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["languages"].widget.attrs["data-languages"] = json.dumps(
            [{"value": name, "code": code} for code, name in language_choices()]
        )
        if self.instance and self.instance.pk:
            from gift_economy.gifts.models import Listing
            wishes_initial = ', '.join(
                sw.display_title for sw in Listing.objects.of(self.instance)
                .filter(type=Listing.TYPE_WISH, event=None).exclude(skill=None).select_related("skill")
            )
            self.fields['skill_wishes'].initial = wishes_initial
            self.initial['skill_wishes'] = wishes_initial
            self.fields['skill_wishes'].widget.attrs['value'] = wishes_initial
        for field in self.fields.values():
            css = field.widget.attrs.get("class", "")
            field.widget.attrs["class"] = f"{css} form-input".strip()
        if "country" in self.fields:
            self.fields["country"].widget.attrs["class"] = "form-select"
        for name in CHECKBOX_FIELDS:
            self.fields[name].widget.attrs["class"] = "form-checkbox mt-1 flex-shrink-0"
        self.fields["kitchen"].widget.attrs["class"] = "form-checkbox"
        # The exit terms are asked for once a buy-in is set
        self.fields["buy_in"].widget.attrs["x-model"] = "buyIn"
        for name in [*HOW_WE_LIVE_FIELDS, "children_welcome"]:
            if isinstance(self.fields[name].widget, forms.Select):
                self.fields[name].widget.attrs["class"] = "form-select"
        if "inhabitants" in self.fields:
            self.fields["inhabitants"].widget.attrs.setdefault(
                "placeholder", _("e.g. 25")
            )
        if "gallery" in self.fields:
            css = self.fields["gallery"].widget.attrs.get("class", "")
            self.fields["gallery"].widget.attrs["class"] = f"{css} form-input".strip()

    # inhabitants is an integer field on the model; no custom cleaning required.

    def how_we_live(self):
        """Its "How we live" section's fields, for the template."""
        return [self[name] for name in HOW_WE_LIVE_FIELDS]

    def clean_kitchen(self):
        kitchen = self.cleaned_data.get("kitchen") or []
        if Community.KITCHEN_ANY in kitchen and {Community.KITCHEN_VEGETARIAN, Community.KITCHEN_VEGAN} & set(kitchen):
            raise forms.ValidationError(_("A kitchen that eats anything isn't vegetarian or vegan."))
        return kitchen

    def clean_currency(self):
        return (self.cleaned_data.get("currency") or "EUR").strip().upper()

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
            "location_public",
            "country",
            "inhabitants",
            "children",
            "video",
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
            "children_welcome",
            *HOW_WE_LIVE_FIELDS,
        ]
        widgets = {
            "location": forms.HiddenInput(),
            "has_workshop_space": forms.Textarea(attrs={"rows": 2}),
            "offers_seminars": forms.Textarea(attrs={"rows": 2}),
            "visitor_requirements": forms.Textarea(attrs={"rows": 3}),
            "description": forms.Textarea(attrs={"rows": 4}),
            "vision": forms.Textarea(attrs={"rows": 3}),
            "accomodation": forms.Textarea(attrs={"rows": 3}),
            "video": forms.URLInput(attrs={"placeholder": _("YouTube or Vimeo link")}),
            "exit_terms": forms.Textarea(attrs={"rows": 3}),
            "animals": forms.Textarea(attrs={"rows": 3}),
            "house_agreements": forms.Textarea(attrs={"rows": 4}),
            "statutes_file": forms.ClearableFileInput(attrs={"accept": "application/pdf"}),
            "skills": TagWidget(attrs={"placeholder": _("Add skills, comma separated"), "data-skill-tags": _("Popular skills to explore")}),
        }
        labels = {
            "location_name": _("Location"),
            "location": _("Geo location"),
            "inhabitants": _("How many people live in your community?"),
            "children": _("How many of them are under 18?"),
            "max_guests": _("Maximum number of people you can host"),
            "has_workshop_space": _("Do you have workshop spaces where people can build/construct/manufacture things?"),
            "offers_seminars": _("Do you offer any seminars that visitors could attend?"),
            "visitor_requirements": _("Requirements for visitors"),
        }
        help_texts = {
            "offers_seminars": _("List seminars, topics, and how visitors can join. Later you can add each one as an event on your community page, so people find it on the events map too."),
        }


class InviteForm(forms.Form):
    """The ambassador invites someone to become a member: who (found by name) and a few
    words."""

    user = forms.ModelChoiceField(
        get_user_model().objects.filter(is_active=True), label=_("Who"), widget=forms.HiddenInput,
        error_messages={"required": _("Please choose someone."), "invalid_choice": _("Please choose someone.")},
    )
    message = forms.CharField(
        label=_("A few words to them"), widget=forms.Textarea(attrs={"rows": 4, "class": "form-textarea w-full"}),
        help_text=_("Why you'd like them to become a member."),
    )

    def __init__(self, community, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.community = community

    def chosen_user(self):
        """The person picked so far (or come from their profile), to show their name."""
        pk = self.data.get("user") if self.is_bound else self.initial.get("user")
        return get_user_model().objects.filter(pk=pk).first() if pk and str(pk).isdigit() else None

    def clean_user(self):
        user = self.cleaned_data["user"]
        if self.community.memberships.current().filter(user=user).exists():
            raise forms.ValidationError(_("They are a member already, or have been asked."))
        return user
