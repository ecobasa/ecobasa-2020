from django import forms
from django.utils.translation import gettext_lazy as _

from gift_economy.gifts import units
from gift_economy.gifts.models import Listing, ListingCategory, themed_choices
from gift_economy.gifts.skills.models import _taxonomy, get_or_create_skill

from .models import Project


class ProjectForm(forms.ModelForm):
    skills_to_learn = forms.CharField(
        label=_("Skills you can learn here"), required=False,
        help_text=_("Comma-separated. People looking for these skills find your project and your community."),
    )
    field_order = ["title", "description", "skills_to_learn"]

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
        self.fields["skills_to_learn"].widget.attrs["placeholder"] = _("e.g. Clay building, Welding")
        if self.instance.pk:
            self.initial["skills_to_learn"] = ", ".join(l.display_title for l in self.instance.skills_to_learn())
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

    def save_skills_to_learn(self, project):
        """Make the community's skill offers in the project the skills named (in any
        language), after the project is saved. They list the community for these skills
        while the project runs."""
        names = [n.strip() for n in self.cleaned_data.get("skills_to_learn", "").split(",") if n.strip()]
        wanted = {get_or_create_skill(name)[0].pk for name in names}
        offers = project.listings.filter(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL)
        offers.exclude(skill_id__in=wanted).delete()
        for skill_id in wanted - set(offers.values_list("skill_id", flat=True)):
            Listing.objects.create(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL, skill_id=skill_id, project=project)


def skill_for_title(title):
    """The skill a need's title names, in any language, if it is in the taxonomy. Unknown
    names (e.g. "Helping hands") stay plain text and don't create a skill."""
    slug = _taxonomy()[1].get(title.strip().lower())
    if not slug:
        return None
    return get_or_create_skill(slug=slug, name=title)[0]


class NeedForm(forms.ModelForm):
    """One thing a project needs, as the community's wish in it: helping hands or
    knowledge (with a skill, if it names a known one), a material, a tool or anything
    else, with how much of it."""

    KIND_CHOICES = [
        (Listing.KIND_HANDS, _("Helping hands")),
        (Listing.KIND_KNOWLEDGE, _("Knowledge")),
        (Listing.KIND_MATERIAL, _("Material")),
        (Listing.KIND_TOOL, _("Tool")),
        (Listing.KIND_OTHER, _("Something else")),
    ]
    kind = forms.ChoiceField(label=_("Kind"), choices=KIND_CHOICES, initial=Listing.KIND_HANDS)
    title = forms.CharField(label=_("What is needed?"), max_length=255)
    category = forms.ModelChoiceField(ListingCategory.objects.all(), required=False, label=_("Gift category"))

    class Meta:
        model = Listing
        fields = ["kind", "title", "quantity", "unit", "description"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["kind"].widget.attrs["class"] = "form-select w-full"
        self.fields["title"].widget.attrs.update({
            "class": "form-input w-full", "autocomplete": "off", "list": "need-skill-suggestions",
            "data-need-title": "", "placeholder": _("e.g. Carpentry, clay, a cement mixer"),
        })
        self.fields["quantity"].widget.attrs.update({"class": "form-input w-full", "min": "1", "placeholder": _("How many?")})
        self.fields["unit"].widget.attrs["class"] = "form-select w-full"
        self.fields["unit"].choices = [("", _("Unit"))] + Listing._meta.get_field("unit").choices
        self.fields["description"] = forms.CharField(label=_("Details"), max_length=200, required=False)
        self.fields["description"].widget.attrs.update({
            "class": "form-input w-full", "placeholder": _("Details, e.g. 15 cm diameter"),
        })
        self.fields["category"].widget.attrs["class"] = "form-select w-full"
        self.fields["category"].empty_label = _("Gift category (optional)")
        self.fields["category"].choices = [
            ("", self.fields["category"].empty_label), *themed_choices(ListingCategory.objects.all()),
        ]
        if self.instance.pk:
            # Show the skill in the editor's language
            self.initial["title"] = self.instance.display_title
            self.initial["category"] = next(iter(self.instance.categories.all()), None)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("quantity") and not cleaned.get("unit") and cleaned.get("kind") == Listing.KIND_HANDS:
            cleaned["unit"] = units.PEOPLE
        if cleaned.get("kind") not in Listing.THING_KINDS:
            cleaned["category"] = None
        return cleaned

    def save(self, commit=True):
        need = super().save(commit=False)
        need.type = Listing.TYPE_WISH
        need.skill = skill_for_title(need.title) if need.kind in (Listing.KIND_HANDS, Listing.KIND_KNOWLEDGE) else None
        if commit:
            need.save()
            self.save_category(need)
        return need

    def save_category(self, need):
        category = self.cleaned_data.get("category")
        need.categories.set([category] if category else [])


class BaseNeedFormSet(forms.BaseInlineFormSet):
    def get_queryset(self):
        # Only the project's needs, not the skills you can learn in it
        return super().get_queryset().filter(type=Listing.TYPE_WISH).order_by("order", "created_at")


NeedFormSet = forms.inlineformset_factory(
    Project, Listing, form=NeedForm, formset=BaseNeedFormSet, fk_name="project", extra=0, can_delete=True,
)


class HelpOfferForm(forms.Form):
    """Someone offers to help with a project: with some of its needs, on site and/or by
    bringing things, saying how much they bring where a need has a quantity. Each open
    need gets a checkbox (need_<id>) and, if it has a quantity, an amount (quantity_<id>)."""

    stay_from = forms.DateField(label=_("Arrival"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    stay_to = forms.DateField(label=_("Departure"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    message = forms.CharField(
        label=_("Message"), widget=forms.Textarea(attrs={"rows": 4}),
        help_text=_("Who you are, what you can do or bring, and how you would get there. Also tell them what you need: food (diet, allergies), where you would sleep (tent, bed …) and anything else that matters to you."),
    )

    def __init__(self, project, *args, preselected=(), **kwargs):
        super().__init__(*args, **kwargs)
        self.project = project
        self.needs = [need for need in project.needs() if not need.is_done]
        preselected = {str(pk) for pk in preselected}
        for need in self.needs:
            self.fields[f"need_{need.pk}"] = forms.BooleanField(
                required=False, initial=str(need.pk) in preselected,
                widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            )
            if need.quantity:
                remaining = need.remaining or need.quantity
                self.fields[f"quantity_{need.pk}"] = forms.IntegerField(
                    required=False, min_value=1, initial=1 if need.unit == units.PEOPLE else remaining,
                    widget=forms.NumberInput(attrs={"class": "form-input w-24", "min": "1"}),
                )
        self.fields["message"].widget.attrs["class"] = "form-textarea w-full"
        for name in ("stay_from", "stay_to"):
            self.fields[name].widget.attrs["class"] = "form-input w-full"
            if project.starts_on:
                self.fields[name].widget.attrs["min"] = project.starts_on.isoformat()
            if project.ends_on:
                self.fields[name].widget.attrs["max"] = project.ends_on.isoformat()

    def need_rows(self):
        """(need, checkbox, amount field or None) for the template."""
        return [
            (need, self[f"need_{need.pk}"], self[f"quantity_{need.pk}"] if f"quantity_{need.pk}" in self.fields else None)
            for need in self.needs
        ]

    def chosen_needs(self):
        """[(need, quantity or None)] that were ticked."""
        return [
            (need, self.cleaned_data.get(f"quantity_{need.pk}"))
            for need in self.needs if self.cleaned_data.get(f"need_{need.pk}")
        ]

    def clean(self):
        cleaned = super().clean()
        stay_from, stay_to = cleaned.get("stay_from"), cleaned.get("stay_to")
        if stay_from and stay_to and stay_to < stay_from:
            self.add_error("stay_to", _("The stay can't end before it starts."))
        return cleaned
