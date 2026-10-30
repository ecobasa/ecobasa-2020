"""Trees, shrubs and climbers from temperate to tropical climates: fruit, nut and berry
plants, citrus, spice and drink plants, nitrogen fixers and other useful woody plants
for forest gardens, agroforestry, orchards and hedges, for swapping young plants, scion
wood, rootstocks and cuttings.

Each entry: (slug, broader thing's slug, gift category slug, en, de, es, fr, other
names in any language separated by "|"). A broader thing goes before the narrower ones;
names are singular (plurals and German compounds are recognized, see gifts.things).
Other names hold the botanical name, so it matches in every language, regional words
(Austrian: Marille, Zwetschke, Ringlotte, Ribisel, Agrasel, Dirndl, Asperl, Holler,
Hetscherl, Maroni, Kriecherl, Adlitzbeere, Grantn; Swiss: Baumnuss, Träubeli, Holder,
Tierlibaum, Arve, Heubeeri; Palatinate: Keschde), names from where the crop grows
(Portuguese, Swahili, Hindi, Tagalog: Mangueira, Embe, Kathal, Malunggay), the fruit's
name where the tree has its own (Manzano/Manzana) and well-known varieties ("Boskoop",
"Bühler Frühzwetschge", "Alphonso"), so a variety names its crop. Groups follow how
nurseries sort fruit (Kernobst, Steinobst, Zitrus, Tropenobst, Beerenobst, Schalenobst,
Wildobst, Kletterobst); the varieties themselves stay free text (Listing.variety); the
form of the plant material (young plant, scion wood, rootstock, cutting) is chosen
apart (Listing.plant_form)."""

S = "seeds-plants"
G = "garden-farm"
# Plants are always in "Seeds & Plants" too (Listing.thing_categories); these say more
H = "health-body"

PLANTS = [
    # --- Pome fruit -----------------------------------------------------------------
    ("fruit-tree", "", S, "Fruit tree", "Obstbaum", "Árbol frutal", "Arbre fruitier", "Obstgehölz|Hochstamm|Halbstamm|Buschbaum|Spindelbaum|Säulenobst|Streuobst|Spalierobst|Frutal"),
    ("pome-fruit", "fruit-tree", S, "Pome fruit", "Kernobst", "Fruta de pepita", "Fruit à pépins", "Pomoideae"),
    ("apple", "pome-fruit", S, "Apple", "Apfel", "Manzano", "Pommier", "Malus domestica|Apfelbaum|Manzana|Pomme|Boskoop|Gravensteiner|Goldparmäne|Jakob Fischer|Topaz|Ontario|Berlepsch|Kaiser Wilhelm|Rheinischer Bohnapfel|Öpfel"),
    ("crab-apple", "apple", S, "Crab apple", "Holzapfel", "Manzano silvestre", "Pommier sauvage", "Malus sylvestris|Wildapfel|Zierapfel|Malus baccata|Beerenapfel"),
    ("pear", "pome-fruit", S, "Pear", "Birne", "Peral", "Poirier", "Pyrus communis|Birnbaum|Pera|Poire|Williams Christ|Gute Luise|Conference|Alexander Lucas|Gellerts Butterbirne|Mostbirne|Pyrus pyraster|Wildbirne|Holzbirne"),
    ("nashi", "pear", S, "Asian pear", "Nashi", "Nashi", "Nashi", "Pyrus pyrifolia|Nashibirne|Apfelbirne|Asienbirne|Pera asiática|Poire asiatique"),
    ("quince", "pome-fruit", S, "Quince", "Quitte", "Membrillo", "Cognassier", "Cydonia oblonga|Quittenbaum|Apfelquitte|Birnenquitte|Coing|Konstantinopler Apfelquitte|Portugiesische Birnenquitte"),
    ("japanese-quince", "pome-fruit", S, "Japanese quince", "Scheinquitte", "Membrillero japonés", "Cognassier du Japon", "Chaenomeles japonica|Chaenomeles speciosa|Zierquitte|Japanische Quitte|Nordische Zitrone|Cido"),
    ("medlar", "pome-fruit", S, "Medlar", "Mispel", "Níspero europeo", "Néflier", "Mespilus germanica|Echte Mispel|Asperl|Nèfle|Nottingham|Westerveld|Kurpfälzer Süßmispel"),

    # --- Stone fruit ----------------------------------------------------------------
    ("stone-fruit", "fruit-tree", S, "Stone fruit", "Steinobst", "Fruta de hueso", "Fruit à noyau", "Prunus"),
    ("plum", "stone-fruit", S, "Plum", "Pflaume", "Ciruelo", "Prunier", "Prunus domestica|Pflaumenbaum|Zwetschge|Zwetschke|Zwetsche|Quetsche|Hauszwetschge|Bühler Frühzwetschge|Ortenauer|Cacaks Schöne|Ciruela|Prune"),
    ("greengage", "plum", S, "Greengage", "Reneklode", "Ciruela claudia", "Reine-claude", "Prunus domestica subsp. italica|Ringlotte|Ringlo|Edelpflaume|Große Grüne Reneklode|Graf Althanns Reneklode"),
    ("mirabelle", "plum", S, "Mirabelle plum", "Mirabelle", "Ciruela mirabel", "Mirabellier", "Prunus domestica subsp. syriaca|Mirabelle von Nancy|Mirabelle de Metz"),
    ("bullace", "plum", S, "Bullace", "Krieche", "Ciruela damascena", "Prunier de Saint-Julien", "Prunus insititia|Prunus domestica subsp. insititia|Kriecherl|Haferpflaume|Haferschlehe|Damaszenerpflaume|damson"),
    ("cherry-plum", "plum", S, "Cherry plum", "Kirschpflaume", "Ciruelo mirobolán", "Prunier myrobolan", "Prunus cerasifera|Myrobalane|Wildpflaume|Blutpflaume"),
    ("sweet-cherry", "stone-fruit", S, "Sweet cherry", "Süßkirsche", "Cerezo", "Cerisier", "Prunus avium|Kirschbaum|Kirsche|Vogelkirsche|Wildkirsche|Herzkirsche|Knorpelkirsche|Cereza|Cerise|Hedelfinger|Schneiders Späte Knorpelkirsche|Kriese"),
    ("sour-cherry", "stone-fruit", S, "Sour cherry", "Sauerkirsche", "Guindo", "Griottier", "Prunus cerasus|Weichsel|Weichselkirsche|Schattenmorelle|Amarelle|Morelle|Guinda|Griotte|Morellenfeuer"),
    ("peach", "stone-fruit", S, "Peach", "Pfirsich", "Melocotonero", "Pêcher", "Prunus persica|Pfirsichbaum|Weinbergpfirsich|Roter Weinbergpfirsich|Nektarine|Melocotón|Durazno|Pêche|Benedicte|Kernechter vom Vorgebirge"),
    ("apricot", "stone-fruit", S, "Apricot", "Aprikose", "Albaricoquero", "Abricotier", "Prunus armeniaca|Marille|Marillenbaum|Albaricoque|Damasco|Abricot|Ungarische Beste|Klosterneuburger|Kioto"),
    ("nanking-cherry", "stone-fruit", S, "Nanking cherry", "Filzkirsche", "Cerezo de Nanking", "Cerisier de Nankin", "Prunus tomentosa|Japanische Mandelkirsche|Koreanische Kirsche|Chinesische Zwergkirsche"),

    # --- Other fruit trees ----------------------------------------------------------
    ("mulberry", "fruit-tree", S, "Mulberry", "Maulbeere", "Morera", "Mûrier", "Morus alba|Morus nigra|Morus rubra|Maulbeerbaum|Schwarze Maulbeere|Weiße Maulbeere|Illinois Everbearing|Black Tabor|Mûre de mûrier"),
    ("fig", "fruit-tree", S, "Fig", "Feige", "Higuera", "Figuier", "Ficus carica|Feigenbaum|Higo|Figue|Brown Turkey|Bayernfeige|Violetta|Dalmatie"),
    ("persimmon", "fruit-tree", S, "Persimmon", "Kaki", "Caqui", "Plaqueminier", "Diospyros kaki|Kakibaum|Dattelpflaume|Sharonfrucht|Winterharte Kaki|Diospyros kaki × virginiana|Diospyros virginiana|Amerikanische Persimone|Diospyros lotus|Lotuspflaume"),
    ("pawpaw", "fruit-tree", S, "Pawpaw", "Indianerbanane", "Asimina", "Asiminier", "Asimina triloba|Papau|Dreilappige Papau|Asimina"),
    ("jujube", "fruit-tree", S, "Jujube", "Chinesische Dattel", "Azufaifo", "Jujubier", "Ziziphus jujuba|Jujube|Brustbeere|Rote Dattel|Azufaifa"),
    ("strawberry-tree", "fruit-tree", S, "Strawberry tree", "Erdbeerbaum", "Madroño", "Arbousier", "Arbutus unedo|Westlicher Erdbeerbaum|Arbouse"),
    ("olive", "fruit-tree", S, "Olive tree", "Olivenbaum", "Olivo", "Olivier", "Olea europaea|Ölbaum|Olive|Aceituna|Oliva"),
    ("pomegranate", "fruit-tree", S, "Pomegranate", "Granatapfel", "Granado", "Grenadier", "Punica granatum|Granatapfelbaum|Granada|Grenade|Romã|Anar|Komamanga"),
    ("loquat", "fruit-tree", S, "Loquat", "Japanische Wollmispel", "Níspero japonés", "Néflier du Japon", "Eriobotrya japonica|Wollmispel|Loquate|Nèfle du Japon|Nêspera"),
    ("feijoa", "fruit-tree", S, "Feijoa", "Feijoa", "Feijoa", "Feijoa", "Acca sellowiana|Ananasguave|Brasilianische Guave|Pineapple guava|Guayabo del país|Goiaba-serrana"),
    ("carob", "fruit-tree", S, "Carob", "Johannisbrotbaum", "Algarrobo", "Caroubier", "Ceratonia siliqua|Johannisbrot|Karob|Algarroba|Caroube|Alfarrobeira"),
    ("prickly-pear", "fruit-tree", S, "Prickly pear", "Kaktusfeige", "Nopal", "Figuier de Barbarie", "Opuntia ficus-indica|Feigenkaktus|Opuntie|Higo chumbo|Chumbera|Nopales|Figo-da-índia"),

    # --- Citrus ---------------------------------------------------------------------
    ("citrus", "fruit-tree", S, "Citrus", "Zitrus", "Cítrico", "Agrume", "Zitruspflanze|Zitrusbaum|Agrumen|Cítricos|Agrumes|Citrinos"),
    ("lemon", "citrus", S, "Lemon", "Zitrone", "Limonero", "Citronnier", "Citrus limon|Zitronenbaum|Limón|Citron|Limão|Meyer-Zitrone|Citrus × meyeri|Limau|Ndimu"),
    ("lime-fruit", "citrus", S, "Lime", "Limette", "Lima", "Limettier", "Citrus aurantiifolia|Citrus × latifolia|Limettenbaum|Limón verde|Citron vert|Makrut-Limette|Makrut|Citrus hystrix|Calamansi|Calamondin"),
    ("orange", "citrus", S, "Orange", "Orange", "Naranjo", "Oranger", "Citrus sinensis|Orangenbaum|Apfelsine|Naranja|Laranja|Blutorange|Bitterorange|Pomeranze|Citrus aurantium|Chungwa"),
    ("mandarin", "citrus", S, "Mandarin", "Mandarine", "Mandarino", "Mandarinier", "Citrus reticulata|Clementine|Satsuma|Tangerine|Mandarina|Clémentine|Tangerina|Mexerica"),
    ("grapefruit", "citrus", S, "Grapefruit", "Grapefruit", "Pomelo", "Pamplemoussier", "Citrus × paradisi|Citrus maxima|Pampelmuse|Pummelo|Toronja|Pamplemousse|Grapefruitbaum|Toranja"),
    ("kumquat", "citrus", S, "Kumquat", "Kumquat", "Kumquat", "Kumquat", "Citrus japonica|Fortunella|Zwergorange|Quinoto"),
    ("yuzu", "citrus", S, "Yuzu", "Yuzu", "Yuzu", "Yuzu", "Citrus junos|Yuzu-Zitrone"),
    ("trifoliate-orange", "citrus", S, "Trifoliate orange", "Dreiblättrige Orange", "Naranjo trifoliado", "Oranger trifolié", "Poncirus trifoliata|Citrus trifoliata|Bitterzitrone|Poncirus|Flying Dragon"),

    # --- Tropical fruit -------------------------------------------------------------
    ("tropical-fruit", "fruit-tree", S, "Tropical fruit", "Tropenobst", "Fruta tropical", "Fruit tropical", "Tropenfrucht|Tropische Früchte|Exoten|Frutas tropicales|Fruits tropicaux|Frutas tropicais"),
    ("mango", "tropical-fruit", S, "Mango", "Mango", "Mango", "Manguier", "Mangifera indica|Mangobaum|Manga|Mangueira|Mangue|Embe|Alphonso|Ataulfo|Tommy Atkins|Kesar"),
    ("avocado", "tropical-fruit", S, "Avocado", "Avocado", "Aguacate", "Avocatier", "Persea americana|Avocadobaum|Palta|Abacate|Avocat|Hass|Parachichi"),
    ("papaya", "tropical-fruit", S, "Papaya", "Papaya", "Papaya", "Papayer", "Carica papaya|Papayabaum|Melonenbaum|Lechosa|Mamão|Papaye|Fruta bomba|Papai"),
    ("banana", "tropical-fruit", S, "Banana", "Banane", "Banano", "Bananier", "Musa|Musa acuminata|Musa × paradisiaca|Bananenstaude|Kochbanane|Mehlbanane|Plátano|Plátano macho|Guineo|Cambur|Banane plantain|Bananeira|Ndizi|Ensete|Ensete ventricosum"),
    ("pineapple", "tropical-fruit", S, "Pineapple", "Ananas", "Piña", "Ananas", "Ananas comosus|Ananaspflanze|Abacaxi|Nanasi"),
    ("guava", "tropical-fruit", S, "Guava", "Guave", "Guayabo", "Goyavier", "Psidium guajava|Guavenbaum|Guayaba|Goiaba|Goyave|Erdbeerguave|Psidium cattleianum|Mpera"),
    ("lychee", "tropical-fruit", S, "Lychee", "Litschi", "Lichi", "Litchi", "Litchi chinensis|Litschibaum|Lichia"),
    ("longan", "tropical-fruit", S, "Longan", "Longan", "Longan", "Longanier", "Dimocarpus longan|Drachenauge|Ojo de dragón|Œil de dragon"),
    ("rambutan", "tropical-fruit", S, "Rambutan", "Rambutan", "Rambután", "Ramboutanier", "Nephelium lappaceum|Ramboutan|Achotillo|Mamón chino"),
    ("mangosteen", "tropical-fruit", S, "Mangosteen", "Mangostan", "Mangostán", "Mangoustanier", "Garcinia mangostana|Mangostane|Mangoustan|Manggis"),
    ("jackfruit", "tropical-fruit", S, "Jackfruit", "Jackfrucht", "Yaca", "Jacquier", "Artocarpus heterophyllus|Jackfruchtbaum|Jaca|Jaque|Kathal|Fenesi"),
    ("breadfruit", "tropical-fruit", S, "Breadfruit", "Brotfrucht", "Árbol del pan", "Arbre à pain", "Artocarpus altilis|Brotfruchtbaum|Fruta de pan|Fruit à pain|Fruta-pão"),
    ("durian", "tropical-fruit", S, "Durian", "Durian", "Durián", "Durian", "Durio zibethinus|Stinkfrucht|Durio"),
    ("soursop", "tropical-fruit", S, "Soursop", "Stachelannone", "Guanábana", "Corossolier", "Annona muricata|Graviola|Corossol|Sauersack|Mstafeli"),
    ("cherimoya", "tropical-fruit", S, "Cherimoya", "Cherimoya", "Chirimoyo", "Chérimolier", "Annona cherimola|Chirimoya|Chérimole|Cherimoyabaum"),
    ("sugar-apple", "tropical-fruit", S, "Sugar apple", "Zimtapfel", "Anón", "Pommier cannelle", "Annona squamosa|Süßsack|Rahmapfel|Annona reticulata|Atemoya|Anona|Pomme cannelle|Pinha|Sitaphal|Custard apple"),
    ("starfruit", "tropical-fruit", S, "Starfruit", "Karambole", "Carambolo", "Carambolier", "Averrhoa carambola|Sternfrucht|Carambola|Carambole|Kamrakh"),
    ("dragon-fruit", "tropical-fruit", S, "Dragon fruit", "Drachenfrucht", "Pitahaya", "Pitaya", "Selenicereus undatus|Hylocereus undatus|Fruit du dragon|Thanh long"),
    ("passion-fruit", "tropical-fruit", S, "Passion fruit", "Passionsfrucht", "Maracuyá", "Fruit de la passion", "Passiflora edulis|Maracuja|Maracujá|Grenadille|Granadilla|Passiflora ligularis|Parchita"),
    ("tamarillo", "tropical-fruit", S, "Tamarillo", "Baumtomate", "Tomate de árbol", "Tamarillo", "Solanum betaceum|Cyphomandra betacea|Tree tomato|Tomate andine"),
    ("lucuma", "tropical-fruit", S, "Lucuma", "Lucuma", "Lúcuma", "Lucuma", "Pouteria lucuma|Lucmo"),
    ("sapodilla", "tropical-fruit", S, "Sapodilla", "Breiapfel", "Chicozapote", "Sapotillier", "Manilkara zapota|Sapotille|Sapodillbaum|Chiku|Sapoti"),
    ("mamey-sapote", "tropical-fruit", S, "Mamey sapote", "Mamey-Sapote", "Mamey", "Sapotier", "Pouteria sapota|Mamey colorado|Zapote mamey"),
    ("jaboticaba", "tropical-fruit", S, "Jaboticaba", "Jabuticaba", "Jaboticaba", "Jaboticaba", "Plinia cauliflora|Myrciaria cauliflora|Jabuticabeira|Brasilianische Baumtraube"),
    ("acerola", "tropical-fruit", S, "Acerola", "Acerola", "Acerola", "Acérola", "Malpighia emarginata|Barbados-Kirsche|Barbados cherry|Cereza de Barbados|Cerise des Antilles"),
    ("tamarind", "tropical-fruit", S, "Tamarind", "Tamarinde", "Tamarindo", "Tamarinier", "Tamarindus indica|Indische Dattel|Tamarin|Imli|Ukwaju"),
    ("baobab", "tropical-fruit", S, "Baobab", "Affenbrotbaum", "Baobab", "Baobab", "Adansonia digitata|Mbuyu|Pain de singe|Monkey bread"),
    ("coconut", "tropical-fruit", S, "Coconut palm", "Kokospalme", "Cocotero", "Cocotier", "Cocos nucifera|Kokosnuss|Kokos|Coconut|Coco|Noix de coco|Coqueiro|Nariyal|Mnazi"),
    ("date-palm", "tropical-fruit", S, "Date palm", "Dattelpalme", "Palmera datilera", "Palmier dattier", "Phoenix dactylifera|Dattel|Dátil|Datte|Tâmara|Medjool|Deglet Nour|Tende"),
    ("cacao", "tropical-fruit", S, "Cacao", "Kakaobaum", "Cacao", "Cacaoyer", "Theobroma cacao|Kakao|Kakaopflanze|Cacau|Cacaueiro|Cacaotier"),

    # --- Soft fruit -----------------------------------------------------------------
    ("soft-fruit", "", S, "Berry bush", "Beerenobst", "Arbusto de bayas", "Petit fruit", "Beerenstrauch|Strauchbeere|Beerengehölz|soft fruit|Frutos rojos|Petits fruits"),
    ("currant", "soft-fruit", S, "Currant", "Johannisbeere", "Grosellero", "Groseillier", "Ribes|Ribisel|Johannisbeerstrauch|Grosella|Groseille"),
    ("redcurrant", "currant", S, "Redcurrant", "Rote Johannisbeere", "Grosellero rojo", "Groseillier rouge", "Ribes rubrum|Ribes sativum|Träubeli|Weiße Johannisbeere|Rosa Johannisbeere|Rote Ribisel|Jonkheer van Tets|Rovada|Rolan"),
    ("blackcurrant", "currant", S, "Blackcurrant", "Schwarze Johannisbeere", "Grosellero negro", "Cassissier", "Ribes nigrum|Cassis|Schwarze Ribisel|Titania|Ometa|Ben Sarek"),
    ("clove-currant", "currant", S, "Clove currant", "Goldjohannisbeere", "Grosellero dorado", "Groseillier doré", "Ribes aureum|Ribes odoratum|Gold-Johannisbeere|Duftjohannisbeere"),
    ("jostaberry", "soft-fruit", S, "Jostaberry", "Jostabeere", "Josta", "Josta", "Ribes × nidigrolaria|Ribes nidigrolaria|Jochelbeere"),
    ("gooseberry", "soft-fruit", S, "Gooseberry", "Stachelbeere", "Uva espina", "Groseillier à maquereau", "Ribes uva-crispa|Agrasel|Krausbeere|Uva crispa|Groseille à maquereau|Hinnonmäki|Invicta"),
    ("raspberry", "soft-fruit", S, "Raspberry", "Himbeere", "Frambueso", "Framboisier", "Rubus idaeus|Herbsthimbeere|Sommerhimbeere|Gelbe Himbeere|Frambuesa|Framboise|Autumn Bliss|Glen Ample|Himbeer|Gelbe Himbeere|Dorman Red|Rubus parvifolius"),
    ("blackberry", "soft-fruit", S, "Blackberry", "Brombeere", "Zarzamora", "Ronce fruitière", "Rubus fruticosus|Rubus armeniacus|dornenlose Brombeere|Mora|Mûre|Thornless Evergreen|Theodor Reimers|Loch Ness|Navaho|Kratzbeere"),
    ("tayberry", "blackberry", S, "Tayberry", "Taybeere", "Tayberry", "Tayberry", "Loganberry|Loganbeere|Boysenberry|Boysenbeere|Rubus × loganobaccus|Himbeer-Brombeere"),
    ("wineberry", "soft-fruit", S, "Japanese wineberry", "Japanische Weinbeere", "Frambuesa japonesa", "Ronce du Japon", "Rubus phoenicolasius|Rotborstige Himbeere|Weinbeere"),
    ("black-raspberry", "raspberry", S, "Black raspberry", "Schwarze Himbeere", "Frambuesa negra", "Framboisier noir", "Rubus occidentalis|Black Jewel|Bristol|blackcap"),
    ("purple-raspberry", "raspberry", S, "Purple raspberry", "Lila Himbeere", "Frambuesa púrpura", "Framboisier pourpre", "Rubus × neglectus|Rubus idaeus × neglectus|Glen Coe|Violette Himbeere|Purpurhimbeere"),
    ("blueberry", "soft-fruit", S, "Blueberry", "Heidelbeere", "Arándano", "Myrtille", "Vaccinium corymbosum|Kulturheidelbeere|Blaubeere|Schwarzbeere|Heubeeri|Vaccinium myrtillus|Waldheidelbeere|Bluecrop|Reka"),
    ("lingonberry", "soft-fruit", S, "Lingonberry", "Preiselbeere", "Arándano rojo", "Airelle rouge", "Vaccinium vitis-idaea|Grantn|Kronsbeere|cowberry|Red Pearl"),
    ("cranberry", "soft-fruit", S, "Cranberry", "Cranberry", "Arándano americano", "Canneberge", "Vaccinium macrocarpon|Großfrüchtige Moosbeere|Kranbeere|Moosbeere|Vaccinium oxycoccos"),
    ("haskap", "soft-fruit", S, "Haskap", "Maibeere", "Madreselva azul", "Camérisier bleu", "Lonicera caerulea|Sibirische Blaubeere|Blaue Heckenkirsche|Honigbeere|Kamtschatka-Heckenkirsche|honeyberry|Haskap"),

    # --- Wild fruit -----------------------------------------------------------------
    ("wild-fruit", "", S, "Wild fruit", "Wildobst", "Fruta silvestre", "Fruit sauvage", "Wildfrucht|Wildobstgehölz|Wildgehölz|Heckenobst|Vogelnährgehölz"),
    ("elder", "wild-fruit", H, "Elder", "Holunder", "Saúco", "Sureau", "Sambucus nigra|Schwarzer Holunder|Holler|Holder|Holunderbeere|Fliederbeere|Holunderblüte|elderberry|elderflower|Haschberl|Haschee|Sambucus canadensis|Haschberg"),
    ("sea-buckthorn", "wild-fruit", H, "Sea buckthorn", "Sanddorn", "Espino amarillo", "Argousier", "Hippophae rhamnoides|Fasanbeere|Haffdorn|Weidendorn|Leikora|Hergo|Pollmix|Askola"),
    ("rose-hip", "wild-fruit", H, "Rose hip", "Hagebutte", "Escaramujo", "Églantier", "Rosa canina|Rosa rugosa|Rosa villosa|Rosa pendulina|Hundsrose|Kartoffelrose|Apfelrose|Wildrose|Hetscherl|Hiefe|Hiffe|Cynorrhodon|Rosal silvestre"),
    ("cornelian-cherry", "wild-fruit", S, "Cornelian cherry", "Kornelkirsche", "Cornejo macho", "Cornouiller mâle", "Cornus mas|Dirndl|Dirndlstrauch|Herlitze|Tierlibaum|Gelber Hartriegel|Jolico|Bylda|Dublany|Schönbrunner Gourmetdirndl"),
    ("sloe", "wild-fruit", S, "Sloe", "Schlehe", "Endrino", "Prunellier", "Prunus spinosa|Schlehdorn|Schwarzdorn|Endrina|Prunelle"),
    ("mahaleb-cherry", "wild-fruit", S, "Mahaleb cherry", "Steinweichsel", "Cerezo de Santa Lucía", "Cerisier de Sainte-Lucie", "Prunus mahaleb|Felsenkirsche|Mahaleb|Türkische Weichsel"),
    ("hawthorn", "wild-fruit", H, "Hawthorn", "Weißdorn", "Espino albar", "Aubépine", "Crataegus monogyna|Crataegus laevigata|Hagedorn|Mehlfässchen|Crataegus"),
    ("azarole", "hawthorn", S, "Azarole", "Azaroldorn", "Acerolo", "Azérolier", "Crataegus azarolus|Welsche Mispel|Mittelmeer-Mispel|Azarole|Crataegus pinnatifida|Chinesischer Weißdorn|Crataegus schraderiana"),
    ("serviceberry", "wild-fruit", S, "Serviceberry", "Felsenbirne", "Guillomo", "Amélanchier", "Amelanchier lamarckii|Amelanchier alnifolia|Amelanchier ovalis|Saskatoon|Juneberry|Korinthenbaum|Felsenmispel|Kupfer-Felsenbirne|Thiessen"),
    ("rowan", "wild-fruit", S, "Rowan", "Eberesche", "Serbal de cazadores", "Sorbier des oiseleurs", "Sorbus aucuparia|Sorbus aucuparia var. edulis|Mährische Eberesche|Vogelbeere|Vogelbeeri|Vogelbeerbaum|Moravica|Konzentra|Essbare Eberesche"),
    ("service-tree", "wild-fruit", S, "Service tree", "Speierling", "Serbal común", "Cormier", "Sorbus domestica|Spierling|Sporbirne|Sperberbaum|Schmerbirne"),
    ("wild-service-tree", "wild-fruit", S, "Wild service tree", "Elsbeere", "Mostajo", "Alisier torminal", "Sorbus torminalis|Elsebeere|Adlitzbeere|Arlesbeere|Ruhrbirne|Schöne Else"),
    ("chokeberry", "wild-fruit", S, "Chokeberry", "Apfelbeere", "Aronia", "Aronia", "Aronia melanocarpa|Aronia prunifolia|Aroniabeere|Schwarze Eberesche"),
    ("goji", "wild-fruit", H, "Goji", "Goji", "Goji", "Goji", "Lycium barbarum|Lycium chinense|Gojibeere|Goji-Beere|Bocksdorn|Wolfsbeere|wolfberry|Chinesische Wolfsbeere"),
    ("barberry", "wild-fruit", S, "Barberry", "Berberitze", "Agracejo", "Épine-vinette", "Berberis vulgaris|Sauerdorn|Essigbeere|Zereschk|Berberis"),
    ("oregon-grape", "wild-fruit", S, "Oregon grape", "Mahonie", "Mahonia", "Mahonia", "Mahonia aquifolium|Berberis aquifolium|Gewöhnliche Mahonie"),
    ("elaeagnus", "wild-fruit", G, "Silverberry", "Ölweide", "Eleagno", "Chalef", "Elaeagnus|Silberölweide|Elaeagnus commutata"),
    ("autumn-olive", "elaeagnus", G, "Autumn olive", "Schirm-Ölweide", "Eleagno umbelado", "Chalef d'automne", "Elaeagnus umbellata|Korallen-Ölweide|Korallenölweide"),
    ("goumi", "elaeagnus", G, "Goumi", "Vielblütige Ölweide", "Goumi", "Goumi", "Elaeagnus multiflora|Essbare Ölweide|Reichblütige Ölweide"),
    ("ebbinge-silverberry", "elaeagnus", G, "Ebbinge's silverberry", "Wintergrüne Ölweide", "Eleagno de Ebbinge", "Chalef d'Ebbinge", "Elaeagnus × ebbingei|Elaeagnus ebbingei|Immergrüne Ölweide|Elaeagnus pungens"),

    # --- Nuts -----------------------------------------------------------------------
    ("nut-tree", "", S, "Nut tree", "Schalenobst", "Fruto seco", "Fruit à coque", "Nussgehölz|Nussstrauch|Nüsse|nut tree|Frutos secos"),
    ("walnut", "nut-tree", S, "Walnut", "Walnuss", "Nogal", "Noyer", "Juglans regia|Walnussbaum|Nussbaum|Baumnuss|Welschnuss|Nuez|Noix|Geisenheimer|Weinsberg|Franquette|Broadview|Red Moravian|Czerniowicki"),
    ("black-walnut", "walnut", S, "Black walnut", "Schwarznuss", "Nogal negro", "Noyer noir", "Juglans nigra|Amerikanische Schwarznuss"),
    ("heartnut", "walnut", S, "Heartnut", "Herznuss", "Nogal japonés", "Noyer du Japon", "Juglans ailantifolia|Japanische Walnuss|Juglans cinerea|Graunuss|Butternussbaum|Buartnut"),
    ("manchurian-walnut", "walnut", S, "Manchurian walnut", "Mandschurische Walnuss", "Nogal de Manchuria", "Noyer de Mandchourie", "Juglans mandshurica|Mandschurische Nuss"),
    ("sweet-chestnut", "nut-tree", S, "Sweet chestnut", "Esskastanie", "Castaño", "Châtaignier", "Castanea sativa|Edelkastanie|Marone|Maroni|Marroni|Keschde|Keste|Castaña|Châtaigne|Marron|Castanea sativa × crenata|Bouche de Bétizac|Marigoule|Castanea crenata"),
    ("hazel", "nut-tree", S, "Hazel", "Haselnuss", "Avellano", "Noisetier", "Corylus avellana|Haselstrauch|Hasel|Lambertsnuss|Corylus maxima|Zellernuss|Hallesche Riesennuss|Avellana|Noisette|filbert|cobnut"),
    ("turkish-hazel", "hazel", S, "Turkish hazel", "Baumhasel", "Avellano turco", "Noisetier de Byzance", "Corylus colurna|Türkische Hasel"),
    ("almond", "nut-tree", S, "Almond", "Mandel", "Almendro", "Amandier", "Prunus dulcis|Prunus amygdalus|Mandelbaum|Almendra|Amande|Robijn|Dürkheimer Krachmandel"),
    ("hickory", "nut-tree", S, "Hickory", "Hickorynuss", "Nogal americano", "Caryer", "Carya ovata|Carya laciniosa|Schuppenrinden-Hickory|Königsnuss|Hickory|Carya"),
    ("pecan", "hickory", S, "Pecan", "Pekannuss", "Pacana", "Pacanier", "Carya illinoinensis|Pecannuss|Nuez pecana|Noix de pécan"),
    ("bitternut", "hickory", S, "Bitternut hickory", "Bitternuss", "Nogal amargo", "Caryer amer", "Carya cordiformis|Bitternuss-Hickory|Sumpfhickory"),
    ("swiss-stone-pine", "nut-tree", S, "Swiss stone pine", "Zirbe", "Pino cembro", "Pin cembro", "Pinus cembra|Zirbelkiefer|Arve|Zirbelnuss|Zirbennuss|Pinus koraiensis|Koreakiefer|Pinus sibirica"),
    ("stone-pine", "nut-tree", S, "Stone pine", "Pinie", "Pino piñonero", "Pin parasol", "Pinus pinea|Pinienkern|Piñón|Pignon"),
    ("ginkgo", "nut-tree", S, "Ginkgo", "Ginkgo", "Ginkgo", "Ginkgo", "Ginkgo biloba|Fächerblattbaum|Ginkgonuss|Ginkgo-Nuss|Ginkyo"),
    ("monkey-puzzle", "nut-tree", S, "Monkey puzzle", "Andentanne", "Araucaria", "Désespoir des singes", "Araucaria araucana|Chilenische Araukarie|Araukarie|Pehuén"),
    ("pistachio", "nut-tree", S, "Pistachio", "Pistazie", "Pistachero", "Pistachier", "Pistacia vera|Pistazienbaum|Pistacho|Pistache"),
    ("cashew", "nut-tree", S, "Cashew", "Cashewbaum", "Marañón", "Anacardier", "Anacardium occidentale|Cashewnuss|Cajueiro|Caju|Anacarde|Merey|Korosho|Kaju"),
    ("macadamia", "nut-tree", S, "Macadamia", "Macadamia", "Macadamia", "Macadamia", "Macadamia integrifolia|Macadamia tetraphylla|Queensland-Nuss|Macadamianuss"),
    ("shea", "nut-tree", S, "Shea tree", "Sheanussbaum", "Karité", "Karité", "Vitellaria paradoxa|Butyrospermum parkii|Shea|Karitébaum|Shi"),

    # --- Climbing fruit -------------------------------------------------------------
    ("climbing-fruit", "", S, "Climbing fruit", "Kletterobst", "Trepadora frutal", "Fruitier grimpant", "Rankobst|Schlingpflanze|Kletterpflanze|Rankpflanze"),
    ("grapevine", "climbing-fruit", S, "Grapevine", "Weinrebe", "Vid", "Vigne", "Vitis vinifera|Weinstock|Weintraube|Tafeltraube|Rebe|Traube|Uva|Raisin|PIWI|Muskattraube|Muscat bleu|Isabella|Vitis labrusca"),
    ("kiwi", "climbing-fruit", S, "Kiwi", "Kiwi", "Kiwi", "Kiwi", "Actinidia deliciosa|Actinidia chinensis|Kiwipflanze|Kiwifrucht|Strahlengriffel|Solissimo"),
    ("hardy-kiwi", "kiwi", S, "Hardy kiwi", "Kiwibeere", "Kiwiño", "Kiwaï", "Actinidia arguta|Actinidia kolomikta|Minikiwi|Mini-Kiwi|Weiki|Issai|Nergi|Ken's Red|Scharfzähniger Strahlengriffel"),
    ("hop", "climbing-fruit", H, "Hop", "Hopfen", "Lúpulo", "Houblon", "Humulus lupulus|Hopfenspargel|Hopfensprosse|Hopfenpflanze"),
    ("schisandra", "climbing-fruit", H, "Schisandra", "Beerentraube", "Esquisandra", "Schisandra", "Schisandra chinensis|Chinesisches Spaltkörbchen|Fünf-Geschmack-Frucht|Wu Wei Zi|Magnolienbeere|Limonnik"),
    ("akebia", "climbing-fruit", S, "Chocolate vine", "Akebie", "Akebia", "Akébie", "Akebia quinata|Akebia trifoliata|Klettergurke|Schokoladenwein|Fingerblättrige Akebie"),
    ("maypop", "climbing-fruit", H, "Maypop", "Fleischfarbene Passionsblume", "Pasionaria", "Passiflore officinale", "Passiflora incarnata|Winterharte Passionsblume|Passiflora caerulea|Blaue Passionsblume|Passionsblume"),

    # --- Spice plants ---------------------------------------------------------------
    ("spice-plant", "", S, "Spice plant", "Gewürzpflanze", "Planta de especias", "Plante à épices", "Gewürzstrauch|Gewürzbaum|Especias|Épices|Especiarias"),
    ("sichuan-pepper", "spice-plant", S, "Sichuan pepper", "Szechuanpfeffer", "Pimienta de Sichuan", "Poivre du Sichuan", "Zanthoxylum simulans|Zanthoxylum piperitum|Zanthoxylum schinifolium|Zanthoxylum armatum|Japanpfeffer|Sansho|Timut|Sichuanpfeffer"),
    ("bay-laurel", "spice-plant", S, "Bay laurel", "Lorbeer", "Laurel", "Laurier-sauce", "Laurus nobilis|Lorbeerbaum|Gewürzlorbeer|Echter Lorbeer"),
    ("black-pepper", "spice-plant", S, "Black pepper", "Pfeffer", "Pimienta", "Poivrier", "Piper nigrum|Pfefferpflanze|Pfefferstrauch|Grüner Pfeffer|Weißer Pfeffer|Poivre|Pimenta-do-reino|Long pepper|Langer Pfeffer|Piper longum|Kampot"),
    ("vanilla", "spice-plant", S, "Vanilla", "Vanille", "Vainilla", "Vanillier", "Vanilla planifolia|Gewürzvanille|Vanilleorchidee|Baunilha|Bourbon-Vanille"),
    ("cinnamon", "spice-plant", S, "Cinnamon", "Zimt", "Canelo", "Cannelier", "Cinnamomum verum|Cinnamomum cassia|Zimtbaum|Ceylon-Zimt|Kassia|Cassia|Canela|Cannelle|Caneleira|Mdalasini"),
    ("cardamom", "spice-plant", S, "Cardamom", "Kardamom", "Cardamomo", "Cardamome", "Elettaria cardamomum|Grüner Kardamom|Schwarzer Kardamom|Amomum|Iliki|Elaichi"),
    ("clove", "spice-plant", S, "Clove", "Gewürznelke", "Clavo de olor", "Giroflier", "Syzygium aromaticum|Nelkenbaum|Gewürznelkenbaum|Clou de girofle|Cravo-da-índia|Karafuu"),
    ("nutmeg", "spice-plant", S, "Nutmeg", "Muskatnuss", "Nuez moscada", "Muscadier", "Myristica fragrans|Muskatnussbaum|Macis|Mace|Muskatblüte|Noix de muscade|Noz-moscada"),
    ("allspice", "spice-plant", S, "Allspice", "Jamaikapfeffer", "Pimienta de Jamaica", "Piment de la Jamaïque", "Pimenta dioica|Nelkenpfeffer|Pimentbaum|Allgewürz|Pimenta-da-jamaica"),
    ("ginger", "spice-plant", S, "Ginger", "Ingwer", "Jengibre", "Gingembre", "Zingiber officinale|Ingwerknolle|Ingwerwurzel|Gengibre|Tangawizi|Adrak"),
    ("turmeric", "spice-plant", S, "Turmeric", "Kurkuma", "Cúrcuma", "Curcuma", "Curcuma longa|Gelbwurz|Gelbwurzel|Açafrão-da-terra|Manjano|Haldi"),
    ("galangal", "spice-plant", S, "Galangal", "Galgant", "Galanga", "Galanga", "Alpinia galanga|Alpinia officinarum|Thai-Ingwer|Siam-Ingwer|Lengkuas"),
    ("lemongrass", "spice-plant", S, "Lemongrass", "Zitronengras", "Hierba limón", "Citronnelle", "Cymbopogon citratus|Lemon grass|Zitronellgras|Capim-santo|Capim-limão|Sereh|Mchaichai"),
    ("curry-leaf", "spice-plant", S, "Curry leaf", "Curryblatt", "Hoja de curry", "Kaloupilé", "Murraya koenigii|Currybaum|Curry tree|Kari patta|Arbre à curry|Feuille de curry"),
    ("pandan", "spice-plant", S, "Pandan", "Pandan", "Pandan", "Pandanus", "Pandanus amaryllifolius|Schraubenbaum|Pandanblatt|Pandan wangi|Bai toey"),

    # --- Leaf, drink and shoot plants -----------------------------------------------
    ("linden", "", H, "Linden", "Linde", "Tilo", "Tilleul", "Tilia cordata|Tilia platyphyllos|Lindenbaum|Winterlinde|Sommerlinde|Lindenblüte|lime tree|basswood|Tila"),
    ("chinese-toon", "", S, "Chinese toon", "Chinesischer Surenbaum", "Cedro chino", "Cédrèle de Chine", "Toona sinensis|Cedrela sinensis|Gemüsebaum|Zwiebelbaum|Xiang Chun|Toona"),
    ("moringa", "", S, "Moringa", "Moringa", "Moringa", "Moringa", "Moringa oleifera|Meerrettichbaum|Drumstick tree|Mlonge|Mronge|Malunggay|Sajna|Ben ailé"),
    ("chaya", "", S, "Chaya", "Chaya", "Chaya", "Chaya", "Cnidoscolus aconitifolius|Tree spinach|Mexikanischer Baumspinat"),
    ("neem", "", H, "Neem", "Neembaum", "Nim", "Margousier", "Azadirachta indica|Niembaum|Neem tree|Mwarubaini|Nimbo"),
    ("coffee", "", S, "Coffee plant", "Kaffeepflanze", "Cafeto", "Caféier", "Coffea arabica|Coffea canephora|Coffea liberica|Kaffeestrauch|Kaffeebaum|Arabica|Robusta|Cafezeiro|Kahawa"),
    ("tea-plant", "", H, "Tea plant", "Teestrauch", "Planta del té", "Théier", "Camellia sinensis|Teepflanze|Thea sinensis|Chá"),
    ("yerba-mate", "", H, "Yerba mate", "Mate", "Yerba mate", "Maté", "Ilex paraguariensis|Matestrauch|Matetee|Erva-mate"),
    ("rooibos", "", H, "Rooibos", "Rooibos", "Rooibos", "Rooibos", "Aspalathus linearis|Rotbusch"),
    ("sugarcane", "", G, "Sugarcane", "Zuckerrohr", "Caña de azúcar", "Canne à sucre", "Saccharum officinarum|Cana-de-açúcar|Miwa|Ganna"),
    ("vetiver", "", G, "Vetiver", "Vetivergras", "Vetiver", "Vétiver", "Chrysopogon zizanioides|Vetiveria zizanioides|Khus|Pasto vetiver"),
    ("bamboo", "", S, "Bamboo", "Bambus", "Bambú", "Bambou", "Phyllostachys|Phyllostachys edulis|Phyllostachys aureosulcata|Phyllostachys nuda|Moso|Bambussprosse|Bambusschössling|Bambusa|Dendrocalamus|Guadua|Gigantochloa|Mianzi"),

    # --- Nitrogen fixers and pioneer trees ------------------------------------------
    ("nitrogen-fixer", "", G, "Nitrogen-fixing tree", "Stickstoffsammler", "Fijador de nitrógeno", "Fixateur d'azote", "Stickstofffixierer|Stickstoffbinder|N-Fixierer|nitrogen fixer"),
    ("siberian-pea-shrub", "nitrogen-fixer", G, "Siberian pea shrub", "Erbsenstrauch", "Acacia de Siberia", "Caraganier", "Caragana arborescens|Gemeiner Erbsenstrauch|Caragana"),
    ("alder", "nitrogen-fixer", G, "Alder", "Erle", "Aliso", "Aulne", "Alnus glutinosa|Alnus cordata|Alnus incana|Schwarzerle|Herzblättrige Erle|Italienische Erle|Grauerle"),
    ("black-locust", "nitrogen-fixer", G, "Black locust", "Robinie", "Falsa acacia", "Robinier", "Robinia pseudoacacia|Scheinakazie|Falsche Akazie|Akazie|Akazienblüte"),
    ("leucaena", "nitrogen-fixer", G, "Leucaena", "Leucaena", "Leucaena", "Leucaena", "Leucaena leucocephala|Weißkopfmimose|Guaje|Ipil-ipil|Lamtoro|Faux mimosa"),
    ("gliricidia", "nitrogen-fixer", G, "Gliricidia", "Gliricidia", "Madre de cacao", "Gliricidia", "Gliricidia sepium|Mata ratón|Madero negro|Mother of cocoa|Kakawate"),
    ("inga", "nitrogen-fixer", G, "Inga", "Inga", "Guaba", "Pois sucré", "Inga edulis|Ice cream bean|Eiscremebohne|Guama|Ingá|Pacay"),
    ("calliandra", "nitrogen-fixer", G, "Calliandra", "Calliandra", "Calliandra", "Calliandra", "Calliandra calothyrsus|Puderquastenstrauch|Powder puff"),
    ("sesbania", "nitrogen-fixer", G, "Sesbania", "Sesbanie", "Sesbania", "Sesbania", "Sesbania sesban|Sesbania grandiflora|Agati|Katurai"),
    ("faidherbia", "nitrogen-fixer", G, "Faidherbia", "Anabaum", "Faidherbia", "Faidherbia", "Faidherbia albida|Acacia albida|Winterthorn|Apple-ring acacia|Kad|Msangu"),

    # --- Pioneer and biomass trees --------------------------------------------------
    ("pioneer-tree", "", G, "Pioneer tree", "Pioniergehölz", "Árbol pionero", "Arbre pionnier", "Biomassegehölz|Ammengehölz|Vorwaldgehölz|Pionierbaum|Biomasse-Gehölz|chop and drop"),
    ("poplar", "pioneer-tree", G, "Poplar", "Pappel", "Álamo", "Peuplier", "Populus|Hybridpappel|Balsampappel|Schwarzpappel|Zitterpappel|Espe|Aspe|Chopo"),
    ("willow", "pioneer-tree", G, "Willow", "Weide", "Sauce", "Saule", "Salix|Korbweide|Flechtweide|Silberweide|Salweide|Kopfweide|Salix viminalis|Mimbre|Osier"),
    ("birch", "pioneer-tree", G, "Birch", "Birke", "Abedul", "Bouleau", "Betula pendula|Betula pubescens|Sandbirke|Moorbirke|Hängebirke|Birkenwasser|Birkensaft"),
    ("field-maple", "pioneer-tree", G, "Field maple", "Feldahorn", "Arce campestre", "Érable champêtre", "Acer campestre|Maßholder|Massholder|Acer"),
]
