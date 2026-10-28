from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from gift_economy.references.models import ReferenceRequest
from gift_economy.references.reference_requests import reply_address


class Command(BaseCommand):
    help = (
        "Development: answer a reference request email the way a mail app would, quoting it, "
        "so fetch_reference_replies can pick the reply up from Mailpit."
    )

    def add_arguments(self, parser):
        parser.add_argument("text", help="The reply")
        parser.add_argument("--key", help="Reference request key (default: the latest request)")
        parser.add_argument("--photo", help="Path of an image to attach")

    def handle(self, *args, text, key=None, photo=None, **options):
        if not settings.DEBUG:
            raise CommandError("Only for development.")
        requests = ReferenceRequest.objects.select_related("user")
        reference_request = requests.filter(key=key).first() if key else requests.order_by("-sent_at").first()
        if reference_request is None:
            raise CommandError("No such reference request.")
        to = reply_address(reference_request)
        if not to:
            raise CommandError("REFERENCE_REPLY_ADDRESS is not set.")
        sent = timezone.localtime(reference_request.sent_at).strftime("%a, %d %b %Y at %H:%M")
        message = EmailMessage(
            subject=f"Re: … [#{reference_request.key}]",
            body=f"{text}\n\nOn {sent}, {settings.DEFAULT_FROM_EMAIL} wrote:\n> Hello …\n",
            from_email=reference_request.user.email,
            to=[to],
        )
        if photo:
            message.attach_file(photo)
        message.send()
        self.stdout.write(f"Reply from {reference_request.user.email} sent to {to}")
