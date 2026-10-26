from django.core.management.base import BaseCommand

from projects.freshness import archive_stale_projects


class Command(BaseCommand):
    help = "Archive ended and unconfirmed projects, and ask about stale ones (run daily)."

    def handle(self, *args, **options):
        archived, reminded = archive_stale_projects()
        self.stdout.write(f"Archived {archived} project(s), asked about {reminded}.")
