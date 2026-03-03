from django import template
from django.db.models import Q
from postman.models import Message

register = template.Library()


def _extract_skills_from_text(text):
    """Return tuple (text_without_skills, [skills...]) by extracting trailing 'Skills: ...' line."""
    if not text:
        return text, []
    import re
    m = re.search(r"Skills:\s*(.+)$", text, flags=re.IGNORECASE | re.DOTALL)
    if not m:
        return text, []
    skills_text = m.group(1).strip()
    cleaned = re.sub(r"\n?Skills:\s*.+$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    skills = [s.strip() for s in re.split(r",\s*", skills_text) if s.strip()]
    return cleaned, skills


@register.simple_tag
def conversation_messages(message):
    """Return queryset of messages in the same thread as `message`, ordered by `sent_at`.

    Behavior:
    - If `message.thread` is set, use that as the thread root.
    - Otherwise treat `message` as the root and include any messages with `thread=message`.
    """
    if not message:
        return Message.objects.none()

    root = getattr(message, "thread", None) or message
    qs = Message.objects.filter(Q(thread=root) | Q(pk=root.pk)).order_by("sent_at")
    return qs


@register.filter(is_safe=True)
def format_message_body(body):
    """Render message body as HTML and format any "Requested stay" block.

    If the body contains a block starting with "Requested stay:", parse
    optional "From <iso-datetime>" and "To <iso-datetime>" lines and
    render them in a small summary box. Falls back to preserving plain
    text (with newlines -> <br>) when parsing fails.
    """
    if not body:
        return ""

    import re
    from django.utils.safestring import mark_safe
    from django.utils import timezone
    from django.utils.formats import date_format
    import datetime

    parts = re.split(r"Requested stay:\s*", body, maxsplit=1)

    skills_list = []

    if len(parts) == 1:
        # no special block; still check for appended Skills: line
        main, skills_list = _extract_skills_from_text(body.strip())
        # preserve whitespace
        html_main = template.defaultfilters.linebreaksbr(template.defaultfilters.force_escape(main))
        html = ["<div class=\"whitespace-pre-wrap\">%s</div>" % html_main]
        # render skills if present
        if skills_list:
            html.append('<h3>Skills</h3><div class="mt-3 text-xs text-secondary flex flex-wrap gap-2">')
            for t in skills_list:
                html.append('<span class="inline-flex items-center bg-secondary text-primary px-3 py-1 rounded-full text-sm font-medium">%s</span>' % template.defaultfilters.force_escape(t))
            html.append('</div>')
        return mark_safe(''.join(html))

    main, stay = parts[0].strip(), parts[1].strip()
    # extract skills from the stay block if present
    stay, skills_list = _extract_skills_from_text(stay)

    # find From and To lines
    from_dt = None
    to_dt = None
    m_from = re.search(r"From\s+(.+)", stay)
    m_to = re.search(r"To\s+(.+)", stay)
    def _parse_iso(s):
        try:
            # Accept common ISO formats from datetime-local input
            dt = datetime.datetime.fromisoformat(s.strip())
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return timezone.localtime(dt)
        except Exception:
            return None

    if m_from:
        from_dt = _parse_iso(m_from.group(1))
    if m_to:
        to_dt = _parse_iso(m_to.group(1))

    # build HTML
    html = []
    if main:
        html.append("<div class=\"whitespace-pre-wrap mb-3\">%s</div>" % (template.defaultfilters.linebreaksbr(template.defaultfilters.force_escape(main))))

    html.append('<div class="p-3 rounded border border-brown bg-secondary bg-opacity-10">')
    html.append('<div class="font-semibold mb-1">Requested stay</div>')
    if from_dt:
        html.append('<div><strong>From:</strong> %s</div>' % date_format(from_dt, 'SHORT_DATETIME_FORMAT'))
    elif m_from:
        html.append('<div><strong>From:</strong> %s</div>' % template.defaultfilters.force_escape(m_from.group(1)))
    if to_dt:
        html.append('<div><strong>To:</strong> %s</div>' % date_format(to_dt, 'SHORT_DATETIME_FORMAT'))
    elif m_to:
        html.append('<div><strong>To:</strong> %s</div>' % template.defaultfilters.force_escape(m_to.group(1)))

    # if no parsed dates, include raw remainder
    if not from_dt and not to_dt and stay:
        html.append('<div class="text-sm text-brown mt-2 whitespace-pre-wrap">%s</div>' % template.defaultfilters.linebreaksbr(template.defaultfilters.force_escape(stay)))

    html.append('</div>')

    # render extracted skills (if any) as pill badges after the main/stay block
    if skills_list:
        html.append('<div class="mt-3 text-xs text-secondary flex flex-wrap gap-2">')
        for t in skills_list:
            html.append('<span class="inline-flex items-center bg-primary text-secondary px-3 py-1 rounded-full text-sm font-medium">%s</span>' % template.defaultfilters.force_escape(t))
        html.append('</div>')

    return mark_safe(''.join(html))


@register.simple_tag
def parse_requested_dates(body):
    """Return a dict with parsed requested-from/to datetimes (ISO and display).

    Usage in template: {% parse_requested_dates part.body as rd %}
    rd will be a dict-like object with keys: from_iso, to_iso, from_display, to_display
    """
    import re
    from django.utils import timezone
    from django.utils.formats import date_format
    import datetime

    result = {"from_iso": "", "to_iso": "", "from_display": "", "to_display": ""}
    if not body:
        return result

    m_from = re.search(r"From\s+(.+)", body)
    m_to = re.search(r"To\s+(.+)", body)

    def _parse_iso(s):
        try:
            dt = datetime.datetime.fromisoformat(s.strip())
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return timezone.localtime(dt)
        except Exception:
            return None

    if m_from:
        dt = _parse_iso(m_from.group(1))
        if dt:
            result["from_iso"] = dt.isoformat()
            result["from_display"] = date_format(dt, "SHORT_DATETIME_FORMAT")
        else:
            result["from_display"] = m_from.group(1).strip()

    if m_to:
        dt = _parse_iso(m_to.group(1))
        if dt:
            result["to_iso"] = dt.isoformat()
            result["to_display"] = date_format(dt, "SHORT_DATETIME_FORMAT")
        else:
            result["to_display"] = m_to.group(1).strip()

    return result


@register.filter(is_safe=False)
def strip_requested_block(body):
    """Remove a trailing 'Requested stay:' block (and following skills) from message body."""
    if not body:
        return ""
    import re
    # Remove 'Requested stay:' and everything that follows it
    cleaned = re.sub(r"Requested stay:\s*.*$", "", body, flags=re.IGNORECASE | re.DOTALL).strip()
    # Also strip any trailing 'Skills: ...' line (in case it's not inside the Requested block)
    cleaned, _ = _extract_skills_from_text(cleaned)
    return cleaned


@register.simple_tag
def extract_skills(body, limit=5):
    """Extract a comma-separated 'Skills: ...' trailing line from the message body and return up to `limit` skills as a list."""
    if not body:
        return []
    _, skills = _extract_skills_from_text(body)
    return skills[:int(limit)]
