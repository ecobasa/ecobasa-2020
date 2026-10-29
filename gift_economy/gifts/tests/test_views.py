import pytest

from django.test import Client
from django.shortcuts import reverse
from pytest_django.asserts import assertRedirects

from users.models import User
from ..models import Listing
from ..testing import need


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
def test_a_persons_gifts_name_their_community(user, listing):
    from django.contrib.gis.geos import Point
    from communities.models import Community
    here = Point(14.9857, 51.1642, srid=4326)
    user.name, user.location = "Max", here
    user.save()
    Community.objects.create(name="Hof Sonnenschein", owner=user, location=here)

    assert "Hof Sonnenschein" in Client().get(reverse("gifts:api-list")).content.decode()
    props = Client().get(reverse("gifts:api-markers")).json()["features"][0]["properties"]
    assert props["user_name"] == "Max" and props["member_of"] == "Hof Sonnenschein"


@pytest.mark.django_db
@pytest.mark.parametrize("kind", ["knowledge", "hands"])
def test_knowledge_and_helping_hands_have_no_amount(user_client, kind):
    user_client.post(reverse("gifts:create"), {
        "type": "offer", "kind": kind, "title": "Rocket stove advice", "quantity": "3", "unit": "kg",
    })
    listing = Listing.objects.get(title="Rocket stove advice")
    assert listing.quantity is None and listing.unit == ""


@pytest.mark.django_db
def test_a_projects_helping_hands_keep_their_amount(user, user_client):
    from communities.models import Community
    from projects.models import Project
    project = Project.objects.create(community=Community.objects.create(name="Hof Sonnenschein", owner=user), title="Roof")
    hands = need(project, kind=Listing.KIND_HANDS, title="Roofers", quantity=2, unit="people")
    user_client.post(reverse("gifts:edit", args=[hands.pk]), {
        "type": "wish", "kind": "hands", "title": "Roofers", "quantity": "3", "unit": "people",
    })
    hands.refresh_from_db()
    assert hands.quantity == 3 and hands.unit == "people"
