"""The timezone of a place, from the tables that come with the system's timezone data: the
zone of the place's country (zone.tab) whose main city is nearest, among the zones of their
own (zone1970.tab; Busingen is only another name for Zurich's). Good enough to preset a
form, where it can be changed, in a country with one clock. Where a country has several
(the US, Russia, Brazil…) their borders follow states and counties, not the nearest city:
Dallas is nearer to Indiana's main city than to Chicago. There the browser's knows better,
when it is one of that country's (`zones_apart`)."""

import math
import os
import zoneinfo
from datetime import date, datetime
from functools import cache


def _degrees(text):
    """+DDMM, +DDMMSS, +DDDMM or +DDDMMSS as degrees."""
    sign = -1 if text[0] == "-" else 1
    digits = text[1:]
    whole = 2 if len(digits) in (4, 6) else 3
    parts = [digits[:whole], digits[whole:whole + 2], digits[whole + 2:] or "0"]
    return sign * (int(parts[0]) + int(parts[1]) / 60 + int(parts[2]) / 3600)


def _rows(name):
    """The columns of a table's lines; none without it."""
    for folder in zoneinfo.TZPATH:
        path = os.path.join(folder, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as table:
                return [line.rstrip("\n").split("\t") for line in table if line.strip() and not line.startswith("#")]
    return []


@cache
def _cities():
    """[(latitude, longitude, zone, country)] of the main city of each zone of its own."""
    own = {row[2] for row in _rows("zone1970.tab")}
    cities = []
    for country, coordinates, zone, *_area in _rows("zone.tab"):
        if own and zone not in own:
            continue
        # +5230+01322: latitude, then longitude from the second sign
        cut = max(coordinates.rfind("+"), coordinates.rfind("-"))
        cities.append((_degrees(coordinates[:cut]), _degrees(coordinates[cut:]), zone, country))
    return cities


def _nearest(point, country):
    """The city (as in _cities) of `country` (its code, any without) nearest `point`."""
    if point is None or not _cities():
        return None
    lat, lon = math.radians(point.y), math.radians(point.x)

    def distance(city):
        city_lat, city_lon = math.radians(city[0]), math.radians(city[1])
        # The angle between them on the globe
        return math.acos(max(-1, min(1, (
            math.sin(lat) * math.sin(city_lat) + math.cos(lat) * math.cos(city_lat) * math.cos(lon - city_lon)
        ))))

    cities = [city for city in _cities() if city[3] == country] or _cities()
    return min(cities, key=distance)


def _clock(name):
    """Its offsets in winter and summer."""
    year = date.today().year
    return tuple(datetime(year, month, 15, tzinfo=zoneinfo.ZoneInfo(name)).utcoffset() for month in (1, 7))


def zone_at(point, country=None):
    """The timezone's name ("Europe/Berlin") at `point`, in `country` (its code) where it is
    known; None without a point."""
    city = _nearest(point, country)
    return city[2] if city else None


def zones_apart(point, country=None):
    """The zones of the country at `point` if they keep more than one clock; else none."""
    city = _nearest(point, country)
    if not city:
        return []
    zones = [other[2] for other in _cities() if other[3] == city[3]]
    return zones if len({_clock(zone) for zone in zones}) > 1 else []


@cache
def countries_apart():
    """The codes of the countries whose zones keep more than one clock."""
    zones = {}
    for _lat, _lon, zone, country in _cities():
        zones.setdefault(country, []).append(zone)
    return sorted(country for country, names in zones.items() if len({_clock(zone) for zone in names}) > 1)
