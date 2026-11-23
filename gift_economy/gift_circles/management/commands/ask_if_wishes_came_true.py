from django.core.management.base import BaseCommand

from gift_economy.gift_circles.wishes import send_questions


class Command(BaseCommand):
    help = "Ask who got a yes for a wish at a gift-circle two weeks ago whether it came true (run once a day)."

    def handle(self, *args, **options):
        self.stdout.write(f"Sent {send_questions()} email(s).")
