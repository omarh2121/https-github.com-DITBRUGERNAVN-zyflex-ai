# =============================================================================
# sales_agent.py – Agent 3: B2B Sales Lead Generator
#
# Ansvar: Find potentielle samarbejdspartnere i det valgte område.
# - Hoteller uden fast taxa-aftale
# - Sygehuse og klinikker
# - Skoler og uddannelsesinstitutioner
# - Event-arrangører
# Output: Prioriteret liste af leads med kontaktforslag og salgstekst.
# =============================================================================

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging
import requests
from config import OVERPASS_URL

logger = logging.getLogger(__name__)


class SalesAgent:
    """
    Agent 3 – finder B2B leads og genererer salgstekst.
    Kald .run(data_agent_result, analysis_agent_result) for at starte.
    """

    def __init__(self, status_callback=None):
        self.status_callback = status_callback or (lambda msg: None)
        self.result = {}

    def run(self, data: dict, analysis: dict) -> dict:
        city = data.get("city", "Horsens")
        lat  = data.get("lat", 55.8615)
        lon  = data.get("lon", 9.8506)

        self._update(f"Scanner {city} for hoteller og hospitaler...")
        hotels    = self._find_pois(lat, lon, "tourism", "hotel",    city)

        self._update("Scanner for skoler og uddannelse...")
        schools   = self._find_pois(lat, lon, "amenity", "school",   city)

        self._update("Scanner for klinikker og sygehuse...")
        hospitals = self._find_pois(lat, lon, "amenity", "hospital", city)

        self._update("Finder event-venues...")
        venues    = self._find_pois(lat, lon, "amenity", "theatre",  city)

        self._update("Beregner lead-prioritering...")
        all_leads = self._score_leads(hotels, schools, hospitals, venues, analysis)

        self._update(f"✅ {len(all_leads)} leads fundet i {city}")

        self.result = {
            "city":           city,
            "total_leads":    len(all_leads),
            "top_leads":      all_leads[:8],
            "all_leads":      all_leads,
            "outreach_emails": [self._draft_email(l, city) for l in all_leads[:3]],
            "summary": f"{len(hotels)} hoteller, {len(hospitals)} sygehuse, {len(schools)} skoler fundet",
        }
        return self.result

    # ── POI-finder ────────────────────────────────────────────────────────────

    def _find_pois(self, lat, lon, key, value, city, radius=3000) -> list:
        query = f"""
        [out:json][timeout:10];
        node["{key}"="{value}"](around:{radius},{lat},{lon});
        out body;
        """
        try:
            resp = requests.post(OVERPASS_URL, data={"data": query}, timeout=15)
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            results = []
            for el in elements:
                tags = el.get("tags", {})
                name = tags.get("name", f"Ukendt {value}")
                results.append({
                    "name":    name,
                    "type":    value,
                    "lat":     el.get("lat", lat),
                    "lon":     el.get("lon", lon),
                    "phone":   tags.get("phone", tags.get("contact:phone", "")),
                    "website": tags.get("website", tags.get("contact:website", "")),
                    "address": tags.get("addr:street", "") + " " + tags.get("addr:housenumber", ""),
                    "city":    city,
                })
            return results
        except Exception as e:
            logger.warning(f"POI-søgning fejlede ({value}): {e} – bruger mock")
            return self._mock_pois(value, city)

    def _mock_pois(self, poi_type: str, city: str) -> list:
        mocks = {
            "hotel":    [{"name": f"{city} Hotel & Konference", "type": "hotel",   "phone": "", "website": "", "address": "Centerby 1", "city": city, "lat": 0, "lon": 0}],
            "hospital": [{"name": f"{city} Sygehus",            "type": "hospital","phone": "", "website": "", "address": "Hospitalsvejen 1", "city": city, "lat": 0, "lon": 0}],
            "school":   [{"name": f"{city} Gymnasium",          "type": "school",  "phone": "", "website": "", "address": "Skolevej 1", "city": city, "lat": 0, "lon": 0}],
            "theatre":  [{"name": f"{city} Kulturhus",          "type": "theatre", "phone": "", "website": "", "address": "Kulturtorvet 1", "city": city, "lat": 0, "lon": 0}],
        }
        return mocks.get(poi_type, [])

    # ── Lead-scoring ─────────────────────────────────────────────────────────

    def _score_leads(self, hotels, schools, hospitals, venues, analysis) -> list:
        leads = []

        for h in hotels:
            leads.append({**h, "category": "Hotel", "priority": "HØJ",
                "revenue_potential": "15.000–40.000 kr/md",
                "pitch": "Fast aftale: airport-kørsel, gæstetransport, business-kunder",
                "action": f"Ring til {h['name']} og tilbyd prøveuge gratis"})

        for h in hospitals:
            leads.append({**h, "category": "Sygehus/Klinik", "priority": "HØJ",
                "revenue_potential": "20.000–60.000 kr/md",
                "pitch": "Patienttransport, pårørende-kørsel, personale-transport",
                "action": f"Send tilbud til {h['name']} indkøbsafdeling"})

        for s in schools:
            leads.append({**s, "category": "Skole/Uddannelse", "priority": "MIDDEL",
                "revenue_potential": "5.000–15.000 kr/md",
                "pitch": "Elevkørsel, ekskursioner, personaletransport",
                "action": f"Kontakt {s['name']} – spørg efter indkøbsansvarlig"})

        for v in venues:
            leads.append({**v, "category": "Event-venue", "priority": "MIDDEL",
                "revenue_potential": "8.000–25.000 kr/md",
                "pitch": "Event-transport, VIP-kørsel, publikumstransport",
                "action": f"Mød event-manager på {v['name']}"})

        # Sortér: HØJ først
        priority_order = {"HØJ": 0, "MIDDEL": 1, "LAV": 2}
        leads.sort(key=lambda x: priority_order.get(x.get("priority", "LAV"), 2))
        return leads

    # ── Email-udkast ─────────────────────────────────────────────────────────

    def _draft_email(self, lead: dict, city: str) -> dict:
        name     = lead["name"]
        category = lead["category"]
        pitch    = lead["pitch"]

        subject = f"Professionel transportpartner til {name} – Zyflex ApS"
        body = f"""Hej,

Jeg hedder Mo og er direktør i Zyflex ApS – et lokalt taxafirma med fokus på pålidelig og professionel transport i {city}-området.

Jeg kontakter jer, fordi vi gerne vil tilbyde {name} en fast transportaftale.

Det betyder:
✓ Altid en bil klar når I har brug for det
✓ Fast lav pris – ikke taxameter-priser
✓ Direkte kontakt – ingen app, ingen ventetid
✓ {pitch}

Vi tilbyder en gratis prøveuge, så I kan se kvaliteten selv.

Må jeg ringe for at aftale 15 min?

Med venlig hilsen,
Mo Jensen
Zyflex ApS
Tlf: [dit nummer]"""

        return {"lead": name, "category": category, "subject": subject, "body": body}

    def _update(self, msg):
        logger.info(f"[SalesAgent] {msg}")
        self.status_callback(msg)
