from __future__ import annotations

import math

EARTH_RADIUS_MILES = 3958.8
COMPASS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]


def miles_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def bearing_degrees(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass(degrees: float) -> str:
    return COMPASS[int((degrees % 360 + 22.5) // 45) % 8]


def direction_from(lat1: float, lon1: float, lat2: float, lon2: float) -> str:
    """Compass direction from point 1 to point 2, e.g. "SW"."""
    return compass(bearing_degrees(lat1, lon1, lat2, lon2))


def offset(lat: float, lon: float, miles: float, bearing: float) -> tuple[float, float]:
    """Point `miles` away from (lat, lon) along `bearing` degrees."""
    d = miles / EARTH_RADIUS_MILES
    b = math.radians(bearing)
    p1, l1 = math.radians(lat), math.radians(lon)
    p2 = math.asin(math.sin(p1) * math.cos(d) + math.cos(p1) * math.sin(d) * math.cos(b))
    l2 = l1 + math.atan2(math.sin(b) * math.sin(d) * math.cos(p1), math.cos(d) - math.sin(p1) * math.sin(p2))
    return math.degrees(p2), math.degrees(l2)


COMPASS_BEARING = {name: i * 45.0 for i, name in enumerate(COMPASS)}

# Florida county FIPS codes (state 12). NWS alerts list affected counties as SAME
# codes: "0" + state + county, e.g. "012001" for Alachua.
FL_COUNTY_FIPS = {
    "alachua": "001", "baker": "003", "bay": "005", "bradford": "007", "brevard": "009", "broward": "011",
    "calhoun": "013", "charlotte": "015", "citrus": "017", "clay": "019", "collier": "021", "columbia": "023",
    "desoto": "027", "dixie": "029", "duval": "031", "escambia": "033", "flagler": "035", "franklin": "037",
    "gadsden": "039", "gilchrist": "041", "glades": "043", "gulf": "045", "hamilton": "047", "hardee": "049",
    "hendry": "051", "hernando": "053", "highlands": "055", "hillsborough": "057", "holmes": "059",
    "indianriver": "061", "jackson": "063", "jefferson": "065", "lafayette": "067", "lake": "069", "lee": "071",
    "leon": "073", "levy": "075", "liberty": "077", "madison": "079", "manatee": "081", "marion": "083",
    "martin": "085", "miamidade": "086", "monroe": "087", "nassau": "089", "okaloosa": "091", "okeechobee": "093",
    "orange": "095", "osceola": "097", "palmbeach": "099", "pasco": "101", "pinellas": "103", "polk": "105",
    "putnam": "107", "stjohns": "109", "stlucie": "111", "santarosa": "113", "sarasota": "115", "seminole": "117",
    "sumter": "119", "suwannee": "121", "taylor": "123", "union": "125", "volusia": "127", "wakulla": "129",
    "walton": "131", "washington": "133",
}


def fl_county_same_code(county: str) -> str | None:
    """SAME code for a Florida county name, tolerant of "Miami Dade", "St. Johns", "De Soto"."""
    key = "".join(ch for ch in county.lower().replace("saint", "st") if ch.isalpha())
    fips = FL_COUNTY_FIPS.get(key)
    return f"012{fips}" if fips else None


def point_in_polygon(lat: float, lon: float, geometry: dict) -> bool:
    """GeoJSON Polygon / MultiPolygon containment (ray casting, outer rings only)."""
    kind, coords = geometry.get("type"), geometry.get("coordinates") or []
    polygons = [coords] if kind == "Polygon" else coords if kind == "MultiPolygon" else []
    for polygon in polygons:
        ring = polygon[0] if polygon else []
        inside = False
        for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
            if (y1 > lat) != (y2 > lat) and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
                inside = not inside
        if inside:
            return True
    return False
