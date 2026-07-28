from django import forms
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit

from .models import UserSkill, CommunitySkill, Skill, SkillTaxonomy, SkillWish


def _skill_from_taxonomy_data(data_json, lang="en"):
    """Resolve the hidden-field JSON payload to a Skill, creating it if needed."""
    import json as _json
    data = _json.loads(data_json)
    taxonomy = SkillTaxonomy.objects.get(slug=data["slug"])
    name = taxonomy.get_name(lang)
    return Skill.objects.get_or_create(name__iexact=name, defaults={"name": name})


class SkillAutocompleteWidget(forms.TextInput):
    """Text input that lets users type a skill name; must select from taxonomy suggestions."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attrs.setdefault("autocomplete", "off")
        self.attrs.setdefault("data-skill-autocomplete", "true")


class UserSkillForm(forms.ModelForm):
    skill_name = forms.CharField(
        label=_("Skill"),
        max_length=100,
        widget=SkillAutocompleteWidget(attrs={"placeholder": _("e.g. Carpentry, Solar Energy…")}),
    )
    skill_taxonomy_data = forms.CharField(widget=forms.HiddenInput(), required=True)

    class Meta:
        model  = UserSkill
        fields = ["level", "description", "available"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["skill_name"].initial = self.instance.skill.name
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("skill_name"),
            Field("skill_taxonomy_data"),
            Field("level"),
            Field("description"),
            Field("available"),
            Submit("submit", _("Save skill"), css_class="btn mt-2"),
        )

    def clean_skill_taxonomy_data(self):
        try:
            import json as _json
            _json.loads(self.cleaned_data.get("skill_taxonomy_data", ""))
        except (ValueError, TypeError):
            raise forms.ValidationError(_("Please select a skill from the suggestions."))
        return self.cleaned_data["skill_taxonomy_data"]

    def save(self, commit=True):
        skill, _ = _skill_from_taxonomy_data(self.cleaned_data["skill_taxonomy_data"])
        self.instance.skill = skill
        return super().save(commit=commit)


class UserSkillOrWishForm(forms.Form):
    """Single form for adding either a skill offer or a skill wish to a user profile."""
    MODE_OFFER = "offer"
    MODE_WISH  = "wish"
    MODE_CHOICES = [
        (MODE_OFFER, _("I can offer / teach this skill")),
        (MODE_WISH,  _("I want to learn this or need help with it")),
    ]

    mode = forms.ChoiceField(
        choices=MODE_CHOICES,
        widget=forms.RadioSelect,
        initial=MODE_OFFER,
        label=_("How do you relate to this skill?"),
    )
    skill_name = forms.CharField(
        label=_("Skill"),
        max_length=100,
        widget=SkillAutocompleteWidget(attrs={"placeholder": _("e.g. Carpentry, Solar Energy…"), "class": "form-input"}),
    )
    skill_taxonomy_data = forms.CharField(widget=forms.HiddenInput(), required=True)
    level = forms.ChoiceField(
        choices=[("", "—")] + UserSkill.LEVEL_CHOICES,
        required=False,
        label=_("Level"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    wish_level = forms.ChoiceField(
        choices=[("", _("Any level"))] + UserSkill.LEVEL_CHOICES,
        required=False,
        label=_("My current level"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    available = forms.BooleanField(
        required=False,
        initial=True,
        label=_("Available to teach / share"),
        widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}),
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-input"}),
        label=_("Description"),
    )

    def clean_skill_taxonomy_data(self):
        try:
            import json as _json
            _json.loads(self.cleaned_data.get("skill_taxonomy_data", ""))
        except (ValueError, TypeError):
            raise forms.ValidationError(_("Please select a skill from the suggestions."))
        return self.cleaned_data["skill_taxonomy_data"]

    def save(self, user):
        skill, _ = _skill_from_taxonomy_data(self.cleaned_data["skill_taxonomy_data"])
        if self.cleaned_data["mode"] == self.MODE_WISH:
            wish, created = SkillWish.objects.get_or_create(user=user, skill=skill)
            wish.level = self.cleaned_data.get("wish_level") or ""
            wish.description = self.cleaned_data.get("description") or ""
            wish.save()
            return None, wish
        else:
            us, _ = UserSkill.objects.get_or_create(
                user=user, skill=skill,
                defaults={
                    "level":       self.cleaned_data.get("level") or "",
                    "description": self.cleaned_data.get("description") or "",
                    "available":   self.cleaned_data.get("available") or True,
                },
            )
            return us, None


class CommunitySkillOrWishForm(forms.Form):
    """Single form for adding either a skill offer or a skill wish for a community."""
    MODE_OFFER = "offer"
    MODE_WISH  = "wish"
    MODE_CHOICES = [
        (MODE_OFFER, _("We can offer / teach this skill")),
        (MODE_WISH,  _("We're looking for people with this skill")),
    ]

    mode = forms.ChoiceField(
        choices=MODE_CHOICES,
        widget=forms.RadioSelect,
        initial=MODE_OFFER,
        label=_("How does your community relate to this skill?"),
    )
    skill_name = forms.CharField(
        label=_("Skill"),
        max_length=100,
        widget=SkillAutocompleteWidget(attrs={"placeholder": _("e.g. Permaculture, Natural Building…"), "class": "form-input"}),
    )
    skill_taxonomy_data = forms.CharField(widget=forms.HiddenInput(), required=True)
    wish_level = forms.ChoiceField(
        choices=[("", _("Any level — beginners welcome"))] + UserSkill.LEVEL_CHOICES,
        required=False,
        label=_("Minimum level sought"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-input"}),
        label=_("Description"),
    )

    def save(self, community):
        skill, _ = _skill_from_taxonomy_data(self.cleaned_data["skill_taxonomy_data"])
        if self.cleaned_data["mode"] == self.MODE_WISH:
            wish, created = SkillWish.objects.get_or_create(community=community, skill=skill)
            wish.level = self.cleaned_data.get("wish_level") or ""
            wish.description = self.cleaned_data.get("description") or ""
            wish.save()
            return None, wish
        else:
            cs, _ = CommunitySkill.objects.get_or_create(
                community=community, skill=skill,
                defaults={"description": self.cleaned_data.get("description") or ""},
            )
            return cs, None


class CommunitySkillForm(forms.ModelForm):
    skill_name = forms.CharField(
        label=_("Skill"),
        max_length=100,
        widget=SkillAutocompleteWidget(attrs={"placeholder": _("e.g. Permaculture, Natural Building…")}),
    )
    skill_taxonomy_data = forms.CharField(widget=forms.HiddenInput(), required=True)

    class Meta:
        model  = CommunitySkill
        fields = ["description"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["skill_name"].initial = self.instance.skill.name
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("skill_name"),
            Field("skill_taxonomy_data"),
            Field("description"),
            Submit("submit", _("Save skill"), css_class="btn mt-2"),
        )

    def clean_skill_taxonomy_data(self):
        try:
            import json as _json
            _json.loads(self.cleaned_data.get("skill_taxonomy_data", ""))
        except (ValueError, TypeError):
            raise forms.ValidationError(_("Please select a skill from the suggestions."))
        return self.cleaned_data["skill_taxonomy_data"]

    def save(self, commit=True):
        skill, _ = _skill_from_taxonomy_data(self.cleaned_data["skill_taxonomy_data"])
        self.instance.skill = skill
        return super().save(commit=commit)


class SkillWishEditForm(forms.Form):
    """Edit level and description of an existing SkillWish."""
    wish_level = forms.ChoiceField(
        choices=[("", _("Any level"))] + UserSkill.LEVEL_CHOICES,
        required=False,
        label=_("My current level"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 4, "class": "form-input"}),
        label=_("Description"),
    )

    def save(self, wish):
        wish.level = self.cleaned_data.get("wish_level") or ""
        wish.description = self.cleaned_data.get("description") or ""
        wish.save()
        return wish


