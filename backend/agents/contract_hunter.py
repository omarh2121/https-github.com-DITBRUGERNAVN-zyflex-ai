# =============================================================================
# contract_hunter.py – Zyflex Contract Hunter Agent
# Finder potentielle transportaftaler i Horsens, Herning, Vejle,
# Kolding, Aarhus, Ikast og Brande.
# =============================================================================
import json, logging
from datetime import datetime
from pathlib import Path

logger    = logging.getLogger(__name__)
BASE_DIR  = Path(__file__).parent.parent.parent
LEADS_FILE = BASE_DIR / "data" / "owner_leads.json"

# ─────────────────────────────────────────────────────────────────────────────
# INITIAL LEAD DATABASE
# ─────────────────────────────────────────────────────────────────────────────
INITIAL_LEADS = [

    # ── HORSENS ───────────────────────────────────────────────────────────────
    {"navn":"Comwell Bygholm Park","type":"Hotel","by":"Horsens","adresse":"Schüttesvej 6, 8700 Horsens","website":"comwell.com/bygholmpark","tlf":"+45 76 31 95 00","email":"konference.bygholmpark@comwell.com","kontakt":"Konferenceafdeling","beslutningstager":"Hotel Manager","aarsag":"Konferencegæster og hotelgæster til/fra station og Billund","tilbud":"Fast gæste-transportaftale – månedlig faktura","score":88,"maanedlig_dkk":8500,"sandsynlighed":78,"status":"Klar til kontakt","noter":"Direkte email tilgængelig. Send straks.","naeste_handling":"Send email i dag","follow_up":"2026-04-29","kilde":"Research"},
    {"navn":"Scandic Opus Horsens","type":"Hotel","by":"Horsens","adresse":"Bygholm Søvej 1, 8700 Horsens","website":"scandichotels.dk","tlf":"+45 76 25 72 00","email":"","kontakt":"Reception → bed om Sales","beslutningstager":"Sales Manager","aarsag":"Erhvervsgæster der lander i Billund og skal til Horsens","tilbud":"Fast shuttle-aftale til/fra station og lufthavn","score":82,"maanedlig_dkk":6000,"sandsynlighed":72,"status":"Klar til kontakt","noter":"Ring – bed om salgsansvarlig","naeste_handling":"Ring mandag 10:00","follow_up":"2026-04-29","kilde":"Research"},
    {"navn":"Forum Horsens / CASA Arena","type":"Eventsted","by":"Horsens","adresse":"Langmarksvej 53, 8700 Horsens","website":"forumhorsens.dk","tlf":"+45 76 29 23 23","email":"forum@horsens.dk","kontakt":"Event Manager","beslutningstager":"Driftschef","aarsag":"Artister, VIP og personale ved koncerter og events","tilbud":"Diskret VIP-transport + artistkørsel fra/til Billund","score":85,"maanedlig_dkk":7000,"sandsynlighed":75,"status":"Klar til kontakt","noter":"Grøn Koncert + Vi elsker 90'erne er herfra – aftale inden sæson","naeste_handling":"Send email i dag","follow_up":"2026-04-29","kilde":"Research"},
    {"navn":"Regionshospitalet Horsens","type":"Hospital","by":"Horsens","adresse":"Strandpromenaden 35A, 8700 Horsens","website":"regionshospitalet-horsens.dk","tlf":"+45 78 44 20 40","email":"post@horsens.rm.dk","kontakt":"Indkøb & Logistik","beslutningstager":"Logistikchef","aarsag":"Patienttransport, personalekørsel nat/weekend, akutte kørsler","tilbud":"Supplement til fast transportordning – lokalt og hurtigt","score":80,"maanedlig_dkk":15000,"sandsynlighed":60,"status":"Klar til kontakt","noter":"Kræver CVR og ansvarsforsikring. Start med at ringe.","naeste_handling":"Ring til indkøb (78 44 20 40)","follow_up":"2026-04-29","kilde":"Research"},
    {"navn":"VIA University College Horsens","type":"Uddannelse","by":"Horsens","adresse":"Chr. M. Østergaards Vej 4, 8700 Horsens","website":"via.dk","tlf":"+45 87 55 10 00","email":"","kontakt":"Campus Manager","beslutningstager":"Administrationen","aarsag":"Internationale studerende fra Billund, studieture, sen transport","tilbud":"Fast aftale: studerende til/fra Billund + campus-kørsel","score":72,"maanedlig_dkk":3500,"sandsynlighed":62,"status":"Ny","noter":"Mange udenlandske studerende – ingen fast transportaftale pt","naeste_handling":"Ring og spørg om transportbehov","follow_up":"2026-05-05","kilde":"Research"},
    {"navn":"Horsens Kommune – Socialforvaltning","type":"Kommune","by":"Horsens","adresse":"Rådhustorvet 4, 8700 Horsens","website":"horsens.dk","tlf":"+45 76 29 29 29","email":"horsens@horsens.dk","kontakt":"Visitationsafdeling","beslutningstager":"Socialchef","aarsag":"Flextrafik-supplement, handicapkørsel, ældrekørsel","tilbud":"Supplerende transportaftale ved kapacitetsmangel","score":75,"maanedlig_dkk":20000,"sandsynlighed":50,"status":"Ny","noter":"Kræver evt. udbud ved stor volumen. Start med supplement-aftale.","naeste_handling":"Ring og spørg om aktuelle behov","follow_up":"2026-05-01","kilde":"Research"},

    # ── HERNING ───────────────────────────────────────────────────────────────
    {"navn":"Scandic Herning","type":"Hotel","by":"Herning","adresse":"Gl. Landevej 49, 7400 Herning","website":"scandichotels.dk","tlf":"+45 97 12 15 00","email":"","kontakt":"Reception / Sales","beslutningstager":"Hotel Manager","aarsag":"Konferencegæster til MCH, store messer som SPOGA og EUROBIKE","tilbud":"Fast shuttle til MCH og Karup Lufthavn","score":80,"maanedlig_dkk":7500,"sandsynlighed":68,"status":"Ny","noter":"Herning er messeby – MCH tiltrækker tusindvis af erhvervsfolk","naeste_handling":"Ring og spørg om transportbehov til MCH-events","follow_up":"2026-05-06","kilde":"Research"},
    {"navn":"MCH Messecenter Herning","type":"Konferencecenter","by":"Herning","adresse":"Vardevej 1, 7400 Herning","website":"mch.dk","tlf":"+45 99 26 99 26","email":"mch@mch.dk","kontakt":"Event & Transport Manager","beslutningstager":"Driftschef","aarsag":"100.000+ besøgende ved store messer – alle har transportbehov","tilbud":"Officiel taxi-partner til MCH events","score":90,"maanedlig_dkk":12000,"sandsynlighed":65,"status":"Ny","noter":"Officiel partner-aftale er guldet – alle messebesøgende ser Zyflex","naeste_handling":"Ring til MCH transport-koordinator","follow_up":"2026-05-02","kilde":"Research"},
    {"navn":"FC Midtjylland (Herning)","type":"Idrætsklub","by":"Herning","adresse":"MCH Arena, Vardevej 1, 7400 Herning","website":"fcm.dk","tlf":"+45 97 12 40 00","email":"","kontakt":"Administrationen","beslutningstager":"Drifts- / Event Manager","aarsag":"VIP-gæster, spillere, journalister og holdets rejser","tilbud":"Fast VIP-transport til/fra kampe og flyveplads","score":78,"maanedlig_dkk":6000,"sandsynlighed":55,"status":"Ny","noter":"Professionel fodboldklub – diskret VIP-kørsel er nøglen","naeste_handling":"Ring og spørg efter transport-ansvarlig","follow_up":"2026-05-08","kilde":"Research"},
    {"navn":"Herning Sygehus","type":"Hospital","by":"Herning","adresse":"Hospitalsparken 1, 7400 Herning","website":"rm.dk","tlf":"+45 78 43 00 00","email":"","kontakt":"Indkøb & Logistik","beslutningstager":"Logistikchef","aarsag":"Patienttransport og personalekørsel nat/weekend","tilbud":"Supplement til eksisterende kørselsordning","score":77,"maanedlig_dkk":10000,"sandsynlighed":55,"status":"Ny","noter":"Regionshospital – samme tilgang som i Horsens","naeste_handling":"Ring til logistik-afdeling","follow_up":"2026-05-07","kilde":"Research"},

    # ── VEJLE ─────────────────────────────────────────────────────────────────
    {"navn":"Vejle Idrætscenter","type":"Eventsted","by":"Vejle","adresse":"Willy Sørensens Plads 5, 7100 Vejle","website":"vic.dk","tlf":"+45 76 81 10 00","email":"vic@vejle.dk","kontakt":"Event Manager","beslutningstager":"Centerleder","aarsag":"Store idræts- og konferenceevents med mange deltagere","tilbud":"Fast transport til/fra events og station","score":74,"maanedlig_dkk":5500,"sandsynlighed":60,"status":"Ny","noter":"Stort multifunktionscenter – regelmæssige events","naeste_handling":"Send email","follow_up":"2026-05-05","kilde":"Research"},
    {"navn":"Comwell Kellers Park Vejle","type":"Hotel","by":"Vejle","adresse":"Munkebjergvej 125, 7100 Vejle","website":"comwell.com","tlf":"+45 76 42 20 00","email":"","kontakt":"Konferenceafdeling","beslutningstager":"Sales Manager","aarsag":"Konferencegæster fra hele landet – mange har transportbehov","tilbud":"Fast gæste-transport til/fra station og lufthavn","score":76,"maanedlig_dkk":6500,"sandsynlighed":65,"status":"Ny","noter":"Skovhotel med konference – god mulighed","naeste_handling":"Ring og spørg om aftale","follow_up":"2026-05-06","kilde":"Research"},
    {"navn":"Vejle Sygehus","type":"Hospital","by":"Vejle","adresse":"Kabbeltoft 25, 7100 Vejle","website":"svs.dk","tlf":"+45 79 40 50 00","email":"","kontakt":"Logistik","beslutningstager":"Logistikchef","aarsag":"Patienttransport og personalekørsel","tilbud":"Supplement til fast ordning","score":73,"maanedlig_dkk":8000,"sandsynlighed":52,"status":"Ny","noter":"Sydvestjysk Sygehus – stor organisation","naeste_handling":"Ring til indkøb","follow_up":"2026-05-09","kilde":"Research"},

    # ── KOLDING ───────────────────────────────────────────────────────────────
    {"navn":"Kolding Sygehus","type":"Hospital","by":"Kolding","adresse":"Skovvangen 2, 6000 Kolding","website":"sygehuslillebaelt.dk","tlf":"+45 76 36 20 00","email":"","kontakt":"Logistik / Indkøb","beslutningstager":"Indkøbschef","aarsag":"Patienttransport, akutte kørsler, personalekørsel","tilbud":"Hurtig lokal taxapartner – supplement til fast ordning","score":78,"maanedlig_dkk":9000,"sandsynlighed":58,"status":"Ny","noter":"Sygehus Lillebælt – stor organisation med mange afdelinger","naeste_handling":"Ring til indkøbsafdeling","follow_up":"2026-05-06","kilde":"Research"},
    {"navn":"Hotel Koldingfjord","type":"Hotel","by":"Kolding","adresse":"Fjordvej 154, 6000 Kolding","website":"koldingfjord.dk","tlf":"+45 76 51 00 00","email":"hotel@koldingfjord.dk","kontakt":"Sales","beslutningstager":"Hotel Director","aarsag":"Konferencegæster og hotelgæster med transportbehov","tilbud":"Fast shuttle til Kolding Station og Billund Lufthavn","score":79,"maanedlig_dkk":6000,"sandsynlighed":66,"status":"Ny","noter":"Ekslusivt konferencehotel – høj betalingsvillighed","naeste_handling":"Send email","follow_up":"2026-05-05","kilde":"Research"},
    {"navn":"Kolding Kommune – Jobcenter","type":"Jobcenter","by":"Kolding","adresse":"Bredgade 1, 6000 Kolding","website":"kolding.dk","tlf":"+45 79 79 79 79","email":"jobcenter@kolding.dk","kontakt":"Jobcenterchef","beslutningstager":"Visitator","aarsag":"Borgere på revalidering, fleksjob, praktik der skal transporteres","tilbud":"Fast aftale: social transport til aktivering og møder","score":70,"maanedlig_dkk":7000,"sandsynlighed":50,"status":"Ny","noter":"Kommunalt udbud muligt – start med at ringe og spørge","naeste_handling":"Ring til jobcenter","follow_up":"2026-05-08","kilde":"Research"},

    # ── AARHUS ────────────────────────────────────────────────────────────────
    {"navn":"Aarhus Universitetshospital (AUH)","type":"Hospital","by":"Aarhus","adresse":"Palle Juul-Jensens Boulevard 99, 8200 Aarhus","website":"auh.dk","tlf":"+45 78 45 00 00","email":"","kontakt":"Logistik / Indkøb","beslutningstager":"Indkøbschef","aarsag":"Patienttransport, pårørende-kørsel, personaletransport","tilbud":"Hurtig lokal taxapartner for overløb og akutte behov","score":82,"maanedlig_dkk":18000,"sandsynlighed":48,"status":"Ny","noter":"Landets største sygehus – konkurrence fra store taxaselskaber","naeste_handling":"Ring til indkøbsafdeling","follow_up":"2026-05-10","kilde":"Research"},
    {"navn":"Hotel Royal Aarhus","type":"Hotel","by":"Aarhus","adresse":"Store Torv 4, 8000 Aarhus","website":"hotelroyal.dk","tlf":"+45 86 12 00 11","email":"royal@hotelroyal.dk","kontakt":"Reception / General Manager","beslutningstager":"General Manager","aarsag":"VIP-gæster, udenlandske forretningsfolk, kongelig besøg","tilbud":"Diskret VIP-transport – eksklusiv service","score":76,"maanedlig_dkk":8000,"sandsynlighed":55,"status":"Ny","noter":"Premium hotel – betalingsvillighed er høj","naeste_handling":"Send professionel email","follow_up":"2026-05-07","kilde":"Research"},
    {"navn":"Musikhuset Aarhus","type":"Eventsted","by":"Aarhus","adresse":"Thomas Jensens Allé 2, 8000 Aarhus","website":"musikhuset.dk","tlf":"+45 89 40 40 40","email":"info@musikhuset.dk","kontakt":"Event Koordinator","beslutningstager":"Driftschef","aarsag":"Artister, VIP og personale ved koncerter og events","tilbud":"Artisttransport fra Aarhus H og Billund Lufthavn","score":79,"maanedlig_dkk":7000,"sandsynlighed":58,"status":"Ny","noter":"Aarhus' største kulturinstitution – mange events","naeste_handling":"Send email med reference til CASA Arena aftale","follow_up":"2026-05-06","kilde":"Research"},

    # ── IKAST & BRANDE ────────────────────────────────────────────────────────
    {"navn":"Ikast Plejecenter","type":"Plejehjem","by":"Ikast","adresse":"Ikast","website":"ikast-brande.dk","tlf":"+45 99 60 30 00","email":"","kontakt":"Centerledelse","beslutningstager":"Plejehjemsleder","aarsag":"Beboere der skal til læge, hospital, besøg – fast ugentlig kørsel","tilbud":"Fast ugentlig transportaftale – forudsigelige tider","score":68,"maanedlig_dkk":3500,"sandsynlighed":58,"status":"Ny","noter":"Lille marked men loyal – let at vinde og fastholde","naeste_handling":"Ring til center","follow_up":"2026-05-07","kilde":"Research"},
    {"navn":"Brande Håndværker- og Industriforening","type":"Erhverv","by":"Brande","adresse":"Brande","website":"","tlf":"","email":"","kontakt":"Formanden","beslutningstager":"Formand","aarsag":"Lokale virksomheder med medarbejdere der skal til møder i Vejle/Horsens","tilbud":"Erhvervskørsel til møder i nabobyer","score":58,"maanedlig_dkk":2500,"sandsynlighed":40,"status":"Skal tjekkes","noter":"Find kontakt via Ikast-Brande Erhvervsråd","naeste_handling":"Find kontaktinfo online","follow_up":"2026-05-12","kilde":"Research"},
]

STATUS_OPTIONS = [
    "Ny","Skal tjekkes","Klar til kontakt","Mail skrevet","Mail sendt",
    "Ringet","Afventer svar","Møde booket","Tilbud sendt","Aftale vundet","Afvist"
]


class ContractHunterAgent:
    """Finder og administrerer potentielle transportkontrakter for Zyflex."""

    def __init__(self, status_callback=None):
        self.status_callback = status_callback or (lambda msg: None)

    def run(self, city: str = "alle") -> dict:
        self._update("Starter Contract Hunter...")
        leads = self._load_leads()
        if not leads:
            self._update("Initialiserer lead-database...")
            leads = self._seed_leads()

        city_lower = city.lower()
        if city_lower != "alle":
            leads = [l for l in leads if l.get("by","").lower() == city_lower]

        leads_sorted = sorted(leads, key=lambda x: x.get("score", 0), reverse=True)
        top_leads    = [l for l in leads_sorted if l.get("score", 0) >= 75]
        warm_leads   = [l for l in leads_sorted if 55 <= l.get("score", 0) < 75]
        monthly_pot  = sum(l.get("maanedlig_dkk", 0) for l in top_leads)

        self._update(f"✅ {len(leads_sorted)} leads · {len(top_leads)} varme · ~{monthly_pot:,} kr/md potentiale")

        return {
            "alle_leads":  leads_sorted,
            "top_leads":   top_leads,
            "warm_leads":  warm_leads,
            "total_leads": len(leads_sorted),
            "monthly_pot": monthly_pot,
            "byer":        sorted(set(l.get("by","") for l in leads_sorted)),
            "typer":       sorted(set(l.get("type","") for l in leads_sorted)),
            "statuses":    STATUS_OPTIONS,
        }

    # ── Leads CRUD ────────────────────────────────────────────────────────────

    def _load_leads(self) -> list:
        if LEADS_FILE.exists():
            try:
                return json.loads(LEADS_FILE.read_text(encoding="utf-8"))
            except Exception:
                return []
        return []

    def _seed_leads(self) -> list:
        """Fyld database med initial lead-liste."""
        now = datetime.now().isoformat()
        leads = []
        for i, l in enumerate(INITIAL_LEADS):
            lead = {
                "id": i + 1,
                "created_at": now,
                "updated_at": now,
                **l
            }
            leads.append(lead)
        self._save_leads(leads)
        return leads

    def _save_leads(self, leads: list):
        LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
        LEADS_FILE.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── Email & script generator ──────────────────────────────────────────────

    def generate_email(self, lead: dict, sender_name: str = "Mo Jensen", sender_phone: str = "") -> dict:
        navn     = lead.get("navn", "")
        tilbud   = lead.get("tilbud", "")
        aarsag   = lead.get("aarsag", "")
        kategori = lead.get("type", "")
        by       = lead.get("by", "")

        if kategori in ("Hotel", "Konferencecenter"):
            emne = f"Fast taxapartner til {navn} – lokalt og pålideligt"
            tekst = f"""Hej,

Jeg hedder {sender_name} og ejer Zyflex ApS – et lokalt taxafirma i {by}.

Jeres gæster har brug for pålidelig transport, og jeg tror vi kan hjælpe:

✓ Garanteret afhentning inden for 8 minutter
✓ Faste priser til station og Billund Lufthavn – ingen overraskelser
✓ Månedlig faktura til jer – ingen kontantbøvl
✓ Diskrete, professionelle chauffører der kender lokalområdet
✓ Tilgængelig 24/7 – også sent om natten

Mange af jeres gæster lander i Billund og har brug for nem transport videre. Vi ordner det.

Må jeg ringe en dag og tage en kort snak om en aftale?

Med venlig hilsen
{sender_name}
Zyflex ApS – {by}
Tlf: {sender_phone or "[DIT TLF]"}
Email: omarhajimohamed62@gmail.com"""

        elif kategori in ("Hospital", "Plejehjem", "Kommune", "Jobcenter"):
            emne = f"Lokal transportpartner til {navn}"
            tekst = f"""Til rette vedkommende,

Jeg hedder {sender_name} og driver Zyflex ApS – et CVR-registreret taxafirma i {by}.

Mange sundhedsinstitutioner bruger lokale taxafirmaer som supplement:
• {aarsag}

Vi tilbyder: {tilbud}

Vi er lokale, hurtige og kender området. Har I behov for en lokal samarbejdspartner?

Med venlig hilsen
{sender_name}
Zyflex ApS
Tlf: {sender_phone or "[DIT TLF]"}
Email: omarhajimohamed62@gmail.com"""

        elif kategori in ("Eventsted", "Idrætsklub"):
            emne = f"VIP og artisttransport til {navn}"
            tekst = f"""Hej,

Jeg hedder {sender_name} og driver Zyflex ApS i {by}.

Vi specialiserer os i diskret, professionel transport til events:

✓ Artistkørsel fra Billund Lufthavn og hoteller
✓ VIP-transport til/fra events
✓ Late-night kørsel for personale
✓ Faktura pr. event eller månedligt

{aarsag}

Kan vi lave en aftale inden næste event?

Med venlig hilsen
{sender_name} · Zyflex ApS · Tlf: {sender_phone or "[DIT TLF]"}"""

        else:
            emne = f"Transportaftale til {navn}"
            tekst = f"""Hej,

Jeg hedder {sender_name} og driver Zyflex ApS i {by}.

Vi tilbyder: {tilbud}

Grund: {aarsag}

Interesseret i en snak? Ring eller skriv.

{sender_name} · Zyflex ApS · {sender_phone or "[DIT TLF]"}"""

        return {"emne": emne, "tekst": tekst}

    def generate_call_script(self, lead: dict) -> str:
        navn     = lead.get("navn", "")
        kontakt  = lead.get("kontakt", "Receptionen")
        tilbud   = lead.get("tilbud", "transportaftale")
        by       = lead.get("by", "")

        return f"""📞 OPKALDSSCRIPT – {navn}

Sig: "Hej, jeg hedder Mo Jensen og ejer Zyflex ApS i {by}.
Jeg ringer fordi jeg gerne vil tale med {kontakt} om transport til jeres [gæster/patienter/medarbejdere]."

➡ Hvis de spørger hvad det drejer sig om:
"Vi tilbyder {tilbud}. Mange [hoteller/hospitaler/institutioner] i {by} bruger lokale taxafirmaer som supplement – jeg ville høre om det er noget I mangler?"

➡ Hvis de er interesserede:
"Fedt! Hvad ville det bedste tidspunkt være for et kort møde – 15-20 minutter? Jeg kan komme forbi eller tage det på telefon."

➡ Hvis de siger "ring tilbage":
"Selvfølgelig – hvornår passer det bedst? Og hvem skal jeg bede om?"

➡ Hvis de siger nej:
"Okay, jeg respekterer det. Må jeg sende en kort email med vores info, hvis behovet opstår fremover?"

✅ Husk at skrive navn og svar ind i dashboard!"""

    def _update(self, msg: str):
        logger.info(f"[ContractHunter] {msg}")
        self.status_callback(msg)


# ── Singleton helpers ─────────────────────────────────────────────────────────

def load_all_leads() -> list:
    if LEADS_FILE.exists():
        try:
            return json.loads(LEADS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def save_lead(lead: dict) -> dict:
    leads = load_all_leads()
    lead["updated_at"] = datetime.now().isoformat()
    if lead.get("id"):
        leads = [l if l.get("id") != lead["id"] else lead for l in leads]
    else:
        lead["id"] = max((l.get("id", 0) for l in leads), default=0) + 1
        lead["created_at"] = lead["updated_at"]
        leads.append(lead)
    LEADS_FILE.parent.mkdir(parents=True, exist_ok=True)
    LEADS_FILE.write_text(json.dumps(leads, ensure_ascii=False, indent=2), encoding="utf-8")
    return lead


def delete_lead(lead_id: int) -> bool:
    leads = load_all_leads()
    new_leads = [l for l in leads if l.get("id") != lead_id]
    if len(new_leads) == len(leads):
        return False
    LEADS_FILE.write_text(json.dumps(new_leads, ensure_ascii=False, indent=2), encoding="utf-8")
    return True
