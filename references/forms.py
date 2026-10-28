from django import forms
from django.utils.translation import gettext_lazy as _

from gifts.models import Listing
from gifts.skills.models import get_or_create_skill

from .models import Reference, ReferenceSkill, subject_owner


class ReferenceForm(forms.ModelForm):
    """A reference, written on its subject's page or from the email after a match (`story`:
    worded for the author as their story). About a person or community it can also tag
    skills and name gifts. A photo is shrunk while validating."""

    skill_names = forms.CharField(label=_("Skills"), required=False)
    photo = forms.ImageField(label=_("Photo"), required=False)

    class Meta:
        model = Reference
        fields = ("impression", "text", "share_publicly")
        # As written: Django would capitalise "ecobasa"
        labels = {"share_publicly": Reference._meta.get_field("share_publicly").verbose_name}
        widgets = {
            "impression": forms.RadioSelect,
            "text": forms.Textarea(attrs={
                "rows": 4, "class": "form-input",
                "placeholder": _("What happened? How did you feel, and what did you need?"),
            }),
        }

    def __init__(self, *args, subject=None, story=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.story = story
        if story:
            self.fields["text"].label = _("Your story")
            self.fields["text"].widget.attrs.update(rows=6, placeholder=_("What happened? What are you grateful for?"))
        # Only people and communities hold skills and give gifts
        self.can_tag = subject is not None and hasattr(subject, "add_skill")
        if not self.can_tag:
            del self.fields["skill_names"]
        elif self.instance.pk:
            self.fields["skill_names"].initial = ", ".join(
                t.skill.get_name() for t in self.instance.skill_tags.exclude(status=ReferenceSkill.STATUS_DECLINED)
            )

    def clean_photo(self):
        from .reference_requests import shrink_photo

        photo = self.cleaned_data.get("photo")
        if not photo:
            return None
        try:
            return shrink_photo(photo)
        except ValueError:
            raise forms.ValidationError(_("This photo could not be read. Please try another one."))

    def save_reference(self, author, subject, match=None):
        """Save it as `author`'s reference about `subject`, with photo and tags."""
        reference = self.save(commit=False)
        reference.author = author
        reference.recipient = subject_owner(subject)
        reference.subject = subject
        if match is not None:
            reference.match = match
        photo = self.cleaned_data.get("photo")
        if photo:
            reference.photo.save(photo.name, photo, save=False)
        reference.save()
        self.save_tags(reference, holder=subject)
        return reference

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



def form_context(subject, form, own=None, gift_names=()):
    """What references/_reference_form_fields.html needs besides the form: the gifts named
    so far (`gift_names` adds more, e.g. from a match) and suggestions for skills and gifts."""
    from django.utils.translation import gettext

    names = list(own.gift_names) if own else []
    names += [name for name in gift_names if name and name not in names]
    listings = getattr(subject, "listings", None)
    return {
        "form": form,
        "reference": own,
        "gift_names": names,
        # Skills they already list, suggested first in the skill input
        "held_skills": [
            s.get_match_display_name() for s in getattr(subject, "get_reference_subjects", lambda: [])()
            if getattr(s, "get_skill_holder", lambda: None)() is not None
        ] if form.can_tag else [],
        "held_skills_header": gettext("Skills listed here"),
        "gift_suggestions": [
            l.display_title for l in listings.filter(kind__in=Listing.THING_KINDS)
        ] if form.can_tag and listings is not None else [],
        # A community (or one of its offers and wishes): the guide adds a note about writing to a group
        "about_community": subject._meta.model_name == "community" or bool(getattr(subject, "community_id", None)),
    }
