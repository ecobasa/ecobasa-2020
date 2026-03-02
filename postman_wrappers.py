from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseForbidden
from django.urls import reverse

from postman.views import MessageView
from postman.models import Message, STATUS_ACCEPTED
from postman.views import WriteView
from django.http import QueryDict


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


def postman_write_wrapper(request, recipients=None):
    """Wrap django-postman's write view.

    On GET delegate to WriteView. On POST, if the sender is authenticated
    and provided stay fields, append the sender's skills to the message body
    before delegating to the original WriteView. This avoids trusting client
    hidden inputs for skills.
    """
    # delegate GET directly
    if request.method == "GET":
        return WriteView.as_view()(request, recipients=recipients) if recipients else WriteView.as_view()(request)

    if request.method == "POST":
        # if sender authenticated and this looks like a volunteer request, append skills
        try:
            user = request.user
            is_volunteer = bool(request.POST.get('stay_from') or request.POST.get('stay_to') or (request.POST.get('subject') and 'Request volunteering stay' in request.POST.get('subject')))
            if user.is_authenticated and is_volunteer:
                # prefer posted sender_skills (user-edited) if provided, else fallback to stored tags
                posted = (request.POST.get('sender_skills') or '').strip()
                if posted:
                    skills_list = posted
                else:
                    try:
                        skills_qs = getattr(user, 'skills').all()
                        skills_list = ', '.join([t.name for t in skills_qs])
                    except Exception:
                        skills_list = ''

                if skills_list:
                    new_post = request.POST.copy()
                    body = new_post.get('body', '') or ''
                    # append skills block
                    body = body + "\n\nSkills: " + skills_list
                    new_post['body'] = body
                    # replace request._post so downstream view sees modified data
                    request._post = new_post
        except Exception:
            # best-effort: if anything fails, continue to delegate
            pass

        return WriteView.as_view()(request, recipients=recipients) if recipients else WriteView.as_view()(request)

    return HttpResponse(status=405)
