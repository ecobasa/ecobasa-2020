from django import forms
from django.core.exceptions import ValidationError
from django.contrib.auth import password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _
from django.utils.text import slugify

from crispy_forms.helper import FormHelper
from crispy_forms.layout import Layout, Field
from croppie.fields import CroppieField

from gifting.forms import Fieldset
from .models import User
from skills.models import Skill, UserSkill, SkillWish


class SafeCroppieField(CroppieField):
    """CroppieField that returns None instead of crashing when no image is uploaded."""
    def compress(self, data_list):
        if data_list and data_list[0]:
            return super().compress(data_list)
        return None


class LoginForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = _("Email (use your account email to log in)")
        self.fields["username"].widget.attrs.setdefault("placeholder", _("email@example.com"))
        self.error_messages["invalid_login"] = _("Credentials are not correct.")


class RegisterForm(forms.ModelForm):
    password = forms.CharField(
        label=_("Password"),
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        strip=False,
        help_text=password_validation.password_validators_help_text_html(),
    )
    image = SafeCroppieField(
        required=False,
        options={
            "enableExif": True,
            "viewport": {"width": 200, "height": 200, "type": "circle"},
            "boundary": {"width": 300, "height": 300},
        },
    )
    skills = forms.CharField(
        required=False,
        label=_("What can you offer or teach?"),
        help_text=_("Everyday skills count just as much as professional ones — cooking, gardening, basic repairs, childcare are all valuable to communities."),
    )
    skill_wishes = forms.CharField(
        required=False,
        label=_("What do you want to learn or need help with?"),
        help_text=_("Sharing what you need helps communities match you with the right people and experiences."),
    )

    class Meta:
        model = User
        fields = ["name", "email", "image", "skills", "skill_wishes", "about", "world", "ecobasa_what",
                  "location_name", "location", "country"]
        widgets = {
            "location": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        self.fields["name"].widget.attrs["autofocus"] = True
        self.fields["image"].required = False
        if "country" in self.fields:
            self.fields["country"].widget.attrs.update({"class": "form-select"})
        for fname in ("about", "world", "ecobasa_what"):
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({"class": "h-32"})
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Fieldset(
                _("Personal Info"),
                Field("name"),
                Field("image"),
                header_text=_("Trust is the only currency in our gift-economy network — real names help to build trust."),
            ),
            Fieldset(
                _("Account"),
                Field("email"),
                Field("password"),
                header_text=_("Required to log in."),
            ),
            Fieldset(
                _("About you"),
                Field("about"),
                Field("world"),
                Field("ecobasa_what"),
                Field("skills"),
                Field("skill_wishes"),
                header_text=_("Tell communities you want to visit or join who you are and what you have to offer."),
            ),
        )

    def _post_clean(self):
        super()._post_clean()
        password = self.cleaned_data.get("password")
        if password:
            try:
                password_validation.validate_password(password, self.instance)
            except ValidationError as error:
                self.add_error("password", error)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password"])
        if not user.username:
            base = slugify(self.cleaned_data.get("name") or user.email.split("@")[0]) or 'user'
            slug = base
            n = 2
            while User.objects.filter(username=slug).exists():
                slug = f'{base}{n}'
                n += 1
            user.username = slug
        if commit:
            user.save()
            skills_val = self.cleaned_data.get("skills", "")
            if skills_val:
                for name in [s.strip() for s in skills_val.split(",") if s.strip()]:
                    skill, _ = Skill.objects.get_or_create(
                        name__iexact=name, defaults={"name": name}
                    )
                    UserSkill.objects.get_or_create(user=user, skill=skill)
            wish_val = self.cleaned_data.get("skill_wishes", "")
            if wish_val:
                for name in [s.strip() for s in wish_val.split(",") if s.strip()]:
                    skill, _ = Skill.objects.get_or_create(
                        name__iexact=name, defaults={"name": name}
                    )
                    SkillWish.objects.get_or_create(user=user, skill=skill)
        return user


class ProfileUpdateForm(forms.ModelForm):
    image = SafeCroppieField(
        required=False,
        options={
            "enableExif": True,
            "viewport": {"width": 200, "height": 200, "type": "circle"},
            "boundary": {"width": 300, "height": 300},
        },
    )
    skills = forms.CharField(
        required=False,
        label=_("What can you offer or teach?"),
        help_text=_("Everyday skills count just as much as professional ones — cooking, gardening, basic repairs, childcare are all valuable to communities."),
    )
    skill_wishes = forms.CharField(
        required=False,
        label=_("What do you want to learn or need help with?"),
        help_text=_("Sharing what you need helps communities match you with the right people and experiences."),
    )

    class Meta:
        model = User
        fields = ["name", "image", "about", "world", "ecobasa_what", "skills", "skill_wishes",
                  "location_name", "location", "country"]
        widgets = {
            "location": forms.HiddenInput(),
        }

    clear_image = forms.BooleanField(required=False, label=_("Remove current photo"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        instance = kwargs.get('instance')
        has_image = bool(instance and instance.image)
        if instance is not None:
            skills_initial = ', '.join(
                instance.user_skills.select_related("skill").values_list("skill__name", flat=True)
            )
            self.fields['skills'].initial = skills_initial
            self.initial['skills'] = skills_initial
            self.fields['skills'].widget.attrs.update({'value': skills_initial})
            wishes_initial = ', '.join(
                instance.skill_wishes.select_related("skill").values_list("skill__name", flat=True)
            )
            self.fields['skill_wishes'].initial = wishes_initial
            self.initial['skill_wishes'] = wishes_initial
            self.fields['skill_wishes'].widget.attrs.update({'value': wishes_initial})
        text_input_class = "block w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        textarea_class = "block w-full rounded-md border border-gray-300 px-3 py-2 text-sm h-32"
        for fname in ('name', 'skills', 'skill_wishes', 'location_name'):
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({'class': text_input_class})
        if 'country' in self.fields:
            self.fields['country'].widget.attrs.update({'class': 'form-select'})
        for fname in ('about', 'world', 'ecobasa_what'):
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({'class': textarea_class})
        self.fields['image'].label = _("Upload new photo") if has_image else _("Photo")
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("name"),
            Field("image"),
            Field("about"),
            Field("world"),
            Field("ecobasa_what"),
            Field("skills"),
            Field("skill_wishes"),
        )

    def save(self, commit=True):
        user = super().save(commit=False)
        new_image = self.cleaned_data.get('image')
        if not new_image and self.cleaned_data.get('clear_image') and user.image:
            user.image = None
        if commit:
            user.save()
            skills_val = self.cleaned_data.get('skills', '') or ''
            for name in [s.strip() for s in skills_val.split(',') if s.strip()]:
                skill, _ = Skill.objects.get_or_create(
                    name__iexact=name, defaults={"name": name}
                )
                UserSkill.objects.get_or_create(user=user, skill=skill)
            wish_val = self.cleaned_data.get('skill_wishes', '') or ''
            new_wish_names = [s.strip() for s in wish_val.split(',') if s.strip()]
            user.skill_wishes.all().delete()
            for name in new_wish_names:
                skill, _ = Skill.objects.get_or_create(name__iexact=name, defaults={"name": name})
                SkillWish.objects.create(user=user, skill=skill)
        return user