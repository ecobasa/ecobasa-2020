import pytest

from django.contrib.gis.geos import Point
from django.test import Client
from django.urls import reverse
from django.utils import translation

from gift_economy.gifts.models import Listing
from gift_economy.matches.models import Match
from users.models import User
from ..models import Community, Membership


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
    return Community.objects.create(name="Hof Kleeblatt", ambassador=ambassador, location=Point(14.98, 51.16))


@pytest.fixture
def ole(db):
    return _user("ole@example.com", "Ole")


def _form_data(community, **fields):
    data = {"name": community.name, "type": community.type, "status": community.status, "currency": "eur"}
    data.update(fields)
    return data


@pytest.mark.django_db
class TestProfile:
    def test_ambassador_fills_in_how_they_live(self, community, ambassador):
        form_page = _client(ambassador).get(reverse("communities:update", args=[community.slug])).content.decode()
        assert 'name="looking_for_members"' in form_page and "data-languages" in form_page
        response = _client(ambassador).post(reverse("communities:update", args=[community.slug]), _form_data(
            community, looking_for_members="on", kitchen=[Community.KITCHEN_VEGAN, Community.KITCHEN_GLUTEN_FREE], children_welcome=Community.CHILDREN_WELCOME,
            pets=Community.PETS_ASK, buy_in="15000", buy_in_kind=Community.BUY_IN_SHARES, exit_terms="Paid back within a year.",
            work_hours="10", decision_making=Community.DECISIONS_CONSENT, trial_months="6", languages="de,en",
        ))
        assert response.status_code == 302
        community.refresh_from_db()
        assert community.looking_for_members and community.kitchen == [Community.KITCHEN_VEGAN, Community.KITCHEN_GLUTEN_FREE]
        assert community.languages == ["de", "en"] and community.currency == "EUR" and community.buy_in == 15000

        with translation.override("en"):
            page = Client().get(community.get_absolute_url()).content.decode()
            apply_page = _client(_user("ole@example.com")).get(reverse("communities:apply", args=[community.slug])).content.decode()
            facts = {label: value for _icon, label, value in community.lives()}
        # The exit terms only for who asks to become a member
        assert "How we live" in page and "Paid back within a year." not in page
        assert "Paid back within a year." in apply_page
        assert facts["Buy-in"] == "15 000 EUR (Cooperative shares)"
        assert facts["Work commitment"] == "10 hours per week" and facts["Languages"] == "German, English"
        assert facts["Shared kitchen"] == "Vegan, Gluten-free"

    def test_eating_anything_is_not_vegetarian(self, community, ambassador):
        response = _client(ambassador).post(
            reverse("communities:update", args=[community.slug]),
            _form_data(community, kitchen=[Community.KITCHEN_ANY, Community.KITCHEN_VEGETARIAN]),
        )
        assert response.status_code == 200
        community.refresh_from_db()
        assert community.kitchen == []

    def test_unknown_language_is_refused(self, community, ambassador):
        response = _client(ambassador).post(
            reverse("communities:update", args=[community.slug]), _form_data(community, languages="de,klingon"),
        )
        assert response.status_code == 200
        community.refresh_from_db()
        assert community.languages == []

    def test_nothing_filled_in_shows_no_section(self, community):
        with translation.override("en"):
            assert "How we live" not in Client().get(community.get_absolute_url()).content.decode()


@pytest.mark.django_db
class TestFilters:
    @pytest.fixture
    def others(self, ambassador):
        found = {}
        for name, fields in {
            "Vegan Hof": dict(kitchen=[Community.KITCHEN_VEGAN, Community.KITCHEN_GLUTEN_FREE], buy_in=20000, languages=["de"], looking_for_members=True),
            "Veggie Hof": dict(kitchen=[Community.KITCHEN_VEGETARIAN], buy_in=5000, work_hours=20, languages=["fr", "en"]),
            "Any Hof": dict(kitchen=[Community.KITCHEN_ANY, Community.KITCHEN_GLUTEN_FREE], pets=Community.PETS_WELCOME, work_hours=5),
        }.items():
            found[name] = Community.objects.create(name=name, ambassador=ambassador, location=Point(10, 50), **fields)
        return found

    def _names(self, **params):
        response = Client().get(reverse("communities:api-markers"), params)
        return sorted(feature["properties"]["name"] for feature in response.json()["features"])

    def test_filters(self, community, others):
        assert self._names(looking="1") == ["Vegan Hof"]
        # A vegetarian kitchen fits a vegan one too
        assert self._names(kitchen="vegetarian") == ["Vegan Hof", "Veggie Hof"]
        assert self._names(kitchen="vegan") == ["Vegan Hof"]
        # Several diets: the kitchen cooks all of them
        assert self._names(kitchen="gluten_free") == ["Any Hof", "Vegan Hof"]
        assert self._names(kitchen="vegetarian,gluten_free") == ["Vegan Hof"]
        assert self._names(pets="ask") == ["Any Hof"]
        assert self._names(language="en") == ["Veggie Hof"]
        # Up to an amount: none asked fits
        assert self._names(buy_in="10000") == ["Any Hof", "Hof Kleeblatt", "Veggie Hof"]
        assert self._names(work="10") == ["Any Hof", "Hof Kleeblatt", "Vegan Hof"]
        assert self._names(kitchen="vegetarian", language="de") == ["Vegan Hof"]

    def test_list_filters_too(self, community, others):
        response = Client().get(reverse("communities:api-list"), {"kitchen": "vegan"})
        assert [c.name for c in response.context["communities"]] == ["Vegan Hof"]

    def test_language_filter_offers_the_languages_in_use(self, community, others):
        with translation.override("en"):
            filters = {param: choices for param, _label, choices in Client().get(reverse("communities:list")).context["life_filters"]}
        assert filters["language"] == [("en", "English"), ("fr", "French"), ("de", "German")]


@pytest.mark.django_db
class TestShowingOffers:
    @pytest.fixture
    def member(self, community, ole):
        return Membership.objects.create(community=community, user=ole)

    def test_offers_show_only_when_the_member_wants(self, community, member, ole):
        Listing.objects.create(owner=ole, type="offer", kind="other", title="Plum jam")
        assert Client().get(community.get_absolute_url()).context["gifts"] == []

        _client(ole).post(reverse("communities:show_offers", args=[community.slug]), {"shows_offers": "1"})
        member.refresh_from_db()
        assert member.shows_offers
        assert [listing.title for listing in Client().get(community.get_absolute_url()).context["gifts"]] == ["Plum jam"]

        _client(ole).post(reverse("communities:show_offers", args=[community.slug]), {"shows_offers": "0"})
        member.refresh_from_db()
        assert not member.shows_offers

    def test_only_members_switch_it(self, community):
        stranger = _user("kim@example.com")
        response = _client(stranger).post(reverse("communities:show_offers", args=[community.slug]), {"shows_offers": "1"})
        assert response.status_code == 302
        assert not community.memberships.filter(user=stranger).exists()


@pytest.mark.django_db
class TestInvitations:
    def _invite(self, by, community, person, message="Come and live with us."):
        return _client(by).post(reverse("communities:invite", args=[community.slug]), {"user": person.pk, "message": message})

    def test_ambassador_invites_and_they_accept(self, community, ambassador, ole):
        response = self._invite(ambassador, community, ole)
        assert response.status_code == 302
        membership = Membership.objects.get(community=community, user=ole)
        match = membership.match
        assert match.from_user == ambassador and match.recipient == ole
        assert membership.is_invitation and not membership.is_counted
        with translation.override("en"):
            assert match.kind[0] == "Invitation"
            assert membership.get_match_verb() == "invited you to become a member of"
            assert "answer the invitation" in _client(ole).get(community.get_absolute_url()).content.decode()

        # Not an application for the ambassador to answer
        assert list(_client(ambassador).get(community.get_absolute_url()).context["applications"]) == []

        _client(ole).post(reverse("matches:detail", args=[match.pk]), {"action": "accept"})
        assert community.is_member(ole)

    def test_inviting_a_member_again_is_refused(self, community, ambassador):
        response = self._invite(ambassador, community, ambassador)
        assert response.status_code == 200
        assert "They are a member already" in response.content.decode()

    def test_only_the_ambassador_invites(self, community, ole):
        kim = _user("kim@example.com")
        assert self._invite(ole, community, kim).status_code == 403
        assert not community.memberships.filter(user=kim).exists()

    def test_people_search_leaves_out_members(self, community, ambassador, ole):
        _user("olga@example.com", "Olga")
        Membership.objects.create(community=community, user=ole)
        response = _client(ambassador).get(reverse("communities:api-people", args=[community.slug]), {"q": "ol"})
        assert [person["name"] for person in response.json()["results"]] == ["Olga"]
        assert _client(ole).get(reverse("communities:api-people", args=[community.slug]), {"q": "ol"}).status_code == 403

    def test_declined_invitation_can_be_sent_again(self, community, ambassador, ole):
        self._invite(ambassador, community, ole)
        match = Membership.objects.get(community=community, user=ole).match
        _client(ole).post(reverse("matches:detail", args=[match.pk]), {"action": "decline"})
        assert Match.objects.get(pk=match.pk).status == Match.STATUS_DECLINED
        assert self._invite(ambassador, community, ole).status_code == 302
