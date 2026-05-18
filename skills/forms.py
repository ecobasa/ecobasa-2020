from django import forms
from django.utils.translation import gettext_lazy as _
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field, Submit

from .models import UserSkill, CommunitySkill, SkillRequest, SkillRequestMessage, Skill, SkillWish


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


class UserSkillOrWishForm(forms.Form):
    """Single form for adding either a skill offer or a skill wish to a user profile."""
    MODE_OFFER = "offer"
    MODE_WISH  = "wish"
    MODE_CHOICES = [
        (MODE_OFFER, _("I can offer / teach this skill")),
        (MODE_WISH,  _("I want to learn this skill")),
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

    def save(self, user):
        name = self.cleaned_data["skill_name"].strip()
        skill, _ = Skill.objects.get_or_create(name__iexact=name, defaults={"name": name})
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
        name = self.cleaned_data["skill_name"].strip()
        skill, _ = Skill.objects.get_or_create(name__iexact=name, defaults={"name": name})
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


class SkillRequestForm(forms.ModelForm):
    proposed_lat = forms.FloatField(required=False, widget=forms.HiddenInput())
    proposed_lon = forms.FloatField(required=False, widget=forms.HiddenInput())

    class Meta:
        model  = SkillRequest
        fields = ["message", "location_type", "proposed_location", "proposed_lat", "proposed_lon", "proposed_date"]
        widgets = {
            "message":           forms.Textarea(attrs={"rows": 4, "class": "form-input"}),
            "location_type":     forms.RadioSelect(),
            "proposed_date":     forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-input"}),
            "proposed_location": forms.TextInput(attrs={
                "placeholder": _("City, region, address…"),
                "class": "form-input",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.layout = Layout(
            Field("message"),
            Field("location_type"),
            Field("proposed_location"),
            Field("proposed_lat"),
            Field("proposed_lon"),
            Field("proposed_date"),
            Submit("submit", _("Send request"), css_class="btn mt-2"),
        )


class SkillRequestResponseForm(forms.Form):
    response_message    = forms.CharField(
        label=_("Message"), required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-input"}),
    )
    counter_location_type = forms.ChoiceField(
        label=_("Counter location type"),
        choices=SkillRequest.LOC_CHOICES,
        required=False,
        widget=forms.RadioSelect(),
    )
    counter_location = forms.CharField(
        label=_("Counter location"),
        max_length=255, required=False,
        widget=forms.TextInput(attrs={"placeholder": _("City, region, address…"), "class": "form-input"}),
    )
    counter_lat  = forms.FloatField(required=False, widget=forms.HiddenInput())
    counter_lon  = forms.FloatField(required=False, widget=forms.HiddenInput())
    counter_date = forms.DateTimeField(
        label=_("Counter date"),
        required=False,
        widget=forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-input"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("response_message"),
            Field("counter_location_type", x_show="isCounter"),
            Field("counter_location",      **{"x-show": "isCounter"}),
            Field("counter_lat"),
            Field("counter_lon"),
            Field("counter_date",          **{"x-show": "isCounter"}),
        )


class SkillRequestMessageForm(forms.Form):
    body = forms.CharField(
        label=_("Message"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "class": "form-input", "placeholder": _("Write a message…")}),
    )
