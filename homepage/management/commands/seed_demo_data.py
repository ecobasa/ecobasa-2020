"""
Seeds the local dev database with a small, tongue-in-cheek but structurally
complete demo dataset: users, communities (every type/status), listing
categories, listings (offers & wishes, some with photos), skills (every
level), skill wishes (user + community), matches (every status, every
target type), match messages, volunteer details, notifications
(every tag), and references (every impression and subject type, with
confirmed/pending/declined skill tags and gift names).

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
from gifts.models import Listing, ListingCategory
from matches.models import Match, MatchMessage, VolunteerDetails
from notifications.models import Notification, SKILL_NUDGE_TEXT
from references.models import Reference, ReferenceSkill
from references.notifications import notify_reference_created
from skills.models import CommunitySkill, Skill, SkillWish, UserSkill
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


class Command(BaseCommand):
    help = "Seed the local dev database with themed demo data (safe to re-run)"

    def handle(self, *args, **options):
        users = self._seed_users()
        communities = self._seed_communities(users)
        categories = self._seed_listing_categories()
        self._seed_listings(users, categories)
        self._seed_community_photos(communities)
        skills = self._seed_skills()
        self._seed_user_skills(users, skills)
        self._seed_community_skills(communities, skills)
        self._seed_skill_wishes(users, communities, skills)
        self._seed_matches_and_notifications(users, communities)
        self._seed_references(users, communities)

        self.stdout.write(self.style.SUCCESS(
            "\nDone. Log in as any of these (password: %s):" % DEMO_PASSWORD
        ))
        for u in users.values():
            self.stdout.write(f"  {u.email}")
        self.stdout.write(self.style.WARNING(
            "\nNote: no User.image avatars were seeded (attaching real people's "
            "photos to fictional profiles felt off) — some Listings and "
            "Communities do have photos now, see seed_images/SOURCES.md."
        ))

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
            communities[spec["name"]] = community
        return communities

    # ── Listing categories & listings ───────────────────────────────────

    def _seed_listing_categories(self):
        self.stdout.write("Seeding listing categories…")
        names = [
            "Garden & Farm", "Tools & Equipment", "Food & Preserves",
            "Household & Furniture", "Building Materials", "Books & Learning",
        ]
        categories = {}
        for order, name in enumerate(names):
            cat, _created = ListingCategory.objects.get_or_create(
                name=name, defaults={"order": order},
            )
            categories[name] = cat
        return categories

    def _seed_listings(self, users, categories):
        self.stdout.write("Seeding listings…")
        specs = [
            dict(
                title="17kg of surplus zucchini (please, we beg you)", type="offer",
                owner="luna@ecobasa.demo", category="Food & Preserves",
                description="They will not stop. We have tried everything. Take them, we have more.",
                image="zucchini.jpg",
            ),
            dict(
                title="Slightly judgmental goat, free to a good home", type="offer",
                owner="bjorn@ecobasa.demo", category="Garden & Farm",
                description="Comes with opinions about your fence height. Excellent weeder, terrible listener.",
                image="goat.jpg",
            ),
            dict(
                title="Kombucha SCOBY, comes with 45-minute lecture on gut health", type="offer",
                owner="mireille@ecobasa.demo", category="Food & Preserves",
                description="The lecture is technically optional. The SCOBY is not.",
                image="kombucha.jpg",
            ),
            dict(
                title="Desperately seeking a wheelbarrow with actual working wheels", type="wish",
                owner="diego@ecobasa.demo", category="Tools & Equipment",
                description="Ours now travels exclusively in gentle, tragic circles.",
            ),
            dict(
                title="Need: a printer that isn't possessed by a bureaucratic demon", type="wish",
                owner="sam@ecobasa.demo", category="Household & Furniture",
                description="It only prints when it senses fear. We are all very afraid.",
            ),
            dict(
                title="Hand-me-down yoga mats (only slightly haunted)", type="offer",
                owner="ana@ecobasa.demo", category="Household & Furniture",
                description="Previous owner achieved great inner peace, then moved to Bali. Mats remain.",
            ),
            dict(
                title="Looking for scaffolding to fix our leaning composting toilet", type="wish",
                owner="luna@ecobasa.demo", category="Building Materials",
                description="It has a nice view for now. That will not last much longer.",
            ),
            dict(
                title="Firewood, chopped with more enthusiasm than technique", type="offer",
                owner="bjorn@ecobasa.demo", category="Building Materials",
                description="Sizes range from 'kindling' to 'geological event'. Burns fine either way.",
            ),
            dict(
                title="Wish: someone who understands sourdough starters better than my ex", type="wish",
                owner="mireille@ecobasa.demo", category="Food & Preserves",
                description="Low bar. My ex thought 'discard' meant throwing away the whole jar.",
            ),
            dict(
                title="Box of permaculture books, mild goat-chew damage", type="offer",
                owner="diego@ecobasa.demo", category="Books & Learning",
                description="Chapter on fencing is unfortunately the most eaten. Ironic, the goats thought so too.",
            ),
        ]

        for spec in specs:
            owner = users[spec["owner"]]
            listing, created = Listing.objects.get_or_create(
                title=spec["title"], owner=owner,
                defaults={
                    "type": spec["type"],
                    "description": spec["description"],
                    "location_name": owner.location_name,
                    "location": owner.location,
                },
            )
            if created:
                listing.categories.add(categories[spec["category"]])
            if spec.get("image") and not listing.image:
                _seed_image(listing.image, spec["image"])
                listing.save(update_fields=["image"])

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
            ("luna@ecobasa.demo", "Permaculture Design", UserSkill.LEVEL_EXPERT,
             "Can diagnose a struggling food forest from across the road."),
            ("luna@ecobasa.demo", "Nonviolent Communication", UserSkill.LEVEL_ADVANCED,
             "Mostly used on the chore wheel disputes."),
            ("bjorn@ecobasa.demo", "Woodworking", UserSkill.LEVEL_INTERMEDIATE,
             "Furniture is sturdy. Aesthetics are 'rustic', we've decided."),
            ("bjorn@ecobasa.demo", "Beekeeping", UserSkill.LEVEL_BEGINNER,
             "The bees mostly tolerate me. I consider this a professional relationship."),
            ("mireille@ecobasa.demo", "Fermentation", UserSkill.LEVEL_EXPERT,
             "SCOBY whisperer. Ask about the hotel. Please ask about the hotel."),
            ("mireille@ecobasa.demo", "Bread Baking", UserSkill.LEVEL_ADVANCED,
             "Starter has a name and, allegedly, a personality."),
            ("diego@ecobasa.demo", "Natural Building", UserSkill.LEVEL_ADVANCED,
             "Mud, straw, stubbornness. In that order of importance."),
            ("diego@ecobasa.demo", "Yoga", UserSkill.LEVEL_BEGINNER,
             "The goats don't judge my downward dog. Everyone else does."),
            ("sam@ecobasa.demo", "Solar Panel Installation", UserSkill.LEVEL_INTERMEDIATE,
             "Can wire a panel. Cannot, yet, defeat the printer."),
            ("sam@ecobasa.demo", "Herbal Medicine", UserSkill.LEVEL_BEGINNER,
             "Mostly just tea so far. Ambitious about the future."),
            ("ana@ecobasa.demo", "Yoga", UserSkill.LEVEL_ADVANCED,
             "Can hold a pose longer than the WhatsApp group can hold a decision."),
            ("ana@ecobasa.demo", "Nonviolent Communication", UserSkill.LEVEL_INTERMEDIATE,
             "Still working on applying it to group-chat land debates."),
        ]
        for email, skill_name, level, desc in specs:
            UserSkill.objects.get_or_create(
                user=users[email], skill=skills[skill_name],
                defaults={"level": level, "description": desc},
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
            CommunitySkill.objects.get_or_create(
                community=communities[community_name], skill=skills[skill_name],
                defaults={"description": desc},
            )

    def _seed_skill_wishes(self, users, communities, skills):
        self.stdout.write("Seeding skill wishes…")
        user_specs = [
            ("bjorn@ecobasa.demo", "Fermentation", UserSkill.LEVEL_BEGINNER,
             "I want my sauerkraut to stop trying to kill me."),
            ("sam@ecobasa.demo", "Natural Building", UserSkill.LEVEL_BEGINNER,
             "So I can build a shed that isn't just spite and duct tape."),
        ]
        for email, skill_name, level, desc in user_specs:
            SkillWish.objects.get_or_create(
                user=users[email], skill=skills[skill_name],
                defaults={"level": level, "description": desc},
            )

        community_specs = [
            ("Three Goats and a Dream Farm", "Nonviolent Communication",
             "So goat-ownership disputes stop requiring a formal mediator."),
            ("The Someday Ecovillage (Still Just a WhatsApp Group)", "Permaculture Design",
             "So we have literally any plan at all, beyond 'vibes'."),
        ]
        for community_name, skill_name, desc in community_specs:
            SkillWish.objects.get_or_create(
                community=communities[community_name], skill=skills[skill_name],
                defaults={"description": desc},
            )

    # ── Matches, messages, volunteer details, notifications ─────────────

    def _get_or_create_match(self, from_user, recipient, target, **defaults):
        ct = ContentType.objects.get_for_model(target)
        match, created = Match.objects.get_or_create(
            from_user=from_user, recipient=recipient,
            content_type=ct, object_id=str(target.pk),
            defaults=defaults,
        )
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

        zucchini = Listing.objects.get(title__startswith="17kg of surplus zucchini", owner=luna)
        starter_wish = Listing.objects.get(title__startswith="Wish: someone who understands sourdough", owner=mireille)
        luna_permaculture = UserSkill.objects.get(user=luna, skill__name="Permaculture Design")
        kombucha_fermentation = CommunitySkill.objects.get(
            community=communities["Kombucha Commune"], skill__name="Fermentation",
        )
        bjorn_fermentation_wish = SkillWish.objects.get(user=bjorn, skill__name="Fermentation")
        three_goats_farm = communities["Three Goats and a Dream Farm"]

        # 1. Listing offer target — pending
        match1, created1 = self._get_or_create_match(
            from_user=bjorn, recipient=luna, target=zucchini,
            message="I'll trade you one (1) slightly judgmental goat for a fair share of that zucchini haul.",
            location_type=Match.LOC_YOUR_PLACE,
        )
        if created1:
            Match.objects.filter(pk=match1.pk).update(created_at=timezone.now() - timedelta(days=2))
        self._notify(
            recipient=luna, actor=bjorn, tag=Notification.TAG_REQUESTED,
            match=match1, age_days=2,
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

        # 3. UserSkill target — declined
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

        # 4. CommunitySkill target — counter-proposed
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

        # 5. SkillWish target — pending
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
                    "practice_skill_level": UserSkill.LEVEL_BEGINNER,
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
            dict(author=bjorn, subject=Listing.objects.get(title__startswith="17kg of surplus zucchini", owner=luna),
                 impression=N, age_days=6,
                 text="Took three kilos. Fourteen more followed me home. I did not ask questions."),
            # About a user skill
            dict(author=luna, subject=UserSkill.objects.get(user=diego, skill__name="Natural Building"),
                 impression=P, age_days=15,
                 text="Taught me to read a wall by knocking on it. The wall now knocks back. Highly recommended."),
            # About a community skill — the one negative
            dict(author=ana, subject=CommunitySkill.objects.get(
                    community=communities["Kombucha Commune"], skill__name="Fermentation"),
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
