"""The weekly project email: open needs of projects near someone that match what they can
give, i.e. their skills (a need for carpentry, they list carpentry) and their gift offers
(a need for clay, they offer clay or something in the same gift category). Each need is
suggested to each person once, and nobody gets more than one email a week. Sent by
`send_project_digest` (weekly cron)."""

from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.contrib.gis.db.models.functions import Distance
from django.contrib.gis.measure import D
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.db.models import Max, Prefetch
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _, ngettext

from gifts.models import Listing
from matches.models import Match

from .models import DigestedNeed, Need, Project

UNSUBSCRIBE_SALT = "projects-digest-unsubscribe"
# At most one email per person in this time, however often the command runs
MIN_INTERVAL = timedelta(days=6)


@dataclass
class Suggestion:
    need: Need
    skill_name: str = ""  # their skill this need asks for
    listing: Listing | None = None  # their gift offer that could cover it

    @property
    def reason(self):
        if self.skill_name:
            return _("your skill: %(skill)s") % {"skill": self.skill_name}
        title = f"{self.listing.title} ({self.listing.amount})" if self.listing.amount else self.listing.title
        return _("your gift: %(title)s") % {"title": title}


@dataclass
class ProjectSuggestions:
    project: Project
    distance_km: int
    suggestions: list = field(default_factory=list)

    @property
    def offer_url(self):
        query = "&".join(f"need={s.need.pk}" for s in self.suggestions)
        return f"{reverse('projects:offer_help', args=[self.project.pk])}?{query}"


def _words(text):
    # Short words ("old", "two", "for") say nothing about what a thing is
    return {word for word in text.casefold().replace(",", " ").split() if len(word) >= 4}


def _same_word(a, b):
    """"scythe" and "scythes", "brick" and "bricks": one starts with the other."""
    return a.startswith(b) or b.startswith(a)


def _listing_for(need, listings):
    """Their gift offer that fits a material/tool need: one whose title shares a word
    with the need ("Clay" / "Clay from our pond"), else one in the need's gift category."""
    need_words = _words(need.title)
    for listing in listings:
        if any(_same_word(a, b) for a in need_words for b in _words(listing.title)):
            return listing
    if need.category_id:
        for listing in listings:
            if need.category_id in {category.pk for category in listing.categories.all()}:
                return listing
    return None


def suggestions_for(user):
    """Projects near `user` with open needs they could cover, nearest first. Needs already
    suggested to them, projects of their own communities and projects they already
    offered help with are left out."""
    if user.location is None:
        return []
    skills = {
        us.skill_id: us.skill.get_name()
        for us in user.user_skills.filter(available=True).select_related("skill")
    }
    listings = list(Listing.objects.filter(owner=user, type="offer").prefetch_related("categories"))
    if not skills and not listings:
        return []

    already = set(DigestedNeed.objects.filter(user=user).values_list("need_id", flat=True))
    offered = set(
        Match.objects.filter(from_user=user, content_type__app_label="projects").values_list("object_id", flat=True)
    )
    projects = (
        Project.objects.current()
        .exclude(community__owner=user)
        .filter(community__location__dwithin=(user.location, D(km=user.project_digest_radius)))
        .annotate(distance=Distance("community__location", user.location))
        .order_by("distance")
        .select_related("community")
        .prefetch_related(Prefetch(
            "needs", queryset=Need.objects.select_related("skill").prefetch_related("need_offers__match"),
        ))
    )
    result = []
    for project in projects:
        if str(project.pk) in offered:
            continue
        found = []
        for need in project.needs.all():
            if need.pk in already or need.is_done:
                continue
            if need.skill_id in skills:
                found.append(Suggestion(need, skill_name=skills[need.skill_id]))
            elif need.kind in Need.THING_KINDS:
                listing = _listing_for(need, listings)
                if listing:
                    found.append(Suggestion(need, listing=listing))
        if found:
            result.append(ProjectSuggestions(project, round(project.distance.km), found))
    return result


def subject_for(found):
    """"3 communities near you need Carpentry" when it is all about one skill, else
    "2 projects near you could use your help"."""
    communities = {item.project.community_id for item in found}
    skill_names = {s.skill_name for item in found for s in item.suggestions}
    if len(skill_names) == 1 and "" not in skill_names:
        return ngettext(
            "%(count)s community near you needs %(skill)s",
            "%(count)s communities near you need %(skill)s",
            len(communities),
        ) % {"count": len(communities), "skill": skill_names.pop()}
    return ngettext(
        "%(count)s project near you could use your help",
        "%(count)s projects near you could use your help",
        len(found),
    ) % {"count": len(found)}


def make_unsubscribe_token(user):
    return signing.dumps(user.pk, salt=UNSUBSCRIBE_SALT)


def read_unsubscribe_token(token):
    return signing.loads(token, salt=UNSUBSCRIBE_SALT)


def _absolute(path):
    return settings.SITE_URL.rstrip("/") + path


def send_digest(user, now=None):
    """Email `user` their new suggestions, if there are any and the last email is a week
    old. Returns whether an email was sent."""
    now = now or timezone.now()
    last = DigestedNeed.objects.filter(user=user).aggregate(last=Max("sent_at"))["last"]
    if last and now - last < MIN_INTERVAL:
        return False
    with translation.override(user.language or settings.LANGUAGE_CODE):
        found = suggestions_for(user)
        if not found:
            return False
        subject = subject_for(found)
        context = {
            "recipient": user,
            "headline": subject,
            "found": found,
            "site_url": settings.SITE_URL.rstrip("/"),
            "settings_url": _absolute(reverse("users:update")),
            "unsubscribe_url": _absolute(reverse("projects:digest_unsubscribe", args=[make_unsubscribe_token(user)])),
            "projects_url": _absolute(reverse("projects:list")),
        }
        text_body = render_to_string("projects/email/digest.txt", context)
        html_body = render_to_string("projects/email/digest.html", context)
    message = EmailMultiAlternatives(
        subject=subject, body=text_body, from_email=settings.DEFAULT_FROM_EMAIL, to=[user.email],
        headers={"List-Unsubscribe": f"<{context['unsubscribe_url']}>"},
    )
    message.attach_alternative(html_body, "text/html")
    message.send(fail_silently=True)
    DigestedNeed.objects.bulk_create(
        [DigestedNeed(user=user, need=s.need) for item in found for s in item.suggestions],
        ignore_conflicts=True,
    )
    return True


def send_project_digests(now=None):
    """Send the weekly email to everyone who wants it. Returns how many were sent."""
    from django.contrib.auth import get_user_model

    users = (
        get_user_model().objects.filter(project_digest=True, is_active=True, location__isnull=False)
        .exclude(email="")
    )
    return sum(1 for user in users.iterator() if send_digest(user, now=now))
