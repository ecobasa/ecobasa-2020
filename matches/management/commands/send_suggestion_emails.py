from django.core.management.base import BaseCommand

from matches.emails import send_suggestion_emails


class Command(BaseCommand):
    help = "Email people their new matches (run weekly)."

    def handle(self, *args, **options):
        self.stdout.write(f"Sent {send_suggestion_emails()} email(s).")
