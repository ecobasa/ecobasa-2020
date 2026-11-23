import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def post(client, bot_check_fields):
    def post(text="Hello, I would like to help with translations.", **fields):
        data = {"name": "Lene Moos", "email": "lene@example.com", "subject": "Translations", "message": text,
                **bot_check_fields(), **fields}
        client.post("/contact/", data)
        return data

    return post


def test_a_message_goes_to_us_answerable_to_the_sender(post, mailoutbox, settings):
    post()
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == [settings.CONTACT_EMAIL]
    assert mailoutbox[0].reply_to == ["lene@example.com"]


@pytest.mark.parametrize("fields", [
    {"website": "http://spam.example"},
    {"nonce": "1"},
    {"challenge": "made-up"},
    {"message": "Look at http://a.example http://b.example http://c.example"},
])
def test_bots_send_nothing(post, mailoutbox, fields):
    post(**fields)
    assert mailoutbox == []


def test_too_fast_sends_nothing(post, mailoutbox, monkeypatch):
    import bot_check

    monkeypatch.setattr(bot_check, "MIN_SECONDS", 60)
    post()
    assert mailoutbox == []


def test_a_challenge_sends_once_and_the_same_text_once(client, post, mailoutbox):
    data = post()
    client.post("/contact/", data)
    post(email="other@example.com")
    assert len(mailoutbox) == 1


def test_one_address_sends_a_few_per_hour(post, mailoutbox):
    from homepage.contact import PER_ADDRESS

    for n in range(PER_ADDRESS[0][0] + 1):
        post(text=f"Message number {n} about helping out.", email=f"p{n}@example.com")
    assert len(mailoutbox) == PER_ADDRESS[0][0]


def test_members_write_without_the_challenge(client, mailoutbox, django_user_model):
    member = django_user_model.objects.create_user(email="ivo@example.com", password="secret", name="Ivo")
    client.force_login(member)
    client.post("/contact/", {"subject": "Design", "message": "Can I help with the design of the site?"})
    assert mailoutbox[0].reply_to == ["ivo@example.com"]
