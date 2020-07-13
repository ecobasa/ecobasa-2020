import random
import string


class RandomIdMixin:
    """Sets random id field on first save"""

    RANDOM_ID_LENGTH = 8

    def save(self, *args, **kwargs):
        while not self.random_id:
            new_id = "".join(
                random.sample(string.ascii_lowercase, self.RANDOM_ID_LENGTH)
            )
            if not self.__class__.objects.filter(random_id=new_id).exists():
                self.random_id = new_id
        super().save(*args, **kwargs)
