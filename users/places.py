"""A person's place as others see it: about where, never their door. People meet through
the platform (a match, so there can be references), so nobody gets the address before.

The world is cut into a grid of cells (CELL degrees, about 1–2 km). Others see a point
somewhere in the person's cell, the same one every time (from the cell and the person,
so it can't be averaged out), and the database sorts and filters by the cell's centre
(SnapToGrid), so a search or a map section can't narrow it down further either.
Communities are places to visit, so theirs stay exact."""
import hashlib
import math
import re

from django.conf import settings
from django.contrib.gis.geos import Point

CELL = 0.015


def _cell(value):
    return math.floor(value / CELL + 0.5)


def approximate(point, seed):
    """A point in the cell of `point`, always the same one for the same person (seed)."""
    if point is None:
        return None
    col, row = _cell(point.x), _cell(point.y)
    digest = hashlib.sha256(f"{settings.SECRET_KEY}:{seed}:{col}:{row}".encode()).digest()
    dx, dy = (int.from_bytes(digest[i:i + 4], "big") / 2**32 - 0.5 for i in (0, 4))
    return Point((col + dx) * CELL, (row + dy) * CELL, srid=point.srid or 4326)


# A postcode ("14473", "75001") or a house number ("5", "12a")
_NUMBER = re.compile(r"\b\d[\d\-]*[a-zA-Z]?\b")


def town(name):
    """The place's name without the street: "Hauptstraße 5, 14473 Potsdam, Deutschland"
    → "Potsdam, Deutschland" (the location picker writes it like on a letter)."""
    if not name:
        return name
    parts = [part.strip() for part in name.split(",") if part.strip()]
    if len(parts) >= 2 and (_NUMBER.search(parts[0]) or _NUMBER.search(parts[1])):
        parts = parts[1:]
    parts = [" ".join(_NUMBER.sub("", part).split()) for part in parts]
    return ", ".join(part for part in parts if part)
