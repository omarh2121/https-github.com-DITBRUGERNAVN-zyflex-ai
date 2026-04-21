# =============================================================================
# data_agent.py – Agent 1: Data Collection
#
# Ansvar: Hent ALT rådata for en given by.
# - Geocoder bynavnet til GPS koordinater
# - Henter vejrdata (Open-Meteo)
# - Henter events (Ticketmaster / mock)
# - Henter POI-lokationer (OpenStreetMap)
# - Genererer dynamiske zoner rundt om byen
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import requests
import logging
from datetime import datetime
from config import OPEN_METEO_URL, TICKETMASTER_URL, TICKETMASTER_API_KEY, OVERPASS_URL

# Sti til lokal events-fil
_LOCAL_EVENTS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "events.json"
)

logger = logging.getLogger(__name__)

# ── Hardcodet lookup til hurtig dansk geocoding ───────────────────────────────
DANISH_CITIES = {
    "horsens":      (55.8615, 9.8506),
    "aarhus":       (56.1629, 10.2039),
    "ikast":        (56.1389, 9.1578),
    "skanderborg":  (56.0431, 9.9270),
    "hedensted":    (55.7731, 9.7047),
    "vejle":        (55.7113, 9.5360),
    "silkeborg":    (56.1697, 9.5485),
    "kolding":      (55.4904, 9.4718),
    "fredericia":   (55.5655, 9.7532),
    "odense":       (55.4038, 10.4024),
    "aalborg":      (57.0488, 9.9217),
    "randers":      (56.4607, 10.0360),
    "esbjerg":      (55.4667, 8.4500),
    "herning":      (56.1396, 8.9771),
    "viborg":       (56.4532, 9.4023),
    "holstebro":    (56.3594, 8.6176),
    "copenhagen":   (55.6761, 12.5683),
    "kobenhavn":    (55.6761, 12.5683),
}


class DataAgent:
    """
    Agent 1 – henter al rå-data for en given by.
    Kald .run(city_name) for at starte.
    """

    def __init__(self, status_callback=None):
        self.status_callback = status_callback or (lambda msg: None)
        self.result = {}

    def run(self, city_name: str) -> dict:
        self._update(f"Geocoder '{city_name}'...")
        lat, lon, resolved_name = self._geocode(city_name)

        self._update(f"Henter vejrdata for {resolved_name}...")
        weather = self._fetch_weather(lat, lon)

        self._update(f"Henter events nær {resolved_name}...")
        events = self._fetch_events(city_name)

        self._update(f"Genererer zoner for {resolved_name}...")
        zones = self._build_zones(resolved_name, lat, lon)

        self._update(f"Henter POI-data for {len(zones)} zoner...")
        locations = self._fetch_locations(zones)

        # Markér om events er rigtige eller mock
        real_events = [e for e in events if e.get("source") == "ticketmaster"]
        event_src   = f"{len(real_events)} rigtige" if real_events else f"{len(events)} mock"

        self.result = {
            "city":          resolved_name,
            "lat":           lat,
            "lon":           lon,
            "weather":       weather,
            "events":        events,
            "zones":         zones,
            "locations":     locations,
            "fetched_at":    datetime.now().isoformat(),
            "events_source": "ticketmaster" if real_events else "mock",
        }
        self._update(f"✅ Data hentet – {event_src} events, {len(zones)} zoner")
        return self.result

    # ── Geocoding ────────────────────────────────────────────────────────────

    def _geocode(self, city_name: str):
        key = city_name.lower().strip()

        # Hurtig opslag i dansk tabel
        if key in DANISH_CITIES:
            lat, lon = DANISH_CITIES[key]
            return lat, lon, city_name.title()

        # Fallback: Nominatim (OpenStreetMap geocoding – gratis)
        try:
            resp = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={"q": f"{city_name}, Denmark", "format": "json", "limit": 1},
                headers={"User-Agent": "ZyflexAI/1.0"},
                timeout=8,
            )
            data = resp.json()
            if data:
                return float(data[0]["lat"]), float(data[0]["lon"]), data[0]["display_name"].split(",")[0]
        except Exception as e:
            logger.warning(f"Geocoding fejlede: {e}")

        # Ultimo fallback: Horsens
        logger.warning(f"Bruger Horsens som fallback for '{city_name}'")
        return 55.8615, 9.8506, "Horsens"

    # ── Vejr ─────────────────────────────────────────────────────────────────

    def _fetch_weather(self, lat, lon) -> dict:
        try:
            resp = requests.get(OPEN_METEO_URL, params={
                "latitude": lat, "longitude": lon,
                "current_weather": True,
                "hourly": "precipitation,temperature_2m",
                "forecast_days": 1,
                "timezone": "Europe/Copenhagen",
            }, timeout=10)
            resp.raise_for_status()
            d = resp.json()
            cur = d.get("current_weather", {})
            hrly = d.get("hourly", {})

            times = hrly.get("time", [])
            precip_list = hrly.get("precipitation", [])
            now_str = datetime.now().strftime("%Y-%m-%dT%H:00")
            precip = 0.0
            if now_str in times:
                precip = float(precip_list[times.index(now_str)])
            elif precip_list:
                precip = float(precip_list[0])

            temp  = float(cur.get("temperature", 12))
            wind  = float(cur.get("windspeed", 0))
            wcode = int(cur.get("weathercode", 0))

            return {
                "temperature": temp, "precipitation": precip,
                "windspeed": wind, "weathercode": wcode,
                "is_raining": precip >= 0.5, "is_heavy_rain": precip >= 3.0,
                "is_cold": temp <= 5.0, "source": "open-meteo.com",
                "summary": f"{temp:.1f}°C, {precip:.1f}mm/t {'🌧 Regn' if precip >= 0.5 else '☀️ Tørt'}",
            }
        except Exception as e:
            logger.warning(f"Vejr-fejl: {e}")
            return {"temperature": 12, "precipitation": 0, "windspeed": 10,
                    "is_raining": False, "is_heavy_rain": False, "is_cold": False,
                    "source": "fallback", "summary": "12°C, tørt (fallback)"}

    # ── Events ───────────────────────────────────────────────────────────────

    def _fetch_events(self, city: str) -> list:
        """
        Henter events:
        1. Altid: lokale events fra data/events.json
        2. Ticketmaster hvis API-nøgle er sat i .env
        3. Fallback mock hvis ingen nøgle og ingen lokale events
        """
        local = self._load_local_events(city)

        if not TICKETMASTER_API_KEY:
            logger.info("Ingen Ticketmaster nøgle – tilføj TICKETMASTER_API_KEY i .env")
            return local if local else self._mock_events(city)

        try:
            self._update(f"Henter rigtige events fra Ticketmaster for {city}...")
            resp = requests.get(TICKETMASTER_URL, params={
                "apikey":      TICKETMASTER_API_KEY,
                "city":        city,
                "countryCode": "DK",
                "radius":      "40",
                "unit":        "km",
                "size":        20,
                "sort":        "date,asc",
            }, timeout=12)

            if resp.status_code == 401:
                logger.error("Ticketmaster: Ugyldig API-nøgle – tjek .env filen")
                return self._mock_events(city)

            if resp.status_code == 429:
                logger.warning("Ticketmaster: Rate limit – prøver igen om lidt")
                return self._mock_events(city)

            resp.raise_for_status()
            data       = resp.json()
            events_raw = data.get("_embedded", {}).get("events", [])

            if not events_raw:
                logger.info(f"Ticketmaster: Ingen events fundet for '{city}' – bruger mock")
                return self._mock_events(city)

            out = []
            for e in events_raw:
                venues = e.get("_embedded", {}).get("venues", [{}])
                v      = venues[0] if venues else {}
                loc    = v.get("location", {})

                # Prisbånd → estimeret attendance
                price_ranges = e.get("priceRanges", [])
                attendance   = self._estimate_attendance_from_event(e)

                # Kategori
                cls      = e.get("classifications", [{}])[0]
                segment  = cls.get("segment", {}).get("name", "")
                genre    = cls.get("genre",   {}).get("name", "")
                category = f"{segment} – {genre}".strip(" –") if genre else segment or "Event"

                out.append({
                    "name":       e.get("name", "Ukendt event"),
                    "date":       e.get("dates", {}).get("start", {}).get("localDate", ""),
                    "time":       e.get("dates", {}).get("start", {}).get("localTime", ""),
                    "venue":      v.get("name", "Ukendt venue"),
                    "city":       v.get("city", {}).get("name", city),
                    "lat":        float(loc.get("latitude",  0)) or self._geocode(city)[0],
                    "lon":        float(loc.get("longitude", 0)) or self._geocode(city)[1],
                    "attendance": attendance,
                    "category":   category,
                    "url":        e.get("url", ""),
                    "source":     "ticketmaster",
                })

            logger.info(f"Ticketmaster: {len(out)} rigtige events hentet for '{city}'")
            merged = local + out   # lokale events kommer først
            logger.info(f"📅 Samlet events: {len(merged)} ({len(local)} lokale + {len(out)} Ticketmaster)")
            return merged

        except Exception as e:
            logger.warning(f"Ticketmaster fejl: {e} – bruger mock")
            return local if local else self._mock_events(city)

    def _estimate_attendance_from_event(self, evt: dict) -> int:
        """Estimér antal tilskuere baseret på event-type og metadata."""
        cls     = evt.get("classifications", [{}])[0]
        segment = cls.get("segment", {}).get("name", "").lower()
        genre   = cls.get("genre",   {}).get("name", "").lower()

        if "music" in segment:
            if any(g in genre for g in ["pop", "rock", "hip-hop", "r&b"]):
                return 5000
            return 2000
        if "sports" in segment:
            if any(g in genre for g in ["football", "fodbold", "soccer"]):
                return 8000
            return 3000
        if "arts" in segment:
            return 800
        return 1000

    def _load_local_events(self, city: str) -> list:
        """
        Læser data/events.json og returnerer events for den angivne by.
        Dato-filtrering: kun events i dag eller fremtidige events.
        """
        if not os.path.exists(_LOCAL_EVENTS_FILE):
            return []
        try:
            with open(_LOCAL_EVENTS_FILE, "r", encoding="utf-8") as f:
                all_events = json.load(f)
            today = datetime.now().strftime("%Y-%m-%d")
            city_key = city.lower().strip()
            lat, lon, _ = self._geocode(city)
            out = []
            for e in all_events:
                # Match by eller fremtidig dato
                e_city = e.get("city", "").lower().strip()
                e_date = e.get("date", "")
                if e_city != city_key and city_key not in e_city:
                    continue
                if e_date < today:
                    continue   # springer forbi events der er overstået
                e_lat = lat + e.get("lat_offset", 0.003)
                e_lon = lon + e.get("lon_offset", 0.002)
                genre = e.get("genre", "event")
                att_map = {"sport": 8000, "football": 8000, "music": 4000,
                           "concert": 4000, "culture": 1000, "event": 2000}
                attendance = e.get("expected_attendance",
                                   att_map.get(genre.lower(), 2000))
                out.append({
                    "name":       e.get("name", "Ukendt event"),
                    "date":       e_date,
                    "time":       e.get("time", "19:00"),
                    "venue":      e.get("venue", f"{city} Arena"),
                    "city":       city,
                    "lat":        e_lat,
                    "lon":        e_lon,
                    "attendance": attendance,
                    "category":   genre.title(),
                    "source":     "local",
                })
            if out:
                logger.info(f"📅 Lokale events: {len(out)} event(s) fundet for '{city}'")
            return out
        except Exception as ex:
            logger.warning(f"Kunne ikke læse events.json: {ex}")
            return []

    def _mock_events(self, city: str) -> list:
        today = datetime.now().strftime("%Y-%m-%d")
        lat, lon, _ = self._geocode(city)
        return [
            {"name": f"Fodboldkamp i {city}", "date": today,
             "venue": f"{city} Stadion", "city": city,
             "lat": lat + 0.005, "lon": lon + 0.005,
             "attendance": 5000, "category": "Sport"},
        ]

    # ── Zoner ────────────────────────────────────────────────────────────────

    # Præcise Horsens-lokationer (rigtige GPS-koordinater)
    HORSENS_ZONES = [
        {"id": "centrum",    "name": "Horsens Centrum",       "lat": 55.8608, "lon": 9.8502,  "base_score": 55, "poi_type": "city_center",   "address": "Søndergade, Horsens"},
        {"id": "station",    "name": "Horsens Station",        "lat": 55.8641, "lon": 9.8438,  "base_score": 52, "poi_type": "transport_hub", "address": "Jernbanegade 1, Horsens"},
        {"id": "sygehus",    "name": "Horsens Sygehus",        "lat": 55.8739, "lon": 9.8344,  "base_score": 48, "poi_type": "hospital",      "address": "Sundvej 30, Horsens"},
        {"id": "casa_arena", "name": "CASA Arena",             "lat": 55.8572, "lon": 9.8614,  "base_score": 38, "poi_type": "venue",         "address": "Langmarksvej 60, Horsens"},
        {"id": "havn",       "name": "Horsens Havn",           "lat": 55.8576, "lon": 9.8664,  "base_score": 35, "poi_type": "city_center",   "address": "Havnen, Horsens"},
        {"id": "scandic",    "name": "Scandic Bygholm Park",   "lat": 55.8534, "lon": 9.8423,  "base_score": 40, "poi_type": "transport_hub", "address": "Schützesvej 6, Horsens"},
    ]

    def _build_zones(self, city: str, lat: float, lon: float) -> list:
        """Brug præcise Horsens-zoner, eller generér dynamisk for andre byer."""
        if city.lower().strip() in ("horsens", "horsens by"):
            return [dict(z) for z in self.HORSENS_ZONES]
        # Generisk fallback for andre byer
        return [
            {"id": "centrum",  "name": f"{city} Centrum",  "lat": lat,           "lon": lon,           "base_score": 50, "poi_type": "city_center",   "address": f"{city} centrum"},
            {"id": "station",  "name": f"{city} Station",  "lat": lat + 0.004,   "lon": lon - 0.007,   "base_score": 45, "poi_type": "transport_hub", "address": f"{city} station"},
            {"id": "sygehus",  "name": f"{city} Sygehus",  "lat": lat + 0.010,   "lon": lon - 0.010,   "base_score": 42, "poi_type": "hospital",      "address": f"{city} sygehus"},
            {"id": "arena",    "name": f"{city} Arena",    "lat": lat - 0.006,   "lon": lon + 0.008,   "base_score": 30, "poi_type": "venue",         "address": f"{city} arena"},
            {"id": "nord",     "name": f"{city} Nord",     "lat": lat + 0.015,   "lon": lon,           "base_score": 28, "poi_type": "city_center",   "address": f"{city} nord"},
            {"id": "syd",      "name": f"{city} Syd",      "lat": lat - 0.015,   "lon": lon,           "base_score": 25, "poi_type": "city_center",   "address": f"{city} syd"},
        ]

    # ── Lokationer (POI) ─────────────────────────────────────────────────────

    def _fetch_locations(self, zones: list) -> dict:
        results = {}
        for zone in zones:
            try:
                q = f"""
                [out:json][timeout:8];
                (node["tourism"="hotel"](around:800,{zone['lat']},{zone['lon']});
                 node["amenity"~"bar|pub|restaurant|hospital"](around:800,{zone['lat']},{zone['lon']});
                 node["railway"="station"](around:800,{zone['lat']},{zone['lon']}););
                out count;
                """
                r = requests.post(OVERPASS_URL, data={"data": q}, timeout=12)
                total = int(r.json().get("elements", [{}])[0].get("tags", {}).get("total", 0))
                results[zone["id"]] = self._default_pois(zone["poi_type"], total)
            except Exception:
                results[zone["id"]] = self._default_pois(zone["poi_type"])
        return results

    def _default_pois(self, poi_type: str, total: int = 0) -> dict:
        defaults = {
            "city_center":   {"hotels": 4, "bars": 7, "restaurants": 10, "hospitals": 0, "stations": 1, "total_pois": total or 22},
            "transport_hub": {"hotels": 1, "bars": 2, "restaurants": 4,  "hospitals": 0, "stations": 3, "total_pois": total or 10},
            "hospital":      {"hotels": 0, "bars": 0, "restaurants": 2,  "hospitals": 1, "stations": 0, "total_pois": total or  3},
            "venue":         {"hotels": 2, "bars": 4, "restaurants": 3,  "hospitals": 0, "stations": 0, "total_pois": total or  9},
        }
        return defaults.get(poi_type, defaults["city_center"])

    def _update(self, msg: str):
        logger.info(f"[DataAgent] {msg}")
        self.status_callback(msg)
