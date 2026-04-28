# =============================================================================
# prospect_agent.py – Zyflex AI Prospect & Lead Generator
#
# Ansvar: Find potentielle kunder med høj sandsynlighed for at lave aftale.
# Output: Rangeret liste af prospects med score, kontakt og salgstekst.
#
# Typer:
#   B2B  – firmaer der har løbende transport-behov (hoteller, fabrikker, skoler)
#   PRIV – private kunder med høj frekvens (ældre, pendlere, sygehusbrugere)
#   FAST – kommunale/institutionelle aftaler (flextrafik, sygehus-transport)
# =============================================================================

import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# PROSPECT DATABASE – Horsens & omegn
# Hvert prospect har: navn, type, adresse, tlf, kontaktperson, behov,
#                     månedlig_værdi_dkk, sandsynlighed_pct, noter
# ─────────────────────────────────────────────────────────────────────────────

PROSPECTS = {

    # ── HOTELLER ─────────────────────────────────────────────────────────────
    "hotel": [
        {
            "navn":           "Scandic Opus Horsens",
            "type":           "B2B",
            "kategori":       "hotel",
            "adresse":        "Bygholm Søvej 1, 8700 Horsens",
            "tlf":            "+45 76 25 72 00",
            "email":          "",  # Ring og bed om sales-email
            "kontakt":        "Reception → bed om Sales/Konference",
            "behov":          "Gæste-transport fra/til Horsens Station og Billund Lufthavn",
            "maanedlig_dkk":  6000,
            "sandsynlighed":  82,
            "noter":          "4-stjernet hotel – mange erhvervsgæster der lander i Billund",
            "prioritet":      "HØJ",
        },
        {
            "navn":           "Comwell Bygholm Park",
            "type":           "B2B",
            "kategori":       "hotel",
            "adresse":        "Schüttesvej 6, 8700 Horsens",
            "tlf":            "+45 76 31 95 00",
            "email":          "konference.bygholmpark@comwell.com",
            "kontakt":        "Konferenceafdeling / Sales Manager",
            "behov":          "Fast aftale: gæster til/fra station, konferencer, late-night transport",
            "maanedlig_dkk":  8500,
            "sandsynlighed":  78,
            "noter":          "Konferencehotel – store grupper der skal videre i taxa efter events",
            "prioritet":      "HØJ",
        },
        {
            "navn":           "Danhostel Horsens",
            "type":           "B2B",
            "kategori":       "hotel",
            "adresse":        "Flintebakken 150, 8700 Horsens",
            "tlf":            "+45 75 61 67 77",
            "kontakt":        "Hostel Manager",
            "behov":          "Budget-grupper der skal til station / seværdigheder",
            "maanedlig_dkk":  2500,
            "sandsynlighed":  55,
            "noter":          "Lavere volumen men nem aftale – ingen konkurrence her",
            "prioritet":      "MIDDEL",
        },
    ],

    # ── SYGEHUS & SUNDHED ─────────────────────────────────────────────────────
    "sundhed": [
        {
            "navn":           "Horsens Regionshospital",
            "type":           "FAST",
            "kategori":       "hospital",
            "adresse":        "Strandpromenaden 35A, 8700 Horsens",
            "tlf":            "+45 78 44 20 40",
            "email":          "post@horsens.rm.dk",
            "kontakt":        "Indkøb & Logistik",
            "behov":          "Patient-transport, personale-kørsel nat/weekend, blodprøver",
            "maanedlig_dkk":  15000,
            "sandsynlighed":  70,
            "noter":          "Kommunalt udbud – kræver CVR og forsikring. Stor kontrakt men lang process",
            "prioritet":      "HØJ",
        },
        {
            "navn":           "Falck Horsens",
            "type":           "B2B",
            "kategori":       "sundhed",
            "adresse":        "Horsens",
            "tlf":            "+45 70 10 20 30",
            "kontakt":        "Stationsforstander",
            "behov":          "Backup-transport når egne biler er optaget",
            "maanedlig_dkk":  4000,
            "sandsynlighed":  45,
            "noter":          "Svær at få ind – men meget stabil hvis aftale laves",
            "prioritet":      "MIDDEL",
        },
        {
            "navn":           "Lægecenter Horsens Centrum",
            "type":           "B2B",
            "kategori":       "sundhed",
            "adresse":        "Søndergade, 8700 Horsens",
            "tlf":            "Find via horsens.dk",
            "kontakt":        "Praksismanager",
            "behov":          "Ældre patienter der ikke kan køre selv – faste tider",
            "maanedlig_dkk":  3000,
            "sandsynlighed":  65,
            "noter":          "Nem kontakt – bare ring og spørg om de anbefaler taxa til patienter",
            "prioritet":      "MIDDEL",
        },
    ],

    # ── VIRKSOMHEDER & INDUSTRI ───────────────────────────────────────────────
    "erhverv": [
        {
            "navn":           "NIRAS (ingeniørfirma, Horsens)",
            "type":           "B2B",
            "kategori":       "kontor",
            "adresse":        "Horsens",
            "tlf":            "+45 87 28 11 00",
            "kontakt":        "Receptionen / Office Manager",
            "behov":          "Medarbejder-transport til møder, kunder fra Aarhus/Vejle, sent arbejde",
            "maanedlig_dkk":  5000,
            "sandsynlighed":  60,
            "noter":          "Ingeniørfirma med mange kunder udefra – typisk behov for taxa til station",
            "prioritet":      "MIDDEL",
        },
        {
            "navn":           "Horsens Kommune – Socialforvaltningen",
            "type":           "FAST",
            "kategori":       "kommune",
            "adresse":        "Rådhustorvet 4, 8700 Horsens",
            "tlf":            "+45 76 29 29 29",
            "kontakt":        "Indkøbsafdeling",
            "behov":          "Flextrafik-supplement, handicapkørsel, ældrekørsel",
            "maanedlig_dkk":  20000,
            "sandsynlighed":  50,
            "noter":          "Kræver EU-udbud ved >500k/år. Start med at tilbyde supplement til eksisterende",
            "prioritet":      "HØJ",
        },
        {
            "navn":           "Coop Danmark (lager, Horsens-området)",
            "type":           "B2B",
            "kategori":       "industri",
            "adresse":        "Horsens-området",
            "tlf":            "Find via coop.dk",
            "kontakt":        "HR-afdeling / Logistikchef",
            "behov":          "Medarbejder-transport til skifteholdsarbejde, nat-ture",
            "maanedlig_dkk":  8000,
            "sandsynlighed":  55,
            "noter":          "Store lagre kørerer 3 skift – nat-chauffører har brug for taxa hjem",
            "prioritet":      "MIDDEL",
        },
        {
            "navn":           "Vestas (regionalt – Vejle/Horsens)",
            "type":           "B2B",
            "kategori":       "industri",
            "adresse":        "Vejle / Horsens-korridoren",
            "tlf":            "+45 97 30 00 00",
            "kontakt":        "Travel Manager / HR",
            "behov":          "Internationale medarbejdere fra Billund Lufthavn, konsulenter",
            "maanedlig_dkk":  12000,
            "sandsynlighed":  48,
            "noter":          "Stor virksomhed – mange internationale gæster der lander i Billund",
            "prioritet":      "HØJ",
        },
    ],

    # ── SKOLER & UDDANNELSE ───────────────────────────────────────────────────
    "uddannelse": [
        {
            "navn":           "Horsens Gymnasium (HG)",
            "type":           "B2B",
            "kategori":       "skole",
            "adresse":        "Fussingsvej 8, 8700 Horsens",
            "tlf":            "+45 76 28 98 00",
            "kontakt":        "Skoleleder / Administrationen",
            "behov":          "Ekskursioner, studieture, sen-aftenstransport for elever",
            "maanedlig_dkk":  2000,
            "sandsynlighed":  50,
            "noter":          "Sæsonbetonet – mest aktivt sep-maj. Nemt at lave aftale",
            "prioritet":      "LAV",
        },
        {
            "navn":           "VIA University College Horsens",
            "type":           "B2B",
            "kategori":       "skole",
            "adresse":        "Chr. M. Østergaards Vej 4, 8700 Horsens",
            "tlf":            "+45 87 55 10 00",
            "kontakt":        "Campus Manager",
            "behov":          "Internationale studerende fra Billund, studieture, sen transport",
            "maanedlig_dkk":  3500,
            "sandsynlighed":  62,
            "noter":          "Mange udenlandske studerende – ingen fast transportaftale pt",
            "prioritet":      "MIDDEL",
        },
    ],

    # ── EVENT & UNDERHOLDNING ─────────────────────────────────────────────────
    "events": [
        {
            "navn":           "Forum Horsens / CASA Arena",
            "type":           "B2B",
            "kategori":       "venue",
            "adresse":        "Langmarksvej 53, 8700 Horsens",
            "tlf":            "+45 76 29 23 23",
            "email":          "forum@horsens.dk",
            "kontakt":        "Event Manager / Drift",
            "behov":          "VIP-transport, artistkørsel, sent-event transport for publikum",
            "maanedlig_dkk":  7000,
            "sandsynlighed":  75,
            "noter":          "Stor venue – VIP og artister har ALTID brug for diskret, pålidelig taxa",
            "prioritet":      "HØJ",
        },
        {
            "navn":           "Jomfru Ane Parken / Festivalpladser",
            "type":           "B2B",
            "kategori":       "festival",
            "adresse":        "Horsens Havn",
            "tlf":            "Via Horsens Kommune",
            "kontakt":        "Event-koordinator",
            "behov":          "Festival-transport, scene-kørsel, artistkørsel",
            "maanedlig_dkk":  4000,
            "sandsynlighed":  65,
            "noter":          "Grøn Koncert + Vi elsker 90'erne er HER – aftale inden næste festival",
            "prioritet":      "HØJ",
        },
    ],

    # ── PRIVATE HØJ-FREKVENS KUNDER ───────────────────────────────────────────
    "privat": [
        {
            "navn":           "Ældre borgere (via ældrecentre)",
            "type":           "PRIV",
            "kategori":       "ældrepleje",
            "adresse":        "Horsens Ældrecentre",
            "tlf":            "+45 76 29 29 29 (Horsens Kommune)",
            "kontakt":        "Centerledere på ældrecentre",
            "behov":          "Fast ugentlig kørsel til læge, indkøb, besøg",
            "maanedlig_dkk":  2500,
            "sandsynlighed":  70,
            "noter":          "Lav pris pr. tur men meget høj loyalitet. Mund-til-mund effekt.",
            "prioritet":      "MIDDEL",
        },
        {
            "navn":           "Pendlere Horsens ↔ Aarhus",
            "type":           "PRIV",
            "kategori":       "pendler",
            "adresse":        "Horsens Station",
            "tlf":            "N/A – find via opslag i lokale Facebook-grupper",
            "kontakt":        "Facebook: 'Vi bor i Horsens', 'Horsens Lokalsamfund'",
            "behov":          "Fast morgen/aften-kørsel til station eller direkte til Aarhus",
            "maanedlig_dkk":  3500,
            "sandsynlighed":  55,
            "noter":          "Post i lokale FB-grupper: 'Fast månedlig pris for pendlere'",
            "prioritet":      "MIDDEL",
        },
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# AGENT
# ─────────────────────────────────────────────────────────────────────────────

class ProspectAgent:
    """
    Finder og prioriterer potentielle kunder til Zyflex.
    Kald .run(city) for at starte.
    """

    def __init__(self, status_callback=None):
        self.status_callback = status_callback or (lambda msg: None)

    def run(self, city: str = "Horsens") -> dict:
        self._update(f"Scanner prospects for {city}...")

        all_prospects = []
        for kategori, lista in PROSPECTS.items():
            for p in lista:
                all_prospects.append({**p, "kategori_gruppe": kategori})

        self._update(f"Scorer {len(all_prospects)} prospects...")

        scored = []
        for p in all_prospects:
            score = self._score(p)
            outreach = self._outreach(p)
            scored.append({
                **p,
                "score":          score,
                "outreach_emne":  outreach["emne"],
                "outreach_tekst": outreach["tekst"],
                "roi_dkk":        p["maanedlig_dkk"] * 12,   # Årsværdi
            })

        scored.sort(key=lambda x: x["score"], reverse=True)

        top    = [p for p in scored if p["score"] >= 70]
        middel = [p for p in scored if 50 <= p["score"] < 70]
        lav    = [p for p in scored if p["score"] < 50]

        total_maanedlig = sum(p["maanedlig_dkk"] for p in top)
        total_aars      = total_maanedlig * 12

        self._update(f"✅ {len(top)} høj-prioritet prospects · potentiel top-10 omsætning: {total_maanedlig:,} kr/md")

        return {
            "city":              city,
            "alle_prospects":    scored,
            "top_prospects":     top,
            "middel_prospects":  middel,
            "lav_prospects":     lav,
            "total_top_maaned":  total_maanedlig,
            "total_top_aar":     total_aars,
            "antal_total":       len(scored),
            "antal_top":         len(top),
            "generated_at":      datetime.now().isoformat(),
        }

    # ── Scoring ───────────────────────────────────────────────────────────────

    def _score(self, p: dict) -> int:
        """Kombiner sandsynlighed + månedlig værdi til en samlet prioritets-score."""
        sandsynlighed = p.get("sandsynlighed", 50)
        vaerdi        = p.get("maanedlig_dkk", 1000)

        # Sandsynlighed (0-100) = 60% af score
        s_del = sandsynlighed * 0.60

        # Månedlig værdi: log-skaleret (0-40 point)
        import math
        vaerdi_del = min(40, math.log10(max(1, vaerdi)) / math.log10(20000) * 40)

        return round(s_del + vaerdi_del)

    # ── Outreach tekst ────────────────────────────────────────────────────────

    def _outreach(self, p: dict) -> dict:
        navn = p["navn"]
        behov = p["behov"]
        pris = p["maanedlig_dkk"]
        kategori = p.get("kategori", "")

        if p["type"] == "FAST":
            emne = f"Transportaftale til {navn} – lokalt og pålideligt"
            tekst = (
                f"Hej,\n\n"
                f"Jeg hedder Mo og ejer Zyflex ApS – et lokalt taxafirma i Horsens.\n\n"
                f"Jeg kan se at {navn} har brug for {behov.lower()}.\n\n"
                f"Vi tilbyder faste aftaler med garanteret responstid, faktura månedligt "
                f"og dedikerede chauffører der kender lokalområdet.\n\n"
                f"Må jeg sende et konkret tilbud? Vi starter typisk fra {pris // 2:,} kr/md "
                f"afhængig af volumen.\n\n"
                f"Med venlig hilsen\nMo Jensen – Zyflex ApS\n"
                f"Tlf: [DIT NUMMER]\nEmail: omarhajimohamed62@gmail.com"
            )
        elif kategori in ("hotel", "venue", "festival"):
            emne = f"Fast taxi-aftale til {navn} – dine gæster fortjener det bedste"
            tekst = (
                f"Hej,\n\n"
                f"Jeg hedder Mo og driver Zyflex ApS – lokalt taxafirma i Horsens.\n\n"
                f"Jeres gæster har brug for pålidelig transport – vi kan tilbyde:\n"
                f"✓ Garanteret afhentning inden for 8 min\n"
                f"✓ Faste priser til station og lufthavn\n"
                f"✓ Månedlig faktura – ingen kontanter\n"
                f"✓ Diskrete, professionelle chauffører\n\n"
                f"Lad os tage en kop kaffe og lave en aftale der passer jer.\n\n"
                f"Med venlig hilsen\nMo Jensen – Zyflex ApS\n"
                f"Tlf: [DIT NUMMER]"
            )
        else:
            emne = f"Lokal transportpartner til {navn}"
            tekst = (
                f"Hej,\n\n"
                f"Jeg hedder Mo og driver Zyflex ApS i Horsens.\n\n"
                f"Mange virksomheder i Horsens bruger os til: {behov.lower()}.\n\n"
                f"Vi tilbyder månedlig faktura, faste priser og chauffører der er til rådighed "
                f"også udenfor normal åbningstid.\n\n"
                f"Har I behov for en fast transportaftale?\n\n"
     