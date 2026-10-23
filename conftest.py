import pytest

from django.conf import settings
from django.utils import translation


@pytest.fixture(autouse=True)
def reset_language():
    """Requests made through the test client leave their language active afterwards;
    reset it so one test's language doesn't leak into the next."""
    yield
    translation.activate(settings.LANGUAGE_CODE)
