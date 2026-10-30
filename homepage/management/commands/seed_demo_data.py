"""
Seeds the local dev database with a small, tongue-in-cheek but structurally
complete demo dataset: users, communities (every type/status, one with a public
place), listings (offers & wishes, some with photos, categorized as the listing form
does), seeds & plants (every plant form, from temperate to tropical climates, with
hardiness zones), vehicles and tools to lend and borrow (with loans, by the day and by
the hour, also a community's), a public good, things salvaged from houses taken down
and common goods in places of their own around the map (every kind), skills (every
level), skill wishes (user + community), matches (every status, every target type), match messages,
volunteer details, notifications (every tag), and references (every impression and
subject type, with confirmed/pending/declined skill tags and gift names).

Safe to re-run — everything is get_or_create'd on a natural-ish key, so
running it twice won't duplicate data.

Listing/CommunityPhoto images come from seed_images/ (public domain / CC —
see seed_images/SOURCES.md for attribution), resized for repo size.

    docker compose exec django python manage.py seed_demo_data
"""
import os
from datetime import timedelta

from django.contrib.contenttypes.models import ContentType
from django.contrib.gis.geos import Point
from django.core.files import File
from django.core.management.base import BaseCommand
from django.utils import timezone

from communities.models import Community, CommunityPhoto
from gift_economy.gifts.models import Listing, ListingCategory
from gift_economy.gifts.things import WHITELISTED_KINDS
from gift_economy.matches.models import Contribution, Loan, Match, MatchMessage, VolunteerDetails, loan_span
from notifications.models import Notification, SKILL_NUDGE_TEXT
from gift_economy.references.models import Reference, ReferenceSkill
from gift_economy.references.notifications import notify_reference_created
from gift_economy.gifts.skills.models import Skill, get_or_create_skill
from users.models import User

DEMO_PASSWORD = "ecobasa123"
SEED_IMAGES_DIR = os.path.join(os.path.dirname(__file__), "seed_images")


def _seed_image(field, filename):
    """Attach a local seed_images/ file to an unsaved ImageField, if not already set."""
    if field:
        return
    path = os.path.join(SEED_IMAGES_DIR, filename)
    with open(path, "rb") as fh:
        field.save(filename, File(fh), save=False)


def _as_the_form_would(listing, kind=None, category=None):
    """Its kind (also on older demo data), its categories as the listing form
    sets them (from what it is once recognized, always for seeds and vehicles, else the
    one given; none for skills), and no own place where it is just where its person is."""
    changed = []
    if kind and listing.kind != kind:
        listing.kind = kind
        changed.append("kind")
    owner = listing.owner
    if (listing.location and not listing.community_id and owner.location
            and listing.location.equals_exact(owner.location, 1e-6)):
        listing.location, listing.location_name = None, ""
        changed += ["location", "location_name"]
    if changed:
        # Saving all of it recognizes what it is again
        listing.save()
    if listing.kind in Listing.CATEGORY_KINDS and (listing.thing_id or listing.kind in WHITELISTED_KINDS):
        listing.categories.set(Listing.thing_categories(listing.thing, listing.kind))
    elif listing.kind not in Listing.THING_KINDS:
        listing.categories.clear()
    elif category:
        listing.categories.set(ListingCategory.objects.filter(slug=category))


class Command(BaseCommand):
    help = "Seed the local dev database with themed demo data (safe to re-run)"

    def handle(self, *args, **options):
        users = self._seed_users()
        communities = self._seed_communities(users)
        self._seed_listings(users)
        self._seed_seeds_and_plants(users, communities)
        self._seed_community_photos(communities)
        skills = self._seed_skills()
        self._seed_user_skills(users, skills)
        self._seed_community_skills(communities, skills)
        self._seed_skill_wishes(users, communities, skills)
        self._seed_matches_and_notifications(users, communities)
        self._seed_lending(users, communities)
        self._seed_references(users, communities)
        self._seed_projects(users, communities)
        self._seed_goods_around(users, communities)

        self.stdout.write(self.style.SUCCESS(
            "\nDone. Log in as any of these (password: %s):" % DEMO_PASSWORD
        ))
        for u in users.values():
            self.stdout.write(f"  {u.email}")

    # ── Users ────────────────────────────────────────────────────────────

    def _seed_users(self):
        self.stdout.write("Seeding users…")
        specs = [
            dict(
                email="luna@ecobasa.demo", name="Luna Feldmann",
                about="Professional composter, amateur philosopher. Has strong opinions about worms.",
                world="Turns kitchen scraps into arguments about soil pH.",
                ecobasa_what="Finding a home for 17kg of zucchini before it finds one for me.",
                location_name="Görlitz, Germany", point=(14.9857, 51.1642),
            ),
            dict(
                email="bjorn@ecobasa.demo", name="Björn Achterberg",
                about="Recovering banker turned goat whisperer. The goats are winning.",
                world="Redistributes firewood with more enthusiasm than technique.",
                ecobasa_what="Trading spreadsheets for compost heaps, one day at a time.",
                location_name="Bautzen, Germany", point=(14.4290, 51.1810),
            ),
            dict(
                email="mireille@ecobasa.demo", name="Mireille Dubois",
                about="Fermenting things since before it was cool. Ask me about my kombucha SCOBY hotel.",
                world="Believes most conflicts can be resolved with a jar of sauerkraut.",
                ecobasa_what="Finding someone whose sourdough starter has better boundaries than my ex.",
                location_name="Ariège, France", point=(1.6069, 42.9622),
            ),
            dict(
                email="diego@ecobasa.demo", name="Diego Fernández",
                about="Shepherd, dreamer, terrible singer (ask the goats — they have complaints).",
                world="Builds things out of mud and stubbornness.",
                ecobasa_what="A wheelbarrow whose wheels still believe in themselves.",
                location_name="Extremadura, Spain", point=(-6.3372, 39.4750),
            ),
            dict(
                email="ana@ecobasa.demo", name="Ana Costa",
                about="Still finalizing the WhatsApp group name. Send land tips.",
                world="Manifesting an ecovillage via group chat and vibes.",
                ecobasa_what="A single, solitary plan for anything at all.",
                location_name="Alentejo, Portugal", point=(-7.9147, 38.5667),
            ),
            dict(
                email="sam@ecobasa.demo", name="Sam de Groot",
                about="Turns bureaucratic forms into modern art. Mostly out of spite.",
                world="Fights the printer so nobody else has to.",
                ecobasa_what="A printer that isn't possessed by a bureaucratic demon.",
                location_name="Utrecht, Netherlands", point=(5.1214, 52.0907),
            ),
            dict(
                email="valeria@ecobasa.demo", name="Valeria Mora",
                about="Grows cacao, raises seedlings, loses daily arguments with the howler monkeys.",
                world="Keeps a seed bank in a fridge that also, regrettably, holds the cheese.",
                ecobasa_what="Sending moringa north to people who think a frost is a personality trait.",
                location_name="Puerto Viejo de Talamanca, Costa Rica", point=(-82.7539, 9.6560),
            ),
        ]

        users = {}
        for spec in specs:
            user, created = User.objects.get_or_create(
                email=spec["email"],
                defaults={
                    "name": spec["name"],
                    "about": spec["about"],
                    "world": spec["world"],
                    "ecobasa_what": spec["ecobasa_what"],
                    "location_name": spec["location_name"],
                    "location": Point(*spec["point"], srid=4326),
                },
            )
            if created:
                user.set_password(DEMO_PASSWORD)
                user.save()
            users[spec["email"]] = user
        return users

    # ── Communities ──────────────────────────────────────────────────────

    def _seed_communities(self, users):
        self.stdout.write("Seeding communities…")
        specs = [
            dict(
                name="Sonnenkraut Ecovillage", owner="luna@ecobasa.demo",
                type=Community.COMMUNITY_TYPE_ECOVILLAGE, status=Community.COMMUNITY_STATUS_ESTABLISHED,
                vision="A thriving mess of vegetables, opinions, and mostly-functional compost toilets.",
                description="Est. long enough ago that nobody remembers who planted the first zucchini, or why so many.",
                accomodation="Couch, tent spot, or a yurt if you don't mind the resident spider.",
                inhabitants=14, children=3, max_guests=6,
                location_name="Görlitz, Germany", point=(14.9857, 51.1642),
            ),
            dict(
                name="Kombucha Commune", owner="mireille@ecobasa.demo",
                type=Community.COMMUNITY_TYPE_COMUNE, status=Community.COMMUNITY_STATUS_STARTING,
                vision="Everything ferments eventually — vegetables, ideas, minor disagreements about chores.",
                description="Three years in, still arguing about the chore wheel, deeply in love with our SCOBYs.",
                accomodation="Guest room available, SCOBY hotel viewing included at no extra charge.",
                inhabitants=7, children=1, max_guests=3,
                location_name="Ariège, France", point=(1.6069, 42.9622),
            ),
            dict(
                name="Barefoot Bureaucracy House Project", owner="sam@ecobasa.demo",
                type=Community.COMMUNITY_TYPE_HOUSEPROJECT, status=Community.COMMUNITY_STATUS_ESTABLISHED,
                vision="Consensus decisions, laminated meeting agendas, and surprisingly good soup.",
                description="We turned a old bureaucracy building's paperwork obsession into a well-run household.",
                accomodation="Spare room upstairs. Please read the house agreement (it's laminated, we're serious).",
                inhabitants=9, children=0, max_guests=2,
                location_name="Utrecht, Netherlands", point=(5.1214, 52.0907),
                # The laminated sign on the door says visitors are welcome
                location_public=True,
            ),
            dict(
                name="Three Goats and a Dream Farm", owner="diego@ecobasa.demo",
                type=Community.COMMUNITY_TYPE_FARM, status=Community.COMMUNITY_STATUS_ESTABLISHED,
                vision="Regenerative grazing, mud architecture, and goats who run the place in all but name.",
                description="Started with a dream and one goat. Now three goats, still one dream, more mud.",
                accomodation="Bring your own boots. The goats will judge them regardless.",
                inhabitants=5, children=0, max_guests=4,
                location_name="Extremadura, Spain", point=(-6.3372, 39.4750),
            ),
            dict(
                name="The Someday Ecovillage (Still Just a WhatsApp Group)", owner="ana@ecobasa.demo",
                type=Community.COMMUNITY_TYPE_PROJECT, status=Community.COMMUNITY_STATUS_PLANNING,
                vision="Land, community, purpose — we're 90% vision board, 10% actual plan.",
                description="47 members strong. Zero hectares acquired. Group chat activity: extremely high.",
                accomodation="TBD, pending literally any land at all.",
                inhabitants=None, children=None, max_guests=None,
                location_name="", point=None,
            ),
        ]

        communities = {}
        for spec in specs:
            defaults = {
                "owner": users[spec["owner"]],
                "type": spec["type"],
                "status": spec["status"],
                "vision": spec["vision"],
                "description": spec["description"],
                "accomodation": spec["accomodation"],
                "inhabitants": spec["inhabitants"],
                "children": spec["children"],
                "max_guests": spec["max_guests"],
                "location_name": spec["location_name"],
                "location": Point(*spec["point"], srid=4326) if spec["point"] else None,
            }
            community, _created = Community.objects.get_or_create(
                name=spec["name"], defaults=defaults,
            )
            # Also on older demo data
            if community.location_public != spec.get("location_public", False):
                community.location_public = spec.get("location_public", False)
                community.save(update_fields=["location_public"])
            communities[spec["name"]] = community
        return communities

    # ── Listings ─────────────────────────────────────────────────────────

    def _seed_listings(self, users):
        self.stdout.write("Seeding listings…")
        specs = [
            dict(
                title="Zucchini", type="offer",
                owner="luna@ecobasa.demo",
                description="17 kg of surplus zucchini (please, we beg you). They will not stop. "
                            "We have tried everything. Take them, we have more.",
                image="zucchini.jpg", quantity=17, unit="kg", kind=Listing.KIND_FOOD,
            ),
            dict(
                title="Slightly judgmental goat, free to a good home", type="offer",
                owner="bjorn@ecobasa.demo", category="animals",
                description="Comes with opinions about your fence height. Excellent weeder, terrible listener.",
                image="goat.jpg",
            ),
            dict(
                title="Kombucha SCOBY", type="offer",
                owner="mireille@ecobasa.demo",
                description="Comes with a 45-minute lecture on gut health. The lecture is technically "
                            "optional. The SCOBY is not.",
                image="kombucha.jpg", kind=Listing.KIND_FOOD,
            ),
            dict(
                title="Wheelbarrow", type="wish",
                owner="diego@ecobasa.demo", kind=Listing.KIND_TOOL,
                description="Desperately seeking one with actual working wheels. Ours now travels "
                            "exclusively in gentle, tragic circles.",
            ),
            dict(
                title="Printer", type="wish",
                owner="sam@ecobasa.demo", kind=Listing.KIND_TOOL,
                description="One that isn't possessed by a bureaucratic demon. Ours only prints when "
                            "it senses fear. We are all very afraid.",
            ),
            dict(
                title="Yoga mat", type="offer",
                owner="ana@ecobasa.demo", kind=Listing.KIND_MATERIAL, quantity=4, unit="pieces",
                description="Hand-me-downs, only slightly haunted. Previous owner achieved great inner "
                            "peace, then moved to Bali. Mats remain.",
            ),
            dict(
                title="Scaffolding", type="wish",
                owner="luna@ecobasa.demo", kind=Listing.KIND_TOOL,
                description="To fix our leaning composting toilet. It has a nice view for now. That "
                            "will not last much longer.",
            ),
            dict(
                title="Firewood", type="offer",
                owner="bjorn@ecobasa.demo", kind=Listing.KIND_MATERIAL, quantity=3, unit="m3",
                description="Chopped with more enthusiasm than technique. Sizes range from 'kindling' "
                            "to 'geological event'. Burns fine either way.",
            ),
            dict(
                title="Wish: someone who understands sourdough starters better than my ex", type="wish",
                owner="mireille@ecobasa.demo", kind=Listing.KIND_KNOWLEDGE,
                description="Low bar. My ex thought 'discard' meant throwing away the whole jar.",
            ),
            dict(
                title="Box of permaculture books, mild goat-chew damage", type="offer",
                owner="diego@ecobasa.demo", category="books-learning",
                description="Chapter on fencing is unfortunately the most eaten. Ironic, the goats thought so too.",
            ),
        ]

        for spec in specs:
            owner = users[spec["owner"]]
            listing, created = Listing.objects.get_or_create(
                title=spec["title"], owner=owner,
                defaults={
                    "type": spec["type"],
                    "kind": spec.get("kind", Listing.KIND_OTHER),
                    "description": spec["description"],
                    **{key: spec[key] for key in ("quantity", "unit") if key in spec},
                },
            )
            # Also on older demo data
            _as_the_form_would(listing, spec.get("kind", Listing.KIND_OTHER), spec.get("category"))
            if spec.get("image") and not listing.image:
                _seed_image(listing.image, spec["image"])
                listing.save(update_fields=["image"])

    def _thing(self, holder, type, kind, title, category=None, **fields):
        """A thing a person or community offers or wishes for, by its title."""
        holder_fields = (
            {"community": holder} if isinstance(holder, Community) else {"owner": holder, "community": None}
        )
        listing, created = Listing.objects.get_or_create(
            title=title, type=type, project=None, **holder_fields, defaults={"kind": kind, **fields},
        )
        _as_the_form_would(listing, kind, category)
        return listing, created

    def _seed_seeds_and_plants(self, users, communities):
        """Seeds and plants in every form they are passed on in, temperate to tropical: the
        crop is the title, as the form only takes one from the vocabulary."""
        self.stdout.write("Seeding seeds & plants…")
        luna, bjorn, mireille = users["luna@ecobasa.demo"], users["bjorn@ecobasa.demo"], users["mireille@ecobasa.demo"]
        diego, sam, ana = users["diego@ecobasa.demo"], users["sam@ecobasa.demo"], users["ana@ecobasa.demo"]
        valeria = users["valeria@ecobasa.demo"]
        last_year = timezone.localdate().year - 1
        OFFER, WISH, SEEDS_PLANTS = Listing.TYPE_OFFER, Listing.TYPE_WISH, Listing.KIND_SEEDS_PLANTS
        specs = [
            # (holder, type, crop, fields)
            (luna, OFFER, "Beefsteak tomato", dict(
                variety="Ochsenherz", plant_form=Listing.PLANT_FORM_SEEDS, harvest_year=last_year,
                open_pollinated=True, quantity=12, unit="packets",
                description="Saved from the one tomato plant the zucchini didn't smother.")),
            (mireille, OFFER, "Fig", dict(
                variety="Ronde de Bordeaux", plant_form=Listing.PLANT_FORM_CUTTING, hardiness_zone=7,
                quantity=10, unit="pieces",
                description="Rooted in a jar on the windowsill, next to the SCOBYs. They get along.")),
            (bjorn, OFFER, "Apple", dict(
                variety="Boskoop", plant_form=Listing.PLANT_FORM_SCION, hardiness_zone=4, quantity=20, unit="pieces",
                description="Cut in January from a tree older than my banking career, and far more useful.")),
            (bjorn, OFFER, "Rhubarb", dict(
                plant_form=Listing.PLANT_FORM_OFFSHOOT, hardiness_zone=3, quantity=4, unit="pieces",
                description="Divided with a spade and an apology.")),
            (ana, OFFER, "Jerusalem artichoke", dict(
                plant_form=Listing.PLANT_FORM_TUBER, quantity=3, unit="kg",
                description="Plant them once, have them forever. Like the WhatsApp group.")),
            (communities["Sonnenkraut Ecovillage"], OFFER, "Seed potato", dict(
                variety="Linda", plant_form=Listing.PLANT_FORM_TUBER, quantity=20, unit="kg",
                description="An old variety, kept going by the village since a seed company dropped it.")),
            (valeria, OFFER, "Moringa", dict(
                plant_form=Listing.PLANT_FORM_SEEDS, harvest_year=last_year, open_pollinated=True,
                quantity=30, unit="packets",
                description="The tree grows faster than the monkeys can steal its pods. Barely.")),
            (valeria, OFFER, "Cacao", dict(
                variety="Criollo", plant_form=Listing.PLANT_FORM_YOUNG_PLANT, hardiness_zone=11, quantity=6,
                unit="pieces", description="Six months old, already sulking whenever it drops below 20 °C.")),
            (diego, WISH, "Moringa", dict(
                plant_form=Listing.PLANT_FORM_YOUNG_PLANT, hardiness_zone=9,
                description="For the sunny wall. The goats have promised to leave it alone (they lie).")),
            (sam, WISH, "Runner bean", dict(
                plant_form=Listing.PLANT_FORM_SEEDS, open_pollinated=True,
                description="Open-pollinated please, so I can save my own and stop asking.")),
            (sam, WISH, "Apple", dict(
                plant_form=Listing.PLANT_FORM_ROOTSTOCK, hardiness_zone=8,
                description="To graft scions onto. I have watched four videos and feel ready.")),
            (valeria, WISH, "Avocado", dict(
                variety="Hass", plant_form=Listing.PLANT_FORM_SCION, hardiness_zone=11,
                description="Our seedlings grow beautifully and fruit terribly. Time for grafting.")),
        ]
        for holder, type, crop, fields in specs:
            self._thing(holder, type, SEEDS_PLANTS, crop, **fields)

        # A seed swap waiting for an answer: Sam asks for two of the twelve packets
        tomatoes = Listing.objects.get(owner=luna, kind=SEEDS_PLANTS, title="Beefsteak tomato")
        match, created = self._get_or_create_match(
            from_user=sam, recipient=luna, target=tomatoes,
            message="Two packets for the balcony? I'll report back on how they fare against the pigeons.",
            location_type=Match.LOC_CUSTOM, proposed_location="By post",
        )
        if created:
            Contribution.objects.filter(match=match, listing=tomatoes).update(quantity=2)
        self._notify(recipient=luna, actor=sam, tag=Notification.TAG_REQUESTED, match=match)

    def _seed_community_photos(self, communities):
        self.stdout.write("Seeding community photos…")
        specs = [
            ("Sonnenkraut Ecovillage", "permaculture_garden.jpg"),
            ("Kombucha Commune", "community_garden.jpg"),
            ("Three Goats and a Dream Farm", "cob_hut.jpg"),
        ]
        for community_name, filename in specs:
            community = communities[community_name]
            if community.photos.exists():
                continue
            photo = CommunityPhoto(community=community)
            _seed_image(photo.image, filename)
            photo.save()

    # ── Skills ───────────────────────────────────────────────────────────

    def _seed_skills(self):
        self.stdout.write("Seeding skills…")
        names = [
            "Permaculture Design", "Natural Building", "Beekeeping", "Bread Baking",
            "Yoga", "Herbal Medicine", "Nonviolent Communication",
            "Solar Panel Installation", "Woodworking", "Fermentation",
        ]
        skills = {}
        for name in names:
            skill, _created = Skill.objects.get_or_create(name=name)
            skills[name] = skill
        return skills

    def _seed_user_skills(self, users, skills):
        self.stdout.write("Seeding user skills…")
        specs = [
            ("luna@ecobasa.demo", "Permaculture Design", Listing.LEVEL_EXPERT,
             "Can diagnose a struggling food forest from across the road."),
            ("luna@ecobasa.demo", "Nonviolent Communication", Listing.LEVEL_ADVANCED,
             "Mostly used on the chore wheel disputes."),
            ("bjorn@ecobasa.demo", "Woodworking", Listing.LEVEL_INTERMEDIATE,
             "Furniture is sturdy. Aesthetics are 'rustic', we've decided."),
            ("bjorn@ecobasa.demo", "Beekeeping", Listing.LEVEL_BEGINNER,
             "The bees mostly tolerate me. I consider this a professional relationship."),
            ("mireille@ecobasa.demo", "Fermentation", Listing.LEVEL_EXPERT,
             "SCOBY whisperer. Ask about the hotel. Please ask about the hotel."),
            ("mireille@ecobasa.demo", "Bread Baking", Listing.LEVEL_ADVANCED,
             "Starter has a name and, allegedly, a personality."),
            ("diego@ecobasa.demo", "Natural Building", Listing.LEVEL_ADVANCED,
             "Mud, straw, stubbornness. In that order of importance."),
            ("diego@ecobasa.demo", "Yoga", Listing.LEVEL_BEGINNER,
             "The goats don't judge my downward dog. Everyone else does."),
            ("sam@ecobasa.demo", "Solar Panel Installation", Listing.LEVEL_INTERMEDIATE,
             "Can wire a panel. Cannot, yet, defeat the printer."),
            ("sam@ecobasa.demo", "Herbal Medicine", Listing.LEVEL_BEGINNER,
             "Mostly just tea so far. Ambitious about the future."),
            ("ana@ecobasa.demo", "Yoga", Listing.LEVEL_ADVANCED,
             "Can hold a pose longer than the WhatsApp group can hold a decision."),
            ("ana@ecobasa.demo", "Nonviolent Communication", Listing.LEVEL_INTERMEDIATE,
             "Still working on applying it to group-chat land debates."),
        ]
        for email, skill_name, level, desc in specs:
            Listing.objects.get_or_create(
                owner=users[email], community=None, type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL,
                skill=skills[skill_name], defaults={"level": level, "description": desc},
            )

    def _seed_community_skills(self, communities, skills):
        self.stdout.write("Seeding community skills…")
        specs = [
            ("Sonnenkraut Ecovillage", "Permaculture Design",
             "Full food forest tour, zucchini samples guaranteed."),
            ("Sonnenkraut Ecovillage", "Beekeeping",
             "Hands-on, mostly-safe introduction to our four hives."),
            ("Kombucha Commune", "Fermentation",
             "SCOBY hotel tour included. Lecture length may vary."),
            ("Kombucha Commune", "Bread Baking",
             "Sourdough, taught by a starter with strong opinions."),
            ("Three Goats and a Dream Farm", "Natural Building",
             "Mud walls, straw roofs, and unsolicited goat supervision."),
            ("Barefoot Bureaucracy House Project", "Solar Panel Installation",
             "Learn to wire a panel. Printer exorcism not included."),
        ]
        for community_name, skill_name, desc in specs:
            Listing.objects.get_or_create(
                community=communities[community_name], project=None, type=Listing.TYPE_OFFER,
                kind=Listing.KIND_SKILL, skill=skills[skill_name], defaults={"description": desc},
            )

    def _seed_skill_wishes(self, users, communities, skills):
        self.stdout.write("Seeding skill wishes…")
        user_specs = [
            ("bjorn@ecobasa.demo", "Fermentation", Listing.LEVEL_BEGINNER,
             "I want my sauerkraut to stop trying to kill me."),
            ("sam@ecobasa.demo", "Natural Building", Listing.LEVEL_BEGINNER,
             "So I can build a shed that isn't just spite and duct tape."),
        ]
        for email, skill_name, level, desc in user_specs:
            Listing.objects.get_or_create(
                owner=users[email], community=None, type=Listing.TYPE_WISH, kind=Listing.KIND_SKILL,
                skill=skills[skill_name], defaults={"level": level, "description": desc},
            )

        community_specs = [
            ("Three Goats and a Dream Farm", "Nonviolent Communication",
             "So goat-ownership disputes stop requiring a formal mediator."),
            ("The Someday Ecovillage (Still Just a WhatsApp Group)", "Permaculture Design",
             "So we have literally any plan at all, beyond 'vibes'."),
        ]
        for community_name, skill_name, desc in community_specs:
            # A community looks for people with the skill: helping hands with it
            Listing.objects.get_or_create(
                community=communities[community_name], project=None, type=Listing.TYPE_WISH,
                kind=Listing.KIND_HANDS, skill=skills[skill_name], defaults={"description": desc},
            )

    # ── Matches, messages, volunteer details, notifications ─────────────

    def _get_or_create_match(self, from_user, recipient, target, **defaults):
        ct = ContentType.objects.get_for_model(target)
        match, created = Match.objects.get_or_create(
            from_user=from_user, recipient=recipient,
            content_type=ct, object_id=str(target.pk),
            defaults=defaults,
        )
        if created and isinstance(target, Listing):
            # What the exchange is about is part of it (and covers it, once accepted)
            Contribution.objects.create(match=match, listing=target)
        return match, created

    def _notify(self, recipient, actor, tag, match=None, verb="", is_read=False, age_days=0):
        # Notifications about a match build their text from tag + match at display time;
        # `verb` is only the stored fallback copy.
        notification, created = Notification.objects.get_or_create(
            recipient=recipient, actor=actor, tag=tag, match=match,
            defaults={"link": match.get_absolute_url() if match else "", "is_read": is_read},
        )
        if created:
            notification.verb = verb or notification.text[:255]
            notification.save(update_fields=["verb"])
            if age_days:
                Notification.objects.filter(pk=notification.pk).update(
                    created_at=timezone.now() - timedelta(days=age_days)
                )
        return notification

    def _seed_matches_and_notifications(self, users, communities):
        self.stdout.write("Seeding matches, messages & notifications…")
        luna, bjorn, mireille = users["luna@ecobasa.demo"], users["bjorn@ecobasa.demo"], users["mireille@ecobasa.demo"]
        diego, sam, ana = users["diego@ecobasa.demo"], users["sam@ecobasa.demo"], users["ana@ecobasa.demo"]

        zucchini = Listing.objects.get(title="Zucchini", owner=luna)
        starter_wish = Listing.objects.get(title__startswith="Wish: someone who understands sourdough", owner=mireille)
        luna_permaculture = Listing.objects.get(owner=luna, type="offer", skill__name="Permaculture Design")
        kombucha_fermentation = Listing.objects.get(
            community=communities["Kombucha Commune"], type="offer", skill__name="Fermentation",
        )
        bjorn_fermentation_wish = Listing.objects.get(owner=bjorn, type="wish", skill__name="Fermentation")
        three_goats_farm = communities["Three Goats and a Dream Farm"]

        # 1. Listing offer target — accepted: Björn takes 3 of the 17 kg (his reference
        #    about it is written after this exchange)
        match1, created1 = self._get_or_create_match(
            from_user=bjorn, recipient=luna, target=zucchini,
            message="I'll trade you one (1) slightly judgmental goat for a fair share of that zucchini haul.",
            location_type=Match.LOC_YOUR_PLACE,
        )
        if created1:
            Contribution.objects.filter(match=match1, listing=zucchini).update(quantity=3)
            MatchMessage.objects.create(
                match=match1, sender=luna, body="Keep the goat. Take as much as you can carry.",
                status_to=Match.STATUS_ACCEPTED,
            )
            Match.objects.filter(pk=match1.pk).update(
                status=Match.STATUS_ACCEPTED, created_at=timezone.now() - timedelta(days=9),
                responded_at=timezone.now() - timedelta(days=8),
            )
        self._notify(
            recipient=luna, actor=bjorn, tag=Notification.TAG_REQUESTED,
            match=match1, is_read=True, age_days=9,
        )
        self._notify(
            recipient=bjorn, actor=luna, tag=Notification.TAG_ACCEPTED,
            match=match1, is_read=True, age_days=8,
        )

        # 2. Listing wish target — accepted, with a small conversation
        match2, created2 = self._get_or_create_match(
            from_user=ana, recipient=mireille, target=starter_wish,
            message="I've been told my starter has strong opinions but ultimately works. Interested?",
            location_type=Match.LOC_YOUR_PLACE,
        )
        if created2:
            Match.objects.filter(pk=match2.pk).update(created_at=timezone.now() - timedelta(days=5))
            MatchMessage.objects.create(match=match2, sender=mireille, body="Does it argue back? Mine does.")
            MatchMessage.objects.create(match=match2, sender=ana, body="Only on Tuesdays.")
            MatchMessage.objects.create(
                match=match2, sender=mireille, body="Sold.", status_to=Match.STATUS_ACCEPTED,
            )
            match2.status = Match.STATUS_ACCEPTED
            match2.responded_at = timezone.now() - timedelta(days=4)
            match2.save()
        self._notify(
            recipient=ana, actor=mireille, tag=Notification.TAG_ACCEPTED,
            match=match2, is_read=True, age_days=4,
        )
        self._notify(
            recipient=mireille, actor=ana, tag=Notification.TAG_MESSAGE,
            match=match2, is_read=True, age_days=5,
        )

        # 3. A person's skill — declined
        match3, created3 = self._get_or_create_match(
            from_user=sam, recipient=luna, target=luna_permaculture,
            message="Any chance of a permaculture design session for our house project's back garden?",
            location_type=Match.LOC_YOUR_PLACE,
        )
        if created3:
            Match.objects.filter(pk=match3.pk).update(created_at=timezone.now() - timedelta(days=6))
            MatchMessage.objects.create(
                match=match3, sender=luna,
                body="Sorry, fully booked lecturing the zucchini this month. Try me in spring?",
                status_to=Match.STATUS_DECLINED,
            )
            match3.status = Match.STATUS_DECLINED
            match3.responded_at = timezone.now() - timedelta(days=5)
            match3.save()
        self._notify(
            recipient=sam, actor=luna, tag=Notification.TAG_DECLINED,
            match=match3, age_days=5,
        )

        # 4. A community's skill — counter-proposed
        match4, created4 = self._get_or_create_match(
            from_user=diego, recipient=mireille, target=kombucha_fermentation,
            message="Could I swing by this weekend to learn the fermentation basics?",
            location_type=Match.LOC_YOUR_PLACE,
        )
        if created4:
            Match.objects.filter(pk=match4.pk).update(created_at=timezone.now() - timedelta(days=1))
            MatchMessage.objects.create(
                match=match4, sender=mireille,
                body="This weekend the SCOBY hotel is fully booked (long story). Next week instead?",
                status_to=Match.STATUS_COUNTER,
                counter_location_type=Match.LOC_YOUR_PLACE,
                counter_date=timezone.now() + timedelta(days=9),
            )
            match4.status = Match.STATUS_COUNTER
            match4.save()
        self._notify(
            recipient=diego, actor=mireille, tag=Notification.TAG_COUNTER,
            match=match4, age_days=1,
        )

        # 5. A wish to learn a skill — pending
        match5, created5 = self._get_or_create_match(
            from_user=mireille, recipient=bjorn, target=bjorn_fermentation_wish,
            message="I can save your sauerkraut. No lecture required. Okay — maybe a small one.",
            location_type=Match.LOC_MY_PLACE,
        )
        self._notify(
            recipient=bjorn, actor=mireille, tag=Notification.TAG_REQUESTED,
            match=match5,
        )

        # 6. Community target (volunteering) — accepted, with VolunteerDetails
        match6, created6 = self._get_or_create_match(
            from_user=sam, recipient=diego, target=three_goats_farm,
            message="Could I come volunteer for a couple of weeks? Happy to help with the solar setup.",
            location_type=Match.LOC_YOUR_PLACE,
        )
        if created6:
            Match.objects.filter(pk=match6.pk).update(created_at=timezone.now() - timedelta(days=10))
            VolunteerDetails.objects.get_or_create(
                match=match6,
                defaults={
                    "volunteer_mode": "offer",
                    "stay_from": timezone.now() + timedelta(days=14),
                    "stay_to": timezone.now() + timedelta(days=28),
                    "practice_skills": "Natural Building, Yoga",
                    "practice_skill_level": Listing.LEVEL_BEGINNER,
                    "sender_skills": "Solar Panel Installation",
                },
            )
            MatchMessage.objects.create(
                match=match6, sender=diego,
                body="The goats have been informed. They have no objections (they never do, until they do).",
                status_to=Match.STATUS_ACCEPTED,
            )
            match6.status = Match.STATUS_ACCEPTED
            match6.responded_at = timezone.now() - timedelta(days=9)
            match6.save()
        self._notify(
            recipient=sam, actor=diego, tag=Notification.TAG_ACCEPTED,
            match=match6, is_read=True, age_days=9,
        )

        # Skill nudge — no actor, just a system-ish prompt
        self._notify(
            recipient=bjorn, actor=None, tag=Notification.TAG_SKILL_NUDGE, verb=str(SKILL_NUDGE_TEXT),
            age_days=3,
        )

    # ── Lending, and a public good ───────────────────────────────────────

    def _loan(self, borrower, listing, first_day, last_day, status, message, from_time=None, until_time=None):
        """A request to borrow a thing to lend, from first_day until last_day (days from
        today), by the hour with times."""
        lender = listing.manager
        match, created = self._get_or_create_match(
            from_user=borrower, recipient=lender, target=listing, message=message,
            location_type=Match.LOC_YOUR_PLACE,
        )
        if created:
            today = timezone.localdate()
            starts_at, ends_at = loan_span(
                today + timedelta(days=first_day), today + timedelta(days=last_day), from_time, until_time,
            )
            Loan.objects.create(match=match, starts_at=starts_at, ends_at=ends_at)
            if status == Match.STATUS_ACCEPTED:
                MatchMessage.objects.create(match=match, sender=lender, body="It's yours for those days.",
                                            status_to=status)
                Match.objects.filter(pk=match.pk).update(status=status, responded_at=timezone.now())
        if status == Match.STATUS_ACCEPTED:
            self._notify(recipient=borrower, actor=lender, tag=Notification.TAG_ACCEPTED, match=match)
        else:
            self._notify(recipient=lender, actor=borrower, tag=Notification.TAG_REQUESTED, match=match)
        return match

    def _seed_lending(self, users, communities):
        """Tools and vehicles to lend (a person's, and a community's car sharing), one to
        borrow, loans by the day and by the hour, a public good and food to share."""
        from datetime import time

        self.stdout.write("Seeding things to lend, a public good & food…")
        luna, bjorn, diego = users["luna@ecobasa.demo"], users["bjorn@ecobasa.demo"], users["diego@ecobasa.demo"]
        sam, ana = users["sam@ecobasa.demo"], users["ana@ecobasa.demo"]
        sonnenkraut = communities["Sonnenkraut Ecovillage"]
        OFFER, WISH = Listing.TYPE_OFFER, Listing.TYPE_WISH

        ladder, _created = self._thing(
            bjorn, OFFER, Listing.KIND_TOOL, "Ladder", lend=True, quantity=1,
            description="Seven metres, aluminium, survived one goat. Back by dinner time, please.",
        )
        van, _created = self._thing(
            sonnenkraut, OFFER, Listing.KIND_VEHICLE, "Van", lend=True,
            description="The village van. Smells faintly of compost, drives fully of character.",
        )
        self._thing(
            sam, OFFER, Listing.KIND_VEHICLE, "Cargo bike", lend=True,
            description="A bakfiets that has carried three children, a sofa and once, briefly, a goat.",
        )
        self._thing(
            diego, WISH, Listing.KIND_VEHICLE, "Trailer", lend=True,
            description="For one weekend of hauling clay. The trailer will come back browner but loved.",
        )
        # By the hour, waiting for an answer, and by the day, agreed
        self._loan(luna, ladder, 2, 2, Match.STATUS_PENDING,
                   "Could I borrow the ladder on Saturday morning? The compost toilet roof calls.",
                   from_time=time(9), until_time=time(13))
        self._loan(bjorn, van, 3, 4, Match.STATUS_ACCEPTED,
                   "Could I take the van for two days? Firewood delivery, very enthusiastic.")

        self._thing(
            luna, OFFER, Listing.KIND_FOOD, "Apples", public_good=True, location_public=True,
            location_name="Old railway path, Görlitz", location=Point(14.9712, 51.1718, srid=4326),
            description="Windfall apples along the old railway path. Three old trees nobody owns. "
                        "Bring a bag, leave the wasps their share.",
        )
        # Saved from the bin, past its date and still good; and a wish the apples and
        # the zucchini fit (fruit and vegetables are broader things)
        self._thing(
            ana, OFFER, Listing.KIND_FOOD, "Peanut butter", quantity=24, unit="pieces",
            best_before=timezone.localdate() - timedelta(days=45),
            description="A shop cleared its shelf: 24 jars, a few weeks past the date and still perfectly nutty.",
        )
        self._thing(
            diego, WISH, Listing.KIND_FOOD, "Fruit",
            description="For the jam-making weekend. Bruised, wormy, windfall: all welcome, the pot forgives.",
        )

    # ── Goods around the map ─────────────────────────────────────────────

    def _seed_goods_around(self, users, communities):
        """What comes out of houses taken down (windows, doors, tiles, mirrors, bricks) and
        common goods of every kind, each in a place of its own near its person or community,
        so the map shows every kind of marker spread out. Titles are names from the
        vocabularies, as the form only takes those for tools, materials, vehicles, seeds
        and food; the details are in the description."""
        self.stdout.write("Seeding salvaged and common goods around the map…")
        luna, bjorn, mireille = users["luna@ecobasa.demo"], users["bjorn@ecobasa.demo"], users["mireille@ecobasa.demo"]
        diego, ana, sam = users["diego@ecobasa.demo"], users["ana@ecobasa.demo"], users["sam@ecobasa.demo"]
        valeria = users["valeria@ecobasa.demo"]
        goats, barefoot = communities["Three Goats and a Dream Farm"], communities["Barefoot Bureaucracy House Project"]
        OFFER, WISH = Listing.TYPE_OFFER, Listing.TYPE_WISH
        MATERIAL, TOOL, VEHICLE = Listing.KIND_MATERIAL, Listing.KIND_TOOL, Listing.KIND_VEHICLE
        FOOD, SEEDS_PLANTS, OTHER = Listing.KIND_FOOD, Listing.KIND_SEEDS_PLANTS, Listing.KIND_OTHER
        specs = [
            # (holder, type, kind, title, place, (lon, lat), fields)
            (luna, OFFER, MATERIAL, "Wooden window", "Zittau", (14.8072, 50.8962), dict(
                quantity=6, unit="pieces",
                description="From a farmhouse being taken down. Single glazing, lovely old frames, "
                            "ideal for a cold frame or a greenhouse wall.")),
            (luna, OFFER, MATERIAL, "Floor tiles", "Löbau", (14.6770, 51.0990), dict(
                quantity=25, unit="m2",
                description="30 × 30, terracotta-coloured, carefully chiselled off. Some grout still "
                            "attached at no extra charge.")),
            (luna, OFFER, MATERIAL, "Mirror", "Weißwasser", (14.6370, 51.5050), dict(
                quantity=1, unit="pieces",
                description="Big hallway mirror from the same house. Reflects well, judges nobody.")),
            (bjorn, OFFER, MATERIAL, "Reclaimed brick", "Kamenz", (14.0939, 51.2686), dict(
                quantity=800, unit="pieces",
                description="From an old barn wall, mostly cleaned. Bring gloves and a trailer.")),
            (bjorn, OFFER, TOOL, "Pallet breaker", "Hoyerswerda", (14.2489, 51.4376), dict(
                lend=True, quantity=1,
                description="Turns pallets into planks without turning planks into splinters.")),
            (bjorn, OFFER, MATERIAL, "Lamp", "Bischofswerda", (14.1797, 51.1272), dict(
                quantity=3, unit="pieces",
                description="Three enamel ceiling lamps from a closed-down school. Rewired, tested.")),
            (mireille, WISH, MATERIAL, "Glass bottle", "Mirepoix", (1.8733, 43.0878), dict(
                quantity=300, unit="pieces",
                description="For a bottle wall in the fermentation room. Green and brown preferred.")),
            (mireille, OFFER, TOOL, "Tile nippers", "Lavelanet", (1.8481, 42.9311), dict(
                lend=True, quantity=1,
                description="For mosaics out of broken tiles. Comes with a plaster for the first try.")),
            (mireille, WISH, MATERIAL, "Stove tiles", "Saint-Girons", (1.1458, 42.9847), dict(
                description="Rebuilding an old tiled stove. Any colour, as long as they are complete.")),
            (diego, OFFER, MATERIAL, "Roof tile", "Trujillo", (-5.8826, 39.4597), dict(
                quantity=400, unit="pieces",
                description="Old curved clay tiles from a collapsed shed. Some moss, all character.")),
            (diego, OFFER, MATERIAL, "Front door", "Plasencia", (-6.0884, 40.0303), dict(
                quantity=1, unit="pieces",
                description="Solid chestnut, 90 × 210 cm, with the frame. Needs paint and a little love.")),
            (goats, OFFER, VEHICLE, "Tractor", "Navalmoral de la Mata", (-5.5422, 39.8919), dict(
                lend=True,
                description="Older than all three goats together. Starts on the second try, usually.")),
            (ana, OFFER, MATERIAL, "Cork", "Montemor-o-Novo", (-8.2172, 38.6481), dict(
                quantity=200, unit="kg",
                description="Bark offcuts from this year's harvest. Insulation, floats, pin boards.")),
            (ana, OFFER, FOOD, "Olive", "Estremoz", (-7.5906, 38.8441), dict(
                quantity=20, unit="kg",
                description="From the old grove behind the house. Bitter until you cure them.")),
            (ana, OFFER, OTHER, "Sofa", "Beja", (-7.8632, 38.0151), dict(
                category="furniture",
                description="Three-seater, green, seen better decades. Very comfortable for naps.")),
            (sam, OFFER, MATERIAL, "Interior door", "Amersfoort", (5.3878, 52.1561), dict(
                quantity=5, unit="pieces",
                description="Panel doors from a renovation, 83 cm wide, with handles and hinges.")),
            (sam, OFFER, TOOL, "Glass suction lifter", "Zeist", (5.2332, 52.0894), dict(
                lend=True, quantity=1,
                description="Two cups. For carrying old windows and big tiles without dropping them.")),
            (barefoot, OFFER, MATERIAL, "Pallet", "Nieuwegein", (5.0808, 52.0292), dict(
                quantity=30, unit="pieces",
                description="Euro pallets from the house's moving-in. Our upcycling ambitions ran out first.")),
            (sam, OFFER, MATERIAL, "Mineral wool", "Utrecht Lunetten", (5.1370, 52.0610), dict(
                quantity=12, unit="m2",
                description="Leftover rolls from the attic, bought as a lot and over-ordered by a third. "
                            "Wear a mask, it itches like regret.")),
            (bjorn, OFFER, MATERIAL, "Building material leftovers", "Radeberg", (13.9214, 51.1166), dict(
                description="A trailer-load from a junk lot: half bags of screed and plaster, primer, "
                            "skirting boards, cable conduit, two rolls of vapour barrier.")),
            (mireille, OFFER, MATERIAL, "Bathtub", "Pamiers", (1.6108, 43.1164), dict(
                quantity=1, unit="pieces",
                description="Cast iron, clawfoot, heavier than our disagreements. Makes a great pond.")),
            (diego, WISH, MATERIAL, "Hot tub", "Cáceres", (-6.3711, 39.4753), dict(
                description="Or a wooden bathing barrel. For the goats' spa day (and ours).")),
            (valeria, OFFER, MATERIAL, "Bamboo poles", "Cahuita", (-82.8394, 9.7369), dict(
                quantity=40, unit="pieces",
                description="Guadua, cut at the right moon, cured for a year. Four to six metres.")),
            (valeria, WISH, MATERIAL, "Solar panel", "Limón", (-83.0350, 9.9907), dict(
                quantity=2, unit="pieces",
                description="Used ones welcome. For the fridge, and for the monkeys' viewing pleasure.")),
            (valeria, OFFER, FOOD, "Banana", "Manzanillo", (-82.6553, 9.6331), dict(
                quantity=30, unit="kg",
                description="A whole bunch ripened at once. They always do.")),
            (valeria, OFFER, SEEDS_PLANTS, "Papaya", "Hone Creek", (-82.8000, 9.6900), dict(
                plant_form=Listing.PLANT_FORM_SEEDS, harvest_year=timezone.localdate().year - 1,
                open_pollinated=True, quantity=15, unit="packets",
                description="From the sweetest tree in the garden, dried on the porch.")),
        ]
        for holder, type, kind, title, place, (lon, lat), fields in specs:
            category = fields.pop("category", None)
            self._thing(holder, type, kind, title, category=category, location=Point(lon, lat, srid=4326),
                        location_name=place, **fields)

    # ── References ───────────────────────────────────────────────────────

    def _seed_references(self, users, communities):
        self.stdout.write("Seeding references…")
        luna, bjorn, mireille = users["luna@ecobasa.demo"], users["bjorn@ecobasa.demo"], users["mireille@ecobasa.demo"]
        diego, sam, ana = users["diego@ecobasa.demo"], users["sam@ecobasa.demo"], users["ana@ecobasa.demo"]
        P, N, X = Reference.IMPRESSION_POSITIVE, Reference.IMPRESSION_NEUTRAL, Reference.IMPRESSION_NEGATIVE
        CONFIRMED, PENDING, DECLINED = (
            ReferenceSkill.STATUS_CONFIRMED, ReferenceSkill.STATUS_PENDING, ReferenceSkill.STATUS_DECLINED,
        )

        specs = [
            # About a person — from the accepted sourdough match: gift name + a skill Ana
            # doesn't list yet, waiting for her to confirm it
            dict(author=mireille, subject=ana, impression=P, age_days=3,
                 text="Her starter argued with mine for an hour, then they made the best loaf of my life.",
                 gift_names=["Sourdough starter (opinionated)"], skills=[("Bread Baking", PENDING)]),
            # About a person — a skill they have (confirmed) and one of their offers by name
            dict(author=diego, subject=bjorn, impression=P, age_days=12,
                 text="Built us a gate the goat can't open. The goat is furious. We are delighted.",
                 gift_names=["Slightly judgmental goat"], skills=[("Woodworking", CONFIRMED)]),
            # About a community — from the accepted volunteer stay; one tag declined
            dict(author=sam, subject=communities["Three Goats and a Dream Farm"], impression=P, age_days=8,
                 text="Two weeks of mud walls and goat supervision. Came for solar, stayed for the cob.",
                 skills=[("Natural Building", CONFIRMED), ("Yoga", DECLINED)]),
            dict(author=mireille, subject=communities["Sonnenkraut Ecovillage"], impression=N, age_days=20,
                 text="Lovely people. I now own more zucchini than I own furniture."),
            # About a listing
            dict(author=bjorn, subject=Listing.objects.get(title="Zucchini", owner=luna),
                 match=Match.objects.filter(from_user=bjorn, content_type__model="listing", object_id__in=Listing.objects.filter(
                     title="Zucchini", owner=luna).values("pk")).first(),
                 impression=N, age_days=6,
                 text="Took three kilos. Fourteen more followed me home. I did not ask questions."),
            # About a user skill
            dict(author=luna, subject=Listing.objects.get(owner=diego, type="offer", skill__name="Natural Building"),
                 impression=P, age_days=15,
                 text="Taught me to read a wall by knocking on it. The wall now knocks back. Highly recommended."),
            # About a community skill — the one negative
            dict(author=ana, subject=Listing.objects.get(
                    community=communities["Kombucha Commune"], type="offer", skill__name="Fermentation"),
                 impression=X, age_days=2,
                 text="The lecture lasted three hours and had an intermission. The SCOBY was lovely though."),
        ]

        for spec in specs:
            subject = spec["subject"]
            reference, created = Reference.objects.get_or_create(
                author=spec["author"],
                content_type=ContentType.objects.get_for_model(subject),
                object_id=str(subject.pk),
                defaults={
                    "recipient": subject if isinstance(subject, User) else subject.get_match_owner(),
                    "impression": spec["impression"],
                    "text": spec["text"],
                    "gift_names": spec.get("gift_names", []),
                    "match": spec.get("match"),
                },
            )
            if not created:
                continue
            Reference.objects.filter(pk=reference.pk).update(
                created_at=timezone.now() - timedelta(days=spec["age_days"])
            )
            for skill_name, status in spec.get("skills", []):
                skill, _created = Skill.objects.get_or_create(name=skill_name)
                ReferenceSkill.objects.create(reference=reference, skill=skill, status=status)
            notify_reference_created(reference)
            Notification.objects.filter(reference=reference).update(
                created_at=timezone.now() - timedelta(days=spec["age_days"])
            )

    # ── Projects ─────────────────────────────────────────────────────────

    def _seed_projects(self, users, communities):
        """A dated project with needs and stays (confirmed, requested, overlapping so the
        calendar warns), an ongoing one, and a stale one whose ambassador gets asked."""
        from projects.forms import skill_for_title
        from projects.models import Project

        self.stdout.write("Seeding projects…")
        luna, bjorn, mireille = users["luna@ecobasa.demo"], users["bjorn@ecobasa.demo"], users["mireille@ecobasa.demo"]
        sam, diego = users["sam@ecobasa.demo"], users["diego@ecobasa.demo"]
        sonnenkraut = communities["Sonnenkraut Ecovillage"]
        kombucha = communities["Kombucha Commune"]
        today = timezone.localdate()

        def project(community, title, needs, learn=(), **fields):
            obj, created = Project.objects.get_or_create(
                community=community, title=title, defaults={"created_by": community.owner, **fields},
            )
            # What helpers can learn: the community's skills in the project, listed with it
            # while the project runs
            for name in learn:
                Listing.objects.get_or_create(
                    project=obj, type=Listing.TYPE_OFFER, kind=Listing.KIND_SKILL, skill=get_or_create_skill(name)[0],
                )
            # Needs (the community's wishes in it) are added by title, so re-running adds new
            # demo needs to older demo data
            for order, (kind, need_title, quantity, unit, details) in enumerate(needs):
                skill = None
                if kind in (Listing.KIND_HANDS, Listing.KIND_KNOWLEDGE):
                    skill = skill_for_title(need_title) or Skill.objects.filter(name__iexact=need_title).first()
                need, _need_created = Listing.objects.get_or_create(
                    project=obj, type=Listing.TYPE_WISH, title=need_title, defaults=dict(
                        kind=kind, order=order, quantity=quantity, unit=unit, description=details, skill=skill,
                    ),
                )
                # Tools and materials get their category from what they are
                _as_the_form_would(need)
            return obj, created

        stove, created = project(
            sonnenkraut, "Rocket stove for the community kitchen",
            [
                (Listing.KIND_HANDS, "Natural Building", 2, "people", ""),
                (Listing.KIND_HANDS, "Masonry", 1, "people", ""),
                (Listing.KIND_MATERIAL, "Field stones", 300, "pieces", "fist to head size"),
                (Listing.KIND_MATERIAL, "Clay", 200, "kg", ""),
                (Listing.KIND_MATERIAL, "Chimney pipe", 3, "m", "15 cm diameter"),
                (Listing.KIND_TOOL, "Concrete mixer", None, "", ""),
            ],
            learn=["Natural Building", "Masonry", "Rocket Stove Building"],
            description="Our old kitchen stove eats a forest a winter. We want to build a rocket stove "
                        "with a cob bench next to it, and learn how to build more of them.",
            starts_on=today + timedelta(days=7), ends_on=today + timedelta(days=50),
            food_provided=True, bed_provided=True, volunteers_wanted=4,
            provided_note="Tent spots, the workshop, a ride from Görlitz station",
        )
        project(
            sonnenkraut, "Food forest care",
            [
                (Listing.KIND_HANDS, "Permaculture Design", None, "", ""),
                (Listing.KIND_TOOL, "Scythe", 2, "pieces", ""),
                (Listing.KIND_HANDS, "Woodworking", 1, "people", "a bench under the old apple tree"),
            ],
            learn=["Permaculture Design"],
            description="Mulching, pruning and planting in our young food forest, whenever you are around.",
            food_provided=True,
        )
        stale, _stale_created = project(
            kombucha, "Straw-bale guest house",
            [(Listing.KIND_MATERIAL, "Straw bale", 120, "pieces", ""), (Listing.KIND_KNOWLEDGE, "Natural Building", None, "", "")],
            description="Planning a small guest house for the fermentation workshops.",
            food_provided=True,
        )
        Project.objects.filter(pk=stale.pk).update(updated_at=timezone.now() - timedelta(days=75))

        # Björn (Bautzen, 40 km away) is a woodworker and gives away scythes: the matching
        # suggests the food forest's needs to him, and him to Luna
        self._thing(bjorn, Listing.TYPE_OFFER, Listing.KIND_TOOL, "Scythe", quantity=2,
                    description="Two old ones, sharp enough, with a whetstone.")
        # Wishes for knowledge and helping hands work outside projects too
        Listing.objects.get_or_create(
            owner=sam, type=Listing.TYPE_WISH, kind=Listing.KIND_KNOWLEDGE, title="How to size a battery bank",
            defaults={"description": "Two panels, one fridge, a lot of optimism.", "skill": get_or_create_skill("Solar Panel Installation")[0]},
        )
        Listing.objects.get_or_create(
            owner=diego, type=Listing.TYPE_WISH, kind=Listing.KIND_HANDS, title="Helping hands for the clay harvest",
            defaults={"quantity": 3, "unit": "people", "description": "One weekend in spring, lunch included."},
        )

        if not created:
            return
        needs = {need.title: need for need in stove.needs()}
        stays = [
            # (who, from, to, status, {need: how much})
            (bjorn, 7, 21, Match.STATUS_ACCEPTED, {"Natural Building": 1, "Field stones": 120}),
            (mireille, 10, 17, Match.STATUS_ACCEPTED, {"Clay": 80}),
            (diego, 12, 26, Match.STATUS_PENDING, {"Masonry": 1, "Concrete mixer": None}),
            (sam, 14, 20, Match.STATUS_PENDING, {"Natural Building": 1}),
        ]
        for who, start, end, status, need_titles in stays:
            match = Match(from_user=who, recipient=luna, message="I'd love to help with the rocket stove!", status=status)
            match.target = stove
            match.save()
            VolunteerDetails.objects.create(
                match=match, volunteer_mode="wish",
                stay_from=timezone.now() + timedelta(days=start), stay_to=timezone.now() + timedelta(days=end),
            )
            for title, quantity in need_titles.items():
                Contribution.objects.create(listing=needs[title], match=match, quantity=quantity)
            if status == Match.STATUS_ACCEPTED:
                MatchMessage.objects.create(match=match, sender=luna, body="Welcome!", status_to=status)
                Match.objects.filter(pk=match.pk).update(responded_at=timezone.now())
