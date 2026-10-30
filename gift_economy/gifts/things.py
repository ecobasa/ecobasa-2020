"""Recognizing things (models.Thing) in the titles of offers and wishes, in any language:
"Two old ladders" is a Ladder, "Handkreissäge Bosch" a Circular saw, "Brennholz, trocken"
Firewood. Each kind of listing has its own vocabulary (gifts/vocabularies/): a tool is
looked up among tools, a vehicle among vehicles; "other" things among all of them. Matching then goes by the things and how they relate (related()), so a wish
for a "Leiter" finds an offered "ladder", and a wish for a "saw" an offered "jigsaw".

A name's words each have to be in the title, as they are, in the plural ("ladder" in
"ladders", "Leiter" in "Leitern") or, for words of four letters or more, at the end of a
compound ("Kreissäge" in "Handkreissäge", "Pflanze" in "Tomatenpflanzen"). The thing
whose matching name is longest wins: "Stepladder" over "Ladder", "Firewood" over "Wood";
and a narrower thing over a broader one also in the title ("bean seeds" are Beans, "Tomate
Ochsenherz" a Beefsteak tomato). "Tomatensamen" is read as "Tomaten" + "Samen"."""

import re

# Words shorter than this say nothing on their own ("de", "à", "of")
MIN_WORD = 3
# A compound ends with a name word at least this long ("Kreissäge", not "Rad")
MIN_COMPOUND = 4
# Plural endings: "ladder"–"ladders", "Leiter"–"Leitern", "brush"–"brushes"
MAX_PLURAL = 2
# German compounds that end in what they are seeds of: "Tomatensamen", "Gemüsesaatgut"
SEED_ENDINGS = ("saatgut", "samen", "saat")

_cache = None


def clear_cache():
    global _cache, _names_cache
    _cache = _names_cache = None


def _words(text):
    # "E-Bike", "E-Lastenrad": a one-letter prefix belongs to its word
    text = re.sub(r"\b(\w)-(?=\w)", r"\1", text.casefold())
    # Short words say nothing, unless they mix digits and letters ("3D")
    return [
        word for word in re.findall(r"\w+", text)
        if not word.isdigit() and (len(word) >= MIN_WORD or (re.search(r"\d", word) and re.search(r"[^\W\d]", word)))
    ]


def build_index(things):
    """(names, parents) of the things given (a queryset of Thing, or of the historical
    model in a migration): names is a list of (words of a name, thing id, vocabulary),
    parents maps each thing's id to its broader thing's."""
    names, parents = [], {}
    for thing in things:
        parents[thing.pk] = thing.parent_id
        for name in list(thing.names.values()) + list(thing.other_names):
            words = _words(name)
            if words:
                names.append((words, thing.pk, thing.kind))
    return names, parents


# Kinds of listing whose title has to be a name from their vocabulary: matching depends on
# knowing exactly which crop, food, vehicle, tool or material it is (a salvaged window, not
# "Fenster ausgebaut"); details go in the description
WHITELISTED_KINDS = ("seeds_plants", "food", "vehicle", "tool", "material")

_names_cache = None


def _names():
    """{vocabulary: {name in any language, folded: (thing id, the name)}}, cached."""
    global _names_cache
    if _names_cache is None:
        from .models import Thing
        _names_cache = {}
        for thing in Thing.objects.all():
            names = _names_cache.setdefault(thing.kind, {})
            for name in list(thing.names.values()) + list(thing.other_names):
                names.setdefault(" ".join(name.casefold().split()), (thing.pk, name))
    return _names_cache


def thing_named(name, kind):
    """The id of the thing of the kind's vocabulary called exactly that, in any language
    or by one of its other names, else None."""
    found = _names().get(kind, {}).get(" ".join((name or "").casefold().split()))
    return found[0] if found else None


def suggest(q, kind, lang="en", limit=15):
    """Names from the kind's vocabulary for what is being typed: in the reader's language
    or by one of a thing's other names (a regional word like "Paradeiser", a botanical
    name); only if none fits, in another language ("Tomato" typed in German). Each thing
    once, names starting with what was typed first, then those with a word starting with
    it ("Prunus tomentosa" after "Tomate")."""
    from .models import Thing
    q = " ".join(q.casefold().split())
    if len(q) < 2:
        return []

    def rank(name):
        """0 starts with it, 1 a word starts with it, 2 has it inside, None not at all."""
        folded = " ".join(name.casefold().split())
        if q not in folded:
            return None
        return 0 if folded.startswith(q) else 1 if f" {q}" in folded else 2

    own, foreign = [], []
    for thing in Thing.objects.filter(kind=kind).only("names", "other_names"):
        reader = thing.get_name(lang)
        for name in [reader, *thing.other_names]:
            if (fit := rank(name)) is not None:
                own.append((fit, name.casefold(), name))
                break
        else:
            for name in thing.names.values():
                if (fit := rank(name)) is not None:
                    foreign.append((fit, name.casefold(), name))
                    break
    return [name for *_, name in sorted(own or foreign)][:limit]


def _index():
    global _cache
    if _cache is None:
        from .models import Thing
        _cache = build_index(Thing.objects.all())
    return _cache


def _word_fits(name_word, title_word):
    """How well a title word stands for a name word: 2 the same, 1 a plural or a
    compound ending with it, 0 not."""
    if title_word == name_word:
        return 2
    if title_word.startswith(name_word) and len(title_word) - len(name_word) <= MAX_PLURAL:
        return 1
    if len(name_word) >= MIN_COMPOUND and any(
        title_word[:len(title_word) - plural].endswith(name_word) for plural in range(MAX_PLURAL + 1)
    ):
        return 1
    return 0


# Listing kinds looked up in every vocabulary
ANY_VOCABULARY = ("other", None)


def recognize(title, kind=None, index=None):
    """The id of the thing in the title, in the vocabulary of the listing's kind (in all of
    them for "other" things), or None."""
    names, parents = index or _index()
    title_words = _words(title or "")
    if not title_words:
        return None
    title_words += [
        word[:-len(ending)] for word in title_words for ending in SEED_ENDINGS
        if word.endswith(ending) and len(word) - len(ending) >= MIN_WORD
    ]
    scores = {}
    for words, thing_id, vocabulary in names:
        if kind not in ANY_VOCABULARY and vocabulary != kind:
            continue
        score = 0
        for word in words:
            fits = max(_word_fits(word, title_word) for title_word in title_words)
            if not fits:
                break
            score += len(word) * 2 + fits
        else:
            scores[thing_id] = max(score, scores.get(thing_id, 0))
    # A broader thing also in the title gives way to the narrower one
    broader = {ancestor for thing_id in scores for ancestor in _ancestors(thing_id, parents)[1:]}
    candidates = {thing_id: score for thing_id, score in scores.items() if thing_id not in broader}
    return max(candidates, key=candidates.get) if candidates else None


def _ancestors(thing_id, parents):
    seen = []
    while thing_id is not None and thing_id not in seen:
        seen.append(thing_id)
        thing_id = parents.get(thing_id)
    return seen


def related(a, b, index=None):
    """Whether two things fit each other: the same, or one is a broader thing of the
    other (a wish for a saw, an offered jigsaw). Siblings don't (firewood, timber)."""
    if a is None or b is None:
        return False
    parents = (index or _index())[1]
    return a in _ancestors(b, parents) or b in _ancestors(a, parents)


def recognize_all(Listing, Thing):
    """Recognize the things in the titles of all things listed (also with the historical
    models of a migration). Returns how many were recognized."""
    index = build_index(Thing.objects.all())
    count = 0
    # A migration's model may not have every field yet
    fields = [f for f in ("title", "variety", "kind", "thing_id") if f in {field.attname for field in Listing._meta.fields}]
    for listing in Listing.objects.filter(kind__in=("material", "tool", "vehicle", "seeds_plants", "food", "other")).only(*fields):
        variety = getattr(listing, "variety", "")
        title = f"{listing.title} {variety}" if variety else listing.title
        thing_id = recognize(title, listing.kind, index)
        if thing_id != listing.thing_id:
            Listing.objects.filter(pk=listing.pk).update(thing_id=thing_id)
        count += thing_id is not None
    return count
