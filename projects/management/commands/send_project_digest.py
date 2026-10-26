from django.core.management.base import BaseCommand

from projects.digest import send_project_digests


class Command(BaseCommand):
    help = "Email people about projects nearby that need their skills or gifts (run weekly)."

    def handle(self, *args, **options):
        sent = send_project_digests()
        self.stdout.write(f"Sent {sent} project email(s).")
