from django import forms
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit

from .models import UserSkill, CommunitySkill, SkillRequest, Skill


class SkillAutocompleteWidget(forms.TextInput):
    """Text input that lets users type a skill name; the view resolves or creates the Skill."""
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
            Field("level"),
            Field("description"),
            Field("available"),
            Submit("submit", _("Save skill"), css_class="btn mt-2"),
        )

    def save(self, commit=True):
        name = self.cleaned_data["skill_name"].strip()
        skill, _ = Skill.objects.get_or_create(
            name__iexact=name,
            defaults={"name": name},
        )
        self.instance.skill = skill
        return super().save(commit=commit)


class CommunitySkillForm(forms.ModelForm):
    skill_name = forms.CharField(
        label=_("Skill"),
        max_length=100,
        widget=SkillAutocompleteWidget(attrs={"placeholder": _("e.g. Permaculture, Natural Building…")}),
    )

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
            Field("description"),
            Submit("submit", _("Save skill"), css_class="btn mt-2"),
        )

    def save(self, commit=True):
        name = self.cleaned_data["skill_name"].strip()
        skill, _ = Skill.objects.get_or_create(
            name__iexact=name,
            defaults={"name": name},
        )
        self.instance.skill = skill
        return super().save(commit=commit)


class SkillRequestForm(forms.ModelForm):
    class Meta:
        model  = SkillRequest
        fields = ["message", "proposed_location", "proposed_date"]
        widgets = {
            "message":           forms.Textarea(attrs={"rows": 4}),
            "proposed_date":     forms.DateInput(attrs={"type": "date"}),
            "proposed_location": forms.TextInput(attrs={"placeholder": _("City, region or online")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("message"),
            Field("proposed_location"),
            Field("proposed_date"),
            Submit("submit", _("Send request"), css_class="btn mt-2"),
        )
