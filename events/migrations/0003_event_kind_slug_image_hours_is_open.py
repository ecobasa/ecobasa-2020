from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0002_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="kind",
            field=models.CharField(
                choices=[("project", "Project"), ("community_event", "Community event")],
                default="project",
                max_length=20,
                verbose_name="Kind",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="slug",
            field=models.SlugField(blank=True, max_length=255, verbose_name="Slug"),
        ),
        migrations.AddField(
            model_name="event",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="events-images", verbose_name="image"),
        ),
        migrations.AddField(
            model_name="event",
            name="starts_at",
            field=models.TimeField(blank=True, null=True, verbose_name="Starts at"),
        ),
        migrations.AddField(
            model_name="event",
            name="ends_at",
            field=models.TimeField(blank=True, null=True, verbose_name="Ends at"),
        ),
        migrations.AddField(
            model_name="event",
            name="is_open",
            field=models.BooleanField(
                default=False,
                help_text="Otherwise people ask first and you answer, like for a volunteer stay.",
                verbose_name="Open event: people can just come",
            ),
        ),
        migrations.AlterField(
            model_name="event",
            name="ends_on",
            field=models.DateField(
                blank=True,
                help_text="Leave empty if it is ongoing, without an end date.",
                null=True,
                verbose_name="Until",
            ),
        ),
        migrations.AddConstraint(
            model_name="event",
            constraint=models.UniqueConstraint(
                fields=("community", "slug"), name="one_event_slug_per_community"
            ),
        ),
    ]
