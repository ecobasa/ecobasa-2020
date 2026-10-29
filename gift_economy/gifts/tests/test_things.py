import io

import pytest
from django.core.management import call_command

from users.models import User

from ..models import Listing, Thing, ToolThing, VehicleThing
from ..vocabularies import VOCABULARIES
from ..things import recognize, related


def _slug(title):
    thing_id = recognize(title)
    return Thing.objects.get(pk=thing_id).slug if thing_id else None


@pytest.mark.django_db
@pytest.mark.parametrize("title, slug", [
    ("Two old ladders", "ladder"),
    ("Leitern", "ladder"),
    ("Échelle", "ladder"),
    ("escalera de tijera", "stepladder"),
    ("Handkreissäge Bosch", "circular-saw"),
    ("scie circulaire", "circular-saw"),
    ("Old wood saw", "saw"),
    ("Akkuschrauber Makita 18V", "cordless-drill"),
    ("Brennholz, trocken", "firewood"),
    ("bois de chauffage", "firewood"),
    ("Lehm aus dem Teich", "clay"),
    ("Clay bricks", "brick"),
    ("Ziegelsteine", "brick"),
    ("Tomatenpflanzen", "plant"),
    ("Einmachgläser 30 Stück", "canning-jars"),
    ("IBC Container", "water-tank"),
    ("Hosen", "clothes"),
    ("Gartenschlauch 25m", "garden-hose"),
    ("Sägespäne", "sawdust"),
    ("Kartoffeln", None),
    ("", None),
])
def test_recognizes_things_in_any_language(title, slug):
    assert _slug(title) == slug


@pytest.mark.django_db
def test_the_curated_vocabulary_is_loaded_with_its_broader_things():
    assert Thing.objects.count() == sum(len(entries) for entries in VOCABULARIES.values())
    stepladder = Thing.objects.get(slug="stepladder")
    assert stepladder.parent.slug == "ladder"
    assert stepladder.category.slug == "building-renovation"
    assert stepladder.get_name("de") == "Stehleiter"


@pytest.mark.django_db
def test_broader_and_narrower_things_are_related_but_not_siblings():
    things = {thing.slug: thing.pk for thing in Thing.objects.all()}
    assert related(things["saw"], things["jigsaw"])
    assert related(things["plunge-saw"], things["saw"])
    assert related(things["ladder"], things["ladder"])
    assert not related(things["firewood"], things["timber"])
    assert not related(things["ladder"], None)


@pytest.mark.django_db
def test_a_thing_is_recognized_when_saved():
    owner = User.objects.create_user(email="a@example.com", password="x")
    listing = Listing.objects.create(owner=owner, title="Leiter", type="offer", kind=Listing.KIND_TOOL)
    assert listing.thing.slug == "ladder"
    listing.title = "Kettensäge"
    listing.save()
    assert listing.thing.slug == "chainsaw"
    # Skills, knowledge and helping hands are not things
    listing.kind = Listing.KIND_HANDS
    listing.save()
    assert listing.thing is None


@pytest.mark.django_db
def test_loading_again_recognizes_existing_listings():
    owner = User.objects.create_user(email="a@example.com", password="x")
    listing = Listing.objects.create(owner=owner, title="Schubkarre", type="offer")
    Listing.objects.filter(pk=listing.pk).update(thing=None)
    call_command("load_vocabularies", stdout=io.StringIO())
    listing.refresh_from_db()
    assert listing.thing.slug == "wheelbarrow"


@pytest.mark.django_db
def test_the_listing_shows_what_it_is_recognized_as_in_the_readers_language(client):
    owner = User.objects.create_user(email="a@example.com", password="x")
    listing = Listing.objects.create(owner=owner, title="Leiter, 3 m", type="offer", kind=Listing.KIND_TOOL)
    page = client.get(listing.get_absolute_url(), HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert "Recognized as" in page and "Ladder" in page



@pytest.mark.django_db
def test_each_kind_has_its_own_vocabulary():
    assert ToolThing.objects.filter(slug="ladder").exists()
    assert not ToolThing.objects.filter(slug="cargo-bike").exists()
    assert VehicleThing.objects.get(slug="long-john").parent.slug == "cargo-bike"
    things = {thing.pk: thing.slug for thing in Thing.objects.all()}
    # A tool is looked up among tools, a vehicle among vehicles, other things anywhere
    assert things.get(recognize("Lastenrad", "vehicle")) == "cargo-bike"
    assert recognize("Lastenrad", "tool") is None
    assert things.get(recognize("Lastenrad", "other")) == "cargo-bike"
    assert things.get(recognize("Minibagger", "vehicle")) == "mini-excavator"
    assert things.get(recognize("Kastenanhänger 750 kg", "vehicle")) == "box-trailer"


@pytest.mark.django_db
def test_a_thing_added_to_a_vocabulary_belongs_to_it():
    thing = VehicleThing.objects.create(slug="rickshaw", names={"en": "Rickshaw", "de": "Rikscha"})
    assert Thing.objects.get(pk=thing.pk).kind == "vehicle"
    assert recognize("Rikscha", "vehicle") == thing.pk
