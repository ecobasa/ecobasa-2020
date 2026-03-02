from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseForbidden
from django.urls import reverse

from postman.views import MessageView
from postman.models import Message, STATUS_ACCEPTED


def message_view_wrapper(request, message_id):
    """Delegate GET to MessageView, handle POST as a quick-reply.

    If the installed django-postman MessageView doesn't implement POST,
    accept a POST here and create a reply message directly so users can
    send quick replies from the message detail page without being forwarded
    to the compose page.
    """
    if request.method == "GET":
        return MessageView.as_view()(request, message_id=message_id)

    if request.method == "POST":
        if not request.user.is_authenticated:
            return HttpResponseForbidden()

        original = get_object_or_404(Message, pk=message_id)
        recipient = original.sender
        if recipient is None:
            return HttpResponse(status=400)

        body = request.POST.get("body", "").strip()
        if not body:
            # nothing to send
            return redirect(request.POST.get("next", reverse("postman:inbox")))

        # Create a reply message. Use STATUS_ACCEPTED so it appears immediately.
        reply_subject = request.POST.get("subject") or ("Re: " + (original.subject or ""))
        # Determine thread root: use original.thread if present, else the original message
        root = original.thread if getattr(original, "thread_id", None) else original
        create_kwargs = dict(
            subject=reply_subject,
            body=body,
            sender=request.user,
            recipient=recipient,
            moderation_status=STATUS_ACCEPTED,
            thread=root,
        )
        # If Message model supports a parent field, set it to original
        try:
            # attempt to set `parent` if available
            create_kwargs["parent"] = original
        except Exception:
            pass
        reply = Message.objects.create(**create_kwargs)

        # Redirect to `next` if provided, otherwise back to inbox
        return redirect(request.POST.get("next", reverse("postman:inbox")))

    return HttpResponse(status=405)
