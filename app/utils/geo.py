from __future__ import annotations

import math

EARTH_RADIUS_METERS = 6371000


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.radians
    d_lat = rad(lat2 - lat1)
    d_lon = rad(lon2 - lon1)

    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(rad(lat1)) * math.cos(rad(lat2)) * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.asin(math.sqrt(a))
    return EARTH_RADIUS_METERS * c
