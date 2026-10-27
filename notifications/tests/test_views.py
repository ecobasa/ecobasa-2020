import pytest
from django.test import Client

from users.models import User

from ..models import Notification


@pytest.mark.django_db
def test_notification_cards_are_plain_links_marked_read_on_click():
    """htmx on a link would cancel following it, so the card is a plain link that marks
    the notification as read in the background."""
    user = User.objects.create_user(email="n@example.com", password="secret")
    notification = Notification.objects.create(recipient=user, tag=Notification.TAG_MATCH_AREA, link="/matches/1/")
    client = Client()
    client.force_login(user)
    content = client.get("/notifications/").content.decode()
    assert 'href="/matches/1/"' in content and "hx-post" not in content
    assert client.post(f"/notifications/{notification.pk}/mark-read/").status_code == 204
    notification.refresh_from_db()
    assert notification.is_read
