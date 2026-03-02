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
        fields = ["name", "email", "image"]

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

    class Meta:
        model = User
        fields = ["name", "image", "about", "world", "ecobasa_what"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["name"].required = True
        self.helper = FormHelper()
        self.helper.form_tag = False
        self.helper.layout = Layout(
            Fieldset(_("Profile"), Field("name"), Field("image")),
            Fieldset(_("About"), Field("about"), Field("world"), Field("ecobasa_what")),
        )