from django import template
from django.db.models import Q
from postman.models import Message

register = template.Library()


def _extract_skills_from_text(text):
    """Return tuple (text_without_skills, [skills...]) by extracting a 'Skills: ...' line.
    Does NOT match 'Sender-Skills:' lines. Uses MULTILINE so capture stays on one line."""
    if not text:
        return text, []
    import re
    m = re.search(r"(?<![A-Za-z-])Skills:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        return text, []
    skills_text = m.group(1).strip()
    # Also strip the optional preceding label line (e.g. "Skills I want to learn...:")
    cleaned = re.sub(r"\n?(?:[^\n]+\n)?(?<![A-Za-z-])Skills:\s*.+$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
    skills = [s.strip() for s in re.split(r",\s*", skills_text) if s.strip()]
    return cleaned, skills


def _extract_sender_skills_from_text(text):
    """Return tuple (text_without_sender_skills, [skills...]) by extracting 'Sender-Skills: ...' line
    and the preceding label line (e.g. 'My skills:')."""
    if not text:
        return text, []
    import re
    m = re.search(r"Sender-Skills:\s*(.+)$", text, flags=re.IGNORECASE | re.MULTILINE)
    if not m:
        return text, []
    skills_text = m.group(1).strip()
    # Remove the optional preceding label line + the Sender-Skills line itself
    cleaned = re.sub(r"\n?[^\n]+\nSender-Skills:\s*.+$", "", text, flags=re.IGNORECASE | re.MULTILINE).strip()
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


def _render_skill_pills(skills_list, sender_username):
    """Return HTML for a row of skill pills, linked to the sender's userskill page when they have it,
    falling back to the general skill page, or plain text if the skill isn't in the database."""
    from django.urls import reverse
    from django.db.models import Q
    from skills.models import Skill as SkillModel, UserSkill

    # Case-insensitive slug lookup for all skill names at once
    q = Q()
    for name in skills_list:
        q |= Q(name__iexact=name)
    skill_slugs = {s.name.lower(): s.slug for s in SkillModel.objects.filter(q)}

    # Skills the sender actually has in their profile
    sender_skill_slugs = set()
    if sender_username:
        sender_skill_slugs = set(
            UserSkill.objects.filter(user__username=sender_username)
            .values_list('skill__slug', flat=True)
        )

    html = ['<div class="mt-3 flex flex-wrap gap-2">']
    for name in skills_list:
        slug = skill_slugs.get(name.lower())
        label = template.defaultfilters.force_escape(name)
        if slug and sender_username and slug in sender_skill_slugs:
            url = reverse('skills:userskill_detail', args=[slug, sender_username])
        elif slug:
            url = reverse('skills:skill_detail', args=[slug])
        else:
            url = None
        if url:
            html.append(
                '<a href="%s" class="pill bg-primary hover:opacity-80 transition-opacity">'
                '<i class="fa fa-graduation-cap mr-1"></i>%s</a>' % (url, label)
            )
        else:
            html.append('<span class="pill bg-primary">%s</span>' % label)
    html.append('</div>')
    return ''.join(html)


def _render_sender_skill_pills(skills_list, sender_username):
    """Return HTML for purple sender-skill pills with graduation cap icons."""
    from django.urls import reverse
    from django.db.models import Q
    from skills.models import Skill as SkillModel, UserSkill

    q = Q()
    for name in skills_list:
        q |= Q(name__iexact=name)
    skill_slugs = {s.name.lower(): s.slug for s in SkillModel.objects.filter(q)}

    sender_skill_slugs = set()
    if sender_username:
        sender_skill_slugs = set(
            UserSkill.objects.filter(user__username=sender_username)
            .values_list('skill__slug', flat=True)
        )

    html = [
        '<div class="mt-3">',
        '<div class="font-semibold mb-1 opacity-70">Other skills that I can help with</div>',
        '<div class="flex flex-wrap gap-2">',
    ]
    for name in skills_list:
        slug = skill_slugs.get(name.lower())
        label = template.defaultfilters.force_escape(name)
        if slug and sender_username and slug in sender_skill_slugs:
            url = reverse('skills:userskill_detail', args=[slug, sender_username])
        elif slug:
            url = reverse('skills:skill_detail', args=[slug])
        else:
            url = None
        style = 'background-color:#80143b;color:#fff;'
        if url:
            html.append(
                '<a href="%s" class="pill hover:opacity-80 transition-opacity" style="%s">'
                '<i class="fa fa-graduation-cap mr-1"></i>%s</a>' % (url, style, label)
            )
        else:
            html.append('<span class="pill" style="%s"><i class="fa fa-graduation-cap mr-1"></i>%s</span>' % (style, label))
    html.append('</div></div>')
    return ''.join(html)


@register.simple_tag
def format_message_body(message):
    """Render message body as HTML, formatting skills as linked pills and stay dates as a summary box."""
    body = getattr(message, 'body', None) or message  # accept body string as fallback
    sender_username = None
    if hasattr(message, 'sender') and message.sender:
        sender_username = message.sender.username

    if not body:
        return ""

    import re
    from django.utils.safestring import mark_safe
    from django.utils import timezone
    from django.utils.formats import date_format
    import datetime

    body = re.sub(r"\n?Ad-ID:\s*[A-Za-z0-9-_]+\s*$", "", body, flags=re.IGNORECASE)

    parts = re.split(r"Requested stay:\s*", body, maxsplit=1)

    if len(parts) == 1:
        main = body.strip()
        main, sender_skills_list = _extract_sender_skills_from_text(main)
        main, skills_list = _extract_skills_from_text(main)
        html_main = template.defaultfilters.linebreaksbr(template.defaultfilters.force_escape(main))
        html = ['<div class="whitespace-pre-wrap">%s</div>' % html_main]
        if skills_list:
            html.append(_render_skill_pills(skills_list, sender_username))
        if sender_skills_list:
            html.append(_render_sender_skill_pills(sender_skills_list, sender_username))
        return mark_safe(''.join(html))

    main, stay = parts[0].strip(), parts[1].strip()
    main, sender_skills_list = _extract_sender_skills_from_text(main)
    main, skills_list = _extract_skills_from_text(main)
    stay, stay_skills = _extract_skills_from_text(stay)
    skills_list = skills_list + stay_skills

    from_dt = None
    to_dt = None
    m_from = re.search(r"From\s+(.+)", stay)
    m_to = re.search(r"To\s+(.+)", stay)

    def _parse_iso(s):
        try:
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

    html = []
    if main:
        html.append('<div class="whitespace-pre-wrap mb-3">%s</div>' % template.defaultfilters.linebreaksbr(template.defaultfilters.force_escape(main)))

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
    if not from_dt and not to_dt and stay:
        html.append('<div class="text-sm text-brown mt-2 whitespace-pre-wrap">%s</div>' % template.defaultfilters.linebreaksbr(template.defaultfilters.force_escape(stay)))
    html.append('</div>')

    if skills_list:
        html.append(_render_skill_pills(skills_list, sender_username))
    if sender_skills_list:
        html.append(_render_sender_skill_pills(sender_skills_list, sender_username))

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
    """Remove structured metadata blocks (Requested stay, Skills, Sender-Skills, Ad-ID) from message body."""
    if not body:
        return ""
    import re
    cleaned = re.sub(r"Requested stay:\s*.*$", "", body, flags=re.IGNORECASE | re.DOTALL).strip()
    cleaned, _ = _extract_sender_skills_from_text(cleaned)
    cleaned, _ = _extract_skills_from_text(cleaned)
    cleaned = re.sub(r"\n?Ad-ID:\s*[A-Za-z0-9-_]+\s*$", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned


@register.simple_tag
def extract_skills(body, limit=5):
    """Extract a comma-separated 'Skills: ...' line from the message body and return up to `limit` skills as a list."""
    if not body:
        return []
    cleaned, _ = _extract_sender_skills_from_text(body)
    _, skills = _extract_skills_from_text(cleaned)
    return skills[:int(limit)]


@register.simple_tag
def extract_sender_skills(body, limit=5):
    """Extract a comma-separated 'Sender-Skills: ...' line from the message body and return up to `limit` skills as a list."""
    if not body:
        return []
    _, skills = _extract_sender_skills_from_text(body)
    return skills[:int(limit)]
