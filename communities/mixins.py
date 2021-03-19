import random
import string
from django.utils.text import slugify


class UniqueSlugMixin:
    """Sets a unique slug with random chars on first save
    in the form "ldfkajgf-my-glorious-title"
    
    You should:
    Have a field called slugon your model and
    set `UNIQUE_SLUG_FROM_FIELD` on the model to the field which is used to populate the slug
    """

    UNIQUE_SLUG_RANDOM_ID_LENGTH = 8
    UNIQUE_SLUG_FROM_FIELD = "name"

    def save(self, *args, **kwargs):
        while not self.slug:
            random_id = "".join(
                random.sample(string.ascii_lowercase, self.UNIQUE_SLUG_RANDOM_ID_LENGTH)
            )
            new_slug = slugify(random_id + "-" + getattr(self, self.UNIQUE_SLUG_FROM_FIELD))
            if not self.__class__.objects.filter(slug=new_slug).exists():
                self.slug = new_slug
        super().save(*args, **kwargs)