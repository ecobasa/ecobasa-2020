from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from gift_economy.matches.matching import match
from users.models import User

from ..models import FoodThing, Listing


def _user(name):
    return User.objects.create_user(email=f"{name}@example.com", password="secret", username=name, name=name.title())


def _client_for(user):
    client = Client()
    client.login(username=user.email, password="secret")
    return client


def _food(owner, title, type="offer", **fields):
    return Listing.objects.create(owner=owner, title=title, type=type, kind=Listing.KIND_FOOD, **fields)


@pytest.mark.django_db
def test_the_food_vocabulary_is_loaded_apart_from_the_plants():
    plums = FoodThing.objects.get(slug="food-plums")
    assert plums.parent.slug == "food-fruit" and plums.parent.parent.slug == "food"
    assert plums.get_name("de") == "Pflaume" and "Zwetschgen" in plums.other_names
    assert FoodThing.objects.get(slug="food-peanut-butter").parent.slug == "food-nut-butter"
    # The apple tree stays a plant
    assert not FoodThing.objects.filter(slug="apple").exists()


@pytest.mark.django_db
def test_offering_food_with_its_best_before_date():
    anna = _user("anna")
    response = _client_for(anna).post(reverse("gifts:create"), {
        "type": "offer", "kind": "food", "title": "Erdnussbutter", "quantity": "24", "unit": "pieces",
        "best_before": "2026-03-01",
    })
    assert response.status_code == 302
    food = Listing.objects.get()
    assert (food.thing.slug, str(food.best_before), food.kind_label) == ("food-peanut-butter", "2026-03-01", "Food & harvest")
    assert [c.slug for c in food.categories.all()] == ["food-preserves"]


@pytest.mark.django_db
@pytest.mark.parametrize("kind, type", [("food", "wish"), ("material", "offer")])
def test_a_best_before_date_only_for_food_offered(kind, type):
    anna = _user("anna")
    _client_for(anna).post(reverse("gifts:create"), {"type": type, "kind": kind, "title": "Zucchini", "best_before": "2026-03-01"})
    assert Listing.objects.get().best_before is None


@pytest.mark.django_db
@pytest.mark.parametrize("title, ok", [
    ("Zucchini", True),
    ("Paradeiser", True),  # a regional word
    ("Sauerteig", True),
    ("17 kg Zucchini, bitte nehmt sie", False),  # the details go into the description
])
def test_food_only_by_a_name_from_the_vocabulary(title, ok):
    anna = _user("anna")
    response = _client_for(anna).post(reverse("gifts:create"), {"type": "offer", "kind": "food", "title": title})
    assert (response.status_code == 302) is ok


@pytest.mark.django_db
def test_food_past_its_date_stays_listed_with_a_note():
    anna = _user("anna")
    jars = _food(anna, "Peanut butter", best_before=timezone.localdate() - timedelta(days=30))
    fresh = _food(anna, "Honey", best_before=timezone.localdate() + timedelta(days=30))
    assert jars.past_best_before and not fresh.past_best_before
    assert set(Listing.objects.open()) == {jars, fresh}
    page = Client().get(jars.get_absolute_url(), HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert "Best before" in page and "Past its date, often still good" in page
    assert "Past its date" not in Client().get(fresh.get_absolute_url(), HTTP_ACCEPT_LANGUAGE="en").content.decode()


@pytest.mark.django_db
def test_a_wish_for_fruit_finds_offered_plums():
    anna, ben = _user("anna"), _user("ben")
    wish = _food(anna, "Obst", type="wish")
    offer = _food(ben, "Zwetschgen")
    match(offer, notify=False)
    assert [(s.own, s.reason) for s in anna.suggestions.all()] == [(wish, "thing")]


@pytest.mark.django_db
def test_food_doesnt_match_seeds_or_plants_of_the_same_crop():
    anna, ben = _user("anna"), _user("ben")
    Listing.objects.create(owner=anna, title="Tomate", type="wish", kind=Listing.KIND_SEEDS_PLANTS)
    match(_food(ben, "Tomate"), notify=False)
    assert not anna.suggestions.exists()
