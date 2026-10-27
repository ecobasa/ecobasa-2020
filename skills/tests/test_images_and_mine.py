import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image

from skills.models import Skill, SkillWish, UserSkill
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
    from skills.models import SkillTaxonomy, get_or_create_skill
    SkillTaxonomy.objects.create(slug="test-carpentry", names={"en": "Test Carpentry"})
    us = UserSkill.objects.create(user=user, skill=get_or_create_skill(slug="test-carpentry")[0], level="advanced")
    response = client_.post(us.get_edit_url(), {
        "skill_name": "Test Carpentry", "skill_taxonomy_data": '{"slug": "test-carpentry"}',
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
        "skill_name": "Test Carpentry", "skill_taxonomy_data": '{"slug": "test-carpentry"}',
        "image": SimpleUploadedFile("x.png", b"nope", content_type="image/png"),
    })
    assert response.status_code == 200 and "image" in response.context["form"].errors


@pytest.mark.django_db
def test_your_skills_in_the_dashboard(user, client_):
    from django.contrib.contenttypes.models import ContentType
    from references.models import Reference

    us = UserSkill.objects.create(user=user, skill=Skill.objects.create(name="Carpentry"), description="Tables")
    other = User.objects.create_user(email="o@example.com", password="x")
    Reference.objects.create(author=other, recipient=user, text="Lovely table",
                             content_type=ContentType.objects.get_for_model(UserSkill), object_id=str(us.pk))
    SkillWish.objects.create(user=user, skill=Skill.objects.create(name="Welding"))

    response = client_.get(reverse("skills:mine"))
    assert [(s.skill.name, s.reference_count) for s in response.context["skills"]] == [("Carpentry", 1)]
    content = response.content.decode()
    assert f"{us.get_absolute_url()}#references" in content and us.get_edit_url() in content
    assert [(str(t.label), t.count) for t in response.context["tabs"]] == [
        ("Your skills", 1), ("Skills you would like to learn", 1),
    ]
    assert "Welding" in client_.get(reverse("skills:mine"), {"box": "wish"}).content.decode()
