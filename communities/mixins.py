from django.utils.text import slugify


class UniqueSlugMixin:
    """Sets a unique slug with incrementing suffix on first save
    in the form "my-glorious-title-2"

    You should:
     - Have a field called slug on your model and
     - set `UNIQUE_SLUG_FROM_FIELD` on the model to the field which is used to populate the slug
    """

    UNIQUE_SLUG_FROM_FIELD = "name"

    def _slug_is_available(self, slug):
        return not self.__class__.objects.filter(slug=slug).exists()

    def save(self, *args, **kwargs):
        base_slug = slugify(getattr(self, self.UNIQUE_SLUG_FROM_FIELD))
        new_slug = base_slug
        suffix = 1

        while not self._slug_is_available(new_slug):
            suffix += 1
            new_slug = f"{base_slug}-{suffix}"

        self.slug = new_slug

        super().save(*args, **kwargs)
