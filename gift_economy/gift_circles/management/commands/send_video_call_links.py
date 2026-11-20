from django.core.management.base import BaseCommand

from gift_economy.gift_circles.video import send_links


class Command(BaseCommand):
    help = "Send the video call of online gift-circles starting in an hour to who comes (run every 5 minutes)."

    def handle(self, *args, **options):
        self.stdout.write(f"Sent {send_links()} video call link(s).")
