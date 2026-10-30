"""Other things: furniture, household, clothes, children, culture, electronics.

Each entry: (slug, broader thing's slug, gift category slug, en, de, es, fr, other
names in any language separated by "|"). A broader thing goes before the narrower ones;
names are singular (plurals and German compounds are recognized, see gifts.things)."""

OTHER = [
    # ── Home, furniture ──────────────────────────────────────────────────
    ("furniture", "", "furniture", "Furniture", "Möbel", "Muebles", "Meubles", ""),
    ("table", "furniture", "furniture", "Table", "Tisch", "Mesa", "Table", "Esstisch|Schreibtisch|desk"),
    ("chair", "furniture", "furniture", "Chair", "Stuhl", "Silla", "Chaise", "Stühle|Hocker|stool|Bank|bench"),
    ("bed", "furniture", "furniture", "Bed", "Bett", "Cama", "Lit", "Betten|Hochbett|Etagenbett|bunk bed|Bettgestell|bed frame|Kinderbett"),
    ("sofa", "furniture", "furniture", "Sofa", "Sofa", "Sofá", "Canapé", "Couch|Sessel|armchair"),
    ("shelf", "furniture", "furniture", "Shelf", "Regal", "Estantería", "Étagère", "Bücherregal|shelves|Schrank|cupboard|wardrobe|Kleiderschrank"),
    # ── On the move, camping ─────────────────────────────────────────────
    ("sleeping-bag", "", "camping-travel", "Sleeping bag", "Schlafsack", "Saco de dormir", "Sac de couchage", "Isomatte|sleeping mat|Schlafmatte"),
    ("backpack", "", "camping-travel", "Backpack", "Rucksack", "Mochila", "Sac à dos", "Trekkingrucksack"),
    # ── Culture, electronics, children ───────────────────────────────────
    ("book", "", "books-learning", "Book", "Buch", "Libro", "Livre", "Bücher|Fachbuch|Roman|novel"),
    ("musical-instrument", "", "music-instruments", "Musical instrument", "Instrument", "Instrumento musical", "Instrument de musique", ""),
    ("guitar", "musical-instrument", "music-instruments", "Guitar", "Gitarre", "Guitarra", "Guitare", "Ukulele"),
    ("piano", "musical-instrument", "music-instruments", "Piano", "Klavier", "Piano", "Piano", "Keyboard|E-Piano"),
    ("drum", "musical-instrument", "music-instruments", "Drum", "Trommel", "Tambor", "Tambour", "Djembe|Schlagzeug|drum kit|Cajon"),
    ("laptop", "", "electronics-computers", "Laptop", "Laptop", "Portátil", "Ordinateur portable", "Notebook|Computer|Rechner|Tablet"),
    ("phone", "", "electronics-computers", "Phone", "Handy", "Teléfono", "Téléphone", "Smartphone|Mobiltelefon"),
    ("toys", "", "children-toys", "Toys", "Spielzeug", "Juguetes", "Jouets", "Spielsachen|Lego|Puppe|doll|Brettspiel|board game|Spiele|games"),
    ("pram", "", "children-toys", "Pram", "Kinderwagen", "Cochecito", "Poussette", "Buggy|stroller|Babytrage|Tragetuch|baby carrier"),
    ("child-seat", "", "children-toys", "Child seat", "Kindersitz", "Asiento infantil", "Siège enfant", "Fahrradsitz|Fahrradkindersitz"),
    ("sports-gear", "", "camping-travel", "Sports equipment", "Sportgeräte", "Material deportivo", "Matériel de sport", "Ski|Skier|Snowboard|Schlitten|sledge|Inliner|Tischtennisplatte|Slackline"),
    ("medical-aid", "", "health-body", "Mobility aid", "Gehhilfe", "Ayuda para movilidad", "Aide à la mobilité", "Rollstuhl|wheelchair|Krücken|crutches|Rollator"),
    ("mattress", "bed", "furniture", "Mattress", "Matratze", "Colchón", "Matelas", "Matratzen|mattress|Futon|Matratzenauflage|Topper|Gästematratze|Luftmatratze"),
    ("slatted-frame", "bed", "furniture", "Slatted bed base", "Lattenrost", "Somier de láminas", "Sommier à lattes", "Lattenroste|Rollrost|slatted frame|slatted base|Federholzrahmen"),
]
