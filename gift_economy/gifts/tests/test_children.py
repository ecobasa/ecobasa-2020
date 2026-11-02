import pytest
from django.test import Client
from django.urls import reverse

from gift_economy.matches.matching import match
from users.models import User

from ..models import ChildrenThing, Listing, OtherThing


def _user(name):
    return User.objects.create_user(email=f"{name}@example.com", password="secret", username=name, name=name.title())


def _client_for(user):
    client = Client()
    client.login(username=user.email, password="secret")
    return client


def _kids(owner, title, type="offer", **fields):
    return Listing.objects.create(owner=owner, title=title, type=type, kind=Listing.KIND_CHILDREN, **fields)


@pytest.mark.django_db
def test_the_children_vocabulary_holds_toys_and_the_pram_now():
    rain_trousers = ChildrenThing.objects.get(slug="kids-rain-trousers")
    assert rain_trousers.parent.slug == "kids-outdoor-clothing" and rain_trousers.parent.parent.slug == "kids-clothing"
    assert rain_trousers.get_name("de") == "Regenhose" and "Matschhose" in rain_trousers.other_names
    assert ChildrenThing.objects.get(slug="pram").parent.slug == "kids"
    assert not OtherThing.objects.filter(slug__in=("toys", "pram", "child-seat")).exists()


@pytest.mark.django_db
def test_offering_rain_trousers_with_a_size():
    anna = _user("anna")
    response = _client_for(anna).post(reverse("gifts:create"), {
        "type": "offer", "kind": "children", "title": "Matschhose", "size": "104", "unit": "kg",
    })
    assert response.status_code == 302
    trousers = Listing.objects.get()
    assert (trousers.thing.slug, trousers.size, trousers.unit, trousers.size_label) == ("kids-rain-trousers", 104, "", "Size 104")
    assert {c.slug for c in trousers.categories.all()} == {"clothing-textiles", "children-toys"}
    assert "Size 104" in Client().get(trousers.get_absolute_url(), HTTP_ACCEPT_LANGUAGE="en").content.decode()


@pytest.mark.django_db
@pytest.mark.parametrize("title, size, saved", [
    ("Gummistiefel", "27", 27),
    ("Socken", "27", 27),  # socks by shoe size
    ("Schlittschuhe", "33", 33),
    ("Laufrad", "104", None),  # no size for a balance bike
    ("Mütze", "104", None),  # nor for a hat
])
def test_a_size_only_for_clothes_and_shoes(title, size, saved):
    anna = _user("anna")
    _client_for(anna).post(reverse("gifts:create"), {"type": "offer", "kind": "children", "title": title, "size": size})
    assert Listing.objects.get().size == saved


@pytest.mark.django_db
def test_shoes_dont_take_a_clothing_size():
    anna = _user("anna")
    response = _client_for(anna).post(reverse("gifts:create"), {"type": "offer", "kind": "children", "title": "Gummistiefel", "size": "104"})
    assert response.status_code == 200 and not Listing.objects.exists()


@pytest.mark.django_db
@pytest.mark.parametrize("title, ok", [
    ("Vesperdose", True),
    ("Trinkflasche", True),
    ("Stoffwindeln", True),
    ("Kinderrucksack", True),
    ("Kindersnowboard", True),
    ("Duplo", True),
    ("Spielfahrzeuge", True),
    ("Ferngesteuertes Fahrzeug", True),
    ("Tonpapier", True),
    ("Ausmalbuch", True),
    ("Zirkel", True),
    ("Schnittschutzhandschuhe", True),
    ("Spielkonsole", True),
    ("Kinderhandy", True),
    ("Regenhose Gr. 104, kaum getragen", False),  # the details go into the description
])
def test_childrens_things_only_by_a_name_from_the_vocabulary(title, ok):
    anna = _user("anna")
    response = _client_for(anna).post(reverse("gifts:create"), {"type": "offer", "kind": "children", "title": title})
    assert (response.status_code == 302) is ok


@pytest.mark.django_db
def test_recognizing_while_typing_tells_the_sizes():
    data = Client().get(reverse("gifts:api-recognize"), {"kind": "children", "title": "Gummistiefel"}).json()
    assert data["sizes"] == list(Listing.SHOE_SIZES)
    assert Client().get(reverse("gifts:api-recognize"), {"kind": "children", "title": "Laufrad"}).json()["sizes"] == []


@pytest.mark.django_db
@pytest.mark.parametrize("offered, wished, fits", [
    (104, 104, True),
    (110, 104, True),  # to grow into
    (116, 104, False),
    (98, 104, False),  # too small
    (None, 104, True),
    (104, None, True),
])
def test_a_wish_for_outdoor_clothes_finds_rain_trousers_in_its_size(offered, wished, fits):
    anna, ben = _user("anna"), _user("ben")
    wish = _kids(anna, "Outdoorkleidung", type="wish", size=wished)
    match(_kids(ben, "Regenhose", size=offered), notify=False)
    assert [s.own for s in anna.suggestions.all()] == ([wish] if fits else [])


@pytest.mark.django_db
def test_shoe_sizes_fit_one_bigger():
    assert Listing.sizes_fit(28, 27) and Listing.sizes_fit(27, 27)
    assert not Listing.sizes_fit(29, 27) and not Listing.sizes_fit(26, 27)
    # Clothes never fit shoes
    assert not Listing.sizes_fit(104, 27)


@pytest.mark.django_db
def test_childrens_things_can_be_lent():
    anna = _user("anna")
    _client_for(anna).post(reverse("gifts:create"), {"type": "offer", "kind": "children", "title": "Kinderski", "lend": "on"})
    assert Listing.objects.get().lend


@pytest.mark.django_db
@pytest.mark.parametrize("title, slug", [
    # Named for grown-ups too: an "other" listing stays a grown-up's thing
    ("Handy", "phone"),
    ("Schnitzwerkzeug", "carving-tools"),
    ("Papier", "paper"),
    # Only children have these
    ("Lego Duplo", "kids-duplo"),
    ("Schere", "kids-scissors"),
])
def test_other_things_and_childrens_things_named_alike(title, slug):
    assert Listing.objects.create(owner=_user("anna"), title=title, type="offer", kind=Listing.KIND_OTHER).thing.slug == slug
