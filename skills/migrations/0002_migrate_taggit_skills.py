"""
Data migration: convert existing django-taggit skill tags on User and Community
into proper Skill / UserSkill / CommunitySkill records.

Taggit stores its through-table differently for each model:
  - User.skills  uses the generic taggit_taggit_taggeditem table (GenericForeignKey)
  - Community.skills uses the custom communities_taggedskills through table
"""
from django.db import migrations
from django.utils.text import slugify


def migrate_skills_forward(apps, schema_editor):
    Tag             = apps.get_model("taggit",      "Tag")
    TaggedItem      = apps.get_model("taggit",      "TaggedItem")
    TaggedSkills    = apps.get_model("communities", "TaggedSkills")
    User            = apps.get_model("users",       "User")
    Community       = apps.get_model("communities", "Community")
    Skill           = apps.get_model("skills",      "Skill")
    UserSkill       = apps.get_model("skills",      "UserSkill")
    CommunitySkill  = apps.get_model("skills",      "CommunitySkill")
    ContentType     = apps.get_model("contenttypes","ContentType")

    def get_or_create_skill(name):
        name = name.strip()
        slug = slugify(name)
        # handle duplicate slugs by appending a counter
        base_slug, n = slug, 1
        while Skill.objects.filter(slug=slug).exclude(name__iexact=name).exists():
            slug = f"{base_slug}-{n}"; n += 1
        skill, _ = Skill.objects.get_or_create(
            name__iexact=name,
            defaults={"name": name, "slug": slug},
        )
        return skill

    # ── User skills (via generic TaggedItem) ────────────────────────
    user_ct = ContentType.objects.get_for_model(User)
    for ti in TaggedItem.objects.filter(content_type=user_ct).select_related("tag"):
        try:
            user = User.objects.get(pk=ti.object_id)
        except User.DoesNotExist:
            continue
        skill = get_or_create_skill(ti.tag.name)
        UserSkill.objects.get_or_create(user=user, skill=skill)

    # ── Community skills (via custom TaggedSkills through model) ─────
    for ts in TaggedSkills.objects.select_related("tag", "content_object"):
        community = ts.content_object
        if community is None:
            continue
        skill = get_or_create_skill(ts.tag.name)
        CommunitySkill.objects.get_or_create(community=community, skill=skill)


def migrate_skills_backward(apps, schema_editor):
    # Removing new records is safe; taggit data is untouched.
    apps.get_model("skills", "UserSkill").objects.all().delete()
    apps.get_model("skills", "CommunitySkill").objects.all().delete()
    apps.get_model("skills", "Skill").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("skills",      "0001_initial"),
        ("users",       "0001_initial"),
        ("communities", "0001_initial"),
        ("taggit",      "0005_auto_20220424_2025"),
        ("contenttypes","0002_remove_content_type_name"),
    ]

    operations = [
        migrations.RunPython(migrate_skills_forward, migrate_skills_backward),
    ]
