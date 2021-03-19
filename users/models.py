from django.db import models
from django.core.mail import send_mail
from django.urls import reverse
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils.translation import gettext_lazy as _


class UserManager(BaseUserManager):
    """Define a model manager for User model with no username field."""

    use_in_migrations = True

    def get_by_natural_key(self, username):
        """When trying to find the user try email first, then username (for legacy users)"""
        try:
            return self.get(email=username)
        except self.model.DoesNotExist:
            return self.get(username=username)

    def _create_user(self, email, password, **extra_fields):
        """Create and save a User with the given email and password."""
        if not email:
            raise ValueError("The given email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields):
        """Create and save a regular User with the given email and password."""
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password, **extra_fields):
        """Create and save a SuperUser with the given email and password."""
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self._create_user(email, password, **extra_fields)


class User(AbstractUser):
    """user model

     * email is used for logging in
     * username is only used for legacy users, so they can still log in like on the old site
     * name is used instead of first_name and last_name
    """

    # username is only for legacy users and None/null by default, but unique for non-null values
    username = models.CharField(_("username"), unique=True, default=None, max_length=150, blank=True, null=True)

    email = models.EmailField(_("email address"), unique=True)
    first_name = models.CharField(_("First Name"), max_length=150)
    last_name = models.CharField(_("Last Name"), max_length=150)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["first_name", "last_name"]

    objects = UserManager()

    def get_absolute_url(self) -> str:
        return reverse("users:detail", kwargs={"email": self.email})

    def get_full_name(self):
        '''
        Returns the first_name plus the last_name, with a space in between.
        '''
        full_name = '%s %s' % (self.first_name, self.last_name)
        return full_name.strip()

    def get_short_name(self):
        '''
        Returns the short name for the user.
        '''
        return self.first_name

    def email_user(self, subject, message, from_email=None, **kwargs):
        '''
        Sends an email to this User.
        '''
        send_mail(subject, message, from_email, [self.email], **kwargs)