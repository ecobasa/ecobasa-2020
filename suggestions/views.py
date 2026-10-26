from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.contrib import messages
from django.views.decorators.http import require_POST

from dashboard_lists import paginate

from .emails import read_unsubscribe_token
from .models import Suggestion


@login_required
def suggestion_list(request):
    """What fits their wishes, offers and skills, newest first. Opening the page marks
    the new ones as seen."""
    suggestions = (
        request.user.suggestions.filter(dismissed_at=None)
        .select_related("own_type", "other_type", "other_user")
        .prefetch_related("own", "other")
    )
    page = paginate(request, suggestions)
    # Things deleted since are left out (their suggestions go with them, this is a safety net)
    items = [s for s in page.object_list if s.other is not None and s.own is not None]
    new_ids = {s.pk for s in items if s.seen_at is None}
    request.user.suggestions.filter(seen_at=None).update(seen_at=timezone.now())
    return render(request, "suggestions/suggestion_list.html", {
        "page": page, "suggestions": items, "new_ids": new_ids,
    })


@login_required
@require_POST
def dismiss(request, pk):
    suggestion = get_object_or_404(Suggestion, pk=pk, user=request.user)
    suggestion.dismissed_at = timezone.now()
    suggestion.save(update_fields=["dismissed_at"])
    return redirect("suggestions:list")


def unsubscribe(request, token):
    """One click from the weekly email turns it off, no login needed."""
    try:
        pk = read_unsubscribe_token(token)
    except signing.BadSignature:
        return HttpResponseBadRequest("Invalid link.")
    get_user_model().objects.filter(pk=pk).update(match_emails=False)
    messages.success(request, _(
        "You won't get emails about matches any more. You can turn them on again in your profile."
    ))
    return redirect("homepage:homepage")
