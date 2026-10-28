from django.core.management.base import BaseCommand

from gift_economy.references.reference_requests import send_reference_requests


class Command(BaseCommand):
    help = "Ask both sides of matches that just happened for a reference (run daily)."

    def handle(self, *args, **options):
        sent = send_reference_requests()
        self.stdout.write(f"{sent} reference requests sent")
