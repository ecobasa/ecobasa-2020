"""The Köppen-Geiger climate class of a place, for seeds: they grow best in a climate like
the one they were grown in. koppen_at(lat, lon) finds it in the about 3 km map in
koppen.bin (see build_koppen_map.py and NOTICE), read once per process into 1.5 MB."""

import struct
import zlib
from pathlib import Path

WIDTH, HEIGHT = 12960, 6480
# The map's class numbers
CLASSES = [
    None, "Af", "Am", "As", "Aw", "BSh", "BSk", "BWh", "BWk", "Cfa", "Cfb", "Cfc", "Csa", "Csb",
    "Csc", "Cwa", "Cwb", "Cwc", "Dfa", "Dfb", "Dfc", "Dfd", "Dsa", "Dsb", "Dsc", "Dsd", "Dwa",
    "Dwb", "Dwc", "Dwd", "EF", "ET", None,  # 32: ocean
]
# How far to look for land from a place on the coast that falls on a sea pixel (~3 km each)
COAST_PIXELS = 3

_map = None


def _load():
    """(the run-length encoded rows, where each row starts in them)."""
    global _map
    if _map is None:
        data = zlib.decompress(Path(__file__).with_name("koppen.bin").read_bytes())
        starts, offset = [], 0
        for _ in range(HEIGHT):
            starts.append(offset)
            offset += 2 + 3 * struct.unpack_from("<H", data, offset)[0]
        _map = (data, starts)
    return _map


def _class_number(x, y):
    if not (0 <= y < HEIGHT):
        return None
    x %= WIDTH
    data, starts = _load()
    offset = starts[y]
    (count,) = struct.unpack_from("<H", data, offset)
    offset += 2
    for _ in range(count):
        value, length = struct.unpack_from("<BH", data, offset)
        if x < length:
            return value
        x -= length
        offset += 3
    return None


def koppen_at(lat, lon):
    """The Köppen-Geiger class of a place ("Cfb"), or "" if it is at sea."""
    x = round((lon + 180) * WIDTH / 360 - 0.5)
    y = round((90 - lat) * HEIGHT / 180 - 0.5)
    for distance in range(COAST_PIXELS + 1):
        for dy in range(-distance, distance + 1):
            for dx in range(-distance, distance + 1):
                if max(abs(dx), abs(dy)) != distance:
                    continue
                number = _class_number(x + dx, y + dy)
                if number is not None and number < len(CLASSES) and CLASSES[number]:
                    return CLASSES[number]
    return ""
