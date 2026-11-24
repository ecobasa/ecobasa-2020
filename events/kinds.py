"""The kinds of event. A kind gives an event its word, its icon, the settings a new one
starts with, who may host it and where its pages live; nothing else. Code asks an event
about its settings (`is_open`, `max_people`), never about its kind, so a new kind is one
more entry here."""

from django.utils.translation import gettext_lazy as _

PROJECT = "project"
COMMUNITY_EVENT = "community_event"
GIFT_CIRCLE = "gift_circle"

CHOICES = [
    (PROJECT, _("Project")),
    (COMMUNITY_EVENT, _("Community event")),
    (GIFT_CIRCLE, _("Gift-circle")),
]

ICONS = {
    PROJECT: "fa-person-digging",
    COMMUNITY_EVENT: "fa-people-group",
    GIFT_CIRCLE: "fa-hands-holding-circle",
}

# Who may host an event of this kind. Projects and community events are a community's;
# anyone may invite to a gift-circle, also a tour where it stops
HOST_COMMUNITY = "community"
HOST_PERSON = "person"
HOST_TOUR = "tour"
HOSTS = {
    PROJECT: (HOST_COMMUNITY,),
    COMMUNITY_EVENT: (HOST_COMMUNITY,),
    GIFT_CIRCLE: (HOST_COMMUNITY, HOST_PERSON, HOST_TOUR),
}

# Kinds whose pages have an address of their own, whoever hosts them: /<address>/<slug>/.
# The others live under their community's: /communities/<community>/events/<slug>/
ADDRESSES = {
    GIFT_CIRCLE: "gift-circles",
}

# A kind another host than a community may host needs an address of its own: there is no
# community's to live under
assert all(kind in ADDRESSES for kind, hosts in HOSTS.items() if hosts != (HOST_COMMUNITY,))

# Its colour, from the manual's yellow: a project's brighter (+30K), a community event's
# dark (+60K, as their needs on the gifts map); a gift-circle's pill from the logo's
# orange (+30K), its pin primary. A pill's class and, for a map's canvas, the icon's code point in it
COLOURS = {
    PROJECT: "bg-yellow-30k",
    COMMUNITY_EVENT: "bg-yellow-60k",
    GIFT_CIRCLE: "bg-orange-30k",
}
PINS = {
    PROJECT: (0xF85E, "#9b5506"),  # person-digging
    COMMUNITY_EVENT: (0xE533, "#593103"),  # people-group
    GIFT_CIRCLE: (0xE4FB, "#da6137"),  # hands-holding-circle, in primary
}

# Kinds that happen on one day: no "Until", they end the day they start, so they are
# never ongoing
ONE_DAY = (GIFT_CIRCLE,)

# Kinds a person's profile lists, those they host and those they came to
ON_PROFILES = (GIFT_CIRCLE,)

# Kinds with a potluck note: what people could bring to share
POTLUCK = (GIFT_CIRCLE,)

# Kinds where nothing is needed but people: who can't just come asks to join in a few
# words, without days or what they bring
ASK_TO_JOIN = (GIFT_CIRCLE,)

# Fields of an add-on in "I'm coming" and "Ask to join", and on the page for who comes
COMING_FIELDS = {GIFT_CIRCLE: "gift_circles/_attendee_fields.html"}

# Beside each person under "Who is coming"; the template decides whom it shows to
COMING_TOOLS = {GIFT_CIRCLE: "gift_circles/_scribe.html"}

# How visitors without an account come, beside "I'm coming"
GUEST_SIGN_UPS = {GIFT_CIRCLE: "gift_circles/_guest_sign_up.html"}

# On its page: how the host and who comes invite others, and anyone shares it
INVITING = {GIFT_CIRCLE: "gift_circles/_invite.html"}
# A new one invites who lives this close to it (km), if its host ticks it
NEARBY_KM = 25

# On its page: the offers and wishes people bring, and how who comes or hosts brings theirs
BRINGING = {GIFT_CIRCLE: "gift_circles/_bring.html"}

# On its page once it has begun: how it went (stories by who came, as references about
# it), and for who came how to go on (an add-on's template)
HOW_IT_WENT = {GIFT_CIRCLE: "gift_circles/_after.html"}

# How long one usually takes, in minutes: the form fills in "Until" from "From"
DURATIONS = {GIFT_CIRCLE: 90}

# A new one filled in from the query string: an add-on's function (request, event) that
# presets the event and returns what runs once it is saved, or None
PRESETS = {GIFT_CIRCLE: "gift_economy.gift_circles.skill_sharing.start"}

# A short guide for whoever invites, beside the form
GUIDES = {GIFT_CIRCLE: "gift_circles/_host_guide.html"}

# A link to the help page that explains it, wherever one shows (a template taking `colour`)
HELP_LINKS = {GIFT_CIRCLE: "gift_circles/_what_link.html"}

# Pages of an add-on for whoever may edit one, as buttons on its page: (URL name taking
# its slug, what the button says, icon)
TOOLS = {GIFT_CIRCLE: (("gift_circles:print", _("Print the Giftsheet and card"), "fa-print"),)}

# What the form of a new event of this kind starts with
DEFAULTS = {
    PROJECT: {"is_open": False},
    COMMUNITY_EVENT: {"is_open": True},
    GIFT_CIRCLE: {"is_open": True},
}

# What the kind is, for whoever chooses one
HINTS = {
    PROJECT: _("Something you want to realise with help: it needs hands, skills, materials or tools."),
    COMMUNITY_EVENT: _("Something you invite to: an open day, a workshop, a seminar, a festival."),
    GIFT_CIRCLE: _("People meet in a circle and say what they wish for and what they can give."),
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
        "join_request": _("%(actor)s asked to join your project: %(title)s"),
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
        "join_request": _("%(actor)s asked to join your community event: %(title)s"),
        "reminder_subject": _("Is your community event “%(title)s” still current?"),
        "reminder_headline": _("Is your community event still current?"),
        "reminder_question": _("nobody has updated the community event “%(title)s” of %(community)s for a while. Is it still current?"),
        "reminder_update": _("Update the community event"),
    },
    GIFT_CIRCLE: {
        "plural": _("Gift-circles"),
        "new": _("New gift-circle"),
        "edit": _("Edit gift-circle"),
        "start": _("Invite to a gift-circle"),
        "title_placeholder": _("e.g. Gift-circle in the park"),
        "description_placeholder": _("Where exactly do you meet, and is there a potluck?"),
        "saved": _("The gift-circle has been saved."),
        "ended": _("This gift-circle is over."),
        "ended_change_dates": _("This gift-circle is over. Change its dates to bring it back."),
        "archived": _("This gift-circle has been archived."),
        "archived_by_you": _("The gift-circle has been archived. You can bring it back at any time."),
        "archive_question": _("Archive this gift-circle? It will no longer be listed."),
        "confirmed": _("Thanks! The gift-circle shows as up to date again."),
        "confirm_title": _("Shows visitors that this gift-circle is up to date"),
        "stale": _("Nobody has updated this gift-circle for a while. Is it still current? Otherwise it will be archived soon."),
        "no_offers": _("This gift-circle doesn't take sign-ups at the moment."),
        "support": _("Support this gift-circle"),
        "join": _("Join this gift-circle"),
        "references": _("References from this gift-circle"),
        "need": _("Gift-circle need"),
        "own_need": _("your gift-circle %(project)s: %(title)s"),
        "help_request": _("%(actor)s offered to help with your gift-circle: %(title)s"),
        "join_request": _("%(actor)s asked to join your gift-circle: %(title)s"),
        "reminder_subject": _("Is your gift-circle “%(title)s” still current?"),
        "reminder_headline": _("Is your gift-circle still current?"),
        "reminder_question": _("nobody has updated the gift-circle “%(title)s” of %(community)s for a while. Is it still current?"),
        "reminder_update": _("Update the gift-circle"),
    },
}


def event_kind_buttons(host=HOST_COMMUNITY):
    """(kind, what its button says, icon) for "add one of this kind", of the kinds `host`
    may host."""
    return [(value, TEXTS[value]["start"], ICONS[value]) for value, _label in choices_for(host)]


def choices_for(host):
    """The kinds `host` (HOST_COMMUNITY, HOST_PERSON, HOST_TOUR) may host."""
    return [(value, label) for value, label in CHOICES if host in HOSTS[value]]
