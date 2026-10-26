import io
from datetime import timedelta
from email.message import EmailMessage

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from communities.models import Community
from gifts.models import Listing
from matches.models import Match, MatchMessage, VolunteerDetails
from skills.models import Skill, SkillWish, UserSkill
from notifications.models import Notification
from users.models import User

from ..inbox import handle_reply, reply_text
from ..models import Reference, ReferenceRequest, ReferenceSkill
from ..reference_requests import REPLY_MARKER, exchange_text, reference_due_at, send_reference_requests


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    settings.SITE_URL = "https://ecobasa.test"
    settings.REFERENCE_REPLY_ADDRESS = "references@ecobasa.test"


@pytest.fixture
def owner():
    return User.objects.create_user(
        email="owner@example.com", password="secret", username="owner", name="Olga", language="de",
    )


@pytest.fixture
def requester():
    return User.objects.create_user(
        email="requester@example.com", password="secret", username="requester", name="Rafa",
    )


def _match(target, requester, owner, days_ago=10, **fields):
    match = Match(from_user=requester, recipient=owner, message="Hi", status=Match.STATUS_ACCEPTED,
                  responded_at=timezone.now() - timedelta(days=days_ago), **fields)
    match.target = target
    match.save()
    return match


@pytest.fixture
def gift_match(owner, requester):
    return _match(Listing.objects.create(title="Old Bicycle", type="offer", owner=owner), requester, owner)


@pytest.fixture
def stay(owner, requester):
    match = _match(Community.objects.create(name="Goat Farm", owner=owner), requester, owner, days_ago=40)
    VolunteerDetails.objects.create(match=match, stay_to=timezone.now() - timedelta(days=2))
    return match


def _photo(name="photo.jpg", size=(3000, 2000)):
    out = io.BytesIO()
    Image.new("RGB", size, "green").save(out, "JPEG")
    return out.getvalue()


@pytest.mark.django_db
class TestWhenToAsk:
    def test_after_the_stay(self, stay):
        assert reference_due_at(stay) == stay.volunteer_details.stay_to + timedelta(days=1)

    def test_after_the_agreed_date(self, gift_match):
        gift_match.proposed_date = timezone.now() - timedelta(days=3)
        assert reference_due_at(gift_match) == gift_match.proposed_date + timedelta(days=1)

    def test_a_counter_proposals_date_wins(self, gift_match, owner):
        gift_match.proposed_date = timezone.now() - timedelta(days=9)
        counter_date = timezone.now() - timedelta(days=2)
        MatchMessage.objects.create(match=gift_match, sender=owner, status_to=Match.STATUS_COUNTER, counter_date=counter_date)
        assert reference_due_at(gift_match) == counter_date + timedelta(days=1)

    def test_a_week_after_acceptance_without_a_date(self, gift_match):
        assert reference_due_at(gift_match) == gift_match.responded_at + timedelta(days=7)


@pytest.mark.django_db
class TestSendReferenceRequests:
    def test_both_sides_are_asked_once(self, stay, owner, requester, mailoutbox):
        assert send_reference_requests() == 2
        assert send_reference_requests() == 0
        assert sorted(m.to[0] for m in mailoutbox) == [owner.email, requester.email]

    def test_in_their_language_with_reply_address_and_key(self, stay, owner, mailoutbox):
        send_reference_requests()
        reference_request = ReferenceRequest.objects.get(user=owner)
        mail = next(m for m in mailoutbox if m.to == [owner.email])
        assert mail.subject == f"Aufenthalt von Rafa bei Goat Farm: Wie war es? [#{reference_request.key}]"
        assert "Rafa schrieb:" in mail.body and "“Hi”" in mail.body
        assert mail.reply_to == [f"references+{reference_request.key}@ecobasa.test"]
        assert f"https://ecobasa.test/references/request/{reference_request.key}/" in mail.body
        assert REPLY_MARKER in mail.body

    def test_without_reply_address_only_the_link_is_offered(self, settings, stay, mailoutbox):
        settings.REFERENCE_REPLY_ADDRESS = ""
        send_reference_requests()
        assert mailoutbox[0].reply_to == []
        assert REPLY_MARKER not in mailoutbox[0].body

    def test_not_before_the_stay_ended(self, stay):
        stay.volunteer_details.stay_to = timezone.now() + timedelta(days=3)
        stay.volunteer_details.save()
        assert send_reference_requests() == 0

    def test_not_about_long_past_matches(self, stay):
        stay.volunteer_details.stay_to = timezone.now() - timedelta(days=60)
        stay.volunteer_details.save()
        assert send_reference_requests() == 0

    def test_not_about_pending_matches(self, stay):
        stay.status = Match.STATUS_PENDING
        stay.save()
        assert send_reference_requests() == 0

    def test_not_who_already_wrote_about_the_match(self, stay, requester, owner, mailoutbox):
        Reference.objects.create(author=requester, recipient=owner, subject=stay.target, text="Great", match=stay)
        assert send_reference_requests() == 1
        assert mailoutbox[0].to == [owner.email]


def _request_url(match, user):
    send_reference_requests()
    return reverse("references:request", args=[ReferenceRequest.objects.get(match=match, user=user).key])


@pytest.mark.django_db
class TestReferenceRequestForm:
    def test_works_without_login(self, stay, requester):
        response = Client().get(_request_url(stay, requester))
        assert response.status_code == 200
        assert "Goat Farm" in response.content.decode()

    def test_saves_a_reference_about_the_community_with_a_photo(self, stay, requester, owner):
        url = _request_url(stay, requester)
        response = Client().post(url, {
            "impression": "positive", "text": "We milked goats at sunrise.", "share_publicly": "on",
            "photo": SimpleUploadedFile("goats.jpg", _photo(), content_type="image/jpeg"),
        })
        assert response.status_code == 200
        reference = Reference.objects.get(author=requester)
        assert reference.subject == stay.target
        assert reference.recipient == owner
        assert reference.match == stay
        assert reference.share_publicly
        assert Image.open(reference.photo).size == (1600, 1067)
        assert ReferenceRequest.objects.get(user=requester).reference == reference
        assert Notification.objects.filter(recipient=owner, reference=reference).exists()

    def test_owner_writes_about_the_requester_naming_the_gift(self, gift_match, owner, requester):
        gift_match.responded_at = timezone.now() - timedelta(days=8)
        gift_match.save()
        Client().post(_request_url(gift_match, owner), {"impression": "positive", "text": "Rafa fixed it up!"})
        reference = Reference.objects.get(author=owner)
        assert reference.subject == requester
        assert reference.gift_names == ["Old Bicycle"]
        assert not reference.share_publicly

    def test_edits_the_reference_they_already_wrote(self, stay, requester, owner):
        Reference.objects.create(author=requester, recipient=owner, subject=stay.target, text="Old text")
        url = _request_url(stay, requester)
        assert "Old text" in Client().get(url).content.decode()
        Client().post(url, {"impression": "positive", "text": "New text"})
        assert Reference.objects.get(author=requester).text == "New text"

    def test_unreadable_photo_is_rejected(self, stay, requester):
        response = Client().post(_request_url(stay, requester), {
            "impression": "positive", "text": "Hi",
            "photo": SimpleUploadedFile("x.jpg", b"not an image", content_type="image/jpeg"),
        })
        assert response.status_code == 200
        assert not Reference.objects.exists()

    def test_unknown_or_expired_link(self, stay, requester):
        assert Client().get(reverse("references:request", args=["0" * 24])).status_code == 404
        url = _request_url(stay, requester)
        ReferenceRequest.objects.update(sent_at=timezone.now() - timedelta(days=61))
        assert Client().get(url).status_code == 404


@pytest.mark.django_db
class TestWhatItWasAbout:
    """They may have had several exchanges with the same person, so the email says which."""

    def test_each_side_of_each_kind(self, stay, gift_match, owner, requester):
        skill = Skill.objects.create(name="Cob building")
        learning = _match(UserSkill.objects.create(user=owner, skill=skill), requester, owner)
        helping = _match(SkillWish.objects.create(community=stay.target, skill=skill), requester, owner)
        wish = _match(Listing.objects.create(title="Spare tent", type="wish", owner=owner), requester, owner)
        assert exchange_text(stay, requester) == "Your stay at Goat Farm"
        assert exchange_text(stay, owner) == "Rafa's stay at Goat Farm"
        assert exchange_text(gift_match, requester) == "Old Bicycle, a gift from Olga"
        assert exchange_text(gift_match, owner) == "Old Bicycle, your gift to Rafa"
        assert exchange_text(wish, requester) == "Spare tent, your gift to Olga"
        assert exchange_text(learning, requester) == "Learning Cob Building with Olga"
        assert exchange_text(learning, owner) == "Sharing Cob Building with Rafa"
        assert exchange_text(helping, requester) == "Your help with Cob Building for Goat Farm"
        assert exchange_text(helping, owner) == "Rafa's help with Cob Building"

    def test_email_and_form_name_the_exchange_and_its_dates(self, stay, requester, mailoutbox):
        send_reference_requests()
        mail = next(m for m in mailoutbox if m.to == [requester.email])
        assert mail.subject.startswith("Your stay at Goat Farm: how was it?")
        assert "Your stay at Goat Farm" in mail.body
        assert "You wrote: “Hi”" in mail.body
        assert stay.volunteer_details.stay_to.strftime("%Y") in mail.body
        page = Client().get(_request_url(stay, requester)).content.decode()
        assert "Your stay at Goat Farm" in page


@pytest.mark.django_db
class TestEveryKindOfMatch:
    """Gifts, skills and skill wishes get the same email, form, guide and photo as stays."""

    def _answer(self, match, user, text="Thank you!"):
        url = _request_url(match, user)
        page = Client().get(url).content.decode()
        Client().post(url, {"impression": "positive", "text": text})
        return page, Reference.objects.get(author=user, match=match)

    def test_gift(self, gift_match, owner, requester, mailoutbox):
        page, reference = self._answer(gift_match, requester)
        assert "How to write a reference" in page
        assert "You are writing about a community" not in page
        assert reference.subject == owner
        assert reference.gift_names == ["Old Bicycle"]
        assert {m.to[0] for m in mailoutbox} >= {owner.email, requester.email}

    def test_learning_a_skill(self, owner, requester):
        skill = Skill.objects.create(name="Cob building")
        match = _match(UserSkill.objects.create(user=owner, skill=skill), requester, owner)
        page, reference = self._answer(match, requester)
        assert "How to write a reference" in page
        assert reference.subject == owner
        assert [(t.skill, t.status) for t in reference.skill_tags.all()] == [(skill, ReferenceSkill.STATUS_CONFIRMED)]
        _page, reference = self._answer(match, owner)
        assert reference.subject == requester
        assert not reference.skill_tags.exists()

    def test_helping_a_community_with_a_wished_skill(self, owner, requester):
        skill = Skill.objects.create(name="Cob building")
        community = Community.objects.create(name="Goat Farm", owner=owner)
        match = _match(SkillWish.objects.create(community=community, skill=skill), requester, owner)
        page, reference = self._answer(match, requester)
        assert "You are writing about a community" in page
        assert reference.subject == community
        # The ambassador writes about the helper, who confirms the skill
        _page, reference = self._answer(match, owner)
        assert reference.subject == requester
        assert [(t.skill, t.status) for t in reference.skill_tags.all()] == [(skill, ReferenceSkill.STATUS_PENDING)]


def _reply(reference_request, body, to=None, subject="Re: Wie war es?", photo=None, **headers):
    message = EmailMessage()
    message["From"] = reference_request.user.email
    message["To"] = to or f"references+{reference_request.key}@ecobasa.test"
    message["Subject"] = subject
    for name, value in headers.items():
        message[name.replace("_", "-")] = value
    message.set_content(body)
    if photo:
        message.add_attachment(photo, maintype="image", subtype="jpeg", filename="IMG_0001.jpg")
    return message.as_bytes()


@pytest.mark.django_db
class TestReplyByEmail:
    def test_reply_text_drops_quote_and_signature(self):
        body = "Es war wunderbar!\nDanke euch.\n\nAm Mo., 26. Okt. 2026 um 10:00 schrieb ecobasa <\nreferences@x>:\n> Hallo"
        assert reply_text(body) == "Es war wunderbar!\nDanke euch."
        assert reply_text("Lovely\n-- \nSent from my phone") == "Lovely"
        assert reply_text(f"Great\n\n{REPLY_MARKER}\nHello Rafa") == "Great"
        wrapped = "Great time\n\nOn Mon, Oct 26, 2026 at 10:00 AM ecobasa <references+abc@ecobasa.org>\nwrote:\n> Hi"
        assert reply_text(wrapped) == "Great time"

    def test_saves_the_reference_with_the_attached_photo(self, stay, requester, mailoutbox):
        send_reference_requests()
        reference_request = ReferenceRequest.objects.get(user=requester)
        mailoutbox.clear()
        reference = handle_reply(_reply(reference_request, "Thank you, goats!\n\n> quoted", photo=_photo()))
        assert reference.text == "Thank you, goats!"
        assert reference.photo
        # A reply can't agree to sharing: the thank-you email asks for it
        assert not reference.share_publicly
        thanks = next(m for m in mailoutbox if m.to == [requester.email])
        assert "?share=1" in thanks.body
        # A reply can't choose an impression: positive, and the email says how to change it
        assert reference.impression == Reference.IMPRESSION_POSITIVE
        assert "We saved it as “Positive”" in thanks.body

    def test_key_from_the_subject_when_the_address_lost_it(self, stay, requester):
        send_reference_requests()
        reference_request = ReferenceRequest.objects.get(user=requester)
        raw = _reply(reference_request, "Lovely", to="references@ecobasa.test", subject=f"Re: How was it? [#{reference_request.key}]")
        assert handle_reply(raw).text == "Lovely"

    def test_auto_replies_and_unknown_keys_are_ignored(self, stay, requester):
        send_reference_requests()
        reference_request = ReferenceRequest.objects.get(user=requester)
        assert handle_reply(_reply(reference_request, "Out of office", Auto_Submitted="auto-replied")) is None
        reference_request.key = "f" * 24
        assert handle_reply(_reply(reference_request, "Who am I?")) is None
        assert not Reference.objects.exists()

