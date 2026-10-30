"""The curated vocabularies of things, one per kind of listing: tools, materials,
vehicles and other things (and seeds and plants, one vocabulary). A listing's title is
recognized in the vocabulary of its kind only (gifts.things), so "Bohnen" is a seed in a
seed offer and food in a material one. Loaded into gifts.Thing by the load_vocabularies
command."""

from .materials import MATERIALS
from .other import OTHER
from .plants import PLANTS
from .seeds import SEEDS
from .tools import TOOLS
from .vehicles import VEHICLES

# {Thing.kind: entries}
VOCABULARIES = {
    "tool": TOOLS,
    "material": MATERIALS,
    "vehicle": VEHICLES,
    "seeds": SEEDS + PLANTS,
    "other": OTHER,
}
