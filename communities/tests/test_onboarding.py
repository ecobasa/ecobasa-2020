import pytest

from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse
from django.utils import translation

from users.models import User
from .. import onboarding
from ..models import Community, Membership, OnboardingQuestion


def _user(email, name=""):
    return User.objects.create_user(email=email, password="secret", name=name or email.split("@")[0])


def _client(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def ambassador(db):
    return _user("rosa@example.com", "Rosa")


@pytest.fixture
def community(ambassador):
    return Community.objects.create(
        name="Hof Kleeblatt", ambassador=ambassador, location=Point(14.98, 51.16), looking_for_members=True,
    )


def _editor_data(community, on=(), own=(), **fields):
    """The editor's POST: the library questions in `on` switched on with their suggested
    type, `own` as new own questions, and anything else in `fields`."""
    data = {"own-TOTAL_FORMS": str(len(own)), "own-INITIAL_FORMS": "0", "own-MIN_NUM_FORMS": "0", "own-MAX_NUM_FORMS": "1000"}
    for key in onboarding.QUESTIONS:
        data[f"{key}-type"] = onboarding.QUESTIONS[key].type
        if key in on:
            data[f"{key}-on"] = "on"
    for index, question in enumerate(own):
        for name, value in question.items():
            data[f"own-{index}-{name}"] = value
    data.update(fields)
    return data


class TestLibrary:
    def test_keys_are_unique_and_suggested_types_allowed(self):
        keys = [question.key for module in onboarding.MODULES for question in module.questions]
        assert len(keys) == len(set(keys))
        for question in onboarding.QUESTIONS.values():
            assert question.type in question.types
            assert bool(question.text) != bool(question.fact)
            if question.fact:
                assert question.kind == onboarding.AGREE and question.fact_label

    @pytest.mark.django_db
    def test_statements_follow_the_facts(self, community):
        with translation.override("en"):
            kitchen = onboarding.QUESTIONS["kitchen"]
            assert kitchen.text_for(community) == ""
            community.kitchen = [Community.KITCHEN_ANY]
            assert kitchen.text_for(community) == ""
            community.kitchen = [Community.KITCHEN_VEGAN]
            assert kitchen.text_for(community) == "Our shared kitchen cooks: Vegan. That's fine for me."
            community.buy_in, community.buy_in_kind = 15000, Community.BUY_IN_SHARES
            assert "15 000 EUR (Cooperative shares)" in onboarding.QUESTIONS["buy_in"].text_for(community)
            community.languages = ["de", "en"]
            assert "German, English" in onboarding.QUESTIONS["languages"].text_for(community)

    @pytest.mark.django_db
    def test_pets_asked_or_agreed_to(self, community):
        statement, question = onboarding.QUESTIONS["pets"], onboarding.QUESTIONS["pets_along"]
        community.pets = Community.PETS_ASK
        assert statement.text_for(community) == "" and question.text_for(community)
        community.pets = Community.PETS_NONE
        assert statement.text_for(community) and question.text_for(community) == ""

    @pytest.mark.django_db
    def test_country_note(self, community):
        school = onboarding.QUESTIONS["school"]
        assert school.note_for(community) == ""
        community.country = "DE"
        assert school.note_for(community)


@pytest.mark.django_db
class TestEditor:
    def test_only_the_ambassador_sets_it_up(self, community):
        member = _user("ole@example.com", "Ole")
        Membership.objects.create(community=community, user=member)
        url = reverse("communities:onboarding", args=[community.slug])
        assert _client(member).get(url).status_code == 403
        assert _client(member).post(url, _editor_data(community, on=["why_here"])).status_code == 403
        assert not community.onboarding_questions.exists()

    def test_switching_questions_on_and_off(self, community, ambassador):
        url = reverse("communities:onboarding", args=[community.slug])
        page = _client(ambassador).get(url).content.decode()
        assert 'name="why_here-on"' in page and "Motivation and fit" in page

        response = _client(ambassador).post(url, _editor_data(
            community, on=["why_here", "mediation", "support"],
            **{"why_here-required": "on", "why_here-note": "Take your time.", "mediation-type": onboarding.INFO,
               "support-required": "on"},
            after_visit="Six months trial, then the plenum decides.",
        ))
        assert response.status_code == 302
        rows = {row.key: row for row in community.onboarding_questions.all()}
        assert set(rows) == {"why_here", "mediation", "support"}
        assert rows["why_here"].required and rows["why_here"].note == "Take your time."
        assert rows["mediation"].type == onboarding.INFO
        # A sensitive question can't be made required
        assert not rows["support"].required and not rows["support"].is_required
        community.refresh_from_db()
        assert community.after_visit.startswith("Six months")

        _client(ambassador).post(url, _editor_data(community, on=["mediation"]))
        assert list(community.onboarding_questions.values_list("key", flat=True)) == ["mediation"]

    def test_a_type_the_question_cant_have(self, community, ambassador):
        url = reverse("communities:onboarding", args=[community.slug])
        response = _client(ambassador).post(url, _editor_data(
            community, on=["why_here"], **{"why_here-type": onboarding.MUST_MATCH},
        ))
        assert response.status_code == 200
        assert not community.onboarding_questions.exists()

    def test_own_questions(self, community, ambassador):
        url = reverse("communities:onboarding", args=[community.slug])
        _client(ambassador).post(url, _editor_data(community, on=["why_here"], own=[
            {"text": "Can you drive a tractor?", "answer_kind": onboarding.YES_NO, "type": onboarding.INFO, "ORDER": "2"},
            {"text": "Do you play an instrument?", "answer_kind": onboarding.TEXT, "type": onboarding.DISCUSSION, "ORDER": "1"},
        ]))
        own = list(community.onboarding_questions.filter(key=""))
        assert [question.text for question in own] == ["Do you play an instrument?", "Can you drive a tractor?"]
        # After the library's
        assert own[0].position > community.onboarding_questions.get(key="why_here").position

        tractor = own[1]
        data = _editor_data(community, on=["why_here"])
        data.update({
            "own-TOTAL_FORMS": "2", "own-INITIAL_FORMS": "2",
            "own-0-id": str(own[0].pk), "own-0-text": own[0].text, "own-0-answer_kind": onboarding.TEXT,
            "own-0-type": onboarding.DISCUSSION, "own-0-ORDER": "1",
            "own-1-id": str(tractor.pk), "own-1-text": tractor.text, "own-1-answer_kind": onboarding.YES_NO,
            "own-1-type": onboarding.INFO, "own-1-ORDER": "2", "own-1-DELETE": "on",
        })
        _client(ambassador).post(url, data)
        assert list(community.onboarding_questions.filter(key="").values_list("text", flat=True)) == ["Do you play an instrument?"]


def _process(community):
    """A vegan kitchen to agree to, a required and a sensitive question, a yes/no own
    question and a topic for the visit."""
    community.kitchen = [Community.KITCHEN_VEGAN]
    community.after_visit = "Six months trial, then the plenum decides."
    community.save()
    for key, type, required in [("kitchen", onboarding.MUST_MATCH, False), ("pets", onboarding.MUST_MATCH, False),
                                ("why_here", onboarding.INFO, True), ("support", onboarding.INFO, False),
                                ("would_leave", onboarding.DISCUSSION, False)]:
        OnboardingQuestion.objects.create(community=community, key=key, type=type, required=required, position=onboarding.POSITIONS[key])
    return OnboardingQuestion.objects.create(
        community=community, text="Can you drive a tractor?", answer_kind=onboarding.YES_NO, type=onboarding.INFO, position=999,
    )


@pytest.mark.django_db
class TestApplication:
    def test_the_process_shows_only_on_the_apply_page(self, community):
        _process(community)
        ole = _user("ole@example.com", "Ole")
        with translation.override("en"):
            assert "Our shared kitchen cooks" not in _client(ole).get(community.get_absolute_url()).content.decode()
            assert [question.key for question in community.onboarding()][:1] == ["kitchen"]
            page = _client(ole).get(reverse("communities:apply", args=[community.slug])).content.decode()
        assert 'name="lives_here"' in page
        # Must-matches first; pets aren't filled in, so there's nothing to agree to
        assert page.index("Our shared kitchen cooks: Vegan.") < page.index("Why this community, and why now?")
        assert "There are no pets here" not in page
        assert "Can you drive a tractor?" in page and "What would make you leave this community?" in page
        assert "Six months trial" in page

    def test_statements_under_their_texts_and_the_message_after_the_must_matches(self, community):
        _process(community)
        community.house_agreements = "Quiet after ten."
        community.save()
        OnboardingQuestion.objects.create(
            community=community, key="house_agreements", type=onboarding.MUST_MATCH, position=onboarding.POSITIONS["house_agreements"],
        )
        with translation.override("en"):
            page = _client(_user("ole@example.com")).get(reverse("communities:apply", args=[community.slug])).content.decode()
        statement = page.index("read your house agreements")
        assert page.index("Quiet after ten.") < statement < page.index("Our shared kitchen cooks")
        assert page.index("Our shared kitchen cooks") < page.index('name="message"') < page.index("Why this community, and why now?")

    def test_applying(self, community, ambassador):
        tractor = _process(community)
        ole = _user("ole@example.com", "Ole")
        kitchen, why, support = (community.onboarding_questions.get(key=key) for key in ["kitchen", "why_here", "support"])
        url = reverse("communities:apply", args=[community.slug])
        # Not agreed to the kitchen, and the required question left empty
        response = _client(ole).post(url, {f"q{why.pk}": ""})
        assert response.status_code == 200 and not community.memberships.filter(user=ole).exists()

        with translation.override("en"):
            response = _client(ole).post(url, {
                f"q{kitchen.pk}": "on", f"q{why.pk}": "The bread.", f"q{tractor.pk}": "yes", "message": "Hello!",
            })
        membership = community.memberships.get(user=ole)
        assert response.status_code == 302 and membership.match.message == "Hello!"
        answers = {answer["key"] or answer["text"]: answer for answer in membership.application.answers}
        assert answers["kitchen"]["text"] == "Our shared kitchen cooks: Vegan. That's fine for me." and answers["kitchen"]["answer"] is True
        assert answers["why_here"]["answer"] == "The bread." and answers["Can you drive a tractor?"]["answer"] is True
        assert answers["support"]["answer"] is None and answers["support"]["sensitive"]
        assert answers["would_leave"]["type"] == onboarding.DISCUSSION

        # Frozen: changing the process later doesn't change what they answered
        tractor.text = "Can you drive a lorry?"
        tractor.save()
        with translation.override("en"):
            page = _client(ambassador).get(membership.match.get_absolute_url()).content.decode()
        assert "Can you drive a tractor?" in page and "The bread." in page and "Can you drive a lorry?" not in page

    def test_who_already_lives_here_skips_the_questions(self, community):
        _process(community)
        ole = _user("ole@example.com", "Ole")
        response = _client(ole).post(reverse("communities:apply", args=[community.slug]), {"lives_here": "on", "message": "Room 4."})
        membership = community.memberships.get(user=ole)
        assert response.status_code == 302 and not hasattr(membership, "application")

    def test_not_looking_for_members(self, community):
        _process(community)
        community.looking_for_members = False
        community.save()
        ole = _user("ole@example.com", "Ole")
        url = reverse("communities:apply", args=[community.slug])
        with translation.override("en"):
            assert "Our shared kitchen cooks" not in _client(ole).get(url).content.decode()
        assert _client(ole).post(url, {"message": "Room 4."}).status_code == 302
        assert not hasattr(community.memberships.get(user=ole), "application")


@pytest.mark.django_db
class TestShowingOffers:
    def test_in_the_profile_settings(self, community, ambassador):
        membership = community.memberships.get(user=ambassador)
        page = _client(ambassador).get(reverse("users:update")).content.decode()
        assert f'name="shows_offers" value="{membership.pk}"' in page
        client = _client(ambassador)
        data = {"name": "Rosa", "location": Point(14.98, 51.16).ewkt, "shows_offers": [str(membership.pk)]}
        assert client.post(reverse("users:update"), data).status_code == 302
        membership.refresh_from_db()
        assert membership.shows_offers
        data.pop("shows_offers")
        client.post(reverse("users:update"), data)
        membership.refresh_from_db()
        assert not membership.shows_offers
