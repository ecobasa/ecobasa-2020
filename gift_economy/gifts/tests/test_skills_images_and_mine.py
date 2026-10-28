import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image

from gift_economy.gifts.models import Listing
from gift_economy.gifts.testing import skill_offer, skill_wish
from gift_economy.gifts.skills.models import Skill
from users.models import User


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def _photo(name="work.png", size=(2400, 1200)):
    out = io.BytesIO()
    Image.new("RGB", size, "green").save(out, "PNG")
    return SimpleUploadedFile(name, out.getvalue(), content_type="image/png")


@pytest.fixture
def user(db):
    return User.objects.create_user(email="maker@example.com", password="secret", name="Maker", username="maker")


@pytest.fixture
def client_(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_a_skill_can_show_a_photo_of_the_work(user, client_):
    from gift_economy.gifts.skills.models import SkillTaxonomy, get_or_create_skill
    SkillTaxonomy.objects.create(slug="test-carpentry", names={"en": "Test Carpentry"})
    us = skill_offer(user, get_or_create_skill(slug="test-carpentry")[0], level="advanced")
    response = client_.post(us.get_edit_url(), {
        "type": "offer", "kind": "skill", "skill_name": "Test Carpentry",
        "level": "advanced", "description": "Tables", "available": "on", "image": _photo(),
    })
    assert response.status_code == 302, response.content
    us.refresh_from_db()
    assert us.image and us.image.name.endswith(".jpg")
    assert max(Image.open(us.image.path).size) <= 1600  # shrunk
    # On the skill page, and as a small round preview on its pills
    assert us.image.url in client_.get(us.get_absolute_url()).content.decode()
    assert f'<img src="{us.image.url}" alt="" class="inline-block w-5 h-5' in client_.get(user.get_absolute_url()).content.decode()

    # Not a photo: a clear error
    response = client_.post(us.get_edit_url(), {
        "type": "offer", "kind": "skill", "skill_name": "Test Carpentry",
        "image": SimpleUploadedFile("x.png", b"nope", content_type="image/png"),
    })
    assert response.status_code == 200 and "image" in response.context["form"].errors


@pytest.mark.django_db
def test_your_skills_in_the_dashboard(user, client_):
    from django.contrib.contenttypes.models import ContentType
    from gift_economy.references.models import Reference

    us = skill_offer(user, Skill.objects.create(name="Carpentry"), description="Tables")
    Listing.objects.create(owner=user, type="offer", title="Two old scythes")
    other = User.objects.create_user(email="o@example.com", password="x")
    Reference.objects.create(author=other, recipient=user, text="Lovely table",
                             content_type=ContentType.objects.get_for_model(Listing), object_id=str(us.pk))
    skill_wish(user, Skill.objects.create(name="Welding"))

    # Your gifts and wishes, filtered to skills
    response = client_.get(reverse("gifts:mine"), {"what": "skills"})
    assert [(s.display_title, s.reference_count) for s in response.context["page"]] == [("Carpentry", 1)]
    content = response.content.decode()
    assert f"{us.get_absolute_url()}#references" in content and us.get_edit_url() in content
    assert [(str(t.label), t.count) for t in response.context["tabs"]] == [("Your offers", 1), ("Your wishes", 1)]
    assert "Welding" in client_.get(reverse("gifts:mine"), {"what": "skills", "box": "wish"}).content.decode()
    # All your gifts: things and skills
    assert {l.display_title for l in client_.get(reverse("gifts:mine")).context["page"]} == {"Carpentry", "Two old scythes"}
