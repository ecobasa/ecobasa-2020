import pytest

from django.conf import settings
from django.utils import translation


@pytest.fixture(autouse=True)
def reset_language():
    """Requests made through the test client leave their language active afterwards;
    reset it so one test's language doesn't leak into the next."""
    yield
    translation.activate(settings.LANGUAGE_CODE)


@pytest.fixture
def bot_check_fields(monkeypatch):
    """Makes a form's bot check pass: call it for the fields of a solved challenge."""
    import itertools

    import bot_check

    monkeypatch.setattr(bot_check, "MIN_SECONDS", 0)

    def fields():
        challenge = bot_check.challenge()
        nonce = next(str(n) for n in itertools.count() if bot_check.solved(challenge, str(n)))
        return {"website": "", "challenge": challenge, "nonce": nonce}

    return fields
