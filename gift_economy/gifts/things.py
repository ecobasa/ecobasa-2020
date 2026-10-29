"""Recognizing things (models.Thing) in the titles of offers and wishes, in any language:
"Two old ladders" is a Ladder, "Handkreissäge Bosch" a Circular saw, "Brennholz, trocken"
Firewood. Each kind of listing has its own vocabulary (gifts/vocabularies/): a tool is
looked up among tools, a vehicle among vehicles; "other" things among all of them. Matching then goes by the things and how they relate (related()), so a wish
for a "Leiter" finds an offered "ladder", and a wish for a "saw" an offered "jigsaw".

A name's words each have to be in the title, as they are, in the plural ("ladder" in
"ladders", "Leiter" in "Leitern") or, for words of four letters or more, at the end of a
compound ("Kreissäge" in "Handkreissäge", "Pflanze" in "Tomatenpflanzen"). The thing
whose matching name is longest wins: "Stepladder" over "Ladder", "Firewood" over "Wood"."""

import re

# Words shorter than this say nothing on their own ("de", "à", "of")
MIN_WORD = 3
# A compound ends with a name word at least this long ("Kreissäge", not "Rad")
MIN_COMPOUND = 4
# Plural endings: "ladder"–"ladders", "Leiter"–"Leitern", "brush"–"brushes"
MAX_PLURAL = 2

_cache = None


def clear_cache():
    global _cache
    _cache = None


def _words(text):
    return [word for word in re.findall(r"\w+", text.casefold()) if len(word) >= MIN_WORD and not word.isdigit()]


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
    names, _parents = index or _index()
    title_words = _words(title or "")
    if not title_words:
        return None
    best, best_score = None, 0
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
            if score > best_score:
                best, best_score = thing_id, score
    return best


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
    for listing in Listing.objects.filter(kind__in=("material", "tool", "vehicle", "other")).only("pk", "title", "kind", "thing_id"):
        thing_id = recognize(listing.title, listing.kind, index)
        if thing_id != listing.thing_id:
            Listing.objects.filter(pk=listing.pk).update(thing_id=thing_id)
        count += thing_id is not None
    return count
