from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .models import Notification


@login_required
def notification_list(request):
    notifications = request.user.notifications.select_related("actor").all()[:50]
    request.user.notifications.filter(is_read=False).update(is_read=True)
    return render(request, "notifications/list.html", {"notifications": notifications})


@login_required
def recent_json(request):
    """HTMX / fetch endpoint: last 8 notifications with unread count."""
    qs = request.user.notifications.select_related("actor").all()[:8]
    data = [
        {
            "id":         n.pk,
            "verb":       n.verb,
            "link":       n.link,
            "is_read":    n.is_read,
            "actor":      n.actor.name or n.actor.email if n.actor else None,
            "created_at": n.created_at.isoformat(),
        }
        for n in qs
    ]
    return JsonResponse({
        "notifications": data,
        "unread": request.user.notifications.filter(is_read=False).count(),
    })


@login_required
@require_POST
def mark_all_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    next_url = request.POST.get("next") or request.META.get("HTTP_REFERER") or "/"
    return redirect(next_url)
