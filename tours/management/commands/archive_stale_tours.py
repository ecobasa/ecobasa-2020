from django.core.management.base import BaseCommand

from tours.freshness import archive_stale_tours


class Command(BaseCommand):
    help = "Archive tours that are over and unconfirmed tour ideas, and ask about stale ones (run daily)."

    def handle(self, *args, **options):
        archived, reminded = archive_stale_tours()
        self.stdout.write(f"Archived {archived} tour(s), asked about {reminded}.")
