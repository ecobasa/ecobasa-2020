"""Children: what they grow out of or need for a while, outdoors first (rain trousers,
rubber boots, snowsuits, woollen underwear), baby things (cloth nappies, bottles, a
nursing pillow, a cot, a high chair, a changing table), maternity clothes, toys, costumes,
sports gear, lunch boxes, water bottles, backpacks, school and drawing things, carving and
exploring gear, games consoles. Childcare is a skill ("Childcare"), not a thing.

Each entry: (slug, broader thing's slug, gift category slug, en, de, es, fr, other
names in any language separated by "|"). A broader thing goes before the narrower ones.
Clothes and shoes have a size (Listing.size, by SIZED_THINGS): everything under
"childrens-clothes" a clothing size, under "childrens-shoes", socks, ice skates and ski
boots a shoe size; maternity clothes, hats, scarves and gloves none. A slug follows the
English name, so things also made for grown-ups start with "childrens-" ("childrens-snowboard", "childrens-carving-set"); toys,
pram and child seat came from the other things, the children's bike from the vehicles
(car seats and bike trailers for children stay vehicles). Things also named for grown-ups
(snowboard, skis, scooter, carving tools, phone, paper) are named as the children's ones
("Kindersnowboard", "Kinderschnitzset"), so an "other" listing for a snowboard stays a
grown-up's. Children's things are always in "Children & Toys" too
(Listing.thing_categories)."""

T = "children-toys"
C = "clothing-textiles"

CHILDREN = [
    ("childrens-things", "", T, "Children's things", "Kindersachen", "Cosas de niños", "Affaires d'enfant", "Kinderkram|Babysachen|baby things|baby stuff|Babyausstattung|Erstausstattung|cosas de bebé|affaires de bébé"),

    # ── Clothes (with a size) ────────────────────────────────────────────
    ("childrens-clothes", "childrens-things", C, "Children's clothes", "Kinderkleidung", "Ropa infantil", "Vêtements d'enfant", "kids' clothes|Kinderklamotten|Babykleidung|baby clothes|Kleiderpaket|Kleidersack|Kleiderkiste|ropa de bebé|vêtements bébé"),
    # Outdoors, in all weathers
    ("outdoor-clothing", "childrens-clothes", C, "Outdoor clothing", "Outdoorkleidung", "Ropa de exterior", "Vêtements d'extérieur", "Draußenkleidung|Matschsachen|Waldkindergartenkleidung|outdoor wear|Funktionskleidung"),
    ("rain-trousers", "outdoor-clothing", C, "Rain trousers", "Regenhose", "Pantalón de lluvia", "Pantalon de pluie", "Matschhose|Buddelhose|Regenlatzhose|Matschlatzhose|rain pants|waterproof trousers|puddle pants|salopette de pluie"),
    ("rain-jacket", "outdoor-clothing", C, "Rain jacket", "Regenjacke", "Chubasquero", "Veste de pluie", "Matschjacke|Buddeljacke|waterproof jacket|raincoat|Regenmantel|Friesennerz|ciré|impermeable"),
    ("rain-suit", "outdoor-clothing", C, "Rain suit", "Regenoverall", "Mono de lluvia", "Combinaison de pluie", "Regenanzug|Matschoverall|Buddelanzug|puddle suit|Matschanzug"),
    ("snowsuit", "outdoor-clothing", C, "Snowsuit", "Schneeanzug", "Mono de nieve", "Combinaison de neige", "Skianzug|Schneeoverall|Winteroverall|pram suit|Kinderwagenoverall|ski suit|combinaison de ski"),
    ("ski-trousers", "outdoor-clothing", C, "Ski trousers", "Skihose", "Pantalón de esquí", "Pantalon de ski", "Schneehose|Thermohose|snow pants|salopette de ski"),
    ("winter-jacket", "outdoor-clothing", C, "Winter jacket", "Winterjacke", "Chaqueta de invierno", "Blouson d'hiver", "Anorak|Daunenjacke|Schneejacke|Wintermantel|parka|winter coat|doudoune|abrigo de invierno"),
    ("softshell", "outdoor-clothing", C, "Softshell jacket", "Softshelljacke", "Chaqueta softshell", "Veste softshell", "Softshell|Softshellhose|Softshelloverall|Übergangsjacke"),
    ("fleece", "outdoor-clothing", C, "Fleece", "Fleecejacke", "Forro polar", "Polaire", "Fleecepullover|Fleeceoverall|Fleecehose|fleece jacket|veste polaire"),
    ("woollen-underwear", "outdoor-clothing", C, "Woollen underwear", "Wollunterwäsche", "Ropa interior de lana", "Sous-vêtements en laine", "Merino|Merinounterwäsche|Wollbody|Woll-Seide|Wollwalk|Walkjacke|Walkoverall|Walkhose|Funktionsunterwäsche|Skiunterwäsche|thermal underwear|base layer|laine mérinos"),
    ("swimwear", "outdoor-clothing", C, "Swimwear", "Badesachen", "Bañador", "Maillot de bain", "Badeanzug|Badehose|Badeshorts|Badeshirt|UV-Badeshirt|UV-Badeanzug|Schwimmwindel|swimsuit|swimming trunks|Neoprenanzug|wetsuit"),
    # Everyday
    ("bodysuit", "childrens-clothes", C, "Bodysuit", "Body", "Body", "Body", "Bodys|Wickelbody|onesie|Strampler|romper|Strampelanzug|pelele|grenouillère"),
    ("trousers", "childrens-clothes", C, "Trousers", "Hose", "Pantalón", "Pantalon", "Hosen|Jeans|Leggings|Jogginghose|Latzhose|pants|dungarees|shorts|kurze Hose|pantalones"),
    ("tops", "childrens-clothes", C, "Tops", "Oberteile", "Camisetas y jerséis", "Hauts", "Oberteil|T-Shirt|Shirt|Pullover|Pulli|Sweatshirt|Hoodie|Langarmshirt|Strickjacke|cardigan|jumper|sweater|camiseta|jersey|pull|tee-shirt"),
    ("dress", "childrens-clothes", C, "Dress", "Kleid", "Vestido", "Robe", "Kleider|Rock|skirt|falda|jupe"),
    ("sleepwear", "childrens-clothes", C, "Pyjamas", "Schlafanzug", "Pijama", "Pyjama", "Schlafanzüge|pajamas|Nachthemd|nightie"),
    ("baby-sleeping-bag", "childrens-clothes", C, "Baby sleeping bag", "Babyschlafsack", "Saco de dormir de bebé", "Gigoteuse", "Schlafsack für Babys|Winterschlafsack|Sommerschlafsack|Pucksack|Strampelsack|sleep sack|swaddle|turbulette"),
    ("underwear", "childrens-clothes", C, "Underwear", "Unterwäsche", "Ropa interior", "Sous-vêtements", "Unterhosen|Unterhemd|Unterhemden|Strumpfhose|Strumpfhosen|tights|collants|braguitas|culottes"),
    # Socks go by shoe size (Listing.SIZED_THINGS)
    ("socks", "childrens-clothes", C, "Socks", "Socken", "Calcetines", "Chaussettes", "Socke|Strümpfe|Kniestrümpfe|Wollsocken|Stoppersocken|Rutschsocken|ABS-Socken|Skisocken|Wandersocken|wool socks|calcetines antideslizantes|chaussettes antidérapantes"),

    # ── Shoes (with a size) ──────────────────────────────────────────────
    ("childrens-shoes", "childrens-things", C, "Children's shoes", "Kinderschuhe", "Zapatos infantiles", "Chaussures d'enfant", "Schuhe|shoes|Babyschuhe|Lauflernschuhe|Barfußschuhe|barefoot shoes|zapatos|chaussures"),
    ("rubber-boots", "childrens-shoes", C, "Rubber boots", "Gummistiefel", "Botas de agua", "Bottes de pluie", "wellies|wellingtons|rain boots|gumboots|Regenstiefel|Matschstiefel|Buddelstiefel|katiuskas|bottes en caoutchouc"),
    ("winter-boots", "childrens-shoes", C, "Winter boots", "Winterstiefel", "Botas de invierno", "Bottes d'hiver", "Winterschuhe|Schneestiefel|snow boots|Thermostiefel|Moonboots|après-ski"),
    ("hiking-boots", "childrens-shoes", C, "Hiking boots", "Wanderschuhe", "Botas de montaña", "Chaussures de randonnée", "Wanderstiefel|Trekkingschuhe|Bergschuhe|hiking shoes"),
    ("sandals", "childrens-shoes", C, "Sandals", "Sandalen", "Sandalias", "Sandales", "Sandale|Trekkingsandalen|Badeschuhe|Wasserschuhe|water shoes|Clogs|Crocs|chanclas|sandalettes"),
    ("sneakers", "childrens-shoes", C, "Trainers", "Turnschuhe", "Zapatillas", "Baskets", "Sneaker|Sneakers|sneakers|Kinderturnschuhe|Halbschuhe|tenis"),
    ("sports-shoes", "childrens-shoes", C, "Sports shoes", "Sportschuhe", "Calzado deportivo", "Chaussures de sport", "Hallenschuhe|indoor shoes|Fußballschuhe|football boots|Stollenschuhe|Laufschuhe|running shoes|Kletterschuhe|zapatillas deportivas"),
    ("slippers", "childrens-shoes", C, "Slippers", "Hausschuhe", "Pantuflas", "Chaussons", "Puschen|Schlappen|Pantoffeln|Krabbelschuhe|Lederpuschen|Hüttenschuhe|zapatillas de casa|patucos"),

    # ── Hats, scarves, gloves (no size) ──────────────────────────────────
    ("hat", "childrens-things", C, "Hat", "Mütze", "Gorro", "Bonnet", "Mützen|beanie|Wintermütze|Strickmütze|Schlupfmütze|Schalmütze|Balaclava|Sturmhaube|Sonnenhut|sun hat|Schirmmütze|cap|Kappe|Hut|Regenhut|Südwester|sou'wester|gorra|chapeau"),
    ("scarf", "childrens-things", C, "Scarf", "Schal", "Bufanda", "Écharpe", "Schals|Loopschal|Halstuch|Schlauchschal|neck warmer|Buff|snood|cuello|tour de cou"),
    ("gloves", "childrens-things", C, "Gloves", "Handschuhe", "Guantes", "Gants", "Handschuh|Fäustlinge|Fäustling|mittens|Fausthandschuhe|Skihandschuhe|Matschhandschuhe|Regenhandschuhe|Fingerhandschuhe|manoplas|moufles"),

    # ── Nappies, carrying ────────────────────────────────────────────────
    ("cloth-nappies", "childrens-things", T, "Cloth nappies", "Stoffwindeln", "Pañales de tela", "Couches lavables", "Stoffwindel|cloth diapers|reusable nappies|Mullwindeln|Mullwindel|muslins|Prefolds|Windelüberhose|Überhose|nappy cover|Wollüberhose|Höschenwindel|Windeleinlagen|Moltontücher|pañales reutilizables"),
    ("pram", "childrens-things", T, "Pram", "Kinderwagen", "Cochecito", "Poussette", "Buggy|stroller|pushchair|Sportwagen|Fahrradanhänger für Kinder|carrito"),
    ("baby-carrier", "childrens-things", T, "Baby carrier", "Babytrage", "Portabebés", "Porte-bébé", "Tragetuch|Tragehilfe|sling|baby sling|Kraxe|Rückentrage|Kindertrage|hiking child carrier|fular"),
    ("child-seat", "childrens-things", T, "Child seat", "Kindersitz", "Asiento infantil", "Siège enfant", "Fahrradsitz|Fahrradkindersitz|bike seat|Kinderfahrradsitz"),
    ("nursing-pillow", "childrens-things", T, "Nursing pillow", "Stillkissen", "Cojín de lactancia", "Coussin d'allaitement", "Schwangerschaftskissen|pregnancy pillow|Seitenschläferkissen|Lagerungskissen|breastfeeding pillow|nursing cushion|almohada de lactancia"),
    ("baby-bottles", "childrens-things", "kitchen-household", "Baby bottles", "Babyfläschchen", "Biberones", "Biberons", "Fläschchen|Babyflasche|Babyflaschen|Glasfläschchen|feeding bottle|Sterilisator|Vaporisator|bottle steriliser|Flaschenwärmer|bottle warmer|biberón|biberon"),
    ("breast-pump", "childrens-things", "health-body", "Breast pump", "Milchpumpe", "Sacaleches", "Tire-lait", "Brustpumpe|Handmilchpumpe|elektrische Milchpumpe|extractor de leche"),
    ("potty", "childrens-things", "health-body", "Potty", "Töpfchen", "Orinal infantil", "Pot pour bébé", "Kindertöpfchen|Toilettensitz für Kinder|Toilettenaufsatz|Kindertoilettensitz|toilet trainer|Tritthocker|step stool|réducteur de toilettes|reductor de WC"),
    ("baby-monitor", "childrens-things", "electronics-computers", "Baby monitor", "Babyphone", "Vigilabebés", "Babyphone", "Babyfon|Babyphon|Video-Babyphone|baby phone|écoute-bébé|monitor de bebé"),
    ("maternity-clothes", "childrens-things", C, "Maternity clothes", "Umstandsmode", "Ropa premamá", "Vêtements de grossesse", "Umstandskleidung|Umstandshose|Umstandskleid|Schwangerschaftskleidung|Bauchband|Stillkleidung|Still-BH|Stilltop|nursing bra|nursing top|pregnancy clothes|ropa de lactancia|vêtements d'allaitement"),

    # ── Baby and children's furniture ───────────────────────────────────────,
    ("childrens-furniture", "childrens-things", "furniture", "Baby & children's furniture", "Baby- & Kindermöbel", "Muebles infantiles", "Meubles d'enfant", "Kindermöbel|Babymöbel|children's furniture|nursery furniture|Kinderzimmermöbel|muebles de bebé|mobilier enfant"),
    ("high-chair", "childrens-furniture", "furniture", "High chair", "Hochstuhl", "Trona", "Chaise haute", "Kinderhochstuhl|Treppenhochstuhl|Babystuhl|Sitzerhöhung|booster seat|chaise bébé"),
    ("cot", "childrens-furniture", "furniture", "Cot", "Kinderbett", "Cuna", "Lit bébé", "Babybett|Gitterbett|Kinderbettchen|Juniorbett|crib|Wiege|cradle|Stubenwagen|Moses basket|lit à barreaux|berceau"),
    ("travel-cot", "cot", "furniture", "Travel cot", "Reisebett", "Cuna de viaje", "Lit parapluie", "Reisebettchen|Kinderreisebett|travel crib|lit de voyage"),
    ("bedside-cot", "cot", "furniture", "Bedside cot", "Beistellbett", "Cuna de colecho", "Lit cododo", "Babybalkon|Anstellbett|co-sleeper|bedside crib|cododo|colecho"),
    ("changing-table", "childrens-furniture", "furniture", "Changing table", "Wickeltisch", "Cambiador", "Table à langer", "Wickelkommode|Wickelaufsatz|Wickelauflage|Wickelunterlage|changing mat|changing unit|matelas à langer|cambiador portátil"),
    ("baby-bath", "childrens-furniture", "health-body", "Baby bath", "Babybadewanne", "Bañera para bebé", "Baignoire bébé", "Babywanne|Badeeimer|Badewanneneinsatz|Badesitz|bath seat|baignoire pour bébé"),
    ("bouncer", "childrens-furniture", "furniture", "Baby bouncer", "Babywippe", "Hamaca para bebé", "Transat", "Wippe|Babyschaukel|baby swing|Federwiege|Hängewiege|baby rocker|bouncy chair|transat bébé|balancelle"),
    ("playpen", "childrens-furniture", "furniture", "Playpen", "Laufstall", "Parque infantil", "Parc bébé", "Laufgitter|Krabbelgitter|play yard|parque de bebé|parc à bébé"),
    ("baby-gate", "childrens-furniture", "furniture", "Baby gate", "Treppenschutzgitter", "Barrera de seguridad", "Barrière de sécurité", "Treppengitter|Türschutzgitter|Schutzgitter|stair gate|safety gate|barrera de escalera|barrière d'escalier"),
    ("childrens-desk-chair", "childrens-furniture", "furniture", "Children's desk & chair", "Kinderschreibtisch & -stuhl", "Escritorio y silla infantil", "Bureau et chaise enfant", "Kinderschreibtisch|Kinderstuhl|Kindertisch|Kindersitzgruppe|mitwachsender Schreibtisch|mitwachsender Stuhl|Schülerschreibtisch|children's desk|children's chair|children's table|pupitre"),

    # ── Lunch, drinks, backpacks ─────────────────────────────────────────
    ("lunchbox", "childrens-things", "kitchen-household", "Lunch box", "Brotdose", "Fiambrera", "Boîte à goûter", "Vesperdose|Vesperbox|Brotbox|Brotzeitdose|Brotzeitbox|Jausenbox|Jausendose|Znünibox|Lunchbox|Bento|Edelstahldose|Kindergartendose|lonchera|boîte à tartines"),
    ("water-bottle", "childrens-things", "kitchen-household", "Water bottle", "Trinkflasche", "Botella de agua", "Gourde", "Trinkflaschen|Kindertrinkflasche|Edelstahlflasche|Thermosflasche|Isolierflasche|Thermoskanne|sippy cup|Schnabeltasse|Trinklernbecher|cantimplora|bidón|termo"),
    ("childrens-backpack", "childrens-things", T, "Children's backpack", "Kinderrucksack", "Mochila infantil", "Sac à dos enfant", "Kindergartenrucksack|Kitarucksack|Kita-Rucksack|Schulranzen|Schulrucksack|Ranzen|school bag|satchel|cartable|mochila escolar"),

    # ── Toys ─────────────────────────────────────────────────────────────
    ("toys", "childrens-things", T, "Toys", "Spielzeug", "Juguetes", "Jouets", "Spielsachen|Holzspielzeug|wooden toys|juguete|jouet"),
    ("outdoor-toys", "toys", T, "Outdoor toys", "Draußenspielzeug", "Juguetes de exterior", "Jeux d'extérieur", "Sandspielzeug|Sandkastenspielzeug|sand toys|Buddelzeug|Eimer und Schaufel|bucket and spade|Wasserspielzeug|Schwimmflügel|Kescher|Seifenblasen|Straßenkreide|Springseil|Federball|Frisbee|Wikingerschach|Kubb|Schaukel|swing|Sandkasten|sandpit"),
    ("building-blocks", "toys", T, "Building blocks", "Bausteine", "Bloques de construcción", "Jeux de construction", "Bauklötze|Holzbausteine|Klemmbausteine|Kapla|Murmelbahn|marble run|bloques|cubes"),
    ("lego", "building-blocks", T, "Lego", "Lego", "Lego", "Lego", "Legosteine|Lego-Steine|Lego Technic|Lego City|Lego Friends|Legokiste|LEGO bricks"),
    ("duplo", "building-blocks", T, "Duplo", "Duplo", "Duplo", "Duplo", "Duplosteine|Duplo-Steine|Lego Duplo|Duplokiste"),
    ("board-games", "toys", T, "Board games", "Brettspiele", "Juegos de mesa", "Jeux de société", "Brettspiel|board game|Gesellschaftsspiel|Gesellschaftsspiele|Kartenspiel|Kartenspiele|card game|Würfelspiel|Spiele|games|Memory|juego de mesa|jeu de société"),
    ("puzzles", "toys", T, "Puzzles", "Puzzles", "Puzles", "Puzzles", "Puzzle|jigsaw puzzle|jigsaw|Holzpuzzle|Steckpuzzle|rompecabezas|casse-tête"),
    ("toy-vehicles", "toys", T, "Toy vehicles", "Spielfahrzeuge", "Vehículos de juguete", "Véhicules jouets", "Spielfahrzeug|Spielzeugauto|Spielzeugautos|toy car|toy cars|Matchbox|Siku|Spielzeugbagger|Spielzeugtraktor|Holzeisenbahn|Spielzeugeisenbahn|Brio|toy train|Carrerabahn|Autorennbahn|coches de juguete|petites voitures"),
    ("rc-vehicles", "toy-vehicles", T, "Remote-controlled vehicle", "Ferngesteuertes Fahrzeug", "Vehículo teledirigido", "Véhicule télécommandé", "ferngesteuerte Fahrzeuge|ferngesteuertes Auto|ferngesteuerte Autos|Fernsteuerauto|ferngesteuerter Bagger|ferngesteuertes Boot|remote control car|coche teledirigido|voiture télécommandée"),
    ("dolls", "toys", T, "Dolls & soft toys", "Puppen & Kuscheltiere", "Muñecas y peluches", "Poupées & peluches", "Puppe|doll|Kuscheltier|Stofftier|Teddy|Teddybär|soft toy|Puppenwagen|Puppenhaus|Kaufladen|Spielküche|play kitchen|muñeca|peluche"),
    ("costumes", "toys", T, "Costumes & dress-up", "Verkleidung & Kostüme", "Disfraces", "Déguisements", "Kostüm|Verkleidung|Faschingskostüm|Karnevalskostüm|Halloweenkostüm|Verkleidungskiste|dress-up|fancy dress|costume|disfraz|déguisement"),
    ("baby-toys", "toys", T, "Baby toys", "Babyspielzeug", "Juguetes para bebés", "Jouets d'éveil", "Rassel|rattle|Greifling|Beißring|teether|Motorikschleife|Spielbogen|Krabbeldecke|play mat|sonajero|hochet"),
    ("childrens-instruments", "toys", "music-instruments", "Children's instruments", "Kinderinstrumente", "Instrumentos infantiles", "Instruments pour enfant", "Blockflöte|recorder|Glockenspiel|Xylophon|xylophone|Kinderukulele|Kindergitarre|Kinderkeyboard|Orff-Instrumente|Rhythmusinstrumente|flauta dulce|flûte à bec|metalófono"),

    # ── Sports gear ──────────────────────────────────────────────────────
    ("childrens-sports-gear", "childrens-things", "camping-travel", "Children's sports gear", "Kindersportgeräte", "Material deportivo infantil", "Matériel de sport pour enfants", "Kindersportsachen|Sportsachen für Kinder"),
    ("childrens-bike", "childrens-sports-gear", "bikes-vehicles", "Children's bike", "Kinderfahrrad", "Bicicleta infantil", "Vélo enfant", "Kinderrad|kids' bike|Jugendrad|Jugendfahrrad|bici de niño"),
    ("balance-bike", "childrens-sports-gear", "bikes-vehicles", "Balance bike", "Laufrad", "Bicicleta sin pedales", "Draisienne", "Lauflernrad|push bike|run bike|Holzlaufrad"),
    ("childrens-tricycle", "childrens-sports-gear", "bikes-vehicles", "Children's tricycle", "Kinderdreirad", "Triciclo infantil", "Tricycle enfant", "Dreirad für Kinder"),
    ("ride-on", "childrens-sports-gear", T, "Ride-on toy", "Rutschauto", "Correpasillos", "Porteur", "Bobbycar|Bobby-Car|Rutscher|ride-on|Tretauto|pedal car"),
    ("childrens-scooter", "childrens-sports-gear", "bikes-vehicles", "Children's scooter", "Kinderroller", "Patinete infantil", "Trottinette enfant", "Kickboard|Laufroller|Tretroller für Kinder"),
    ("skateboard", "childrens-sports-gear", "camping-travel", "Skateboard", "Skateboard", "Skateboard", "Skateboard", "Longboard|Pennyboard|Penny board|patineta"),
    ("childrens-inline-skates", "childrens-sports-gear", "camping-travel", "Children's inline skates", "Kinderinliner", "Patines infantiles", "Rollers enfant", "Rollschuhe|roller skates|Kinderrollschuhe|patines|patins à roulettes"),
    ("childrens-snowboard", "childrens-sports-gear", "camping-travel", "Children's snowboard", "Kindersnowboard", "Snowboard infantil", "Snowboard enfant", "Kinder-Snowboard|Kindersnowboardboots|Kindersnowboardschuhe"),
    ("childrens-skis", "childrens-sports-gear", "camping-travel", "Children's skis", "Kinderski", "Esquís infantiles", "Skis enfant", "Kinderskier|Kinder-Ski|Kinderlanglaufski|Kinderskistöcke"),
    ("childrens-ski-boots", "childrens-sports-gear", "camping-travel", "Children's ski boots", "Kinderskischuhe", "Botas de esquí infantiles", "Chaussures de ski enfant", "Skischuhe|Skistiefel|Kinderskistiefel|Langlaufschuhe|Snowboardboots|Snowboardschuhe|ski boots|botas de esquí|chaussures de ski"),
    ("ice-skates", "childrens-sports-gear", "camping-travel", "Ice skates", "Schlittschuhe", "Patines de hielo", "Patins à glace", "Schlittschuh|Kinderschlittschuhe|Kufen|Doppelkufen|Gleitschuhe|Hockeyschlittschuhe|Eiskunstlaufschuhe|ice skate|patins"),
    ("trampoline", "childrens-sports-gear", T, "Trampoline", "Trampolin", "Cama elástica", "Trampoline", "Gartentrampolin|Minitrampolin|Indoortrampolin|trampolín"),
    ("sledge", "childrens-sports-gear", "camping-travel", "Sledge", "Schlitten", "Trineo", "Luge", "sled|Rodel|Rodelschlitten|Davoser|Poporutscher|Rutschteller|snow tube"),
    ("childrens-helmet", "childrens-sports-gear", T, "Children's helmet", "Kinderhelm", "Casco infantil", "Casque enfant", "Fahrradhelm|Skihelm|Kletterhelm|bike helmet|ski helmet|casco|casque"),

    # ── School, drawing, crafting ────────────────────────────────────────
    ("school-supplies", "childrens-things", "books-learning", "School supplies", "Schulsachen", "Material escolar", "Fournitures scolaires", "Schulbedarf|Schreibwaren|stationery"),
    ("pencil-case", "school-supplies", "books-learning", "Pencil case", "Federmappe", "Estuche", "Trousse", "Mäppchen|Federmäppchen|Schlampermäppchen|Federtasche|pencil pouch|estuche escolar|trousse scolaire"),
    ("pens", "school-supplies", "arts-crafts", "Pens & crayons", "Stifte", "Lápices y rotuladores", "Crayons & feutres", "Stift|Buntstifte|Wachsmalstifte|Wachsmalblöcke|Filzstifte|Fasermaler|Bleistifte|Füller|Füllfederhalter|Kreide|Ölkreiden|Wasserfarben|Wasserfarbkasten|Malkasten|Fingerfarben|coloured pencils|felt-tip pens|markers|paint box|lápices de colores|rotuladores|ceras|crayons de couleur|feutres"),
    ("paper-pads", "school-supplies", "arts-crafts", "Paper & pads", "Papier & Blöcke", "Papel y blocs", "Papier & blocs", "Papierstapel"),
    ("drawing-paper", "paper-pads", "arts-crafts", "Drawing paper", "Zeichenpapier", "Papel de dibujo", "Papier à dessin", "Malpapier|Zeichenblock|Malblock|Skizzenbuch|Skizzenblock|Aquarellpapier|Malrolle|sketchbook|drawing pad|watercolour paper|bloc de dibujo|bloc à dessin"),
    ("craft-paper", "paper-pads", "arts-crafts", "Craft paper", "Bastelpapier", "Papel para manualidades", "Papier de bricolage", "Tonpapier|Tonkarton|Fotokarton|Transparentpapier|Origamipapier|Faltpapier|Krepppapier|Seidenpapier|Glanzpapier|Bastelkarton|construction paper|origami paper|tissue paper|crepe paper|cartulina|papel de seda|papier crépon|papier de soie"),
    ("exercise-books", "paper-pads", "books-learning", "Exercise books", "Hefte", "Cuadernos", "Cahiers", "Heft|Schulhefte|Schreibhefte|Karoheft|Linienheft|Collegeblock|Schreibblock|Ringbuch|exercise book|notepad|writing pad|cuaderno|cahier"),
    ("colouring-books", "school-supplies", "books-learning", "Colouring books", "Malbücher", "Libros para colorear", "Livres de coloriage", "Malbuch|Ausmalbuch|Ausmalbücher|Ausmalbilder|Mandalas|Rätselheft|Stickerbuch|colouring book|coloring book|activity book|libro para colorear|cahier de coloriage"),
    ("childrens-books", "school-supplies", "books-learning", "Children's books", "Kinderbücher", "Libros infantiles", "Livres pour enfants", "Kinderbuch|Bilderbuch|Bilderbücher|Pappbilderbuch|Pappbuch|Vorlesebuch|Erstlesebuch|Jugendbuch|Jugendbücher|picture book|board book|kids' books|cuentos infantiles|album jeunesse"),
    ("schoolbooks", "school-supplies", "books-learning", "Schoolbooks", "Schulbücher", "Libros de texto", "Manuels scolaires", "Schulbuch|Lehrbuch|Lehrbücher|Arbeitsheft|Arbeitshefte|Lernhilfe|Lernhilfen|Wörterbuch|Atlas|textbook|textbooks|workbook|libro de texto|manuel scolaire"),
    ("childrens-scissors", "school-supplies", "arts-crafts", "Children's scissors", "Kinderschere", "Tijeras infantiles", "Ciseaux pour enfant", "Schere|Scheren|Bastelschere|Kinderscheren|scissors|tijeras|ciseaux"),
    ("ruler", "school-supplies", "books-learning", "Ruler", "Lineal", "Regla", "Règle", "Lineale|Geodreieck|Zeichendreieck|set square|escuadra|équerre"),
    ("drawing-compasses", "school-supplies", "books-learning", "Compasses", "Zirkel", "Compás", "Compas", "Schulzirkel|Zirkelkasten|pair of compasses|drawing compass"),
    ("clipboard", "school-supplies", "books-learning", "Clipboard", "Klemmbrett", "Tabla con pinza", "Porte-bloc", "Klemmbretter|Schreibbrett|Klemmmappe|clipboards|planchette"),

    # ── Nature, exploring, carving ───────────────────────────────────────
    ("nature-woodcraft", "childrens-things", "camping-travel", "Nature & woodcraft", "Natur & Schnitzen", "Naturaleza y tallado", "Nature & sculpture sur bois", "Forscherausrüstung|Waldkindergartenausrüstung|Naturforscher"),
    ("childrens-carving-knife", "nature-woodcraft", "arts-crafts", "Children's carving knife", "Kinderschnitzmesser", "Cuchillo de tallar infantil", "Couteau à sculpter pour enfant", "Schnitzmesser für Kinder|Kindermesser|Taschenmesser|pocket knife|Opinel|Morakniv|navaja|canif"),
    ("childrens-carving-set", "nature-woodcraft", "arts-crafts", "Children's carving set", "Kinderschnitzset", "Set de tallado infantil", "Kit de sculpture pour enfant", "Schnitzset für Kinder|Schnitzwerkzeug für Kinder|Kinderschnitzwerkzeug|Schnitzset|children's carving tools"),
    ("cut-gloves", "nature-woodcraft", "arts-crafts", "Cut-resistant gloves", "Schnittschutzhandschuhe", "Guantes anticorte", "Gants anti-coupure", "schnittfeste Handschuhe|Schnittschutzhandschuh|Schnitzhandschuh|Schnitzhandschuhe|carving glove|cut-resistant glove"),
    ("microscope", "nature-woodcraft", "books-learning", "Microscope", "Mikroskop", "Microscopio", "Microscope", "Kindermikroskop|Stereomikroskop|Binokular|Lupe|magnifying glass|lupa|loupe"),
    ("compass", "nature-woodcraft", "camping-travel", "Compass", "Kompass", "Brújula", "Boussole", "Marschkompass|Wanderkompass|Kinderkompass"),

    # ── Electronics ──────────────────────────────────────────────────────
    ("video-games", "childrens-things", "electronics-computers", "Video games", "Computerspiele", "Videojuegos", "Jeux vidéo", "Computerspiel|Videospiele|Videospiel|Konsolenspiele|Konsolenspiel|computer games|video game|videojuego|jeu vidéo"),
    ("game-console", "childrens-things", "electronics-computers", "Game console", "Spielkonsole", "Consola de videojuegos", "Console de jeux", "Spielkonsolen|Konsole|Nintendo|Playstation|Xbox|Gameboy|Game Boy|games console|consola|console"),
    ("childrens-phone", "childrens-things", "electronics-computers", "Children's phone", "Kinderhandy", "Móvil infantil", "Téléphone pour enfant", "Handy für Kinder|Kindersmartphone|Kinder-Smartphone|Smartwatch für Kinder|Kinderuhr mit GPS|kids' phone"),
]
