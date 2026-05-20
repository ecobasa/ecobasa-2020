def skill_nudge(request):
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    if request.session.get("skill_nudge_dismissed"):
        return {}
    has_skills = (
        request.user.user_skills.exists()
        or request.user.skill_wishes.exists()
    )
    if has_skills:
        return {}
    return {"show_skill_nudge": True}
