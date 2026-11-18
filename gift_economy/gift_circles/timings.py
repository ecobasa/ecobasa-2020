"""How long each round of a gift-circle takes: 1.5 hours by default, shared out the same
way over the time the host gave it (45 minutes for a few people, 3 hours for 50)."""

from datetime import datetime

from django.utils.translation import ngettext

# Minutes of each round in a gift-circle of 1.5 hours
ROUNDS = {"welcome": 10, "wishes": 35, "offers": 30, "thanks": 10, "close": 5}
DEFAULT = sum(ROUNDS.values())


def minutes(event):
    """How long it takes by its hours, or None without both."""
    if not (event.starts_at and event.ends_at):
        return None
    day = event.starts_on or datetime.min.date()
    taken = (datetime.combine(day, event.ends_at) - datetime.combine(day, event.starts_at)).seconds // 60
    return taken or None


def _duration(total):
    hours, rest = divmod(total, 60)
    parts = []
    if hours:
        parts.append(ngettext("%(count)s hour", "%(count)s hours", hours) % {"count": hours})
    if rest:
        parts.append(ngettext("%(count)s minute", "%(count)s minutes", rest) % {"count": rest})
    return " ".join(parts)


def timings(event):
    """{round: minutes, rounded to 5}, and `duration`: how long it takes in words, or ""
    for the default."""
    total = minutes(event)
    scale = (total or DEFAULT) / DEFAULT
    shares = {name: max(5, round(share * scale / 5) * 5) for name, share in ROUNDS.items()}
    shares["duration"] = _duration(total) if total and total != DEFAULT else ""
    return shares
