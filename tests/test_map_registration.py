"""Plate-carree basemap pixels versus the interactive map projection."""

import math

LONDON_LAT = 51.5081
LONDON_LON = -0.1281
MERCATOR_MAX_LAT = 85.0511287798


def equirect_fraction(lat: float, lon: float) -> tuple[float, float]:
    """Fraction across a plate-carree image. Origin is the north-west corner."""
    return (lon + 180.0) / 360.0, (90.0 - lat) / 180.0


def mercator_y(lat: float) -> float:
    lat = max(min(lat, MERCATOR_MAX_LAT), -MERCATOR_MAX_LAT)
    s = math.sin(math.radians(lat))
    return math.log((1 + s) / (1 - s)) / 2


def equirect_latitude_under_mercator_marker(lat: float) -> float:
    """Latitude of the plate-carree pixel under a Web Mercator marker.

    Leaflet's default CRS stretches an imageOverlay of [-90, 90] between the
    mercator y of ±85.0511287798. Longitude is linear in both projections.
    """
    span = mercator_y(MERCATOR_MAX_LAT)
    y = mercator_y(lat)
    fraction_from_north = (1.0 - y / span) / 2.0
    return 90.0 - fraction_from_north * 180.0


def epsg4326_fraction(lat: float, lon: float) -> tuple[float, float]:
    """Leaflet CRS.EPSG4326 transformation(1/180, 1, -1/180, 0.5) on LonLat."""
    y_north = -90.0 / 180.0 + 0.5
    y_south = 90.0 / 180.0 + 0.5
    y = -lat / 180.0 + 0.5
    x = lon / 180.0 + 1.0
    return (x - 0.0) / 2.0, (y - y_north) / (y_south - y_north)


def test_mercator_puts_london_on_the_northwest_african_pixel():
    apparent = equirect_latitude_under_mercator_marker(LONDON_LAT)
    assert 29.0 < apparent < 31.5


def test_epsg4326_puts_london_on_its_plate_carree_pixel():
    got = epsg4326_fraction(LONDON_LAT, LONDON_LON)
    expect = equirect_fraction(LONDON_LAT, LONDON_LON)
    assert math.isclose(got[0], expect[0], abs_tol=1e-12)
    assert math.isclose(got[1], expect[1], abs_tol=1e-12)


def test_interactive_page_uses_the_plate_carree_crs():
    text = open("orbitrx/ui/leaflet_map.py", encoding="utf-8").read()
    assert "crs: L.CRS.EPSG4326" in text
    assert "function registrationError" in text
