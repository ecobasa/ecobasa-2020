import pytest

from django.test import Client
from django.urls import reverse
from postman.models import STATUS_ACCEPTED, Message

from users.models import User


def _user(name):
    return User.objects.create_user(email=f"{name}@example.com", password="secret", username=name, name=name.title())


def _client_for(user):
    client = Client()
    client.login(username=user.email, password="secret")
    return client


@pytest.mark.django_db
class TestMessagesPage:
    """Received and sent messages are the two tabs of one Messages page."""

    def test_tabs_count_messages_and_unread_ones_wait(self):
        ana, ben = _user("ana"), _user("ben")
        for i in range(2):
            Message.objects.create(sender=ben, recipient=ana, subject=f"Hi {i}", body="…", moderation_status=STATUS_ACCEPTED)
        Message.objects.create(sender=ana, recipient=ben, subject="Hello", body="…", moderation_status=STATUS_ACCEPTED)

        tabs = _client_for(ana).get(reverse("postman:inbox")).context["tabs"]
        assert [(str(t.label), t.count, t.waiting, t.active) for t in tabs] == [
            ("Received", 2, 2, True), ("Sent", 1, 0, False),
        ]
        response = _client_for(ana).get(reverse("postman:sent"))
        assert [t.active for t in response.context["tabs"]] == [False, True]
        assert "Hello" in response.content.decode()

    def test_long_inboxes_are_paged(self):
        from dashboard_lists import PER_PAGE
        ana, ben = _user("ana"), _user("ben")
        for i in range(PER_PAGE + 1):
            Message.objects.create(sender=ben, recipient=ana, subject=f"Hi {i}", body="…", moderation_status=STATUS_ACCEPTED)
        page = _client_for(ana).get(reverse("postman:inbox")).context["page"]
        assert len(page.object_list) == PER_PAGE
        assert page.older_url.endswith("page=2")
