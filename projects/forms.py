from django import forms
from django.utils.translation import gettext_lazy as _

from skills.models import _taxonomy, get_or_create_skill

from .models import Need, Project


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = [
            "title", "description", "starts_on", "ends_on",
            "volunteers_wanted", "food_provided", "bed_provided", "provided_note",
        ]
        widgets = {
            "starts_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "ends_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "description": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs["placeholder"] = _("e.g. Building a rocket stove")
        self.fields["description"].widget.attrs["placeholder"] = _(
            "What do you want to build or do, and what will helpers learn?"
        )
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = "form-checkbox"
            elif isinstance(field.widget, forms.Textarea):
                field.widget.attrs["class"] = "form-textarea w-full"
            else:
                field.widget.attrs["class"] = "form-input w-full"

    def clean(self):
        cleaned = super().clean()
        starts_on, ends_on = cleaned.get("starts_on"), cleaned.get("ends_on")
        if starts_on and ends_on and ends_on < starts_on:
            self.add_error("ends_on", _("The project can't end before it starts."))
        return cleaned


def skill_for_title(title):
    """The skill a need's title names, in any language, if it is in the taxonomy. Unknown
    names (e.g. "Helping hands") stay plain text and don't create a skill."""
    slug = _taxonomy()[1].get(title.strip().lower())
    if not slug:
        return None
    return get_or_create_skill(slug=slug, name=title)[0]


class NeedForm(forms.ModelForm):
    class Meta:
        model = Need
        fields = ["kind", "title", "amount"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].widget.attrs["class"] = "form-select w-full"
        self.fields["title"].widget.attrs.update({
            "class": "form-input w-full", "autocomplete": "off", "list": "need-skill-suggestions",
            "data-need-title": "", "placeholder": _("e.g. Carpentry, clay, a cement mixer"),
        })
        self.fields["amount"].widget.attrs.update({
            "class": "form-input w-full", "placeholder": _("e.g. 2 people, 200 kg"),
        })
        if self.instance.pk and self.instance.skill_id:
            # Show the skill in the editor's language
            self.initial["title"] = self.instance.display_title

    def save(self, commit=True):
        need = super().save(commit=False)
        need.skill = skill_for_title(need.title) if need.kind in (Need.KIND_SKILL, Need.KIND_KNOWLEDGE) else None
        if commit:
            need.save()
        return need


NeedFormSet = forms.inlineformset_factory(
    Project, Need, form=NeedForm, extra=0, can_delete=True,
)


class NeedChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, need):
        label = need.display_title
        return f"{label} ({need.amount})" if need.amount else label


class HelpOfferForm(forms.Form):
    """Someone offers to help with a project: with some of its needs, on site and/or by
    bringing things."""

    needs = NeedChoiceField(
        queryset=Need.objects.none(), required=False, widget=forms.CheckboxSelectMultiple(attrs={"class": "form-checkbox"}),
        label=_("What can you help with?"),
    )
    stay_from = forms.DateField(label=_("Arrival"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    stay_to = forms.DateField(label=_("Departure"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    message = forms.CharField(
        label=_("Message"), widget=forms.Textarea(attrs={"rows": 4}),
        help_text=_("Who you are, what you can do or bring, and how you would get there."),
    )

    def __init__(self, project, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.fields["needs"].queryset = project.needs.filter(covered_at=None).select_related("skill")
        self.fields["message"].widget.attrs["class"] = "form-textarea w-full"
        for name in ("stay_from", "stay_to"):
            self.fields[name].widget.attrs["class"] = "form-input w-full"
            if project.starts_on:
                self.fields[name].widget.attrs["min"] = project.starts_on.isoformat()
            if project.ends_on:
                self.fields[name].widget.attrs["max"] = project.ends_on.isoformat()

    def clean(self):
        cleaned = super().clean()
        stay_from, stay_to = cleaned.get("stay_from"), cleaned.get("stay_to")
        if stay_from and stay_to and stay_to < stay_from:
            self.add_error("stay_to", _("The stay can't end before it starts."))
        return cleaned

