import re

import pytest
from postman.models import Message

from users.models import User

pytestmark = pytest.mark.django_db


def test_a_new_account_posts_only_after_opening_the_link(client, bot_check_fields, mailoutbox):
    client.post("/users/register/", {"name": "Max", "email": "max@example.com", "password": "asdaogfisgaf",
                                     **bot_check_fields()})
    other = User.objects.create_user(email="ina@example.com", password="secret", name="Ina")
    write = {"recipients": str(other.pk), "subject": "Hi", "body": "Hello Ina"}

    client.post("/messages/write/", write)
    assert not Message.objects.exists()

    link = re.search(r"https?://\S+/users/confirm/\S+/", mailoutbox[0].body).group(0)
    client.get(link)
    assert User.objects.get(email="max@example.com").email_confirmed
    client.post("/messages/write/", write)
    assert Message.objects.exists()


def test_accounts_made_otherwise_count_as_confirmed():
    assert User.objects.create_user(email="ivo@example.com", password="secret").email_confirmed
