from django.core.management.base import BaseCommand

from gift_economy.matches.matching import match_everything


class Command(BaseCommand):
    help = "Match all existing wishes, offers, skills and project needs (once, after deploying the matching)."

    def add_arguments(self, parser):
        parser.add_argument("--notify", action="store_true", help="Also notify people about what was found.")

    def handle(self, *args, **options):
        self.stdout.write(f"Created {match_everything(notify=options['notify'])} suggestion(s).")
