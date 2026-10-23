from django import forms
from django.utils.translation import gettext_lazy as _

from skills.models import get_or_create_skill

from .models import Reference, ReferenceSkill


class ReferenceForm(forms.ModelForm):
    """A reference; about a person or community it can also tag skills and name gifts."""

    skill_names = forms.CharField(label=_("Skills"), required=False)

    class Meta:
        model = Reference
        fields = ("impression", "text")
        widgets = {
            "impression": forms.RadioSelect,
            "text": forms.Textarea(attrs={
                "rows": 4, "class": "form-input",
                "placeholder": _("What happened? How did you feel, and what did you need?"),
            }),
        }

    def __init__(self, *args, subject=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Only people and communities hold skills and give gifts
        self.can_tag = subject is not None and hasattr(subject, "add_skill")
        if not self.can_tag:
            del self.fields["skill_names"]
        elif self.instance.pk:
            self.fields["skill_names"].initial = ", ".join(
                t.skill.get_name() for t in self.instance.skill_tags.exclude(status=ReferenceSkill.STATUS_DECLINED)
            )

    def gift_names(self):
        if not self.can_tag:
            return []
        names = self.data.getlist("gift_names") if hasattr(self.data, "getlist") else []
        return list(dict.fromkeys(n.strip()[:200] for n in names if n.strip()))

    def save_tags(self, reference, holder):
        """Sync the tagged skills: keep the status of skills still tagged, drop removed ones,
        and add new ones — confirmed right away if the holder already has the skill."""
        if not self.can_tag:
            return
        reference.gift_names = self.gift_names()
        reference.save(update_fields=["gift_names"])

        names = [n.strip() for n in self.cleaned_data.get("skill_names", "").split(",") if n.strip()]
        skills = list({skill.pk: skill for skill in (get_or_create_skill(name=n)[0] for n in names)}.values())
        reference.skill_tags.exclude(skill__in=skills).delete()
        tagged = set(reference.skill_tags.values_list("skill_id", flat=True))
        for skill in skills:
            if skill.pk not in tagged:
                status = ReferenceSkill.STATUS_CONFIRMED if holder.has_skill(skill) else ReferenceSkill.STATUS_PENDING
                ReferenceSkill.objects.create(reference=reference, skill=skill, status=status)
