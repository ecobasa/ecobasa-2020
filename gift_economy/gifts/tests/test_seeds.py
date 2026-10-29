import pytest
from django.test import Client
from django.urls import reverse

from gift_economy.matches.matching import match
from users.models import User

from ..models import Listing


def _user(name):
    return User.objects.create_user(email=f"{name}@example.com", password="secret", username=name, name=name.title())


def _client_for(user):
    client = Client()
    client.login(username=user.email, password="secret")
    return client


def _seeds(owner, title, type="offer", **fields):
    return Listing.objects.create(owner=owner, title=title, type=type, kind=Listing.KIND_SEEDS, **fields)


@pytest.mark.django_db
def test_offering_seeds_with_variety_year_and_open_pollinated():
    anna = _user("anna")
    response = _client_for(anna).post(reverse("gifts:create"), {
        "type": "offer", "kind": "seeds", "title": "Tomate", "variety": "Ochsenherz", "harvest_year": "2025",
        "open_pollinated": "on", "quantity": "5", "unit": "packets",
    })
    assert response.status_code == 302
    seeds = Listing.objects.get()
    assert (seeds.variety, seeds.harvest_year, seeds.open_pollinated) == ("Ochsenherz", 2025, True)
    assert seeds.thing.slug == "beefsteak-tomato"  # the variety names the type
    assert seeds.display_title == "Tomate ‘Ochsenherz’"
    assert seeds.amount == "5 packets" and seeds.kind_label == "Seeds"
    page = Client().get(seeds.get_absolute_url(), HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert "Harvested 2025" in page and "Open-pollinated" in page


@pytest.mark.django_db
def test_seed_details_only_for_seeds():
    anna = _user("anna")
    _client_for(anna).post(reverse("gifts:create"), {
        "type": "offer", "kind": "material", "title": "Bohnen", "variety": "Borlotti", "harvest_year": "2025",
    })
    beans = Listing.objects.get()
    assert (beans.variety, beans.harvest_year) == ("", None)
    assert beans.thing is None  # beans to eat aren't seeds


@pytest.mark.django_db
def test_a_wish_for_a_crop_finds_its_varieties_and_not_food():
    anna, ben = _user("anna"), _user("ben")
    _seeds(anna, "Tomatensamen", type="wish")
    _seeds(anna, "Bohnen", type="wish")
    offer = _seeds(ben, "Ochsenherz")
    match(offer, notify=False)
    match(Listing.objects.create(owner=ben, title="Bohnen", type="offer", kind=Listing.KIND_MATERIAL), notify=False)
    match(_seeds(ben, "Stangenbohne", variety="Borlotti"), notify=False)
    assert sorted((str(s.own), str(s.other), s.reason) for s in anna.suggestions.all()) == [
        ("Bohnen", "Stangenbohne ‘Borlotti’", "thing"),
        ("Tomatensamen", "Ochsenherz", "thing"),
    ]


@pytest.mark.django_db
def test_seed_vocabulary_in_the_admin():
    from ..models import SeedThing
    assert SeedThing.objects.get(slug="beefsteak-tomato").parent.slug == "tomato"
    assert SeedThing.objects.filter(slug="phacelia").exists()
    assert not SeedThing.objects.filter(slug="ladder").exists()


@pytest.mark.django_db
def test_seeds_find_their_climate_from_their_place():
    from datetime import date
    from django.contrib.gis.geos import Point
    anna = _user("anna")
    anna.location = Point(15.62, 48.52, srid=4326)  # Schiltern, Lower Austria
    anna.save()
    seeds = _seeds(anna, "Paradeiser", variety="Kremser Perle", harvest_year=date.today().year - 3)
    assert (seeds.koppen, seeds.climate, seeds.climate_name) == ("Cfb", Listing.CLIMATE_TEMPERATE, "Temperate")
    assert seeds.latitude_display == "49° N" and seeds.seed_age == 3
    page = Client().get(seeds.get_absolute_url(), HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert "3 years old" in page and "Temperate" in page and "Cfb" in page
    # Its own place: where the mother plant grew
    seeds.location = Point(-9.14, 38.72, srid=4326)  # Lisbon
    assert (seeds.koppen, seeds.climate) == ("Csa", Listing.CLIMATE_MEDITERRANEAN)
    # Only seeds have a climate
    tool = Listing.objects.create(owner=anna, title="Leiter", type="offer", kind=Listing.KIND_TOOL)
    assert tool.climate == ""


@pytest.mark.django_db
def test_seeds_are_suggested_by_climate_not_latitude():
    """The highlands of Bogotá are temperate like Vienna; Lisbon is closer but mediterranean."""
    from django.contrib.gis.geos import Point
    wisher = User.objects.create_user(email="w@example.com", password="x", location=Point(16.37, 48.21, srid=4326), match_global=True)
    _seeds(wisher, "Tomate", type="wish")
    for name, place in [
        ("bogota", Point(-74.07, 4.71, srid=4326)),  # Cfb
        ("moscow", Point(37.62, 55.76, srid=4326)),  # Dfb: a neighbouring zone
        ("lisbon", Point(-9.14, 38.72, srid=4326)),  # Csa
        ("manaus", Point(-60.02, -3.12, srid=4326)),  # Af
        ("unknown", None),  # no place: it may fit
    ]:
        giver = User.objects.create_user(email=f"{name}@example.com", password="x", location=place, match_global=True)
        match(_seeds(giver, f"Tomate {name}"), notify=False)
    assert sorted(str(s.other) for s in wisher.suggestions.all()) == ["Tomate bogota", "Tomate moscow", "Tomate unknown"]


def test_koppen_classes_have_their_zones():
    assert Listing.climate_for_koppen("Cwb") == Listing.CLIMATE_TEMPERATE  # Bogotá, Addis Ababa
    assert Listing.climate_for_koppen("Cfb") == Listing.CLIMATE_TEMPERATE  # Central Europe
    assert Listing.climate_for_koppen("Dfb") == Listing.CLIMATE_CONTINENTAL
    assert Listing.climate_for_koppen("Csa") == Listing.CLIMATE_MEDITERRANEAN
    assert Listing.climate_for_koppen("XYZ") == ""
    assert all(zone in dict(Listing.CLIMATE_CHOICES) for zone in Listing.KOPPEN)
    # Neighbours both ways
    assert all(a in Listing.CLIMATE_FITS[b] for a, zones in Listing.CLIMATE_FITS.items() for b in zones)


@pytest.mark.django_db
def test_a_cargo_bike_wish_finds_an_electric_one_too():
    """An upgrade is always welcome: narrower things fit the broader wish."""
    anna, ben = _user("anna"), _user("ben")
    Listing.objects.create(owner=anna, title="Lastenrad", type="wish", kind=Listing.KIND_VEHICLE, lend=True)
    offer = Listing.objects.create(owner=ben, title="E-Lastenrad", type="offer", kind=Listing.KIND_VEHICLE, lend=True)
    match(offer, notify=False)
    assert [(str(s.own), str(s.other), s.reason) for s in anna.suggestions.all()] == [("Lastenrad", "E-Lastenrad", "thing")]


@pytest.mark.parametrize("place, lat, lon, koppen", [
    ("Vienna", 48.21, 16.37, "Cfb"),
    ("Bogotá", 4.71, -74.07, "Cfb"),
    ("Quito", -0.18, -78.47, "Cfb"),
    ("Addis Ababa", 9.03, 38.74, "Cwb"),
    ("Lisbon", 38.72, -9.14, "Csa"),
    ("Manaus", -3.12, -60.02, "Af"),
    ("Cairo", 30.04, 31.24, "BWh"),
    ("Moscow", 55.76, 37.62, "Dfb"),
    ("Tromsø", 69.65, 18.96, "Dfc"),
    ("Atlantic", 40.0, -40.0, ""),
])
def test_the_koppen_map(place, lat, lon, koppen):
    from ..climate import koppen_at
    assert koppen_at(lat, lon) == koppen


@pytest.mark.django_db
def test_suggestions_while_typing_come_from_the_vocabulary():
    url = reverse("gifts:api-things")
    def suggest(kind, q, lang):
        return Client().get(url, {"kind": kind, "q": q}, HTTP_ACCEPT_LANGUAGE=lang).json()["results"]
    assert "Tomate" in suggest("seeds", "Tom", "de")
    assert "Tomato" in suggest("seeds", "Tom", "en")
    assert "Paradeiser" in suggest("seeds", "Paradei", "de")  # the Austrian word as typed
    assert suggest("seeds", "Paradei", "de")[0] == "Paradeiser"
    assert "Lastenrad" in suggest("vehicle", "Lasten", "de")
    assert "Tomate" not in suggest("vehicle", "Tom", "de")  # each kind its own vocabulary
    assert suggest("seeds", "T", "de") == []
    # The reader's language first, names starting with it first; no other languages if it fits
    assert suggest("vehicle", "Trans", "de") == ["Transporter", "Transportrad", "Autotransporter"]
    assert suggest("seeds", "Tom", "de")[0] == "Tomate"


@pytest.mark.django_db
@pytest.mark.parametrize("kind, title, ok", [
    ("seeds", "Paradeiser", True),
    ("seeds", "tomate", True),
    ("seeds", "Solanum lycopersicum", True),
    ("seeds", "Mein Lieblingsgemüse", False),
    ("seeds", "Tomatensamen von Oma", False),
    ("vehicle", "Lastenrad", True),
    ("vehicle", "Rakete", False),
    ("tool", "Selbstgebaute Presse", True),  # tools and materials stay free text
])
def test_seeds_and_vehicles_only_by_a_name_from_the_vocabulary(kind, title, ok):
    anna = _user("anna")
    response = _client_for(anna).post(reverse("gifts:create"), {"type": "offer", "kind": kind, "title": title})
    assert (response.status_code == 302) is ok
    if not ok:
        assert "choose one from the suggestions" in response.content.decode()


@pytest.mark.django_db
def test_paradeiser_and_tomatoes_are_the_same_crop():
    """Regional words are other names of the same thing, so they match each other."""
    anna, ben = _user("anna"), _user("ben")
    wish = _seeds(anna, "Tomate", type="wish")
    offer = _seeds(ben, "Paradeiser")
    assert offer.thing == wish.thing and offer.thing.slug == "tomato"
    match(offer, notify=False)
    assert [(str(s.own), str(s.other), s.reason) for s in anna.suggestions.all()] == [("Tomate", "Paradeiser", "thing")]


@pytest.mark.django_db
def test_a_project_needs_a_vehicle_from_the_vocabulary():
    from communities.models import Community
    from projects.forms import NeedForm
    from projects.models import Project
    community = Community.objects.create(name="Hof", owner=_user("anna"))
    project = Project.objects.create(community=community, title="Umzug")
    assert NeedForm({"kind": "vehicle", "title": "Transporter"}, instance=Listing(project=project)).is_valid()
    assert not NeedForm({"kind": "vehicle", "title": "Raumschiff"}, instance=Listing(project=project)).is_valid()


@pytest.mark.django_db
@pytest.mark.parametrize("kind, title, categories", [
    ("seeds", "Tomate", ["seeds-plants"]),
    ("seeds", "Kamille", ["health-body", "seeds-plants"]),  # a medicinal herb
    ("seeds", "Färberwaid", ["clothing-textiles", "seeds-plants"]),  # a dye plant
    ("vehicle", "Lastenrad", ["bikes-vehicles"]),
    ("vehicle", "Wohnmobil", ["camping-travel"]),
])
def test_seeds_and_vehicles_get_their_categories_from_what_they_are(kind, title, categories):
    from ..models import ListingCategory
    anna = _user("anna")
    # A category chosen anyway doesn't count
    chosen = ListingCategory.objects.get(slug="furniture").pk
    _client_for(anna).post(reverse("gifts:create"), {"type": "offer", "kind": kind, "title": title, "categories": [chosen]})
    listing = Listing.objects.get()
    assert sorted(c.slug for c in listing.categories.all()) == categories


@pytest.mark.django_db
def test_tools_and_vehicles_are_counted_in_pieces():
    anna = _user("anna")
    _client_for(anna).post(reverse("gifts:create"), {"type": "offer", "kind": "tool", "title": "Leiter", "quantity": "3", "unit": "kg"})
    ladders = Listing.objects.get()
    assert (ladders.quantity, ladders.unit, ladders.amount) == (3, "", "3")


@pytest.mark.django_db
def test_tools_and_materials_get_their_categories_once_recognized():
    from ..models import ListingCategory
    anna = _user("anna")
    garden = ListingCategory.objects.get(slug="garden-farm").pk
    client = _client_for(anna)
    client.post(reverse("gifts:create"), {"type": "offer", "kind": "tool", "title": "Leiter", "categories": [garden]})
    client.post(reverse("gifts:create"), {"type": "offer", "kind": "material", "title": "Kartoffeln", "categories": [garden]})
    ladder, potatoes = Listing.objects.get(title="Leiter"), Listing.objects.get(title="Kartoffeln")
    assert [c.slug for c in ladder.categories.all()] == ["building-renovation"]  # from the vocabulary
    assert [c.slug for c in potatoes.categories.all()] == ["garden-farm"]  # not recognized: as chosen


@pytest.mark.django_db
def test_what_a_title_is_recognized_as_while_typing():
    url = reverse("gifts:api-recognize")
    def recognized(**params):
        return Client().get(url, params, HTTP_ACCEPT_LANGUAGE="de").json()
    assert recognized(kind="tool", title="Alte Leiter") == {"thing": "Leiter", "categories": ["Bauen & Renovieren"]}
    assert sorted(recognized(kind="seeds", title="Kamille")["categories"]) == ["Gesundheit & Körperpflege", "Saatgut & Pflanzen"]
    assert recognized(kind="seeds", title="Tomatensamen") == {"thing": None, "categories": []}  # seeds: only names from the list
    assert recognized(kind="other", title="Leiter") == {"thing": None, "categories": []}  # other things keep a choice


@pytest.mark.django_db
def test_the_place_starts_from_the_profile_and_stays_with_it_unless_moved():
    from django.contrib.gis.geos import Point
    from communities.models import Community
    anna = _user("anna")
    anna.location, anna.location_name = Point(15.62, 48.52, srid=4326), "Schiltern"
    anna.save()
    client = _client_for(anna)
    form = client.get(reverse("gifts:create")).context["form"]
    assert form.initial["location"] == anna.location and form.initial["location_name"] == "Schiltern"
    hof = Community.objects.create(name="Hof", owner=anna, location=Point(16.37, 48.21, srid=4326), location_name="Wien")
    form = client.get(reverse("gifts:create"), {"community": hof.slug}).context["form"]
    assert form.initial["location_name"] == "Wien"

    # Left as it was: no place of its own, it follows the profile
    client.post(reverse("gifts:create"), {"type": "offer", "kind": "tool", "title": "Leiter",
                                          "location": "SRID=4326;POINT (15.62 48.52)", "location_name": "Schiltern"})
    ladder = Listing.objects.get(title="Leiter")
    assert ladder.location is None and ladder.point == anna.location
    # Moved on the map: its own place
    client.post(reverse("gifts:create"), {"type": "offer", "kind": "tool", "title": "Spaten",
                                          "location": "SRID=4326;POINT (14.99 51.15)", "location_name": "Görlitz"})
    spade = Listing.objects.get(title="Spaten")
    assert spade.location is not None and spade.location_name == "Görlitz"
