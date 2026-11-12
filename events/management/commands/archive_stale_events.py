from django.core.management.base import BaseCommand

from events.freshness import archive_stale_events


class Command(BaseCommand):
    help = "Archive ended and unconfirmed events, and ask about stale ones (run daily)."

    def handle(self, *args, **options):
        archived, reminded = archive_stale_events()
        self.stdout.write(f"Archived {archived} event(s), asked about {reminded}.")
