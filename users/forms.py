from django import forms
from django.forms import ClearableFileInput
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
    image = CroppieField(
        required=False,
        options={
            "enableExif": True,
            "viewport": {
                "width": 200,
                "height": 200,
                "type": 'circle'
            },
            "boundary": {
                "width": 300,
                "height": 300
            }
        })

    class Meta:
        model = User
        fields = ["name", "email", "image", "location_name", "location", "country"]
        widgets = {
            "location": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        self.fields["name"].widget.attrs["autofocus"] = True
        self.fields["image"].required = False
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Fieldset(_("Personal Info"), Field("name"), Field("image"), header_text=_("Trust is the only currency in our gift-economy network, real names help to build trust"), ),
            Fieldset(
                _("Account"),
                Field("email"),
                Field("password"),
                header_text=_("Nessecary to logging in"),
            ),
        )

    def _post_clean(self):
        super()._post_clean()
        # Validate the password after self.instance is updated with form data
        # by super().
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
            # derive a safe username slug from name or email prefix
            base = self.cleaned_data.get("name") or user.email.split("@")[0]
            user.username = slugify(base)
        if commit:
            user.save()
        return user


class ProfileUpdateForm(forms.ModelForm):
    image = forms.ImageField(required=False, widget=ClearableFileInput)
    # comma-separated skills input for Taggit (editable via Tagify in the template)
    skills = forms.CharField(required=False, label=_("Skills"), help_text=_("Comma-separated list of skills."))

    class Meta:
        model = User
        fields = ["name", "image", "about", "world", "ecobasa_what", "skills",
                  "location_name", "location", "country"]
        widgets = {
            "location": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        # Prefill skills from Taggit manager when editing an existing user
        instance = kwargs.get('instance')
        if instance is not None:
            skills_initial = ', '.join([t.name for t in instance.skills.all()])
            self.fields['skills'].initial = skills_initial
            self.initial['skills'] = skills_initial
            self.fields['skills'].widget.attrs.update({'value': skills_initial})
        text_input_class = "block w-full rounded-md border border-gray-300 px-3 py-2 text-sm"
        textarea_class = "block w-full rounded-md border border-gray-300 px-3 py-2 text-sm h-32"
        for fname in ('name', 'skills', 'location_name'):
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({'class': text_input_class})
        for fname in ('about', 'world', 'ecobasa_what'):
            if fname in self.fields:
                self.fields[fname].widget.attrs.update({'class': textarea_class})
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Field("name"),
            Field("image"),
            Field("skills"),
            Field("about"),
            Field("world"),
            Field("ecobasa_what"),
        )

    def save(self, commit=True):
        # Save user fields then update Taggit skills from the comma-separated input
        user = super().save(commit=commit)
        skills_val = self.cleaned_data.get('skills', '')
        if skills_val is not None:
            # split on commas and strip whitespace
            tags = [s.strip() for s in skills_val.split(',') if s.strip()]
            if commit:
                user.skills.set(tags)
            else:
                # Defer tag setting for callers that save(commit=False)
                self._skills_to_set = tags
        return user