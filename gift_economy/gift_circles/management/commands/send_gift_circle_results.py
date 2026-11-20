from django.core.management.base import BaseCommand

from gift_economy.gift_circles.results import close_forgotten


class Command(BaseCommand):
    help = "Close the Giftsheets of past gift-circles nobody closed, and send their results (run once a day)."

    def handle(self, *args, **options):
        self.stdout.write(f"Closed {close_forgotten()} Giftsheet(s).")
