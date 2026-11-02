"""Children: what they grow out of or need for a while, outdoors first (rain trousers,
rubber boots, snowsuits, woollen underwear), and toys, sports gear, cloth nappies, lunch
boxes, water bottles, backpacks, school and drawing things, carving and exploring gear,
games consoles. Childcare is a skill ("Childcare"), not a thing.

Each entry: (slug, broader thing's slug, gift category slug, en, de, es, fr, other
names in any language separated by "|"). A broader thing goes before the narrower ones.
Clothes and shoes have a size (Listing.size, by SIZED_THINGS): everything under
"kids-clothing" a clothing size, under "kids-shoes", socks and ice skates a shoe size; hats, scarves and gloves
don't. Slugs start with "kids-" (toys, pram and child seat came from the other things and
keep theirs, as does the children's bike from the vehicles; car seats and bike trailers
for children stay vehicles). Things also named for grown-ups (snowboard, skis, scooter,
carving tools, phone, paper) are named as the children's ones ("Kindersnowboard",
"Kinderschnitzset"), so an "other" listing for a snowboard stays a grown-up's. Children's things are always in "Children & Toys" too
(Listing.thing_categories)."""

T = "children-toys"
C = "clothing-textiles"

CHILDREN = [
    ("kids", "", T, "Children's things", "Kindersachen", "Cosas de niños", "Affaires d'enfant", "Kinderkram|Babysachen|baby things|baby stuff|Babyausstattung|Erstausstattung|cosas de bebé|affaires de bébé"),

    # ── Clothes (with a size) ────────────────────────────────────────────
    ("kids-clothing", "kids", C, "Children's clothes", "Kinderkleidung", "Ropa infantil", "Vêtements d'enfant", "kids' clothes|Kinderklamotten|Babykleidung|baby clothes|Kleiderpaket|Kleidersack|Kleiderkiste|ropa de bebé|vêtements bébé"),
    # Outdoors, in all weathers
    ("kids-outdoor-clothing", "kids-clothing", C, "Outdoor clothing", "Outdoorkleidung", "Ropa de exterior", "Vêtements d'extérieur", "Draußenkleidung|Matschsachen|Waldkindergartenkleidung|outdoor wear|Funktionskleidung"),
    ("kids-rain-trousers", "kids-outdoor-clothing", C, "Rain trousers", "Regenhose", "Pantalón de lluvia", "Pantalon de pluie", "Matschhose|Buddelhose|Regenlatzhose|Matschlatzhose|rain pants|waterproof trousers|puddle pants|salopette de pluie"),
    ("kids-rain-jacket", "kids-outdoor-clothing", C, "Rain jacket", "Regenjacke", "Chubasquero", "Veste de pluie", "Matschjacke|Buddeljacke|waterproof jacket|raincoat|Regenmantel|Friesennerz|ciré|impermeable"),
    ("kids-rain-suit", "kids-outdoor-clothing", C, "Rain suit", "Regenoverall", "Mono de lluvia", "Combinaison de pluie", "Regenanzug|Matschoverall|Buddelanzug|puddle suit|Matschanzug"),
    ("kids-snowsuit", "kids-outdoor-clothing", C, "Snowsuit", "Schneeanzug", "Mono de nieve", "Combinaison de neige", "Skianzug|Schneeoverall|Winteroverall|pram suit|Kinderwagenoverall|ski suit|combinaison de ski"),
    ("kids-ski-trousers", "kids-outdoor-clothing", C, "Ski trousers", "Skihose", "Pantalón de esquí", "Pantalon de ski", "Schneehose|Thermohose|snow pants|salopette de ski"),
    ("kids-winter-jacket", "kids-outdoor-clothing", C, "Winter jacket", "Winterjacke", "Chaqueta de invierno", "Blouson d'hiver", "Anorak|Daunenjacke|Schneejacke|Wintermantel|parka|winter coat|doudoune|abrigo de invierno"),
    ("kids-softshell", "kids-outdoor-clothing", C, "Softshell jacket", "Softshelljacke", "Chaqueta softshell", "Veste softshell", "Softshell|Softshellhose|Softshelloverall|Übergangsjacke"),
    ("kids-fleece", "kids-outdoor-clothing", C, "Fleece", "Fleecejacke", "Forro polar", "Polaire", "Fleecepullover|Fleeceoverall|Fleecehose|fleece jacket|veste polaire"),
    ("kids-wool-layer", "kids-outdoor-clothing", C, "Woollen underwear", "Wollunterwäsche", "Ropa interior de lana", "Sous-vêtements en laine", "Merino|Merinounterwäsche|Wollbody|Woll-Seide|Wollwalk|Walkjacke|Walkoverall|Walkhose|Funktionsunterwäsche|Skiunterwäsche|thermal underwear|base layer|laine mérinos"),
    ("kids-swimwear", "kids-outdoor-clothing", C, "Swimwear", "Badesachen", "Bañador", "Maillot de bain", "Badeanzug|Badehose|Badeshorts|Badeshirt|UV-Badeshirt|UV-Badeanzug|Schwimmwindel|swimsuit|swimming trunks|Neoprenanzug|wetsuit"),
    # Everyday
    ("kids-bodysuit", "kids-clothing", C, "Bodysuit", "Body", "Body", "Body", "Bodys|Wickelbody|onesie|Strampler|romper|Strampelanzug|pelele|grenouillère"),
    ("kids-trousers", "kids-clothing", C, "Trousers", "Hose", "Pantalón", "Pantalon", "Hosen|Jeans|Leggings|Jogginghose|Latzhose|pants|dungarees|shorts|kurze Hose|pantalones"),
    ("kids-tops", "kids-clothing", C, "Tops", "Oberteile", "Camisetas y jerséis", "Hauts", "Oberteil|T-Shirt|Shirt|Pullover|Pulli|Sweatshirt|Hoodie|Langarmshirt|Strickjacke|cardigan|jumper|sweater|camiseta|jersey|pull|tee-shirt"),
    ("kids-dress", "kids-clothing", C, "Dress", "Kleid", "Vestido", "Robe", "Kleider|Rock|skirt|falda|jupe"),
    ("kids-sleepwear", "kids-clothing", C, "Pyjamas", "Schlafanzug", "Pijama", "Pyjama", "Schlafanzüge|pajamas|Nachthemd|nightie|Babyschlafsack|Kinderschlafsack|baby sleeping bag|gigoteuse|saco de dormir de bebé"),
    ("kids-underwear", "kids-clothing", C, "Underwear", "Unterwäsche", "Ropa interior", "Sous-vêtements", "Unterhosen|Unterhemd|Unterhemden|Strumpfhose|Strumpfhosen|tights|collants|braguitas|culottes"),
    # Socks go by shoe size (Listing.SIZED_THINGS)
    ("kids-socks", "kids-clothing", C, "Socks", "Socken", "Calcetines", "Chaussettes", "Socke|Strümpfe|Kniestrümpfe|Wollsocken|Stoppersocken|Rutschsocken|ABS-Socken|Skisocken|Wandersocken|wool socks|calcetines antideslizantes|chaussettes antidérapantes"),

    # ── Shoes (with a size) ──────────────────────────────────────────────
    ("kids-shoes", "kids", C, "Children's shoes", "Kinderschuhe", "Zapatos infantiles", "Chaussures d'enfant", "Schuhe|shoes|Babyschuhe|Lauflernschuhe|Barfußschuhe|barefoot shoes|zapatos|chaussures"),
    ("kids-rubber-boots", "kids-shoes", C, "Rubber boots", "Gummistiefel", "Botas de agua", "Bottes de pluie", "wellies|wellingtons|rain boots|gumboots|Regenstiefel|Matschstiefel|Buddelstiefel|katiuskas|bottes en caoutchouc"),
    ("kids-winter-boots", "kids-shoes", C, "Winter boots", "Winterstiefel", "Botas de invierno", "Bottes d'hiver", "Winterschuhe|Schneestiefel|snow boots|Thermostiefel|Moonboots|après-ski"),
    ("kids-hiking-boots", "kids-shoes", C, "Hiking boots", "Wanderschuhe", "Botas de montaña", "Chaussures de randonnée", "Wanderstiefel|Trekkingschuhe|Bergschuhe|hiking shoes"),
    ("kids-sandals", "kids-shoes", C, "Sandals", "Sandalen", "Sandalias", "Sandales", "Sandale|Trekkingsandalen|Badeschuhe|Wasserschuhe|water shoes|Clogs|Crocs|chanclas|sandalettes"),
    ("kids-sneakers", "kids-shoes", C, "Trainers", "Turnschuhe", "Zapatillas", "Baskets", "Sneaker|Sneakers|sneakers|Kinderturnschuhe|Halbschuhe|tenis"),
    ("kids-sports-shoes", "kids-shoes", C, "Sports shoes", "Sportschuhe", "Calzado deportivo", "Chaussures de sport", "Hallenschuhe|indoor shoes|Fußballschuhe|football boots|Stollenschuhe|Laufschuhe|running shoes|Kletterschuhe|zapatillas deportivas"),
    ("kids-slippers", "kids-shoes", C, "Slippers", "Hausschuhe", "Pantuflas", "Chaussons", "Puschen|Schlappen|Pantoffeln|Krabbelschuhe|Lederpuschen|Hüttenschuhe|zapatillas de casa|patucos"),

    # ── Hats, scarves, gloves (no size) ──────────────────────────────────
    ("kids-hat", "kids", C, "Hat", "Mütze", "Gorro", "Bonnet", "Mützen|beanie|Wintermütze|Strickmütze|Schlupfmütze|Schalmütze|Balaclava|Sturmhaube|Sonnenhut|sun hat|Schirmmütze|cap|Kappe|Hut|Regenhut|Südwester|sou'wester|gorra|chapeau"),
    ("kids-scarf", "kids", C, "Scarf", "Schal", "Bufanda", "Écharpe", "Schals|Loopschal|Halstuch|Schlauchschal|neck warmer|Buff|snood|cuello|tour de cou"),
    ("kids-gloves", "kids", C, "Gloves", "Handschuhe", "Guantes", "Gants", "Handschuh|Fäustlinge|Fäustling|mittens|Fausthandschuhe|Skihandschuhe|Matschhandschuhe|Regenhandschuhe|Fingerhandschuhe|manoplas|moufles"),

    # ── Nappies, carrying ────────────────────────────────────────────────
    ("kids-cloth-nappies", "kids", T, "Cloth nappies", "Stoffwindeln", "Pañales de tela", "Couches lavables", "Stoffwindel|cloth diapers|reusable nappies|Mullwindeln|Mullwindel|muslins|Prefolds|Windelüberhose|Überhose|nappy cover|Wollüberhose|Höschenwindel|Windeleinlagen|Moltontücher|pañales reutilizables"),
    ("pram", "kids", T, "Pram", "Kinderwagen", "Cochecito", "Poussette", "Buggy|stroller|pushchair|Sportwagen|Fahrradanhänger für Kinder|carrito"),
    ("kids-carrier", "kids", T, "Baby carrier", "Babytrage", "Portabebés", "Porte-bébé", "Tragetuch|Tragehilfe|sling|baby sling|Kraxe|Rückentrage|Kindertrage|hiking child carrier|fular"),
    ("child-seat", "kids", T, "Child seat", "Kindersitz", "Asiento infantil", "Siège enfant", "Fahrradsitz|Fahrradkindersitz|bike seat|Kinderfahrradsitz"),

    # ── Lunch, drinks, backpacks ─────────────────────────────────────────
    ("kids-lunchbox", "kids", "kitchen-household", "Lunch box", "Brotdose", "Fiambrera", "Boîte à goûter", "Vesperdose|Vesperbox|Brotbox|Brotzeitdose|Brotzeitbox|Jausenbox|Jausendose|Znünibox|Lunchbox|Bento|Edelstahldose|Kindergartendose|lonchera|boîte à tartines"),
    ("kids-water-bottle", "kids", "kitchen-household", "Water bottle", "Trinkflasche", "Botella de agua", "Gourde", "Trinkflaschen|Kindertrinkflasche|Edelstahlflasche|Thermosflasche|Isolierflasche|Thermoskanne|sippy cup|Schnabeltasse|Trinklernbecher|cantimplora|bidón|termo"),
    ("kids-backpack", "kids", T, "Children's backpack", "Kinderrucksack", "Mochila infantil", "Sac à dos enfant", "Kindergartenrucksack|Kitarucksack|Kita-Rucksack|Schulranzen|Schulrucksack|Ranzen|school bag|satchel|cartable|mochila escolar"),

    # ── Toys ─────────────────────────────────────────────────────────────
    ("toys", "kids", T, "Toys", "Spielzeug", "Juguetes", "Jouets", "Spielsachen|Holzspielzeug|wooden toys|juguete|jouet"),
    ("kids-outdoor-toys", "toys", T, "Outdoor toys", "Draußenspielzeug", "Juguetes de exterior", "Jeux d'extérieur", "Sandspielzeug|Sandkastenspielzeug|sand toys|Buddelzeug|Eimer und Schaufel|bucket and spade|Wasserspielzeug|Schwimmflügel|Kescher|Seifenblasen|Straßenkreide|Springseil|Federball|Frisbee|Wikingerschach|Kubb|Schaukel|swing|Sandkasten|sandpit"),
    ("kids-building-toys", "toys", T, "Building blocks", "Bausteine", "Bloques de construcción", "Jeux de construction", "Bauklötze|Holzbausteine|Klemmbausteine|Kapla|Murmelbahn|marble run|bloques|cubes"),
    ("kids-lego", "kids-building-toys", T, "Lego", "Lego", "Lego", "Lego", "Legosteine|Lego-Steine|Lego Technic|Lego City|Lego Friends|Legokiste|LEGO bricks"),
    ("kids-duplo", "kids-building-toys", T, "Duplo", "Duplo", "Duplo", "Duplo", "Duplosteine|Duplo-Steine|Lego Duplo|Duplokiste"),
    ("kids-games", "toys", T, "Board games", "Brettspiele", "Juegos de mesa", "Jeux de société", "Brettspiel|board game|Gesellschaftsspiel|Gesellschaftsspiele|Kartenspiel|Kartenspiele|card game|Würfelspiel|Spiele|games|Memory|juego de mesa|jeu de société"),
    ("kids-puzzles", "toys", T, "Puzzles", "Puzzles", "Puzles", "Puzzles", "Puzzle|jigsaw puzzle|jigsaw|Holzpuzzle|Steckpuzzle|rompecabezas|casse-tête"),
    ("kids-toy-vehicles", "toys", T, "Toy vehicles", "Spielfahrzeuge", "Vehículos de juguete", "Véhicules jouets", "Spielfahrzeug|Spielzeugauto|Spielzeugautos|toy car|toy cars|Matchbox|Siku|Spielzeugbagger|Spielzeugtraktor|Holzeisenbahn|Spielzeugeisenbahn|Brio|toy train|Carrerabahn|Autorennbahn|coches de juguete|petites voitures"),
    ("kids-rc-vehicles", "kids-toy-vehicles", T, "Remote-controlled vehicle", "Ferngesteuertes Fahrzeug", "Vehículo teledirigido", "Véhicule télécommandé", "ferngesteuerte Fahrzeuge|ferngesteuertes Auto|ferngesteuerte Autos|Fernsteuerauto|ferngesteuerter Bagger|ferngesteuertes Boot|remote control car|coche teledirigido|voiture télécommandée"),
    ("kids-dolls", "toys", T, "Dolls & soft toys", "Puppen & Kuscheltiere", "Muñecas y peluches", "Poupées & peluches", "Puppe|doll|Kuscheltier|Stofftier|Teddy|Teddybär|soft toy|Puppenwagen|Puppenhaus|Kaufladen|Spielküche|play kitchen|muñeca|peluche"),
    ("kids-baby-toys", "toys", T, "Baby toys", "Babyspielzeug", "Juguetes para bebés", "Jouets d'éveil", "Rassel|rattle|Greifling|Beißring|teether|Motorikschleife|Spielbogen|Krabbeldecke|play mat|sonajero|hochet"),

    # ── Sports gear ──────────────────────────────────────────────────────
    ("kids-sports", "kids", "camping-travel", "Children's sports gear", "Kindersportgeräte", "Material deportivo infantil", "Matériel de sport pour enfants", "Kindersportsachen|Sportsachen für Kinder"),
    ("kids-bike", "kids-sports", "bikes-vehicles", "Children's bike", "Kinderfahrrad", "Bicicleta infantil", "Vélo enfant", "Kinderrad|kids' bike|Jugendrad|Jugendfahrrad|bici de niño"),
    ("kids-balance-bike", "kids-sports", "bikes-vehicles", "Balance bike", "Laufrad", "Bicicleta sin pedales", "Draisienne", "Lauflernrad|push bike|run bike|Holzlaufrad"),
    ("kids-tricycle", "kids-sports", "bikes-vehicles", "Children's tricycle", "Kinderdreirad", "Triciclo infantil", "Tricycle enfant", "Dreirad für Kinder"),
    ("kids-ride-on", "kids-sports", T, "Ride-on toy", "Rutschauto", "Correpasillos", "Porteur", "Bobbycar|Bobby-Car|Rutscher|ride-on|Tretauto|pedal car"),
    ("kids-scooter", "kids-sports", "bikes-vehicles", "Children's scooter", "Kinderroller", "Patinete infantil", "Trottinette enfant", "Kickboard|Laufroller|Tretroller für Kinder"),
    ("kids-skateboard", "kids-sports", "camping-travel", "Skateboard", "Skateboard", "Skateboard", "Skateboard", "Longboard|Pennyboard|Penny board|patineta"),
    ("kids-inline-skates", "kids-sports", "camping-travel", "Children's inline skates", "Kinderinliner", "Patines infantiles", "Rollers enfant", "Rollschuhe|roller skates|Kinderrollschuhe|patines|patins à roulettes"),
    ("kids-snowboard", "kids-sports", "camping-travel", "Children's snowboard", "Kindersnowboard", "Snowboard infantil", "Snowboard enfant", "Kinder-Snowboard|Kindersnowboardboots|Kindersnowboardschuhe"),
    ("kids-skis", "kids-sports", "camping-travel", "Children's skis", "Kinderski", "Esquís infantiles", "Skis enfant", "Kinderskier|Kinder-Ski|Kinderskischuhe|Kinderlanglaufski|Kinderskistöcke"),
    ("kids-ice-skates", "kids-sports", "camping-travel", "Ice skates", "Schlittschuhe", "Patines de hielo", "Patins à glace", "Schlittschuh|Kinderschlittschuhe|Kufen|Doppelkufen|Gleitschuhe|Hockeyschlittschuhe|Eiskunstlaufschuhe|ice skate|patins"),
    ("sledge", "kids-sports", "camping-travel", "Sledge", "Schlitten", "Trineo", "Luge", "sled|Rodel|Rodelschlitten|Davoser|Poporutscher|Rutschteller|snow tube"),
    ("kids-helmet", "kids-sports", T, "Children's helmet", "Kinderhelm", "Casco infantil", "Casque enfant", "Fahrradhelm|Skihelm|Kletterhelm|bike helmet|ski helmet|casco|casque"),

    # ── School, drawing, crafting ────────────────────────────────────────
    ("kids-school", "kids", "books-learning", "School supplies", "Schulsachen", "Material escolar", "Fournitures scolaires", "Schulbedarf|Schreibwaren|stationery|Federmäppchen|Mäppchen|Federtasche|pencil case|estuche|trousse"),
    ("kids-pens", "kids-school", "arts-crafts", "Pens & crayons", "Stifte", "Lápices y rotuladores", "Crayons & feutres", "Stift|Buntstifte|Wachsmalstifte|Wachsmalblöcke|Filzstifte|Fasermaler|Bleistifte|Füller|Füllfederhalter|Kreide|Ölkreiden|Wasserfarben|Wasserfarbkasten|Malkasten|Fingerfarben|coloured pencils|felt-tip pens|markers|paint box|lápices de colores|rotuladores|ceras|crayons de couleur|feutres"),
    ("kids-paper", "kids-school", "arts-crafts", "Paper & pads", "Papier & Blöcke", "Papel y blocs", "Papier & blocs", "Papierstapel"),
    ("kids-drawing-paper", "kids-paper", "arts-crafts", "Drawing paper", "Zeichenpapier", "Papel de dibujo", "Papier à dessin", "Malpapier|Zeichenblock|Malblock|Skizzenbuch|Skizzenblock|Aquarellpapier|Malrolle|sketchbook|drawing pad|watercolour paper|bloc de dibujo|bloc à dessin"),
    ("kids-craft-paper", "kids-paper", "arts-crafts", "Craft paper", "Bastelpapier", "Papel para manualidades", "Papier de bricolage", "Tonpapier|Tonkarton|Fotokarton|Transparentpapier|Origamipapier|Faltpapier|Krepppapier|Seidenpapier|Glanzpapier|Bastelkarton|construction paper|origami paper|tissue paper|crepe paper|cartulina|papel de seda|papier crépon|papier de soie"),
    ("kids-exercise-books", "kids-paper", "books-learning", "Exercise books", "Hefte", "Cuadernos", "Cahiers", "Heft|Schulhefte|Schreibhefte|Karoheft|Linienheft|Collegeblock|Schreibblock|Ringbuch|exercise book|notepad|writing pad|cuaderno|cahier"),
    ("kids-colouring-books", "kids-school", "books-learning", "Colouring books", "Malbücher", "Libros para colorear", "Livres de coloriage", "Malbuch|Ausmalbuch|Ausmalbücher|Ausmalbilder|Mandalas|Rätselheft|Stickerbuch|colouring book|coloring book|activity book|libro para colorear|cahier de coloriage"),
    ("kids-books", "kids-school", "books-learning", "Children's books", "Kinderbücher", "Libros infantiles", "Livres pour enfants", "Kinderbuch|Bilderbuch|Bilderbücher|Pappbilderbuch|Pappbuch|Vorlesebuch|Erstlesebuch|Jugendbuch|Jugendbücher|picture book|board book|kids' books|cuentos infantiles|album jeunesse"),
    ("kids-schoolbooks", "kids-school", "books-learning", "Schoolbooks", "Schulbücher", "Libros de texto", "Manuels scolaires", "Schulbuch|Lehrbuch|Lehrbücher|Arbeitsheft|Arbeitshefte|Lernhilfe|Lernhilfen|Wörterbuch|Atlas|textbook|textbooks|workbook|libro de texto|manuel scolaire"),
    ("kids-scissors", "kids-school", "arts-crafts", "Children's scissors", "Kinderschere", "Tijeras infantiles", "Ciseaux pour enfant", "Schere|Scheren|Bastelschere|Kinderscheren|scissors|tijeras|ciseaux"),
    ("kids-ruler", "kids-school", "books-learning", "Ruler", "Lineal", "Regla", "Règle", "Lineale|Geodreieck|Zeichendreieck|set square|escuadra|équerre"),
    ("kids-drawing-compasses", "kids-school", "books-learning", "Compasses", "Zirkel", "Compás", "Compas", "Schulzirkel|Zirkelkasten|pair of compasses|drawing compass"),
    ("kids-clipboard", "kids-school", "books-learning", "Clipboard", "Klemmbrett", "Tabla con pinza", "Porte-bloc", "Klemmbretter|Schreibbrett|Klemmmappe|clipboards|planchette"),

    # ── Nature, exploring, carving ───────────────────────────────────────
    ("kids-nature", "kids", "camping-travel", "Nature & woodcraft", "Natur & Schnitzen", "Naturaleza y tallado", "Nature & sculpture sur bois", "Forscherausrüstung|Waldkindergartenausrüstung|Naturforscher"),
    ("kids-carving-knife", "kids-nature", "arts-crafts", "Children's carving knife", "Kinderschnitzmesser", "Cuchillo de tallar infantil", "Couteau à sculpter pour enfant", "Schnitzmesser für Kinder|Kindermesser|Taschenmesser|pocket knife|Opinel|Morakniv|navaja|canif"),
    ("kids-carving-tools", "kids-nature", "arts-crafts", "Children's carving set", "Kinderschnitzset", "Set de tallado infantil", "Kit de sculpture pour enfant", "Schnitzset für Kinder|Schnitzwerkzeug für Kinder|Kinderschnitzwerkzeug|Schnitzset|children's carving tools"),
    ("kids-cut-gloves", "kids-nature", "arts-crafts", "Cut-resistant gloves", "Schnittschutzhandschuhe", "Guantes anticorte", "Gants anti-coupure", "schnittfeste Handschuhe|Schnittschutzhandschuh|Schnitzhandschuh|Schnitzhandschuhe|carving glove|cut-resistant glove"),
    ("kids-microscope", "kids-nature", "books-learning", "Microscope", "Mikroskop", "Microscopio", "Microscope", "Kindermikroskop|Stereomikroskop|Binokular|Lupe|magnifying glass|lupa|loupe"),
    ("kids-compass", "kids-nature", "camping-travel", "Compass", "Kompass", "Brújula", "Boussole", "Marschkompass|Wanderkompass|Kinderkompass"),

    # ── Electronics ──────────────────────────────────────────────────────
    ("kids-video-games", "kids", "electronics-computers", "Video games", "Computerspiele", "Videojuegos", "Jeux vidéo", "Computerspiel|Videospiele|Videospiel|Konsolenspiele|Konsolenspiel|computer games|video game|videojuego|jeu vidéo"),
    ("kids-game-console", "kids", "electronics-computers", "Game console", "Spielkonsole", "Consola de videojuegos", "Console de jeux", "Spielkonsolen|Konsole|Nintendo|Playstation|Xbox|Gameboy|Game Boy|games console|consola|console"),
    ("kids-phone", "kids", "electronics-computers", "Children's phone", "Kinderhandy", "Móvil infantil", "Téléphone pour enfant", "Handy für Kinder|Kindersmartphone|Kinder-Smartphone|Smartwatch für Kinder|Kinderuhr mit GPS|kids' phone"),
]
