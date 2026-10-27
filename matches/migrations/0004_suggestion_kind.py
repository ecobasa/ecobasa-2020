from django.db import migrations, models

SKILL_MODELS = {"userskill", "communityskill", "skillwish"}


def sort_existing(apps, schema_editor):
    """Suggestions about skills (or a project's need for a skill or knowledge) are skills
    ones; the rest, about gifts and a project's materials and tools, gift ones."""
    Suggestion = apps.get_model("matches", "Suggestion")
    Need = apps.get_model("projects", "Need")
    for suggestion in Suggestion.objects.select_related("own_type", "other_type"):
        models_ = {suggestion.own_type.model, suggestion.other_type.model}
        skills = bool(models_ & SKILL_MODELS)
        if "need" in models_ and not skills:
            need_id = suggestion.own_id if suggestion.own_type.model == "need" else suggestion.other_id
            skills = Need.objects.filter(pk=need_id, kind__in=("skill", "knowledge")).exists()
        if skills:
            Suggestion.objects.filter(pk=suggestion.pk).update(kind="skills")


class Migration(migrations.Migration):

    dependencies = [
        ("matches", "0003_suggestion"),
        ("projects", "0004_delete_digestedneed"),
    ]

    operations = [
        migrations.AddField(
            model_name="suggestion",
            name="kind",
            field=models.CharField(choices=[("gift", "Gifts"), ("skills", "Skills")], default="gift", max_length=10),
        ),
        migrations.RunPython(sort_existing, migrations.RunPython.noop),
    ]
