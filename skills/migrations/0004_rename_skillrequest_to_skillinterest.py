from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("skills", "0003_skillrequest_wish"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="SkillRequest",
            new_name="SkillInterest",
        ),
        migrations.RenameModel(
            old_name="SkillRequestMessage",
            new_name="SkillInterestMessage",
        ),
        migrations.RenameField(
            model_name="skillinterestmessage",
            old_name="request",
            new_name="interest",
        ),
        # Update related_names (no DB change, keeps migration state correct)
        migrations.AlterField(
            model_name="skillinterest",
            name="from_user",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="skill_interests_sent",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="skillinterest",
            name="user_skill",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="interests",
                to="skills.userskill",
            ),
        ),
        migrations.AlterField(
            model_name="skillinterest",
            name="community_skill",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="interests",
                to="skills.communityskill",
            ),
        ),
        migrations.AlterField(
            model_name="skillinterest",
            name="wish",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="offer_interests",
                to="skills.skillwish",
            ),
        ),
        migrations.AlterField(
            model_name="skillinterestmessage",
            name="sender",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="skill_interest_messages",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterModelOptions(
            name="skillinterest",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Skill Interest",
                "verbose_name_plural": "Skill Interests",
            },
        ),
        migrations.AlterModelOptions(
            name="skillinterestmessage",
            options={
                "ordering": ["created_at"],
                "verbose_name": "Skill Interest Message",
                "verbose_name_plural": "Skill Interest Messages",
            },
        ),
    ]
