"""
Loads the curated gift categories, in their themes, into ListingCategory.
Safe to re-run — uses update_or_create on slug.

    docker compose exec django python manage.py load_listing_categories
"""
from django.core.management.base import BaseCommand

# (theme, slug, en, de, es, fr, Font Awesome icon), in the order they are listed
CATEGORIES = [
    # ── Land & Food ─────────────────────────────────────────────────────
    ("land", "seeds-plants",          "Seeds & Plants",          "Saatgut & Pflanzen",          "Semillas y plantas",         "Graines & plantes", "fa-seedling"),
    ("land", "garden-farm",           "Garden & Farm",           "Garten & Hof",                "Huerto y granja",            "Jardin & ferme", "fa-tractor"),
    ("land", "animals",               "Animals & Animal care",   "Tiere & Tierbedarf",          "Animales y cuidado animal",  "Animaux & soins animaux", "fa-paw"),
    ("land", "food-preserves",        "Food & Preserves",        "Lebensmittel & Eingemachtes", "Alimentos y conservas",      "Alimentation & conserves", "fa-jar"),
    # ── Building & Energy ───────────────────────────────────────────────
    ("building", "building-renovation", "Building & Renovation", "Bauen & Renovieren",          "Construcción y reformas",    "Construction & rénovation", "fa-trowel-bricks"),
    ("building", "energy-heating",    "Energy & Heating",        "Energie & Heizen",            "Energía y calefacción",      "Énergie & chauffage", "fa-fire-flame-curved"),
    ("building", "water-sanitation",  "Water & Sanitation",      "Wasser & Sanitär",            "Agua y saneamiento",         "Eau & sanitaires", "fa-droplet"),
    ("building", "workshop-repair",   "Workshop & Repair",       "Werkstatt & Reparatur",       "Taller y reparación",        "Atelier & réparation", "fa-toolbox"),
    # ── Home & Living ───────────────────────────────────────────────────
    ("home", "kitchen-household",     "Kitchen & Household",     "Küche & Haushalt",            "Cocina y hogar",             "Cuisine & maison", "fa-kitchen-set"),
    ("home", "furniture",             "Furniture",               "Möbel",                       "Muebles",                    "Meubles", "fa-couch"),
    ("home", "clothing-textiles",     "Clothing & Textiles",     "Kleidung & Textilien",        "Ropa y textiles",            "Vêtements & textiles", "fa-shirt"),
    ("home", "children-toys",         "Children & Toys",         "Kinder & Spielzeug",          "Infancia y juguetes",        "Enfants & jouets", "fa-puzzle-piece"),
    ("home", "health-body",           "Health & Body care",      "Gesundheit & Körperpflege",   "Salud y cuidado personal",   "Santé & soins du corps", "fa-spa"),
    # ── On the Move ─────────────────────────────────────────────────────
    ("move", "bikes-vehicles",        "Bikes & Vehicles",        "Fahrräder & Fahrzeuge",       "Bicicletas y vehículos",     "Vélos & véhicules", "fa-bicycle"),
    ("move", "camping-travel",        "Camping & Travel gear",   "Camping & Reisebedarf",       "Camping y viaje",            "Camping & voyage", "fa-campground"),
    # ── Culture & Learning ──────────────────────────────────────────────
    ("culture", "books-learning",     "Books & Learning",        "Bücher & Lernen",             "Libros y aprendizaje",       "Livres & apprentissage", "fa-book"),
    ("culture", "music-instruments",  "Music & Instruments",     "Musik & Instrumente",         "Música e instrumentos",      "Musique & instruments", "fa-guitar"),
    ("culture", "arts-crafts",        "Arts & Crafts",           "Kunst & Handwerk",            "Arte y manualidades",        "Arts & artisanat", "fa-palette"),
    ("culture", "electronics-computers", "Electronics & Computers", "Elektronik & Computer",    "Electrónica e informática",  "Électronique & informatique", "fa-laptop"),
]


def load_categories(ListingCategory):
    """Create or update the curated categories; returns how many were created."""
    created = 0
    for order, (theme, slug, en, de, es, fr, icon) in enumerate(CATEGORIES):
        _obj, was_created = ListingCategory.objects.update_or_create(
            slug=slug,
            defaults={"theme": theme, "name": en, "names": {"de": de, "es": es, "fr": fr}, "icon": icon, "order": order},
        )
        created += was_created
    return created


class Command(BaseCommand):
    help = "Load the curated gift categories into ListingCategory (safe to re-run)"

    def handle(self, *args, **options):
        from gift_economy.gifts.models import ListingCategory
        created = load_categories(ListingCategory)
        self.stdout.write(self.style.SUCCESS(
            f"Done — {created} created, {len(CATEGORIES) - created} updated ({len(CATEGORIES)} total)"
        ))
