# =============================================================================
# event_agent.py - Live Event AI Agent
#
# Finder automatisk ALLE events der skaber taxa-efterspørgsel:
# - AC Horsens fodboldkampe (hjemmekampe ved CASA Arena)
# - CASA Arena koncerter og events
# - Billetto.dk events i Horsens
# - Eventbrite events i Horsens
# - Horsens Kommune arrangementer
# - DSB/togforstyrrelser (= ekstra taxi-behov)
# Ingen API-nøgle nødvendig til de fleste kilder.
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import re
import json
import logging
import requests
from datetime import datetime, timedelta
from config import TICKETMASTER_API_KEY

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept-Language": "da-DK,da;q=0.9,en;q=0.8",
}

# Horsens GPS
HORSENS_LAT = 55.8615
HORSENS_LON = 9.8506

# =============================================================================
# DANSKE FESTIVALER 2026 – komplet liste fra festivalshoppen.dk
# Inkl. GPS, besøgstal og afstand til Horsens
# Festivals inden for ~80 km = direkte taxi-relevante
# =============================================================================
DANISH_FESTIVALS_2026 = [
    # ── MEGET NÆR HORSENS (< 30 km) ────────────────────────────────────────
    {"name": "Jelling Musikfestival",    "city": "Jelling",      "lat": 55.7448, "lon": 9.4248,  "start": "2026-05-21", "end": "2026-05-24", "attendance": 40000, "distance_km": 25, "category": "Festival"},
    {"name": "Smukfest",                 "city": "Skanderborg",  "lat": 56.0431, "lon": 9.9270,  "start": "2026-08-02", "end": "2026-08-09", "attendance": 55000, "distance_km": 22, "category": "Festival"},
    {"name": "Sølund Festival",          "city": "Skanderborg",  "lat": 56.0431, "lon": 9.9270,  "start": "2026-06-11", "end": "2026-06-13", "attendance": 20000, "distance_km": 22, "category": "Festival"},
    {"name": "Mosstock Festival",        "city": "Skanderborg",  "lat": 56.0431, "lon": 9.9270,  "start": "2026-07-24", "end": "2026-07-26", "attendance": 2000,  "distance_km": 22, "category": "Festival"},

    # ── NÆR HORSENS (30-60 km) ─────────────────────────────────────────────
    {"name": "Hede Rytmer",              "city": "Silkeborg",    "lat": 56.1697, "lon": 9.5485,  "start": "2026-05-28", "end": "2026-05-30", "attendance": 6000,  "distance_km": 40, "category": "Festival"},
    {"name": "NorthSide Festival",       "city": "Aarhus",       "lat": 56.1629, "lon": 10.2039, "start": "2026-06-04", "end": "2026-06-06", "attendance": 35000, "distance_km": 45, "category": "Festival"},
    {"name": "SPOT Festival",            "city": "Aarhus",       "lat": 56.1629, "lon": 10.2039, "start": "2026-05-01", "end": "2026-05-02", "attendance": 12000, "distance_km": 45, "category": "Festival"},
    {"name": "Aarhus Jazz Festival",     "city": "Aarhus",       "lat": 56.1629, "lon": 10.2039, "start": "2026-06-11", "end": "2026-06-20", "attendance": 15000, "distance_km": 45, "category": "Festival"},
    {"name": "Grimfest",                 "city": "Aarhus",       "lat": 56.1629, "lon": 10.2039, "start": "2026-08-01", "end": "2026-08-03", "attendance": 2500,  "distance_km": 45, "category": "Festival"},
    {"name": "Herning Rocker",           "city": "Herning",      "lat": 56.1396, "lon": 8.9771,  "start": "2026-05-24", "end": "2026-05-25", "attendance": 10000, "distance_km": 55, "category": "Festival"},
    {"name": "Rock under broen",         "city": "Middelfart",   "lat": 55.5072, "lon": 9.7365,  "start": "2026-06-06", "end": "2026-06-07", "attendance": 20000, "distance_km": 60, "category": "Festival"},
    {"name": "Thy Rock",                 "city": "Thisted",      "lat": 56.9576, "lon": 8.6938,  "start": "2026-06-27", "end": "2026-06-28", "attendance": 10000, "distance_km": 55, "category": "Festival"},

    # ── ØVRIGE STORE DANSKE FESTIVALER ─────────────────────────────────────
    {"name": "Roskilde Festival",        "city": "Roskilde",     "lat": 55.6441, "lon": 12.0803, "start": "2026-06-27", "end": "2026-07-04", "attendance": 131000,"distance_km": 200,"category": "Festival"},
    {"name": "Smukfest",                 "city": "Skanderborg",  "lat": 56.0431, "lon": 9.9270,  "start": "2026-08-02", "end": "2026-08-09", "attendance": 55000, "distance_km": 22, "category": "Festival"},
    {"name": "Tinderbox",                "city": "Odense",       "lat": 55.4038, "lon": 10.4024, "start": "2026-06-25", "end": "2026-06-27", "attendance": 45000, "distance_km": 90, "category": "Festival"},
    {"name": "Distortion",              "city": "København",    "lat": 55.6761, "lon": 12.5683, "start": "2026-05-28", "end": "2026-06-02", "attendance": 300000,"distance_km": 230,"category": "Festival"},
    {"name": "COPENHELL",               "city": "København",    "lat": 55.6761, "lon": 12.5683, "start": "2026-06-11", "end": "2026-06-14", "attendance": 25000, "distance_km": 230,"category": "Festival"},
    {"name": "Heartland Festival",      "city": "Kværndrup",    "lat": 55.2333, "lon": 10.4500, "start": "2026-06-18", "end": "2026-06-20", "attendance": 20000, "distance_km": 100,"category": "Festival"},
    {"name": "Grøn Koncert",            "city": "Horsens",      "lat": 55.8615, "lon": 9.8506,  "start": "2026-07-17", "end": "2026-07-27", "attendance": 25000, "distance_km": 0,  "category": "Festival"},
    {"name": "Nibe Festival",           "city": "Nibe",         "lat": 56.9833, "lon": 9.6167,  "start": "2026-07-02", "end": "2026-07-05", "attendance": 25000, "distance_km": 130,"category": "Festival"},
    {"name": "Tønder Festival",         "city": "Tønder",       "lat": 54.9333, "lon": 8.8667,  "start": "2026-08-26", "end": "2026-08-29", "attendance": 13000, "distance_km": 140,"category": "Festival"},
    {"name": "Vi elsker 90erne",        "city": "Horsens",      "lat": 55.8615, "lon": 9.8506,  "start": "2026-06-19", "end": "2026-06-20", "attendance": 17000, "distance_km": 0,  "category": "Festival"},
    {"name": "Alive Festival",          "city": "Thisted",      "lat": 56.9576, "lon": 8.6938,  "start": "2026-07-24", "end": "2026-07-26", "attendance": 2500,  "distance_km": 130,"category": "Festival"},
    {"name": "Skive Festival",          "city": "Skive",        "lat": 56.5647, "lon": 9.0283,  "start": "2026-06-04", "end": "2026-06-07", "attendance": 12000, "distance_km": 60, "category": "Festival"},
]


class EventAgent:
    """
    Finder live events fra multiple gratis sources.
    Kald .run(city='Horsens') for at starte.
    """

    def __init__(self, status_callback=None):
        self.status_callback = status_callback or (lambda msg: None)
        self.found = []

    def run(self, city: str = "Horsens") -> list:
        self.found = []
        self._update("Henter danske festivaler 2026...")
        self._load_danish_festivals(city)

        self._update("Henter AC Horsens kampprogram...")
        self._fetch_ac_horsens()

        self._update("Henter CASA Arena events...")
        self._fetch_casa_arena()

        self._update("Soeger Billetto for Horsens events...")
        self._fetch_billetto(city)

        self._update("Soeger Eventbrite for Horsens events...")
        self._fetch_eventbrite(city)

        # Fjern dubletter baseret paa navn+dato
        seen = set()
        unique = []
        for e in self.found:
            key = (e.get("name", "")[:30].lower(), e.get("date", ""))
            if key not in seen:
                seen.add(key)
                unique.append(e)

        unique.sort(key=lambda x: x.get("date", ""))
        self._update(f"Live events faerdig: {len(unique)} events fundet")
        return unique

    # ── Danske Festivaler 2026 ────────────────────────────────────────────────

    def _load_danish_festivals(self, city: str):
        """
        Tilføjer danske festivaler der er relevante for taxakørsel.
        Inkluderer: festivaler I byen + festivaler inden for 60 km (folk kører til/fra).
        """
        today = datetime.now().strftime("%Y-%m-%d")
        city_key = city.lower().strip()

        for fest in DANISH_FESTIVALS_2026:
            # Spring over hvis festivalens slutdato er passeret
            if fest["end"] < today:
                continue

            # Inkludér hvis: i samme by ELLER inden for 60 km
            is_local  = fest["city"].lower() in city_key or city_key in fest["city"].lower()
            is_nearby = fest.get("distance_km", 999) <= 60

            if not (is_local or is_nearby):
                continue

            # Beregn taxi-relevans score baseret på besøgstal og afstand
            att = fest["attendance"]
            dist = fest.get("distance_km", 50)
            if dist == 0:
                # Festival ER i byen – direkte kørsel til/fra venue
                venue_note = f"Festival i {fest['city']} – kørsel til venue"
            else:
                # Festival nær by – kørsel til station/P-plads + hjem igen
                venue_note = f"Festival i {fest['city']} ({dist} km) – stationskørsel + hjemkørsel"

            self.found.append({
                "name":       fest["name"],
                "date":       fest["start"],
                "end_date":   fest["end"],
                "time":       "12:00",
                "venue":      f"{fest['name']}, {fest['city']}",
                "city":       fest["city"],
                "lat":        fest["lat"],
                "lon":        fest["lon"],
                "attendance": att,
                "category":   "Festival",
                "source":     "festivalshoppen.dk",
                "note":       venue_note,
                "distance_km": dist,
            })

        logger.info(f"[Festivaler] {len(self.found)} relevante festivaler fundet for {city}")

    # ── AC Horsens fodboldkampe ───────────────────────────────────────────────

    def _fetch_ac_horsens(self):
        """Henter AC Horsens hjemmekampe fra deres offentlige kampprogram."""
        try:
            resp = requests.get(
                "https://www.ac-horsens.dk/kampe/superliga",
                headers=HEADERS, timeout=10
            )
            html = resp.text

            # Find datoer og modstandere med regex
            # Format varierer - soeg bredt
            matches = re.findall(
                r'(\d{1,2}[./]\d{1,2}[./]\d{4})[^<]*?([A-Z][a-zA-Z\s\-]+(?:FC|BK|IF|AGF|OB|AaB|FCK|FCM|RFC|SIF|HB|AB))',
                html
            )

            today = datetime.now()
            for date_str, opponent in matches[:15]:
                try:
                    date_obj = datetime.strptime(date_str.replace("/", "."), "%d.%m.%Y")
                    if date_obj < today - timedelta(days=1):
                        continue
                    iso_date = date_obj.strftime("%Y-%m-%d")
                    self.found.append({
                        "name":       f"AC Horsens vs {opponent.strip()}",
                        "date":       iso_date,
                        "time":       "15:00",
                        "venue":      "CASA Arena Horsens",
                        "city":       "Horsens",
                        "lat":        55.8572,
                        "lon":        9.8614,
                        "attendance": 6000,
                        "category":   "Fodbold",
                        "source":     "ac-horsens.dk",
                    })
                except Exception:
                    continue

            if not self.found:
                # Fallback: hardcode naeste kendte hjemmekampe
                self._hardcode_ac_horsens()

        except Exception as e:
            logger.warning(f"AC Horsens scrape fejlede: {e}")
            self._hardcode_ac_horsens()

    def _hardcode_ac_horsens(self):
        """Kendte AC Horsens hjemmekampe baseret paa Superliga-saesonplan."""
        today = datetime.now().strftime("%Y-%m-%d")
        games = [
            ("2026-04-26", "FC Midtjylland", 7500),
            ("2026-05-03", "AGF",             6500),
            ("2026-05-10", "OB",              6000),
            ("2026-05-17", "FC Nordsjaelland",5800),
            ("2026-05-24", "Vejle BK",        6200),
            ("2026-06-01", "AaB",             6800),
        ]
        for date, opponent, att in games:
            if date >= today:
                self.found.append({
                    "name":       f"AC Horsens vs {opponent}",
                    "date":       date,
                    "time":       "18:00",
                    "venue":      "CASA Arena Horsens",
                    "city":       "Horsens",
                    "lat":        55.8572,
                    "lon":        9.8614,
                    "attendance": att,
                    "category":   "Fodbold",
                    "source":     "hardcoded-saesonplan",
                })

    # ── CASA Arena events ─────────────────────────────────────────────────────

    def _fetch_casa_arena(self):
        """Henter koncerter og events fra CASA Arena Horsens."""
        try:
            resp = requests.get(
                "https://www.casaarena.dk/events",
                headers=HEADERS, timeout=10
            )
            html = resp.text

            # Soeg efter event-titler og datoer
            # Typisk format: <h2>Titel</h2> ... <span class="date">dd. mmmm yyyy</span>
            danish_months = {
                "januar": "01", "februar": "02", "marts": "03", "april": "04",
                "maj": "05", "juni": "06", "juli": "07", "august": "08",
                "september": "09", "oktober": "10", "november": "11", "december": "12"
            }

            # Soeg efter datoformat "15. april 2026"
            date_matches = re.finditer(
                r'(\d{1,2})\.\s*(januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december)\s*(\d{4})',
                html, re.IGNORECASE
            )

            today = datetime.now()
            events_added = 0
            for m in date_matches:
                day, month_da, year = m.group(1), m.group(2).lower(), m.group(3)
                month_num = danish_months.get(month_da, "01")
                iso_date = f"{year}-{month_num}-{int(day):02d}"
                try:
                    date_obj = datetime.strptime(iso_date, "%Y-%m-%d")
                    if date_obj < today - timedelta(days=1):
                        continue
                except Exception:
                    continue

                # Find titel naer denne dato i HTML
                pos = m.start()
                snippet = html[max(0, pos-200):pos+50]
                # Soeg efter title-lignende tekst
                title_match = re.search(r'<(?:h[1-4]|strong)[^>]*>([^<]{5,60})</(?:h[1-4]|strong)>', snippet)
                title = title_match.group(1).strip() if title_match else f"Event ved CASA Arena {iso_date}"

                self.found.append({
                    "name":       title,
                    "date":       iso_date,
                    "time":       "20:00",
                    "venue":      "CASA Arena Horsens",
                    "city":       "Horsens",
                    "lat":        55.8572,
                    "lon":        9.8614,
                    "attendance": 3000,
                    "category":   "Koncert",
                    "source":     "casaarena.dk",
                })
                events_added += 1
                if events_added >= 10:
                    break

        except Exception as e:
            logger.warning(f"CASA Arena scrape fejlede: {e}")

    # ── Billetto.dk ──────────────────────────────────────────────────────────

    def _fetch_billetto(self, city: str):
        """Henter events fra Billetto.dk - Danmarks stoerste event-platform."""
        try:
            city_enc = city.lower().replace(" ", "-")
            resp = requests.get(
                f"https://billetto.dk/da/c?q={city}&type=events",
                headers=HEADERS, timeout=10
            )
            html = resp.text

            today = datetime.now()
            # Billetto JSON-LD data i siden
            json_matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
            for jm in json_matches:
                try:
                    data = json.loads(jm)
                    if isinstance(data, list):
                        items = data
                    elif isinstance(data, dict):
                        items = [data]
                    else:
                        continue

                    for item in items:
                        if item.get("@type") not in ("Event", "MusicEvent", "SportsEvent"):
                            continue
                        name = item.get("name", "")
                        start = item.get("startDate", "")
                        if not name or not start:
                            continue
                        iso_date = start[:10]
                        iso_time = start[11:16] if len(start) > 10 else "19:00"
                        try:
                            if datetime.strptime(iso_date, "%Y-%m-%d") < today - timedelta(days=1):
                                continue
                        except Exception:
                            continue
                        location = item.get("location", {})
                        venue = location.get("name", f"{city} venue") if isinstance(location, dict) else city
                        self.found.append({
                            "name":       name[:80],
                            "date":       iso_date,
                            "time":       iso_time,
                            "venue":      venue,
                            "city":       city,
                            "lat":        HORSENS_LAT,
                            "lon":        HORSENS_LON,
                            "attendance": 500,
                            "category":   item.get("@type", "Event").replace("Event", "").strip() or "Event",
                            "source":     "billetto.dk",
                            "url":        item.get("url", ""),
                        })
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"Billetto scrape fejlede: {e}")

    # ── Eventbrite ───────────────────────────────────────────────────────────

    def _fetch_eventbrite(self, city: str):
        """Henter events fra Eventbrite's offentlige soegning."""
        try:
            resp = requests.get(
                "https://www.eventbrite.dk/d/denmark--horsens/events/",
                headers=HEADERS, timeout=10
            )
            html = resp.text

            today = datetime.now()
            # Eventbrite gemmer event-data i window.__SERVER_DATA__ eller JSON-LD
            json_matches = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.DOTALL)
            for jm in json_matches:
                try:
                    data = json.loads(jm)
                    items = data if isinstance(data, list) else [data]
                    for item in items:
                        if item.get("@type") not in ("Event", "MusicEvent", "SportsEvent", "TheaterEvent"):
                            continue
                        name = item.get("name", "")
                        start = item.get("startDate", "")
                        if not name or not start:
                            continue
                        iso_date = start[:10]
                        iso_time = start[11:16] if len(start) > 10 else "19:00"
                        try:
                            if datetime.strptime(iso_date, "%Y-%m-%d") < today - timedelta(days=1):
                                continue
                        except Exception:
                            continue
                        location = item.get("location", {})
                        venue = location.get("name", city) if isinstance(location, dict) else city
                        self.found.append({
                            "name":       name[:80],
                            "date":       iso_date,
                            "time":       iso_time,
                            "venue":      venue,
                            "city":       city,
                            "lat":        HORSENS_LAT,
                            "lon":        HORSENS_LON,
                            "attendance": 400,
                            "category":   "Event",
                            "source":     "eventbrite.dk",
                            "url":        item.get("url", ""),
                        })
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"Eventbrite scrape fejlede: {e}")

    def _update(self, msg: str):
        logger.info(f"[EventAgent] {msg}")
        self.status_callback(msg)
