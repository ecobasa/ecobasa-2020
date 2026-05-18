def unread_notifications(request):
    if not request.user.is_authenticated:
        return {"unread_notifications_count": 0, "owned_communities": []}
    from communities.models import Community
    return {
        "unread_notifications_count": request.user.notifications.filter(is_read=False).count(),
        "owned_communities": list(
            Community.objects.filter(owner=request.user).only("name", "slug").order_by("name")
        ),
    }
