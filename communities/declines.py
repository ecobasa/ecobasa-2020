"""What an ambassador starts from when saying no to a membership application: "not now"
or "no", before the visit and after it. Being turned down by a community can hit hard,
so the texts speak for the community (its situation, what it needs), never judge the
person, say the decision plainly and leave the conversation open. Each has a part in
brackets the ambassador fills in or deletes, so nothing goes out as a form letter."""

import re

from django.utils.translation import gettext_lazy as _

NOT_NOW = "not_now"
NO = "no"
KIND_CHOICES = (
    (NOT_NOW, _("Not now")),
    (NO, _("No")),
)

# A part still to fill in or delete
UNFILLED = re.compile(r"\[[^\]]*\]")

# By the stage the application is at (Membership.STAGE_*) and the kind of no
TEXTS = {
    ("application", NOT_NOW): _(
        "Hello %(name)s,\n\n"
        "thank you for your application and for the care you put into your answers. "
        "I'm writing for all of us at %(community)s.\n\n"
        "We talked about it together, and right now we can't take in new members: "
        "[in a few words what's going on with you, e.g. no free room this year, or a time "
        "of big changes among yourselves]. So it's a \"not now\" from us. It's about where "
        "we are at the moment, not about you.\n\n"
        "If you're still looking later, we'd be glad to hear from you again [when, if you "
        "know]. And if you have a question or would like to talk, just write here.\n\n"
        "Warm wishes,\n%(ambassador)s"
    ),
    ("application", NO): _(
        "Hello %(name)s,\n\n"
        "thank you for your application, and for being so open with us about who you are "
        "and what you're looking for. I'm writing for all of us at %(community)s.\n\n"
        "We read your answers carefully and talked about them together, and we've decided "
        "not to invite you for a visit. What mattered most to us: [in a few honest words "
        "what it's about for you: what you need in your life together, not what's wrong "
        "with them].\n\n"
        "We imagine this may be hard to read, especially after you opened up to us. An "
        "application shows only a small part of a person, and our decision isn't a "
        "judgment of who you are. It's about whether our way of living and yours fit "
        "together right now. If you'd like to understand it better, I'm glad to talk with "
        "you, here or on a call.\n\n"
        "Other communities are looking for new members too, and one of them may fit better "
        "what you're looking for.\n\n"
        "All the best on your way,\n%(ambassador)s"
    ),
    ("visit", NOT_NOW): _(
        "Hello %(name)s,\n\n"
        "thank you for visiting us and for the days we shared. I'm writing for all of us "
        "at %(community)s.\n\n"
        "After your visit we sat together, and for now we won't go on with your membership "
        "application process: [what it's about for you right now, e.g. you'd like to get "
        "to know each other longer, or have things to settle among yourselves first]. This "
        "isn't a final no.\n\n"
        "If you like, [what could come next, e.g. another, longer stay, or applying again "
        "in spring]. How is this for you? I'm here if you want to talk.\n\n"
        "Warm wishes,\n%(ambassador)s"
    ),
    ("visit", NO): _(
        "Hello %(name)s,\n\n"
        "thank you for the time you spent with us and for everything you gave during your "
        "visit. I'm writing for all of us at %(community)s.\n\n"
        "After your visit we talked a lot together, and we've decided not to go on with "
        "your membership application process. [What it's about for you: what you noticed "
        "in living together and what you need, without judging who they are. If you "
        "already told them in person, say so.]\n\n"
        "We know this can hurt, all the more after living with us for a while. A few days "
        "show only a part of a whole life, and our decision is about how our living "
        "together and yours fit, not about what you're worth. If you'd like to talk about "
        "it, with me or someone else from us, we're open to that.\n\n"
        "We wish you a place where you can arrive.\n%(ambassador)s"
    ),
}

# Shown to the ambassador next to the texts
GUIDANCE = (
    _("If you've met them, say it in person or on a call first. The message follows that."),
    _("Speak for yourselves: what you need and what you noticed, not what they are."),
    _("Say the decision early and plainly; a vague no keeps people hoping."),
    _("Write only what is true, but not everything that is true."),
    _("\"Not now\" means you'd gladly read a new application from them. If it's about "
      "something fundamental, say so kindly, so they don't hope and apply again in vain."),
    _("Offer a conversation only if someone will really have it, and keep it if they come."),
    _("Don't write it alone or in a hurry: let someone else from the community read it first."),
)


def text(stage, kind, **names):
    return str(TEXTS[(stage, kind)]) % names


def is_unfilled(body):
    return bool(UNFILLED.search(body or ""))
