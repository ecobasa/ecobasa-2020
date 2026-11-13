import pytest
from django.urls import reverse
from django.utils import translation


@pytest.mark.django_db
def test_the_help_pages_open_and_link_to_each_other(client):
    index = client.get("/help/", HTTP_ACCEPT_LANGUAGE="en")
    assert index.status_code == 200
    assert 'href="/help/community-tours/"' in index.content.decode()
    page = client.get("/help/community-tours/", HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert 'id="join"' in page and 'href="/community-tours/new/"' in page


def test_the_help_url_is_in_the_page_language():
    with translation.override("de"):
        assert reverse("help:tours") == "/hilfe/community-tours/"
    with translation.override("es"):
        assert reverse("help:tours") == "/help/community-tours/"


@pytest.mark.django_db
def test_the_other_languages_spelling_leads_to_the_own(client):
    response = client.get("/help/community-tours/?x=1", HTTP_ACCEPT_LANGUAGE="de")
    assert response.status_code == 302 and response["Location"] == "/hilfe/community-tours/?x=1"
    assert client.get("/hilfe/community-tours/", HTTP_ACCEPT_LANGUAGE="de").status_code == 200
    assert client.get("/hilfe/", HTTP_ACCEPT_LANGUAGE="en")["Location"] == "/help/"


@pytest.mark.django_db
def test_the_menu_and_the_tour_pages_lead_to_help(client):
    assert 'href="/help/"' in client.get("/", HTTP_ACCEPT_LANGUAGE="en").content.decode()
    tours = client.get("/community-tours/", HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert 'href="/help/community-tours/#what"' in tours


@pytest.mark.django_db
def test_the_travelling_tips_are_linked_from_the_tours_help(client):
    page = client.get("/help/community-tours/", HTTP_ACCEPT_LANGUAGE="en").content.decode()
    assert 'href="/help/community-tours/travelling-tips/"' in page
    tips = client.get("/help/community-tours/travelling-tips/", HTTP_ACCEPT_LANGUAGE="en")
    assert tips.status_code == 200 and 'id="sailing"' in tips.content.decode()
