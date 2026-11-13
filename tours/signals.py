from django.db.models.signals import post_save
from django.dispatch import receiver

from communities.models import Community


@receiver(post_save, sender=Community)
def rebuild_routes_through(sender, instance, **kwargs):
    """A community's place or whether it is public changed: the routes of tours that stop
    there (also at its events) go through its new public point (plan 5.5, rule 7)."""
    from .models import Tour

    for tour in Tour.objects.filter(stops__community=instance).distinct():
        tour.rebuild_route()
