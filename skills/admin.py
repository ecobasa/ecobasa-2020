from django.contrib import admin
from .models import Skill, UserSkill, CommunitySkill


class UserSkillInline(admin.TabularInline):
    model = UserSkill
    extra = 0
    fields = ("user", "level", "available", "description")
    raw_id_fields = ("user",)


class CommunitySkillInline(admin.TabularInline):
    model = CommunitySkill
    extra = 0
    fields = ("community", "description")
    raw_id_fields = ("community",)


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display  = ("name", "slug", "user_count", "community_count")
    search_fields = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [UserSkillInline, CommunitySkillInline]

    @admin.display(description="Users")
    def user_count(self, obj):
        return obj.user_skills.count()

    @admin.display(description="Communities")
    def community_count(self, obj):
        return obj.community_skills.count()


@admin.register(UserSkill)
class UserSkillAdmin(admin.ModelAdmin):
    list_display  = ("user", "skill", "level", "available", "created_at")
    list_filter   = ("level", "available")
    search_fields = ("user__name", "user__email", "skill__name")
    raw_id_fields = ("user",)


@admin.register(CommunitySkill)
class CommunitySkillAdmin(admin.ModelAdmin):
    list_display  = ("community", "skill", "created_at")
    search_fields = ("community__name", "skill__name")
    raw_id_fields = ("community",)
