# =============================================================================
# fetchers.py – Zyflex AI Data Fetchers
# Each function fetches one type of external data.
# All functions return clean Python dicts/lists – no raw API response.
# If a fetch fails, it logs the error and returns safe fallback data.
# =============================================================================

import requests
import logging
from datetime import datetime
from config import (
    OPEN_METEO_URL,
    TICKETMASTER_URL,
    TICKETMASTER_API_KEY,
    TICKETMASTER_SEARCH_RADIUS,
    TICKETMASTER_CITY,
    TICKETMASTER_COUNTRY,
    OVERPASS_URL,
    OVERPASS_RADIUS_M,
    ZONES,
)

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# 1. WEATHER FETCHER
#    Uses Open-Meteo – completely free, no API key needed.
#    Returns current weather + hourly precipitation for Horsens.
# ─────────────────────────────────────────────────────────────────────────────

def fetch_weather(lat: float = 55.8615, lon: float = 9.8506) -> dict:
    """
    Fetch current weather conditions for a given coordinate.

    Returns:
        {
            "temperature": float,       # Celsius
            "precipitation": float,     # mm/hour current
            "windspeed": float,         # km/h
            "weathercode": int,         # WMO weather code
            "is_raining": bool,
            "is_heavy_rain": bool,
            "is_cold": bool,
            "source": str
        }
    """
    params = {
        "latitude": lat,
        "longitude": lon,
        "current_weather": True,
        "hourly": "precipitation,precipitation_probability,temperature_2m",
        "forecast_days": 1,
        "timezone": "Europe/Copenhagen",
    }

    try:
        response = requests.get(OPEN_METEO_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        current = data.get("current_weather", {})
        hourly  = data.get("hourly", {})

        # Find the precipitation for the current hour
        times = hourly.get("time", [])
        precip = hourly.get("precipitation", [])
        current_hour_str = datetime.now().strftime("%Y-%m-%dT%H:00")
        precipitation = 0.0

        if current_hour_str in times:
            idx = times.index(current_hour_str)
            precipitation = float(precip[idx]) if idx < len(precip) else 0.0
        elif precip:
            # Fallback: use the first available hour
            precipitation = float(precip[0])

        temperature  = float(current.get("temperature", 12.0))
        windspeed    = float(current.get("windspeed", 0.0))
        weathercode  = int(current.get("weathercode", 0))

        result = {
            "temperature":   temperature,
            "precipitation": precipitation,
            "windspeed":     windspeed,
            "weathercode":   weathercode,
            "is_raining":    precipitation >= 0.5,
            "is_heavy_rain": precipitation >= 3.0,
            "is_cold":       temperature <= 5.0,
            "source":        "open-meteo.com",
        }
        logger.info(f"Weather fetched: {temperature}°C, {precipitation}mm/h rain")
        return result

    except Exception as e:
        logger.warning(f"Weather fetch failed: {e} – using fallback data")
        return {
            "temperature":   12.0,
            "precipitation": 0.0,
            "windspeed":     10.0,
            "weathercode":   0,
            "is_raining":    False,
            "is_heavy_rain": False,
            "is_cold":       False,
            "source":        "fallback",
        }


# ─────────────────────────────────────────────────────────────────────────────
# 2. EVENTS FETCHER
#    Uses Ticketmaster Discovery API (optional key).
#    Falls back to mock events if no key is configured.
# ─────────────────────────────────────────────────────────────────────────────

def fetch_events() -> list:
    """
    Fetch upcoming events in the operating area.

    Returns:
        List of dicts:
        [
            {
                "name": str,
                "date": str,          # ISO date
                "venue": str,
                "city": str,
                "lat": float,
                "lon": float,
                "attendance": int,    # Estimated attendance
                "category": str,
            },
            ...
        ]
    """
    if not TICKETMASTER_API_KEY:
        logger.info("No Ticketmaster API key – using mock event data")
        return _mock_events()

    params = {
        "apikey":      TICKETMASTER_API_KEY,
        "city":        TICKETMASTER_CITY,
        "countryCode": TICKETMASTER_COUNTRY,
        "radius":      TICKETMASTER_SEARCH_RADIUS,
        "unit":        "km",
        "size":        20,
        "sort":        "date,asc",
    }

    try:
        response = requests.get(TICKETMASTER_URL, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        events_raw = (
            data.get("_embedded", {}).get("events", [])
        )
        events = []

        for evt in events_raw:
            venue_info = {}
            venues = evt.get("_embedded", {}).get("venues", [])
            if venues:
                venue_info = venues[0]

            location = venue_info.get("location", {})
            events.append({
                "name":       evt.get("name", "Ukendt event"),
                "date":       evt.get("dates", {}).get("start", {}).get("localDate", ""),
                "venue":      venue_info.get("name", "Ukendt venue"),
                "city":       venue_info.get("city", {}).get("name", TICKETMASTER_CITY),
                "lat":        float(location.get("latitude",  55.8615)),
                "lon":        float(location.get("longitude", 9.8506)),
                "attendance": _estimate_attendance(evt),
                "category":   _get_category(evt),
            })

        logger.info(f"Events fetched: {len(events)} events found")
        return events

    except Exception as e:
        logger.warning(f"Events fetch failed: {e} – using mock data")
        return _mock_events()


def _estimate_attendance(evt: dict) -> int:
    """Rough attendance estimate based on event classification."""
    segment = (
        evt.get("classifications", [{}])[0]
           .get("segment", {})
           .get("name", "")
           .lower()
    )
    if "music" in segment:
        return 2000
    if "sports" in segment:
        return 3000
    return 500


def _get_category(evt: dict) -> str:
    """Extract readable category from Ticketmaster classification."""
    classifications = evt.get("classifications", [{}])
    if classifications:
        segment = classifications[0].get("segment", {}).get("name", "Andet")
        genre   = classifications[0].get("genre",   {}).get("name", "")
        return f"{segment} – {genre}" if genre else segment
    return "Andet"


def _mock_events() -> list:
    """
    Realistic mock events for when no API key is present.
    Based on typical events in the Horsens area.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    return [
        {
            "name":       "Fodboldkamp – AC Horsens",
            "date":       today,
            "venue":      "CASA Arena Horsens",
            "city":       "Horsens",
            "lat":        55.8517,
            "lon":        9.8625,
            "attendance": 10000,
            "category":   "Sport – Fodbold",
        },
        {
            "name":       "Fredagskoncert i Horsens",
            "date":       today,
            "venue":      "Horsens Bypark",
            "city":       "Horsens",
            "lat":        55.8615,
            "lon":        9.8506,
            "attendance": 1500,
            "category":   "Musik – Pop",
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# 3. LOCATIONS FETCHER
#    Uses OpenStreetMap Overpass API – free, no key needed.
#    Counts points-of-interest (hotels, bars, hospitals) around each zone.
# ─────────────────────────────────────────────────────────────────────────────

def fetch_locations() -> dict:
    """
    For each zone, count nearby POIs using OpenStreetMap Overpass API.
    POI types that drive taxi demand: hotels, bars, restaurants, hospitals,
    train stations, shopping centres.

    Returns:
        {
            "zone_id": {
                "hotels": int,
                "bars": int,
                "restaurants": int,
                "total_pois": int,
            },
            ...
        }
    """
    results = {}

    for zone in ZONES:
        zone_id = zone["id"]
        lat     = zone["lat"]
        lon     = zone["lon"]
        radius  = OVERPASS_RADIUS_M

        # Overpass QL query – finds key POIs within radius
        query = f"""
        [out:json][timeout:15];
        (
          node["tourism"="hotel"](around:{radius},{lat},{lon});
          node["amenity"="bar"](around:{radius},{lat},{lon});
          node["amenity"="pub"](around:{radius},{lat},{lon});
          node["amenity"="nightclub"](around:{radius},{lat},{lon});
          node["amenity"="restaurant"](around:{radius},{lat},{lon});
          node["amenity"="hospital"](around:{radius},{lat},{lon});
          node["railway"="station"](around:{radius},{lat},{lon});
          node["shop"="mall"](around:{radius},{lat},{lon});
        );
        out count;
        """

        try:
            response = requests.post(
                OVERPASS_URL,
                data={"data": query},
                timeout=20
            )
            response.raise_for_status()
            data = response.json()

            total = data.get("elements", [{}])[0].get("tags", {}).get("total", 0)
            total = int(total) if total else 0

            results[zone_id] = {
                "hotels":      _count_poi(data, "tourism",  "hotel"),
                "bars":        _count_poi(data, "amenity",  "bar") + _count_poi(data, "amenity", "pub"),
                "restaurants": _count_poi(data, "amenity",  "restaurant"),
                "hospitals":   _count_poi(data, "amenity",  "hospital"),
                "stations":    _count_poi(data, "railway",  "station"),
                "total_pois":  total,
            }
            logger.info(f"Locations fetched for {zone_id}: {total} POIs")

        except Exception as e:
            logger.warning(f"Location fetch failed for {zone_id}: {e} – using defaults")
            results[zone_id] = _default_location_data(zone)

    return results


def _count_poi(data: dict, key: str, value: str) -> int:
    """Count elements matching a specific OSM tag."""
    elements = data.get("elements", [])
    return sum(
        1 for el in elements
        if el.get("tags", {}).get(key) == value
    )


def _default_location_data(zone: dict) -> dict:
    """
    Sensible default POI counts when Overpass API is unavailable.
    Based on zone type so scores are still meaningful.
    """
    poi_type = zone.get("poi_type", "city_center")
    defaults = {
        "city_center":   {"hotels": 5,  "bars": 8,  "restaurants": 12, "hospitals": 0, "stations": 1, "total_pois": 26},
        "transport_hub": {"hotels": 2,  "bars": 3,  "restaurants": 5,  "hospitals": 0, "stations": 3, "total_pois": 13},
        "hospital":      {"hotels": 0,  "bars": 0,  "restaurants": 2,  "hospitals": 1, "stations": 0, "total_pois":  3},
        "venue":         {"hotels": 3,  "bars": 5,  "restaurants": 4,  "hospitals": 0, "stations": 0, "total_pois": 12},
    }
    return defaults.get(poi_type, defaults["city_center"])
