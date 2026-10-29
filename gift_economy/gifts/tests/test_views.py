import pytest

from django.test import Client
from django.shortcuts import reverse
from pytest_django.asserts import assertRedirects

from users.models import User
from ..models import Listing


@pytest.fixture
def user():
    return User.objects.create_user(
        email="max@mustermann.com", password="secret", username="max"
    )


@pytest.fixture
def listings(user):
    return [
        Listing.objects.create(
            title="Test", type="offer", description="testdesc", owner=user
        ),
        Listing.objects.create(
            title="Foobar", type="wish", description="foobardesc", owner=user
        ),
    ]


@pytest.fixture
def listing(user):
    return Listing.objects.create(type="offer", title="test", owner=user)


@pytest.fixture
def user_client(db, user):
    """Return a client logged in as user"""
    client = Client()
    client.login(username=user.email, password="secret")
    return client


@pytest.mark.django_db
class TestSearch:
    def test_get_empty(self, client: Client):
        response = client.get("/gifts/")
        assert response.status_code == 200

    def test_get(self, client: Client, listings: [Listing]):
        """The search shell page itself never renders listing titles directly —
        results are fetched separately by the client via gifts:api-list."""
        response = client.get("/gifts/")
        assert response.status_code == 200

        response = client.get(reverse("gifts:api-list"))
        assert response.status_code == 200
        assert "Test" in str(response.content)
        assert "Foobar" in str(response.content)

    def test_filter_by_type(self, client: Client, listings: [Listing]):
        response = client.get(reverse("gifts:api-list"), {"type": "offer"})
        assert "Test" in str(response.content)
        assert "Foobar" not in str(response.content)

        response = client.get(reverse("gifts:api-list"), {"type": "wish"})
        assert "Test" not in str(response.content)
        assert "Foobar" in str(response.content)

    def test_filter_search(self, client: Client, listings: [Listing]):
        response = client.get(reverse("gifts:api-list"), {"search": "testdesc"})
        assert "Test" in str(response.content)
        assert "Foobar" not in str(response.content)

        response = client.get(reverse("gifts:api-list"), {"search": "foobardesc"})
        assert "Test" not in str(response.content)
        assert "Foobar" in str(response.content)


@pytest.mark.django_db
class TestDetail:
    def test_get(self, client: Client, listing: Listing):
        response = client.get(f"/gifts/{listing.pk}/")
        assert response.status_code == 200
        assert "test" in str(response.content)


@pytest.mark.django_db
class TestCreate:
    def test_get(self, user_client: Client):
        response = user_client.get("/gifts/create/")
        assert response.status_code == 200

    def test_get_unauth(self, client: Client):
        response = client.get("/gifts/create/", follow=True)
        assertRedirects(
            response,
            "/users/login/?next=/gifts/create/",
            status_code=302,
            target_status_code=200,
        )

    def test_post_invalid(self, user_client: Client):
        response = user_client.post("/gifts/create/")
        assert response.status_code == 200
        assert "This field is required." in str(response.content)

    def test_post_valid(self, user_client: Client, user: User):
        response = user_client.post(
            "/gifts/create/",
            {"type": "offer", "title": "new test offer"},
            follow=True,
        )
        assert Listing.objects.count() == 1
        assertRedirects(
            response,
            Listing.objects.get().get_absolute_url(),
            status_code=302,
            target_status_code=200,
        )
        listing = Listing.objects.get()
        assert listing.owner == user
        assert "new test offer" in str(response.content)


@pytest.mark.django_db
class TestEdit:
    def test_get(self, user_client: Client, listing: Listing):
        response = user_client.get(f"/gifts/{listing.pk}/edit/")
        assert response.status_code == 200

    def test_get_unauth(self, client: Client, listing: Listing):
        response = client.get(f"/gifts/{listing.pk}/edit/", follow=True)
        assertRedirects(
            response,
            f"/users/login/?next=/gifts/{listing.pk}/edit/",
            status_code=302,
            target_status_code=200,
        )

    def test_404(self, user_client: Client, listing: Listing):
        response = user_client.get("/gifts/abcdefgh/edit/")
        assert response.status_code == 404

    def test_post_invalid(self, user_client: Client, listing: Listing):
        response = user_client.post(f"/gifts/{listing.pk}/edit/")
        assert response.status_code == 200
        assert "This field is required." in str(response.content)

    def test_post_valid(self, user_client: Client, listing: Listing):
        assert Listing.objects.count() == 1
        response = user_client.post(
            f"/gifts/{listing.pk}/edit/",
            {"type": "offer", "title": "new test offer"},
            follow=True,
        )
        assert Listing.objects.count() == 1
        assertRedirects(
            response,
            Listing.objects.get().get_absolute_url(),
            status_code=302,
            target_status_code=200,
        )
        assert "new test offer" in str(response.content)


@pytest.mark.django_db
class TestDelete:
    def test_404(self, user_client: Client):
        response = user_client.get("/gifts/abcdefgh/delete/")
        assert response.status_code == 404

    def test_get_unauth(self, client: Client, listing: Listing):
        response = client.get(f"/gifts/{listing.pk}/delete/", follow=True)
        assertRedirects(
            response,
            f"/users/login/?next=/gifts/{listing.pk}/delete/",
            status_code=302,
            target_status_code=200,
        )

    def test_get(self, user_client: Client, listing: Listing):
        response = user_client.get(f"/gifts/{listing.pk}/delete/")
        assert response.status_code == 200

    def test_post(self, user_client: Client, listing: Listing):
        response = user_client.post(f"/gifts/{listing.pk}/delete/", follow=True)
        assertRedirects(
            response,
            reverse("gifts:mine"),
            status_code=302,
            target_status_code=200,
        )
        assert Listing.objects.all().exists() == False
        # assert "deleted" in str(response.content)


@pytest.mark.django_db
def test_map_popup_on_detail_page_escapes_the_title(client, user):
    """The popup is set with innerHTML: escapejs alone keeps "<" (as \\u003C, which is "<"
    again at runtime), so the title has to be HTML-escaped first."""
    from django.contrib.gis.geos import Point
    listing = Listing.objects.create(
        type="offer", owner=user, title="<img src=x onerror=alert(1)>",
        location_name="<b>here</b>", location=Point(14.98, 51.16, srid=4326),
    )
    content = client.get(reverse("gifts:detail", args=[listing.pk])).content.decode()
    popup = content[content.index("popupEl.innerHTML"):]
    popup = popup[:popup.index(";")]
    assert "\\u003Cimg" not in popup and "\\u0026lt\\u003Bimg" in popup
    assert "\\u003Cb\\u003E" not in popup


@pytest.mark.django_db
def test_listing_with_an_amount(user_client, user):
    response = user_client.post(reverse("gifts:create"), {
        "type": "offer", "title": "Clay", "quantity": "50", "unit": "kg", "description": "",
    })
    listing = Listing.objects.get(title="Clay")
    assert response.status_code == 302 and (listing.quantity, listing.unit) == (50, "kg")
    assert listing.amount == "50 kg"
    assert "50 kg" in user_client.get(reverse("gifts:detail", args=[listing.pk])).content.decode()


@pytest.mark.django_db
def test_list_card_names_the_giver_not_the_viewer(user, listing):
    viewer = User.objects.create_user(email="viewer@example.com", password="x", name="Vera")
    user.name = "Max"
    user.save()
    client = Client()
    client.force_login(viewer)
    content = client.get(reverse("gifts:api-list")).content.decode()
    assert "Max" in content and "Vera" not in content


@pytest.mark.django_db
def test_the_list_leaves_out_your_own_but_the_map_shows_them(user, user_client):
    from django.contrib.gis.geos import Point
    from communities.models import Community
    here = Point(14.9857, 51.1642, srid=4326)
    other = User.objects.create_user(email="other@example.com", password="x", location=here)
    hof = Community.objects.create(name="Hof", owner=user, location=here)
    Listing.objects.create(type="offer", title="Mine", owner=user, location=here)
    Listing.objects.create(type="offer", title="My community's", community=hof)
    Listing.objects.create(type="offer", title="Theirs", owner=other)

    content = user_client.get(reverse("gifts:api-list")).content.decode()
    assert "Theirs" in content and "Mine" not in content and "My community" not in content
    titles = {f["properties"]["title"] for f in user_client.get(reverse("gifts:api-markers")).json()["features"]}
    assert titles == {"Mine", "My community's", "Theirs"}
    # Without signing in, everything
    content = Client().get(reverse("gifts:api-list")).content.decode()
    assert "Theirs" in content and "Mine" in content


@pytest.mark.django_db
def test_back_on_the_form_is_a_link(user_client, listing):
    """It was a <button href=…>, which browsers don't follow."""
    back = '<a class="btn inline-flex items-center text-sm leading-5 font-medium mb-10" href="%s">'
    content = user_client.get(reverse("gifts:edit", args=[listing.pk])).content.decode()
    assert back % reverse("gifts:detail", args=[listing.pk]) in content
    content = user_client.get(reverse("gifts:create")).content.decode()
    assert back % reverse("gifts:search") in content


@pytest.mark.django_db
def test_your_gifts_in_the_dashboard(user_client, user, listings):
    response = user_client.get(reverse("gifts:mine"))
    assert [listing.title for listing in response.context["page"]] == ["Test"]
    assert [(str(t.label), t.count, t.active) for t in response.context["tabs"]] == [
        ("Your offers", 1, True), ("Your wishes", 1, False),
    ]
    assert [listing.title for listing in user_client.get(reverse("gifts:mine"), {"box": "wish"}).context["page"]] == ["Foobar"]
    assert reverse("gifts:create") in response.content.decode()


@pytest.mark.django_db
def test_a_persons_gifts_name_their_community(user, user_client, listing):
    from django.contrib.gis.geos import Point
    from communities.models import Community
    here = Point(14.9857, 51.1642, srid=4326)
    user.name, user.location = "Max", here
    user.save()
    Community.objects.create(name="Hof Sonnenschein", owner=user, location=here)

    assert "Hof Sonnenschein" in Client().get(reverse("gifts:api-list")).content.decode()
    props = user_client.get(reverse("gifts:api-markers")).json()["features"][0]["properties"]
    assert props["user_name"] == "Max" and props["member_of"] == "Hof Sonnenschein"
    # Who it is only for members
    props = Client().get(reverse("gifts:api-markers")).json()["features"][0]["properties"]
    assert props["user_name"] == "" and props["member_of"] == ""


@pytest.mark.django_db
class TestAPersonsPlace:
    """Others see a person's place only about (users.places), on the map, in the list and
    on the detail page, and no search finds out more; a community's stays exact."""

    @pytest.fixture
    def home(self):
        from django.contrib.gis.geos import Point
        return Point(13.06213, 52.39887, srid=4326)

    @pytest.fixture
    def offer(self, user, home):
        user.location, user.location_name = home, "Lindenweg 7, 14467 Potsdam, Deutschland"
        user.save()
        return Listing.objects.create(type="offer", title="Wheelbarrow", owner=user)

    def test_map_shows_it_in_its_cell(self, offer, home):
        from users.places import approximate
        x, y = Client().get(reverse("gifts:api-markers")).json()["features"][0]["geometry"]["coordinates"]
        shown = approximate(home, offer.owner_id)
        assert (x, y) == pytest.approx((shown.x, shown.y)) and (x, y) != (home.x, home.y)

    def test_a_small_map_section_around_it_finds_nothing(self, offer, home):
        from users.places import CELL
        # Around the exact place, but not around its cell's centre
        centre_x, centre_y = round(home.x / CELL) * CELL, round(home.y / CELL) * CELL
        assert abs(home.x - centre_x) > 0.001 or abs(home.y - centre_y) > 0.001
        bbox = f"{home.x - 0.0005},{home.y - 0.0005},{home.x + 0.0005},{home.y + 0.0005}"
        assert Client().get(reverse("gifts:api-markers"), {"bbox": bbox}).json()["features"] == []
        bbox = f"{centre_x - 0.0005},{centre_y - 0.0005},{centre_x + 0.0005},{centre_y + 0.0005}"
        assert len(Client().get(reverse("gifts:api-markers"), {"bbox": bbox}).json()["features"]) == 1

    def test_distance_is_to_its_cell(self, offer, home):
        from users.places import CELL
        centre = (round(home.y / CELL) * CELL, round(home.x / CELL) * CELL)
        response = Client().get(reverse("gifts:api-list"), {"location": f"{centre[0]},{centre[1]}"})
        listing = response.context["listings"][0]
        assert listing.distance.km < 0.01
        content = response.content.decode()
        assert "0.0 km" in content and "Potsdam, Deutschland" in content and "Lindenweg" not in content

    def test_detail_shows_it_about_to_others_and_exactly_to_its_owner(self, offer, home, user_client):
        content = Client().get(offer.get_absolute_url()).content.decode()
        assert "Lindenweg" not in content and str(home.x) not in content and "Potsdam, Deutschland" in content
        content = user_client.get(offer.get_absolute_url()).content.decode()
        assert "Lindenweg 7" in content and str(home.x) in content

    def test_a_communitys_is_rough_too_unless_public(self, user, home):
        from communities.models import Community
        from users.places import approximate
        community = Community.objects.create(name="Hof Lindenblüte", owner=user, location=home)
        Listing.objects.create(type="offer", title="Seeds", community=community)
        coordinates = lambda: Client().get(reverse("gifts:api-markers")).json()["features"][0]["geometry"]["coordinates"]
        shown = approximate(home, community.place_seed)
        assert coordinates() == pytest.approx([shown.x, shown.y])
        community.location_public = True
        community.save()
        assert coordinates() == pytest.approx([home.x, home.y])

    def test_its_own_place_exactly_if_nobody_lives_there(self, offer, user):
        from django.contrib.gis.geos import Point
        tree = Point(13.1, 52.41, srid=4326)
        offer.location, offer.location_name, offer.location_public = tree, "Am Obstweg, Potsdam, Deutschland", True
        offer.save()
        x, y = Client().get(reverse("gifts:api-markers")).json()["features"][0]["geometry"]["coordinates"]
        assert (x, y) == pytest.approx((tree.x, tree.y))
        assert Client().get(offer.get_absolute_url()).context["place_is_exact"]
        # Not public: roughly, like any other
        offer.location_public = False
        offer.save()
        assert not Client().get(offer.get_absolute_url()).context["place_is_exact"]

    def test_the_form_asks_for_it_only_with_a_place_of_its_own(self, offer, user_client):
        content = user_client.get(reverse("gifts:edit", args=[offer.pk])).content.decode()
        assert 'name="location_public"' in content and "own: false" in content


@pytest.mark.django_db
class TestPublicGood:
    """Something found out there: nobody asks for it, every member may edit it, and its
    place is exact."""

    @pytest.fixture
    def tree(self, user):
        from django.contrib.gis.geos import Point
        return Listing.objects.create(
            type="offer", title="Plum tree", owner=user, public_good=True,
            location=Point(13.1, 52.41, srid=4326), location_name="Am Obstweg, Potsdam, Deutschland",
        )

    @pytest.fixture
    def other_client(self, db):
        other = User.objects.create_user(email="ola@example.com", password="secret", username="ola")
        client = Client()
        client.force_login(other)
        return client

    def test_nobody_asks_for_it_and_every_member_may_edit_it(self, tree, other_client):
        response = other_client.get(tree.get_absolute_url())
        assert "Express Interest" not in response.content.decode() and "Public good" in response.content.decode()
        assert response.context["can_edit"] and not response.context["is_owner"]
        assert response.context["place_is_exact"]
        assert other_client.get(reverse("gifts:edit", args=[tree.pk])).status_code == 200
        other_client.post(reverse("gifts:delete", args=[tree.pk]))
        assert not Listing.objects.filter(pk=tree.pk).exists()

    def test_visitors_cant_edit_it(self, tree):
        assert Client().get(reverse("gifts:edit", args=[tree.pk])).status_code == 302

    def test_its_place_is_required_and_exact(self, user_client):
        data = {"type": "offer", "kind": "other", "title": "Firewood", "public_good": "on"}
        response = user_client.post(reverse("gifts:create"), data)
        assert response.context["form"].errors["public_good"] == ["Set on the map where it is found."]
        user_client.post(reverse("gifts:create"), {**data, "location": "POINT (13.2 52.4)"})
        firewood = Listing.objects.get(title="Firewood")
        assert firewood.public_good and firewood.location_public and firewood.place_is_public

    def test_only_offers(self, user_client):
        user_client.post(reverse("gifts:create"), {
            "type": "wish", "kind": "other", "title": "Bench", "public_good": "on", "location": "POINT (13.2 52.4)",
        })
        assert not Listing.objects.get(title="Bench").public_good


@pytest.mark.django_db
def test_the_form_has_one_place_field(user_client):
    """The map writes into the first one, the server took the last: with two, its own
    place was never saved."""
    content = user_client.get(reverse("gifts:create")).content.decode()
    assert content.count('name="location"') == 1 and content.count('name="location_name"') == 1
