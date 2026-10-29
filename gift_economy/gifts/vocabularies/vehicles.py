"""Vehicles: bikes, cargo bikes, cars, vans, trailers, boats and machines that drive.

Each entry: (slug, broader thing's slug, gift category slug, en, de, es, fr, other
names in any language separated by "|"). A broader thing goes before the narrower ones;
names are singular (plurals and German compounds are recognized, see gifts.things)."""

VEHICLES = [
    # ── Bikes ────────────────────────────────────────────────────────────
    ("bicycle", "", "bikes-vehicles", "Bicycle", "Fahrrad", "Bicicleta", "Vélo", "Rad|bike|Drahtesel|bici"),
    ("city-bike", "bicycle", "bikes-vehicles", "City bike", "Stadtrad", "Bicicleta urbana", "Vélo de ville", "Hollandrad|Damenrad|Herrenrad|Citybike|Trekkingrad|trekking bike"),
    ("mountain-bike", "bicycle", "bikes-vehicles", "Mountain bike", "Mountainbike", "Bicicleta de montaña", "VTT", "MTB"),
    ("road-bike", "bicycle", "bikes-vehicles", "Road bike", "Rennrad", "Bicicleta de carretera", "Vélo de route", "Gravelbike|gravel bike"),
    ("e-bike", "bicycle", "bikes-vehicles", "E-bike", "E-Bike", "Bicicleta eléctrica", "Vélo électrique", "Pedelec|ebike|VAE"),
    ("kids-bike", "bicycle", "children-toys", "Children's bike", "Kinderfahrrad", "Bicicleta infantil", "Vélo enfant", "Laufrad|balance bike|draisienne"),
    ("tandem", "bicycle", "bikes-vehicles", "Tandem", "Tandem", "Tándem", "Tandem", ""),
    ("recumbent", "bicycle", "bikes-vehicles", "Recumbent", "Liegerad", "Bicicleta reclinada", "Vélo couché", "Velomobil"),
    ("tricycle", "bicycle", "bikes-vehicles", "Tricycle", "Dreirad", "Triciclo", "Tricycle", "Erwachsenendreirad"),
    ("cargo-bike", "bicycle", "bikes-vehicles", "Cargo bike", "Lastenrad", "Bicicleta de carga", "Vélo cargo", "Lastenfahrrad|Bakfiets|cargobike|Transportrad"),
    ("long-john", "cargo-bike", "bikes-vehicles", "Long John cargo bike", "Long John", "Bicicleta de carga Long John", "Biporteur", "Bakfiets zweirädrig"),
    ("longtail", "cargo-bike", "bikes-vehicles", "Longtail", "Longtail", "Longtail", "Longtail", "Longtail-Lastenrad"),
    ("cargo-trike", "cargo-bike", "bikes-vehicles", "Cargo trike", "Lastendreirad", "Triciclo de carga", "Triporteur", "Christiania|Lastenrad dreirädrig"),
    ("e-cargo-bike", "cargo-bike", "bikes-vehicles", "Electric cargo bike", "E-Lastenrad", "Bicicleta de carga eléctrica", "Vélo cargo électrique", "E-Cargobike|Lastenpedelec"),
    ("bike-trailer", "", "bikes-vehicles", "Bike trailer", "Fahrradanhänger", "Remolque de bicicleta", "Remorque vélo", "Radanhänger"),
    ("child-trailer", "bike-trailer", "children-toys", "Child bike trailer", "Kinderanhänger", "Remolque infantil", "Remorque enfant", "Fahrradkinderanhänger|Chariot|Croozer"),
    ("cargo-bike-trailer", "bike-trailer", "bikes-vehicles", "Cargo bike trailer", "Lastenanhänger", "Remolque de carga para bici", "Remorque de transport vélo", "Fahrradlastenanhänger|Carla Cargo"),
    # ── Small motor vehicles ─────────────────────────────────────────────
    ("e-scooter", "", "bikes-vehicles", "E-scooter", "E-Roller", "Patinete eléctrico", "Trottinette électrique", "E-Scooter|Tretroller|kick scooter"),
    ("motorbike", "", "bikes-vehicles", "Motorbike", "Motorrad", "Moto", "Moto", "Motorcycle"),
    ("moped", "motorbike", "bikes-vehicles", "Moped", "Moped", "Ciclomotor", "Mobylette", "Roller|Mofa|Vespa|scooter|Motorroller"),
    ("quad", "", "garden-farm", "Quad bike", "Quad", "Quad", "Quad", "ATV"),
    # ── Cars and vans ────────────────────────────────────────────────────
    ("car", "", "bikes-vehicles", "Car", "Auto", "Coche", "Voiture", "PKW|Wagen|automobile"),
    ("estate-car", "car", "bikes-vehicles", "Estate car", "Kombi", "Coche familiar", "Break", "station wagon"),
    ("electric-car", "car", "bikes-vehicles", "Electric car", "Elektroauto", "Coche eléctrico", "Voiture électrique", "E-Auto|EV"),
    ("off-road-car", "car", "bikes-vehicles", "Off-road vehicle", "Geländewagen", "Todoterreno", "Tout-terrain", "4x4|Allrad|Jeep"),
    ("van", "", "bikes-vehicles", "Van", "Transporter", "Furgoneta", "Camionnette", "Kleintransporter|Bulli|Sprinter|Lieferwagen"),
    ("minibus", "van", "bikes-vehicles", "Minibus", "Kleinbus", "Minibús", "Minibus", "Neunsitzer|9-Sitzer|Bus"),
    ("campervan", "van", "camping-travel", "Campervan", "Wohnmobil", "Autocaravana", "Camping-car", "Camper|Campingbus|Wohnmobil|motorhome|Bus mit Bett"),
    ("pickup", "", "bikes-vehicles", "Pickup truck", "Pick-up", "Camioneta", "Pick-up", "Pritschenwagen|Pritsche"),
    ("truck", "", "bikes-vehicles", "Truck", "LKW", "Camión", "Camion", "Lastwagen|Lastkraftwagen|7,5-Tonner|lorry"),
    # ── Trailers ─────────────────────────────────────────────────────────
    ("trailer", "", "bikes-vehicles", "Trailer", "Anhänger", "Remolque", "Remorque", "PKW-Anhänger|Hänger|Autoanhänger"),
    ("box-trailer", "trailer", "bikes-vehicles", "Box trailer", "Kastenanhänger", "Remolque cerrado", "Remorque fourgon", "Kofferanhänger|Planenanhänger|Hochplane"),
    ("tipper-trailer", "trailer", "bikes-vehicles", "Tipper trailer", "Kippanhänger", "Remolque basculante", "Remorque benne", "Kipper|Rückwärtskipper|Dreiseitenkipper"),
    ("car-trailer", "trailer", "bikes-vehicles", "Car transporter trailer", "Autotransporter", "Remolque portacoches", "Porte-voiture", "Autotrailer|Fahrzeugtransporter"),
    ("horse-trailer", "trailer", "animals", "Horse trailer", "Pferdeanhänger", "Remolque para caballos", "Van à chevaux", "Viehanhänger|livestock trailer|Tieranhänger"),
    ("boat-trailer", "trailer", "camping-travel", "Boat trailer", "Bootsanhänger", "Remolque para barcos", "Remorque bateau", "Slipwagen"),
    ("caravan", "trailer", "camping-travel", "Caravan", "Wohnwagen", "Caravana", "Caravane", "Campinganhänger|Bauwagen|Tiny House auf Rädern"),
    ("farm-trailer", "trailer", "garden-farm", "Farm trailer", "Ladewagen", "Remolque agrícola", "Remorque agricole", "Traktoranhänger|Kipper landwirtschaftlich|Heuwagen"),
    # ── Machines that drive ──────────────────────────────────────────────
    ("tractor", "", "garden-farm", "Tractor", "Traktor", "Tractor", "Tracteur", "Schlepper|Trecker|Kleintraktor|Einachsschlepper"),
    ("ride-on-mower", "tractor", "garden-farm", "Ride-on mower", "Aufsitzmäher", "Tractor cortacésped", "Tondeuse autoportée", "Rasentraktor"),
    ("mini-excavator", "", "building-renovation", "Mini excavator", "Minibagger", "Miniexcavadora", "Mini-pelle", "Bagger|excavator|digger|Kleinbagger"),
    ("dumper", "", "building-renovation", "Dumper", "Dumper", "Dúmper", "Dumper", "Motorschubkarre|Raupendumper|power barrow"),
    ("forklift", "", "building-renovation", "Forklift", "Gabelstapler", "Carretilla elevadora", "Chariot élévateur", "Stapler"),
    ("skid-steer", "", "building-renovation", "Skid steer loader", "Hoflader", "Minicargadora", "Chargeuse compacte", "Radlader|Kompaktlader|Bobcat|Hoftrac"),
    # ── On the water ─────────────────────────────────────────────────────
    ("boat", "", "camping-travel", "Boat", "Boot", "Barco", "Bateau", "Kahn"),
    ("canoe", "boat", "camping-travel", "Canoe", "Kanu", "Canoa", "Canoë", "Kanadier"),
    ("kayak", "boat", "camping-travel", "Kayak", "Kajak", "Kayak", "Kayak", "Faltboot"),
    ("rowing-boat", "boat", "camping-travel", "Rowing boat", "Ruderboot", "Bote de remos", "Barque", "Schlauchboot|dinghy"),
    ("sailing-boat", "boat", "camping-travel", "Sailing boat", "Segelboot", "Velero", "Voilier", "Jolle"),
    ("sup", "boat", "camping-travel", "Stand-up paddle board", "SUP", "Tabla de paddle surf", "Stand up paddle", "Stand-Up-Paddle|paddle board"),
]
