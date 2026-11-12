"""The kinds of event. A kind gives an event its word, its icon and the settings a new one
starts with; nothing else. Code asks an event about its settings (`is_open`), never about
its kind, so a new kind is one more entry here."""

from django.utils.translation import gettext_lazy as _

PROJECT = "project"
COMMUNITY_EVENT = "community_event"

CHOICES = [
    (PROJECT, _("Project")),
    (COMMUNITY_EVENT, _("Community event")),
]

ICONS = {
    PROJECT: "fa-person-digging",
    COMMUNITY_EVENT: "fa-people-group",
}

# What the form of a new event of this kind starts with
DEFAULTS = {
    PROJECT: {"is_open": False},
    COMMUNITY_EVENT: {"is_open": True},
}

# What the kind is, for whoever chooses one
HINTS = {
    PROJECT: _("Something you want to realise with help: it needs hands, skills, materials or tools."),
    COMMUNITY_EVENT: _("Something you invite to: an open day, a workshop, a seminar, a festival."),
}

# The kind's word in the sentences that name it
TEXTS = {
    PROJECT: {
        "plural": _("Projects"),
        "new": _("New project"),
        "edit": _("Edit project"),
        "start": _("Start a project"),
        "title_placeholder": _("e.g. Building a rocket stove"),
        "description_placeholder": _("What do you want to build or do, and what will helpers learn?"),
        "saved": _("The project has been saved."),
        "ended": _("This project has ended."),
        "ended_change_dates": _("This project has ended. Change its dates to bring it back."),
        "archived": _("This project has been archived."),
        "archived_by_you": _("The project has been archived. You can bring it back at any time."),
        "archive_question": _("Archive this project? It will no longer be listed."),
        "confirmed": _("Thanks! The project shows as up to date again."),
        "confirm_title": _("Shows visitors that this project is up to date"),
        "stale": _("Nobody has updated this project for a while. Is it still current? Otherwise it will be archived soon."),
        "no_offers": _("This project doesn't take offers at the moment."),
        "support": _("Support this project"),
        "join": _("Join this project"),
        "references": _("References from this project"),
        "need": _("Project need"),
        "own_need": _("your project %(project)s: %(title)s"),
        "help_request": _("%(actor)s offered to help with your project: %(title)s"),
        "reminder_subject": _("Is your project “%(title)s” still current?"),
        "reminder_headline": _("Is your project still current?"),
        "reminder_question": _("nobody has updated the project “%(title)s” of %(community)s for a while. Is it still current?"),
        "reminder_update": _("Update the project"),
    },
    COMMUNITY_EVENT: {
        "plural": _("Community events"),
        "new": _("New community event"),
        "edit": _("Edit community event"),
        "start": _("Invite to a community event"),
        "title_placeholder": _("e.g. Open day"),
        "description_placeholder": _("What happens, and who is it for?"),
        "saved": _("The community event has been saved."),
        "ended": _("This community event is over."),
        "ended_change_dates": _("This community event is over. Change its dates to bring it back."),
        "archived": _("This community event has been archived."),
        "archived_by_you": _("The community event has been archived. You can bring it back at any time."),
        "archive_question": _("Archive this community event? It will no longer be listed."),
        "confirmed": _("Thanks! The community event shows as up to date again."),
        "confirm_title": _("Shows visitors that this community event is up to date"),
        "stale": _("Nobody has updated this community event for a while. Is it still current? Otherwise it will be archived soon."),
        "no_offers": _("This community event doesn't take offers at the moment."),
        "support": _("Support this community event"),
        "join": _("Join this community event"),
        "references": _("References from this community event"),
        "need": _("Community event need"),
        "own_need": _("your community event %(project)s: %(title)s"),
        "help_request": _("%(actor)s offered to help with your community event: %(title)s"),
        "reminder_subject": _("Is your community event “%(title)s” still current?"),
        "reminder_headline": _("Is your community event still current?"),
        "reminder_question": _("nobody has updated the community event “%(title)s” of %(community)s for a while. Is it still current?"),
        "reminder_update": _("Update the community event"),
    },
}


def event_kind_buttons():
    """(kind, what its button says, icon) for "add one of this kind"."""
    return [(value, TEXTS[value]["start"], ICONS[value]) for value, _label in CHOICES]
