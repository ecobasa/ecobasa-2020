from django.db import migrations, models


class Migration(migrations.Migration):
    """The project email became the matches email: same settings, broader names."""

    dependencies = [
        ("users", "0004_user_project_digest"),
    ]

    operations = [
        migrations.RenameField(model_name="user", old_name="project_digest_radius", new_name="match_radius"),
        migrations.RenameField(model_name="user", old_name="project_digest", new_name="match_emails"),
        migrations.AlterField(
            model_name="user",
            name="match_emails",
            field=models.BooleanField(
                default=True, verbose_name="Email me weekly about new suggestions for my wishes, offers and skills",
            ),
        ),
    ]
