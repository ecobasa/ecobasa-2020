"""The question library for a community's onboarding process: what is worth asking
people who want to become members, in modules a community switches on as a whole and
then switches single questions off. The wording lives here, translated, so it stays
good in every language; a community only adds a note under a question, or its own
questions (OnboardingQuestion).

Statements come from the community's "How we live" facts ("Our shared kitchen cooks
vegan. That's fine for me."), so nothing is entered twice; one only shows while its
fact is filled in."""

from dataclasses import dataclass, field

from django.utils.translation import gettext, gettext_lazy as _, ngettext

# What a question is to the applicant
INFO = "info"              # answered in the form, read by the ambassador
MUST_MATCH = "must_match"  # agreed to first, before the rest of the form can be sent
DISCUSSION = "discussion"  # not answered in the form: talked about at the visit
TYPE_CHOICES = (
    (INFO, _("Info")),
    (MUST_MATCH, _("Must-match")),
    (DISCUSSION, _("Talk at the visit")),
)

# How a question is answered
TEXT = "text"
YES_NO = "yes_no"
CHOICE = "choice"
NUMBER = "number"
HOUSEHOLD = "household"  # who moves in along (adults, children, pets)
AGREE = "agree"          # a statement to agree to
# What a community's own questions can be
OWN_KIND_CHOICES = (
    (TEXT, _("Text")),
    (YES_NO, _("Yes or no")),
)


@dataclass(frozen=True)
class Question:
    key: str
    # Its wording; a statement from a fact has `fact` instead, which gives the wording
    # for a community, or "" while the fact isn't filled in
    text: str = ""
    kind: str = TEXT
    type: str = INFO  # what the library suggests
    fact: object = None
    # For the editor while the fact isn't filled in
    fact_label: str = ""
    # A question only asked with some facts (e.g. pets only where there may be pets)
    asked_if: object = None
    choices: tuple = ()
    # Support needs, debts, physical capacity: always optional, only for the ambassador
    sensitive: bool = False
    # A note shown when the community is in one of these countries
    country_note: tuple = ()  # (countries, note)
    help_text: str = ""

    @property
    def types(self):
        """What a community may make of it: a statement can be agreed to first, in the form
        or talked about; a question can only be answered or talked about."""
        if self.kind == AGREE:
            return (MUST_MATCH, INFO, DISCUSSION)
        return (INFO, DISCUSSION)

    def is_asked(self, community):
        return self.asked_if is None or bool(self.asked_if(community))

    def text_for(self, community):
        """Its wording for this community ("" for a statement whose fact isn't filled in, or
        a question its facts rule out)."""
        if self.fact:
            return self.fact(community)
        return str(self.text) if self.is_asked(community) else ""

    def note_for(self, community):
        countries, note = self.country_note or ((), "")
        return str(note) if community.country and community.country.code in countries else ""


@dataclass(frozen=True)
class Module:
    key: str
    title: str
    questions: tuple = field(default_factory=tuple)


# ── The statements from the facts ────────────────────────────────────

def _money(community, amount):
    return f"{amount:,} {community.currency}".replace(",", " ")


def _work_hours(community):
    if not community.work_hours:
        return ""
    return ngettext(
        "We each give about %(n)s hour a week to the community. That works for me.",
        "We each give about %(n)s hours a week to the community. That works for me.",
        community.work_hours,
    ) % {"n": community.work_hours}


def _buy_in(community):
    if community.buy_in is None:
        return ""
    amount = _money(community, community.buy_in)
    if community.buy_in_kind:
        amount = f"{amount} ({community.get_buy_in_kind_display()})"
    return gettext("The buy-in is %(amount)s. I can bring at least that.") % {"amount": amount}


def _monthly(community):
    if community.monthly_contribution is None:
        return ""
    return gettext("The monthly contribution is %(amount)s. My income covers it.") % {
        "amount": _money(community, community.monthly_contribution),
    }


def _income_sharing(community):
    return {
        community.INCOME_SHARING_PARTLY: gettext("We share part of our income. I'm open to that."),
        community.INCOME_SHARING_FULLY: gettext("We share all our income. I'm open to that."),
    }.get(community.income_sharing, "")


def _exit_terms(community):
    if community.buy_in is None or not community.exit_terms:
        return ""
    return gettext("I've read what happens to the buy-in when someone leaves, and I accept it.")


def _kitchen(community):
    # Eating anything isn't a rule to agree to
    diets = [str(label) for code, label in community.KITCHEN_CHOICES if code in community.kitchen and code != community.KITCHEN_ANY]
    if not diets:
        return ""
    return gettext("Our shared kitchen cooks: %(diets)s. That's fine for me.") % {"diets": ", ".join(diets)}


def _pets(community):
    # Where they want to be asked first, the household's question about pets asks
    return {
        community.PETS_NONE: gettext("There are no pets here. I'll come without any."),
    }.get(community.pets, "")


def _animals(community):
    if not community.animals:
        return ""
    return gettext("I've read what you say about animals and animal products, and it's fine for me.")


def _children(community):
    return {
        community.CHILDREN_NO_ROOM: gettext("We have no room for more children right now. I'll come without children."),
        community.CHILDREN_ADULTS_ONLY: gettext("We live adults-only. I'll come without children."),
    }.get(community.children_welcome, "")


def _house_agreements(community):
    if not community.house_agreements:
        return ""
    return gettext("I've read your house agreements and will keep to them.")


def _languages(community):
    from .models import language_name

    if not community.languages:
        return ""
    names = ", ".join(language_name(code) for code in community.languages)
    return ngettext(
        "We mainly speak %(languages)s. I speak it or I'm willing to learn it.",
        "We mainly speak %(languages)s. I speak at least one of them or I'm willing to learn.",
        len(community.languages),
    ) % {"languages": names}


def _statutes(community):
    if not community.statutes_url and not community.statutes_file:
        return ""
    return gettext("I've read your vision and statutes.")


def _trial(community):
    if not community.trial_months:
        return ""
    return ngettext(
        "Everyone starts with a trial period of %(n)s month. I accept that.",
        "Everyone starts with a trial period of %(n)s months. I accept that.",
        community.trial_months,
    ) % {"n": community.trial_months}


# ── The library ──────────────────────────────────────────────────────

MODULES = (
    Module("motivation", _("Motivation and fit"), (
        Question("why_here", _("Why this community, and why now?")),
        Question("community_meaning", _("What does living in community mean to you?")),
        Question("give_get", _("What do you hope to give here, and what do you hope to get?")),
        Question("other_communities", _("Which other communities have you visited or lived in, and what made you leave?")),
        Question("would_leave", _("What would make you leave this community?"), type=DISCUSSION),
    )),
    Module("conflict", _("Communication and conflict"), (
        Question("conflict_story", _("Tell us about a real conflict you were part of, and how it ended.")),
        Question("methods", _("Which ways of talking and deciding together do you know from experience?"),
                 help_text=_("For example consensus, sociocracy, nonviolent communication, Forum")),
        Question("feedback", _("How do you take critical feedback?"), type=DISCUSSION),
        Question("mediation", _("When a conflict gets stuck, I'm willing to go into mediation."), kind=AGREE, type=MUST_MATCH),
    )),
    Module("work", _("Work and contribution"), (
        Question("hours", _("How many hours a week can you realistically give, and does that change with the seasons?")),
        Question("work_commitment", kind=AGREE, type=MUST_MATCH, fact=_work_hours, fact_label=_("Work commitment")),
        Question("income_source", _("How will you earn your living?"), kind=CHOICE, choices=(
            ("remote", _("Remote work")),
            ("local_job", _("A local job")),
            ("business", _("A business inside the community")),
            ("none_yet", _("Nothing yet")),
            ("other", _("Other")),
        )),
        Question("physical", _("What physical work can you do, for example on the farm or on building sites?"), sensitive=True),
    )),
    Module("finances", _("Finances"), (
        Question("buy_in", kind=AGREE, type=MUST_MATCH, fact=_buy_in, fact_label=_("Buy-in")),
        Question("monthly", kind=AGREE, type=MUST_MATCH, fact=_monthly, fact_label=_("Monthly contribution")),
        Question("income_sharing", kind=AGREE, type=MUST_MATCH, fact=_income_sharing, fact_label=_("Income sharing")),
        Question("exit_terms", kind=AGREE, type=MUST_MATCH, fact=_exit_terms, fact_label=_("Exit terms")),
        Question("debts", _("Do you have debts we should know about?"), sensitive=True),
    )),
    Module("everyday", _("Everyday agreements"), (
        Question("kitchen", kind=AGREE, type=MUST_MATCH, fact=_kitchen, fact_label=_("Shared kitchen")),
        Question("pets", kind=AGREE, type=MUST_MATCH, fact=_pets, fact_label=_("Pets")),
        Question("animals", kind=AGREE, type=MUST_MATCH, fact=_animals, fact_label=_("Animals and animal products")),
        Question("children", kind=AGREE, type=MUST_MATCH, fact=_children, fact_label=_("Are more children welcome?")),
        Question("house_agreements", kind=AGREE, type=MUST_MATCH, fact=_house_agreements, fact_label=_("House agreements")),
        Question("languages", kind=AGREE, type=MUST_MATCH, fact=_languages, fact_label=_("Languages")),
    )),
    Module("household", _("Household"), (
        Question("who", _("Who would move in with you?"), kind=HOUSEHOLD,
                 help_text=_("Adults and children. Every adult applies on their own.")),
        Question("pets_along", _("Will you bring any pets? If so, which ones, how many, and what are they like?"),
                 help_text=_("With people, children and other animals."),
                 asked_if=lambda community: community.pets != community.PETS_NONE),
        Question("school", _("What are your plans for your children's school?"),
                 country_note=(("DE",), _("School is compulsory in Germany, so homeschooling isn't an option."))),
        Question("childcare", _("What do you expect from shared childcare?"), type=DISCUSSION),
    )),
    Module("support", _("Support needs"), (
        Question("support", _("Is there anything we should know so we can support you well?"), sensitive=True),
    )),
    Module("practical", _("Practical"), (
        Question("timeline", _("When would you like to move in?")),
        Question("notice", _("How long is the notice period where you live now?")),
        Question("registration", _("Do you need to register your address here?"), kind=YES_NO,
                 country_note=(("DE", "AT"), _("Everyone here has to register where they live (Meldeadresse)."))),
        Question("commons", _("What would you bring into the commons?"),
                 help_text=_("What you'd share can also become your offers on ecobasa.")),
    )),
    Module("commitments", _("Commitments"), (
        Question("statutes", kind=AGREE, type=MUST_MATCH, fact=_statutes, fact_label=_("Vision and statutes")),
        Question("trial", kind=AGREE, type=MUST_MATCH, fact=_trial, fact_label=_("Trial period")),
    )),
)

QUESTIONS = {question.key: question for module in MODULES for question in module.questions}
# Where each library question goes in the form, after the must-matches
POSITIONS = {key: position for position, key in enumerate(QUESTIONS)}
MODULE_OF = {question.key: module for module in MODULES for question in module.questions}
