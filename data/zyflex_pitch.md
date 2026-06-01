# Zyflex AI – "Palantir for Taxi"

**Bygget af:** Mo Jensen, Zyflex ApS, Horsens Danmark  
**Status:** MVP klar · Kørende på Render.com

---

## Hvad er det?

Zyflex AI er et datadrevet operationssystem til taxavognmænd.
Det gør præcis det som store logistikfirmaer bruger millioner på –
men til en lille taxaoperatør i Horsens.

Systemet svarer på ét spørgsmål i realtid:

> **"Hvor skal min chauffør køre hen RIGHT NOW for at tjene mest muligt?"**

---

## Hvad er bygget

**6 AI-agenter der kører automatisk:**

| Agent | Funktion |
|-------|---------|
| Data Agent | Henter vejr, events, trafik og GPS-zoner live |
| Analysis Agent | Scorer 6 zoner 0–100 baseret på efterspørgsel |
| Sales Agent | Finder B2B leads med telefon og adresse |
| Ops Agent | Genererer chauffør-briefing: "KØR TIL X KL. Y" |
| Event Agent | Scraper CASA Arena, Billetto, 24 danske festivaler |
| Prospect Agent | Finder nye kunder med outreach-emails klar til send |

**Frontend:**
- Driver View (mobil) – score-ring, GO NOW alarm, earnings estimate
- Admin Dashboard – firmaer, fakturaer, suspend/kick
- Multi-tenant SaaS – 499 kr/md pr. bil

**Teknologi:** Python · FastAPI · Render.com · Google OAuth · ntfy.sh push

---

## Nøgletal

- **Målsætning:** 85.000 kr/md pr. bil
- **SaaS-pris:** 499 kr/md pr. bil
- **Top 4 B2B-prospects identificeret:** 36.500 kr/md potentiale
- **Festivals tracked:** 24 events i 2026 (Smukfest 55k, Jelling 40k m.fl.)
- **Auto-refresh:** Hvert 30. minut uden menneskelig indgriben

---

## Konkurrencefordel

Alle andre taxafirmaer kører rundt og håber på kunder.

Zyflex ved hvor kunderne er – **før de bestiller**.

Det er forskellen på at være chauffør og at være CEO med et system.

---

## Næste skridt

- Skalere fra 1 → 5 biler i Horsens
- Åbne for vognmænd i Aarhus, Vejle, Kolding
- Sælge systemet som SaaS til andre taxaoperatører

**Kontakt:** Mo Jensen · omarhajimohamed62@gmail.com
