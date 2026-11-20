from django.core.management.base import BaseCommand

from gift_economy.gift_circles.reminders import send_reminders


class Command(BaseCommand):
    help = "Remind everyone who comes to a gift-circle tomorrow (run once a day)."

    def handle(self, *args, **options):
        self.stdout.write(f"Sent {send_reminders()} reminder(s).")
