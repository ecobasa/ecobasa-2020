"""
Loads the curated vocabularies of things (gifts/vocabularies/: tools, materials, vehicles,
other things) into Thing, so a wish for a "Leiter" finds an offered "ladder", and one for
a "saw" finds a "circular saw". Safe to re-run — uses update_or_create on slug — and then
recognizes the things in existing listings' titles again.

    docker compose exec django python manage.py load_vocabularies
"""
from django.core.management.base import BaseCommand

from gift_economy.gifts.vocabularies import VOCABULARIES


def load_vocabularies(Thing, ListingCategory=None):
    """Create or update the things of all vocabularies (broader ones first); returns how
    many were created."""
    categories = {c.slug: c for c in ListingCategory.objects.all()} if ListingCategory else {}
    by_slug = {}
    created = 0
    for kind, entries in VOCABULARIES.items():
        for slug, parent, category, en, de, es, fr, others in entries:
            thing, was_created = Thing.objects.update_or_create(slug=slug, defaults={
                "names": {"en": en, "de": de, "es": es, "fr": fr},
                "other_names": [name.strip() for name in others.split("|") if name.strip()],
                "kind": kind,
                "parent": by_slug.get(parent) if parent else None,
                "category": categories.get(category),
            })
            by_slug[slug] = thing
            created += was_created
    return created


class Command(BaseCommand):
    help = "Load the curated vocabularies of things into Thing and recognize them in listings (safe to re-run)"

    def handle(self, *args, **options):
        from gift_economy.gifts.models import Listing, ListingCategory, Thing
        from gift_economy.gifts.things import recognize_all
        created = load_vocabularies(Thing, ListingCategory)
        total = sum(len(entries) for entries in VOCABULARIES.values())
        recognized = recognize_all(Listing, Thing)
        self.stdout.write(self.style.SUCCESS(
            f"Done — {created} created, {total - created} updated ({total} total); {recognized} listings recognized"
        ))
