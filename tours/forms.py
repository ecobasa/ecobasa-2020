import json

from django import forms
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _
from django_countries import countries as all_countries

from communities.models import Community
from events.models import Event
from gift_economy.gifts.skills.models import get_or_create_skill

from .models import Stop, Tour, Traveller


def _style(fields):
    for field in fields.values():
        widget = field.widget
        if isinstance(widget, (forms.RadioSelect, forms.ClearableFileInput, forms.HiddenInput)):
            continue
        if isinstance(widget, forms.CheckboxInput):
            widget.attrs["class"] = "form-checkbox"
        elif isinstance(widget, forms.Textarea):
            widget.attrs["class"] = "form-textarea w-full"
        elif isinstance(widget, forms.Select):
            widget.attrs["class"] = "form-select w-full"
        else:
            widget.attrs["class"] = "form-input w-full"


class TourForm(forms.ModelForm):
    """The basics of a tour: what it is about, how it travels, and whether it looks for
    travellers. The route is planned on its own page."""

    learn_skills = forms.CharField(
        label=_("What we want to learn"), required=False,
        widget=forms.TextInput(attrs={"data-skill-tags": _("Popular skills to explore")}),
        help_text=_("Skills from the list. We use them to find communities and events where you can learn them."),
    )
    countries = forms.CharField(
        label=_("Countries"), required=False, widget=forms.TextInput(attrs={"data-country-tags": ""}),
        help_text=_("Where about you want to go. Once the tour has stops, they say it."),
    )
    field_order = [
        "title", "image", "description", "learn_skills", "travel_mode", "countries", "open_to_join", "max_people",
        "listed", "children_welcome", "animals_welcome", "costs_note", "good_to_know",
    ]

    class Meta:
        model = Tour
        fields = [
            "title", "image", "description", "travel_mode", "open_to_join", "max_people", "listed",
            "children_welcome", "animals_welcome", "costs_note", "good_to_know",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "good_to_know": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["title"].widget.attrs["placeholder"] = _("e.g. Permaculture tour through Portugal")
        self.fields["description"].widget.attrs["placeholder"] = _(
            "Why you travel, what you'd like to do on the way, who you'd like to meet."
        )
        self.fields["learn_skills"].widget.attrs["placeholder"] = _("e.g. Permaculture, Yoga")
        self.fields["max_people"].widget.attrs["min"] = 1
        tour = self.instance
        if tour.pk:
            self.initial["learn_skills"] = ", ".join(skill.get_name() for skill in tour.learn_skills.all())
            # The stops say where it goes
            if tour.stops.exists():
                del self.fields["countries"]
        if "countries" in self.fields:
            chosen = [code for code in (c.code for c in tour.countries)] if tour.pk else []
            self.initial["countries"] = ",".join(chosen)
        _style(self.fields)

    @staticmethod
    def country_whitelist():
        """The countries to choose from, for the tag field: name and code."""
        return json.dumps([{"value": str(name), "code": code} for code, name in all_countries])

    def clean_countries(self):
        codes = [code.strip().upper() for code in self.cleaned_data.get("countries", "").split(",") if code.strip()]
        unknown = [code for code in codes if code not in dict(all_countries)]
        if unknown:
            raise forms.ValidationError(_("Please choose countries from the list."))
        return list(dict.fromkeys(codes))

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("open_to_join"):
            # A tour that looks for travellers is always in the list
            cleaned["listed"] = True
        else:
            cleaned["max_people"] = None
        return cleaned

    def save(self, commit=True):
        tour = super().save(commit=False)
        if "countries" in self.fields:
            tour.countries = self.cleaned_data["countries"]
        if commit:
            tour.save()
            self.save_learn_skills(tour)
        return tour

    def save_learn_skills(self, tour):
        """The skills named, in any language, once the tour is saved."""
        names = [n.strip() for n in self.cleaned_data.get("learn_skills", "").split(",") if n.strip()]
        tour.learn_skills.set([get_or_create_skill(name)[0] for name in names])


class StopForm(forms.ModelForm):
    """One stop: at a community or one of its current events, or at another place (a
    meeting point, a town, a gathering not on ecobasa). Never somebody's home."""

    WHERE_COMMUNITY = "community"
    WHERE_PLACE = "place"
    where = forms.ChoiceField(
        label=_("Where"), widget=forms.RadioSelect, initial=WHERE_COMMUNITY,
        choices=[(WHERE_COMMUNITY, _("At a community")), (WHERE_PLACE, _("Another place"))],
    )
    community = forms.ModelChoiceField(Community.objects.all(), required=False, widget=forms.HiddenInput)
    event = forms.ModelChoiceField(
        Event.objects.none(), required=False, label=_("At one of its events?"),
        empty_label=_("No, a stay at the community"),
    )
    # Another place's name, as the location picker writes it
    location_name = forms.CharField(label=_("Place"), max_length=255, required=False)

    class Meta:
        model = Stop
        fields = [
            "community", "event", "location", "country", "arrive_on", "leave_on", "leave_at", "flexible", "note",
            "onward_mode",
        ]
        widgets = {
            "location": forms.HiddenInput,
            "arrive_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "leave_on": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "leave_at": forms.TimeInput(attrs={"type": "time"}, format="%H:%M"),
            "note": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        stop = self.instance
        self.fields["onward_mode"].label = _("Going on from here by")
        self.fields["onward_mode"].choices = [("", _("As the tour travels"))] + list(Tour.MODE_CHOICES)
        self.fields["note"].widget.attrs["placeholder"] = _("e.g. help with the harvest, a yoga week")
        if stop.pk:
            if stop.community_id:
                self.initial["where"] = self.WHERE_COMMUNITY
            else:
                self.initial["where"] = self.WHERE_PLACE
                self.initial["location_name"] = stop.name
        # The events to choose from: the chosen community's current ones, and the stop's own
        community = self._chosen_community()
        events = Event.objects.none()
        if community is not None:
            events = Event.objects.filter(community=community).current()
            if stop.event_id:
                events = events | Event.objects.filter(pk=stop.event_id)
        self.fields["event"].queryset = events
        _style(self.fields)

    def _chosen_community(self):
        if self.is_bound:
            pk = self.data.get(self.add_prefix("community"))
            return Community.objects.filter(pk=pk).first() if pk and str(pk).isdigit() else None
        return self.instance.community if self.instance.community_id else None

    def chosen_community(self):
        """The community picked so far, to show its name in the search field again."""
        return self._chosen_community()

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("where") == self.WHERE_COMMUNITY:
            if not cleaned.get("community"):
                self.add_error("community", _("Please choose a community."))
            event = cleaned.get("event")
            if event and cleaned.get("community") and event.community_id != cleaned["community"].pk:
                self.add_error("event", _("Please choose one of this community's events."))
        else:
            cleaned["community"] = cleaned["event"] = None
            if not cleaned.get("location"):
                self.add_error("location_name", _("Please choose the place on the map."))
        arrive_on, leave_on = cleaned.get("arrive_on"), cleaned.get("leave_on")
        if arrive_on and leave_on and leave_on < arrive_on:
            self.add_error("leave_on", _("You can't leave before you arrive."))
        return cleaned

    def save(self, commit=True):
        stop = super().save(commit=False)
        if self.cleaned_data["where"] == self.WHERE_PLACE:
            stop.community = stop.event = None
            stop.name = self.cleaned_data.get("location_name", "")
        else:
            stop.location, stop.country, stop.name = None, None, ""
        if commit:
            stop.save()
        return stop


class JoinForm(forms.ModelForm):
    """Asking to come along for the whole route or part of it: where to get on and off,
    how many people, and a few words to the organisers (only when asking, not when
    changing the stretch later)."""

    message = forms.CharField(
        label=_("A few words to the organisers"), widget=forms.Textarea(attrs={"rows": 4}),
        help_text=_("Who you are, why you'd like to come along, what you could bring."),
    )

    class Meta:
        model = Traveller
        fields = ["from_stop", "to_stop", "people", "ride_only"]

    def __init__(self, tour, *args, with_message=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.tour = tour
        self.stops = tour.ordered_stops()
        if len(self.stops) >= 2:
            for name, choices, default in (
                ("from_stop", self.stops[:-1], self.stops[0]),
                ("to_stop", self.stops[1:], self.stops[-1]),
            ):
                field = self.fields[name]
                field.queryset = Stop.objects.filter(pk__in=[stop.pk for stop in choices])
                field.required = True
                field.empty_label = None
                field.label_from_instance = self._stop_label
                self.initial.setdefault(name, default.pk)
            self.fields["from_stop"].label = _("Get on at")
            self.fields["to_stop"].label = _("Get off at")
        else:
            # An idea without a route yet: along for the whole of it
            del self.fields["from_stop"], self.fields["to_stop"]
        self.fields["people"].min_value = 1
        self.fields["people"].widget.attrs["min"] = 1
        if not with_message:
            del self.fields["message"]
        _style(self.fields)

    def _stop_label(self, stop):
        number = next((i + 1 for i, s in enumerate(self.stops) if s.pk == stop.pk), "")
        day = stop.arrive_on or stop.leave_on
        when = f", {date_format(day, 'j M')}" if day else ""
        return f"{number}. {stop.label}{when}"

    def clean_people(self):
        people = self.cleaned_data["people"]
        if not people:
            raise forms.ValidationError(_("At least one."))
        return people

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("from_stop"), cleaned.get("to_stop")
        if start and end and self.tour.stretch(start, end, self.stops) is None:
            self.add_error("to_stop", _("Choose a stop after the one you get on at."))
            return cleaned
        people = cleaned.get("people")
        if people and not self.tour.fits(start, end, people, exclude=self.instance if self.instance.pk else None):
            free = self.tour.free_on(start, end, self.stops, exclude=self.instance if self.instance.pk else None)
            raise forms.ValidationError(
                _("There is no room for that many on this stretch: %(free)s free.") % {"free": free}
            )
        return cleaned


class HostForm(forms.Form):
    """The organisers ask a stop's host to take the group (a tour visit): the days, what
    the group would like to learn there, what it helps with, a few lines. How many come
    follows from the travellers at that stop. As the volunteer form on a community's page:
    at a community its events' needs and its wishes for things, at an event that event's
    needs. Each need gets a checkbox (need_<id>) and, if it has a quantity, an amount
    (quantity_<id>), as when offering help."""

    learn = forms.MultipleChoiceField(
        label=_("What we would like to learn here"), required=False, widget=forms.CheckboxSelectMultiple,
    )

    stay_from = forms.DateField(label=_("Arrival"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    stay_to = forms.DateField(label=_("Departure"), required=False, widget=forms.DateInput(attrs={"type": "date"}))
    message = forms.CharField(
        label=_("Message"), widget=forms.Textarea(attrs={"rows": 5}),
        help_text=_("Who you are as a group, what you would like to do and learn there, what you bring, and what you need: food (diet, allergies), where you would sleep."),
    )

    def __init__(self, stop, people, *args, open_event=False, **kwargs):
        super().__init__(*args, **kwargs)
        from gift_economy.gifts import units
        from gift_economy.gifts.models import Listing

        self.stop = stop
        # (event or None, needs): an event's open needs, then the community's wishes
        self.groups = []
        if open_event:
            # Just saying the tour comes: no needs to choose, a message is optional
            self.fields["message"].required = False
            self.fields["message"].help_text = ""
        elif stop.event_id:
            self.groups = [(stop.event, [need for need in stop.event.needs() if not need.is_done])]
        else:
            community = stop.community
            for event in community.events.current().prefetch_related("listings__contributions__match"):
                self.groups.append((event, [need for need in event.needs() if not need.is_done]))
            self.groups.append((None, list(
                Listing.objects.of(community).open()
                .filter(type=Listing.TYPE_WISH, event=None, kind__in=Listing.THING_KINDS).order_by("-updated_at")
            )))
        self.groups = [(event, needs) for event, needs in self.groups if needs]
        self.needs = [need for _event, needs in self.groups for need in needs]

        # The tour's skills to learn, the ones taught here ticked
        wanted = list(stop.tour.learn_skills.all())
        if wanted and not open_event:
            taught = self._taught()
            self.fields["learn"].choices = [(str(skill.pk), skill.get_name()) for skill in wanted]
            self.fields["learn"].widget.attrs["class"] = "form-checkbox"
            self.initial.setdefault("learn", [str(skill.pk) for skill in wanted if skill.pk in taught])
            self.taught = taught
        else:
            del self.fields["learn"]
        self.initial.setdefault("stay_from", stop.arrive_on)
        self.initial.setdefault("stay_to", stop.leave_on)
        for need in self.needs:
            self.fields[f"need_{need.pk}"] = forms.BooleanField(
                required=False, widget=forms.CheckboxInput(attrs={"class": "form-checkbox"}),
            )
            if need.quantity:
                remaining = need.remaining or need.quantity
                self.fields[f"quantity_{need.pk}"] = forms.IntegerField(
                    required=False, min_value=1,
                    initial=min(people, remaining) if need.unit == units.PEOPLE else remaining,
                    widget=forms.NumberInput(attrs={"class": "form-input w-24", "min": "1"}),
                )
        self.fields["message"].widget.attrs["class"] = "form-textarea w-full"
        for name in ("stay_from", "stay_to"):
            self.fields[name].widget.attrs["class"] = "form-input w-full"

    def _taught(self):
        """Ids of the skills one can learn at the stop: what its event or community offers
        to teach (its events' too), and its members' skills."""
        from gift_economy.gifts.models import Listing

        stop = self.stop
        offers = Listing.objects.open().filter(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL)
        if stop.event_id:
            found = [offers.filter(event=stop.event)]
        else:
            found = [
                Listing.objects.of(stop.community).filter(type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL),
                offers.filter(owner__in=stop.community.members(), community=None),
            ]
        return {pk for queryset in found for pk in queryset.values_list("skill_id", flat=True) if pk}

    def need_groups(self):
        """[(event or None, [(need, checkbox, amount field or None)])] for the template."""
        return [
            (event, [
                (need, self[f"need_{need.pk}"], self[f"quantity_{need.pk}"] if f"quantity_{need.pk}" in self.fields else None)
                for need in needs
            ])
            for event, needs in self.groups
        ]

    def chosen_needs(self):
        return [
            (need, self.cleaned_data.get(f"quantity_{need.pk}"))
            for need in self.needs if self.cleaned_data.get(f"need_{need.pk}")
        ]

    def chosen_skills(self):
        """The names of the skills ticked to learn, comma separated (StayDetails.practice_skills)."""
        if "learn" not in self.fields:
            return ""
        names = dict(self.fields["learn"].choices)
        return ", ".join(names[pk] for pk in self.cleaned_data.get("learn", []))

    def clean(self):
        cleaned = super().clean()
        stay_from, stay_to = cleaned.get("stay_from"), cleaned.get("stay_to")
        if stay_from and stay_to and stay_to < stay_from:
            self.add_error("stay_to", _("The stay can't end before it starts."))
        return cleaned
