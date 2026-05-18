from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def notification_list(request):
    notifications = list(request.user.notifications.select_related("actor").all()[:50])
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, "notifications/list.html", {"notifications": notifications})


@login_required
def recent_json(request):
    """HTMX / fetch endpoint: last 7 notifications with unread count and has_more flag."""
    qs = list(request.user.notifications.select_related("actor").all()[:8])
    has_more = len(qs) == 8
    data = [
        {
            "id":         n.pk,
            "verb":       n.verb,
            "link":       n.link,
            "is_read":    n.is_read,
            "tag":        n.tag,
            "actor":      n.actor.name or n.actor.email if n.actor else None,
            "created_at": n.created_at.isoformat(),
        }
        for n in qs[:7]
    ]
    return JsonResponse({
        "notifications": data,
        "has_more":      has_more,
        "unread": request.user.notifications.filter(is_read=False).count(),
    })


@login_required
@require_POST
def mark_all_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url)
