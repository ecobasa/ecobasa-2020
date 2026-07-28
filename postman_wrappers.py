from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse, HttpResponseForbidden
from django.urls import reverse, reverse_lazy

from postman.views import MessageView
from postman.models import Message, STATUS_ACCEPTED
from postman.views import WriteView


class WriteViewToSent(WriteView):
    success_url = reverse_lazy('postman:sent')


class MessageViewWithReply(MessageView):
    """Like MessageView but also shows a reply form when viewing sent messages."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if context.get('form') is None:
            user = self.request.user
            for m in reversed(self.msgs):
                if m.sender == user and m.recipient and not m.recipient_deleted_at:
                    context['form'] = self.form_class(initial=m.quote(*self.formatters))
                    context['reply_to_pk'] = m.pk
                    break
        return context
from django.http import QueryDict
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from users.templatetags.postman_extras import parse_requested_dates
import datetime
from django.utils import timezone


def message_view_wrapper(request, message_id):
    """Delegate GET to MessageView, handle POST as a quick-reply.

    If the installed django-postman MessageView doesn't implement POST,
    accept a POST here and create a reply message directly so users can
    send quick replies from the message detail page without being forwarded
    to the compose page.
    """
    if request.method == "GET":
        return MessageViewWithReply.as_view()(request, message_id=message_id)

    if request.method == "POST":
        if not request.user.is_authenticated:
            return HttpResponseForbidden()

        original = get_object_or_404(Message, pk=message_id)
        # reply goes to the other person, regardless of who sent the original
        recipient = original.recipient if original.sender == request.user else original.sender
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
        return WriteViewToSent.as_view()(request, recipients=recipients) if recipients else WriteViewToSent.as_view()(request)

    if request.method == "POST":
        # Normalize a mutable copy and append special metadata (skills, ad id)
        try:
            new_post = request.POST.copy()
            user = request.user

            # Append skills block when this is a volunteer request and user is authenticated
            try:
                is_volunteer = bool(new_post.get('stay_from') or new_post.get('stay_to') or (new_post.get('subject') and 'Request volunteering stay' in new_post.get('subject')))
            except Exception:
                is_volunteer = False

            if user.is_authenticated and is_volunteer:
                posted = (new_post.get('sender_skills') or '').strip()
                if posted:
                    skills_list = posted
                else:
                    try:
                        skills_qs = getattr(user, 'skills').all()
                        skills_list = ', '.join([t.name for t in skills_qs])
                    except Exception:
                        skills_list = ''

                if skills_list:
                    body = new_post.get('body', '') or ''
                    body = body + "\n\nSkills: " + skills_list
                    new_post['body'] = body

            # If an ad id was posted, append it to the body so we can link back later
            try:
                ad_id = (new_post.get('ad_random_id') or '').strip()
                if ad_id:
                    body = new_post.get('body', '') or ''
                    body = body + "\n\nAd-ID: " + ad_id
                    new_post['body'] = body
            except Exception:
                pass

            # replace request._post so downstream view sees modified data
            request._post = new_post
        except Exception:
            # best-effort: if anything fails, continue to delegate
            pass

        return WriteViewToSent.as_view()(request, recipients=recipients) if recipients else WriteViewToSent.as_view()(request)

    return HttpResponse(status=405)


@login_required
def inbox_wrapper(request):
    """Render a server-side sorted inbox.

    Accepts a `sort` GET param with values:
      - sent_desc, sent_asc
      - from_desc, from_asc
      - to_desc, to_asc

    For from/to sorting we parse requested dates from the message body
    (via `parse_requested_dates`) and sort in Python with sensible
    fallbacks (to -> sent_at).
    """
    sort = request.GET.get('sort', 'sent_desc')

    try:
        qs = Message.objects.filter(recipient=request.user)
    except Exception:
        qs = Message.objects.none()

    # simple DB ordering for sent_at
    if sort in ('sent_desc', 'sent_asc'):
        order = '-sent_at' if sort == 'sent_desc' else 'sent_at'
        pm_messages = list(qs.order_by(order))
        # compute whether any message contains requested from/to dates
        has_requested_dates = any(parse_requested_dates(m.body).get('from_iso') or parse_requested_dates(m.body).get('to_iso') for m in pm_messages)
        return render(request, 'postman/inbox.html', {'pm_messages': pm_messages, 'has_requested_dates': has_requested_dates})

    # otherwise we'll sort in Python using parsed requested dates
    msgs = list(qs)

    def to_timestamp(val):
        if not val:
            return None
        if isinstance(val, datetime.datetime):
            dt = val
        else:
            try:
                dt = datetime.datetime.fromisoformat(val)
                if timezone.is_naive(dt):
                    dt = timezone.make_aware(dt, timezone.get_current_timezone())
            except Exception:
                return None
        return dt.timestamp()

    def sort_key(m):
        rd = parse_requested_dates(m.body)
        if sort.startswith('from'):
            # prefer from, then to, then sent
            return to_timestamp(rd.get('from_iso')) or to_timestamp(rd.get('to_iso')) or to_timestamp(m.sent_at)
        if sort.startswith('to'):
            # prefer to, then from, then sent
            return to_timestamp(rd.get('to_iso')) or to_timestamp(rd.get('from_iso')) or to_timestamp(m.sent_at)
        return to_timestamp(m.sent_at)

    reverse = sort.endswith('desc')
    msgs.sort(key=lambda m: (sort_key(m) is None, sort_key(m)), reverse=reverse)

    has_requested_dates = any(parse_requested_dates(m.body).get('from_iso') or parse_requested_dates(m.body).get('to_iso') for m in msgs)

    return render(request, 'postman/inbox.html', {'pm_messages': msgs, 'has_requested_dates': has_requested_dates})
