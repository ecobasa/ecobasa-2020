from django.core.management.base import BaseCommand

from references.inbox import fetch_replies


class Command(BaseCommand):
    help = "Save references sent by replying to the reference request email (run every few minutes)."

    def handle(self, *args, **options):
        saved = fetch_replies()
        self.stdout.write(f"{saved} references saved from replies")
