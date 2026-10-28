from datetime import timedelta

import pytest

from django.test import Client
from django.utils import timezone

from notifications.models import Notification
from skills.models import Skill
from gifts.models import Listing
from gifts.testing import skill_offer, skill_wish

from ..models import User


def _login(user):
    Client().login(username=user.email, password="secret")


def _nudges(user):
    return Notification.objects.filter(recipient=user, tag=Notification.TAG_SKILL_NUDGE)


@pytest.fixture
def user():
    return User.objects.create_user(email="max@example.com", password="secret", name="Max")


@pytest.mark.django_db
class TestSkillNudge:
    def test_one_reminder_however_often_you_log_in(self, user):
        _login(user)
        _nudges(user).update(is_read=True)
        _login(user)
        _login(user)
        assert _nudges(user).count() == 1
        assert _nudges(user).get().is_read

    def test_read_reminder_shows_again_after_a_week(self, user):
        _login(user)
        _nudges(user).update(is_read=True, created_at=timezone.now() - timedelta(days=8))
        _login(user)
        nudge = _nudges(user).get()
        assert not nudge.is_read
        assert nudge.created_at > timezone.now() - timedelta(minutes=1)

    def test_adding_a_skill_removes_the_reminder(self, user):
        _login(user)
        skill_offer(user, Skill.objects.create(name="Beekeeping"))
        assert not _nudges(user).exists()
        _login(user)
        assert not _nudges(user).exists()
