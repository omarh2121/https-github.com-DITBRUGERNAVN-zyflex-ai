# 🚕 Zyflex AI – Intelligent Taxa System

> Dit personlige Palantir-system til taxi-drift.
> Datadrevet. Lokal. Ingen cloud nødvendig.

---

## Hvad gør det?

Systemet henter offentlige data i realtid og scorer alle dine driftzoner efter efterspørgsel:

- **Vejr** – regn og kulde = folk tager taxi
- **Events** – koncerter, fodbold = massiv efterspørgsel
- **Tidspunkt** – rush hour, natteliv, frokost
- **Lokationer** – hoteller, sygehuse, stationer

Output: Top 5 zoner at køre i, med score, begrundelse og estimeret indtjening.

---

## Installation (én gang)

### 1. Krav
- Python 3.9 eller nyere: https://python.org/downloads
- VS Code (anbefalet): https://code.visualstudio.com

### 2. Åbn terminal i projektmappen
```
cd zyflex-ai
```

### 3. Installér dependencies
```
pip install -r requirements.txt
```

### 4. Konfigurér API-nøgler (valgfrit)
Åbn `.env` filen og tilføj din Ticketmaster nøgle hvis du har en:
```
TICKETMASTER_API_KEY=din_nøgle_her
```
Gratis nøgle: https://developer.ticketmaster.com/

> Systemet virker uden nøglen – det bruger realistiske mock-events.

---

## Kørsel

```bash
python backend/main.py
```

Det er det. Systemet:
1. Henter vejrdata (Open-Meteo – gratis, ingen nøgle)
2. Henter events (Ticketmaster eller mock)
3. Henter POI-data fra OpenStreetMap
4. Scorer alle zoner
5. Printer resultater i terminalen
6. Gemmer `data/report.json` (til dashboard)
7. Logger til `data/trips.csv` (til historik)

---

## Dashboard

Åbn denne fil i din browser:
```
dashboard/index.html
```

Klik **Opdater** efter du har kørt `main.py`. Dashboardet viser:
- Top zoner med score og begrundelse
- Vejroverblik
- Events i dag
- Estimeret indtjening
- B2B leads

---

## Projektstruktur

```
zyflex-ai/
│
├── backend/
│   ├── main.py          ← Kør dette (entry point)
│   ├── fetchers.py      ← API-kald (vejr, events, lokationer)
│   ├── processor.py     ← Scoring-motor (det intelligente lag)
│   └── config.py        ← Zoner, vægte, indstillinger
│
├── data/
│   ├── report.json      ← Genereres af main.py (læses af dashboard)
│   └── trips.csv        ← Historisk log over kørsler
│
├── dashboard/
│   └── index.html       ← Åbn i browser
│
├── .env                 ← API-nøgler (hemmeligt – del ikke)
├── requirements.txt     ← Python-pakker
└── README.md            ← Denne fil
```

---

## Tilpasning

### Tilføj en ny zone
Åbn `backend/config.py` og tilføj til `ZONES`-listen:
```python
{
    "id":          "ny_zone",
    "name":        "Min By",
    "lat":         55.1234,
    "lon":         9.5678,
    "base_score":  35,
    "poi_type":    "city_center",
    "description": "Beskrivelse af zonen",
},
```

### Juster scoring-vægte
I `backend/config.py`:
```python
SCORING_WEIGHTS = {
    "weather":   25,   # Øg dette hvis vejr er vigtigt i dit område
    "events":    30,   # Høj ved mange events
    "time":      25,   # Rush hour fokus
    "location":  20,   # POI-tæthed
}
```

---

## Data-sources

| Kilde              | API               | Nøgle | Hvad                    |
|--------------------|-------------------|-------|-------------------------|
| Open-Meteo         | open-meteo.com    | Nej   | Vejr + nedbør           |
| Ticketmaster       | ticketmaster.com  | Ja*   | Koncerter, sport, events|
| OpenStreetMap      | overpass-api.de   | Nej   | Hoteller, barer, sygehuse|

*Gratis nøgle tilgængelig

---

## Fremtidige udvidelser

- [ ] DSB API – togforsinkelser (folk hopper i taxa)
- [ ] Vejdirektoratet – vejarbejde og trafikdata
- [ ] FastAPI REST endpoint – del data med apps
- [ ] Automatisk kørsel (Windows Task Scheduler / cron)
- [ ] Multi-chauffør koordination
- [ ] Historisk analyse og mønstre

---

## Automatisk kørsel (valgfrit)

### Windows – kør hver time automatisk
1. Åbn **Task Scheduler**
2. Opret ny opgave → Trigger: Hver time
3. Action: `python C:\sti\til\zyflex-ai\backend\main.py`

### Eller manuelt fra VS Code terminal:
```bash
python backend/main.py
```

---

*Zyflex ApS · Bygget med åbne data og Python*
