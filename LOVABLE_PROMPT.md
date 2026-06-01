# Zyflex AI – Lovable Prompt

Kopiér ALT nedenfor (mellem `=== START ===` og `=== END ===`) ind i Lovable.

---

=== START ===

Build a production-ready React + Vite + Tailwind frontend for **Zyflex AI**, a Danish taxi intelligence platform.

The backend is already deployed on Render and exposes a FastAPI REST API. You are ONLY building the frontend. Do NOT build any backend, database, or auth — talk to the API.

## Backend base URL

Use this environment variable:
```
VITE_API_URL = https://REPLACE-WITH-MY-RENDER-URL.onrender.com
```

(Mo will replace this with his actual Render URL after first deploy.)

All `fetch` calls use `${import.meta.env.VITE_API_URL}/api/...`.

## Brand & design

- **Language:** Danish only — every label, button, message in Danish.
- **Brand color:** Electric blue `#3b82f6` (primary), `#60a5fa` (light), `#1e3a5f` (dark accent).
- **Background:** Deep navy `#080c14` (almost black).
- **Surface cards:** `#0f1520` with `1px solid #1e2d45` border.
- **Text:** White `#fff`, secondary `#94a3b8`, muted `#4a5568`.
- **Accent green** (earnings, success): `#22c55e`.
- **Accent red** (GO NOW alarm, errors): `#ef4444`.
- **Accent amber** (high score 70-84): `#f59e0b`.
- **Font:** System UI stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`).
- **Style:** Modern, dark, clean, Tesla/Stripe-inspired. Big typography. Mobile-first for driver, desktop-first for owner.
- **Icons:** Use `lucide-react`.
- **Logo:** Just the text `🚕 ZYFLEX` in bold blue with letter-spacing.
- **No gradients except** the primary GO NOW box and CTAs.
- **Radius:** 14–24px on cards/buttons.

## Pages to build

### 1. `/` Landing page (public, marketing)
Hero with headline "Zyflex AI – Palantir for Taxi". Subline in Danish: "AI-systemet der finder hotspots i realtid, reducerer tomkørsel og øger din indtjening pr. bil med 20–30%."
Sections: Problem (taxa-vognmænd kører blindt), Løsning (data + AI), Resultater (5 biler i stedet for 1), Kontakt.
Contact form posts to `POST /api/contact` with `{name, email, phone, company, message}`.
Footer: "Zyflex ApS · Horsens · Danmark · 2026".

### 2. `/driver/login` Driver PIN login (mobile-first)
Single fullscreen card. Logo, title "ZYFLEX CHAUFFØR", numeric PIN input (4 digits), big "LOG IND" button.
Submit `POST /api/driver/login` with `{pin: "2121"}`.
Response: `{status: "ok", token: "..."}` on success, `{status: "error", message: "Forkert kode"}` on fail.
Save token to `localStorage.setItem('driver_token', token)` and redirect to `/driver`.
Show shake animation + "Forkert kode – prøv igen" on wrong PIN.

### 3. `/driver` Driver dashboard (mobile-first, fullscreen)
**Auth gate:** if no `driver_token` in localStorage → redirect to `/driver/login`.

**On mount:**
1. Get GPS via `navigator.geolocation.getCurrentPosition()`. Fallback to Horsens centrum (lat 55.8615, lng 9.8506) if denied.
2. Call `POST /api/thranw/recommend` with body `{lat, lng, city: "Horsens"}` and header `Authorization: Bearer <driver_token>`.
3. Auto-refresh every 5 minutes.

**Layout (top to bottom, fullscreen on mobile):**
- Top strip: 🚕 ZYFLEX logo left, current time right.
- **Primary box** (gradient `#0f2040 → #0d1520`, blue border-bottom 3px):
  - Tag: "KØR HER NU" (small uppercase blue letters)
  - Zone name HUGE (2.2rem, bold 900): from `recommendation_text`
  - Reason (small, muted): from `reason`
  - Distance pill: "{distance_km} km væk"
  - Score ring (SVG circle, 72×72, color = blue/amber/red by score band) showing zone_score/100
  - Earnings: "{expected_earnings_per_hour} kr" big green, plus "~{calc} kr/md (8t × 22 dage)" tiny green below
- **Event bar** (only if `event_note` is present and not "Ingen events i nærheden"): green bar with pulsing dot + event text.
- **Næste område** card: first item from `alternatives` array — name, score, distance, kr/t.
- **Stats row** (3 columns): Vejr (parsed from `weather_note`), Events (from `event_note`), Sikkerhed ({confidence × 100}%).
- **Action row**: big blue "📍 Naviger" button (opens `map_link` in new tab) + grey "💬 Feedback" button (opens modal).
- **Footer**: "Opdateret: HH:MM" + "🔄 Opdater" button (re-fetches).

**Feedback modal:**
4 buttons in 2×2 grid: "🔥 Travlt her", "😶 Ingen kunder", "⏳ Venter", "✅ God tur".
On click: `POST /api/feedback` with `{zone: <current zone_name>, action: "busy"|"no_customers"|"holding"|"good", comment: ""}`. Show "✅ Tak!" toast and close.

**GO NOW alarm (CRITICAL):**
When response has `go_now: true` OR `zone_score >= 85`:
- Fullscreen RED overlay (`#dc2626`)
- Bouncing 🚨 icon (5rem)
- Text "GÅ NU!" (3rem white)
- Zone name + score below
- Vibrate device: `navigator.vibrate?.([400,100,400,100,800])`
- Big white "Forstået – kører nu" button → closes overlay AND opens `map_link`
- Don't show again until next refresh sets go_now back true.

### 4. `/owner/login` Owner PIN login (desktop-first)
Same as driver login but title "ZYFLEX OWNER" with 🔐 logo.
Submit `POST /api/owner/login` with `{pin}`.
Save `localStorage.setItem('owner_token', token)`, redirect to `/owner`.

### 5. `/owner` Owner dashboard (desktop, sidebar layout)
**Auth gate:** require `owner_token` in localStorage → else redirect `/owner/login`.

All API calls send header `Authorization: Bearer <owner_token>`.

**Sidebar (left, dark):** Dashboard · Hotspots · Agenter · Leads · Kontakter · Indstillinger · Log ud.

**Top bar:** Search · Notifications · Profile · Date.

**Tab 1 – Dashboard (default):**
- 4 KPI cards top: "Estimeret i dag" (kr), "Top zone" (name + score), "Aktive leads" (count), "Hotspots nu" (count).
- Hotspot map: use `react-leaflet` with OpenStreetMap tiles. Markers from `GET /api/thranw/zones` response (`zones[]` each has `lat`, `lon`, `name`, `score`, `is_hotspot`). Color marker by score: red ≥85, amber ≥70, blue ≥55, grey <55. Click marker → popup with name, score, earn_dkk_hr.
- Below map: ranked zone table (name, score, grade, kr/t, events_near, recommendation).
- Right column: live agent status from `GET /api/owner/agents`, refreshed every 10s. Each agent shows name, ikon, status (idle/running/done/error), besked, progress bar.

**Tab 2 – Hotspots:** Zone-by-zone breakdown. Same data as map tab but as detailed cards.

**Tab 3 – Agenter:** From `GET /api/owner/agents`. Card per agent showing formål, skills array, current status. Button "Kør alle agenter nu" calls `POST /api/run` with `{city: "Horsens"}`.

**Tab 4 – Leads:** From `GET /api/owner/leads?by=&type=&status=&q=`. Filterable table — by city, type (hotel/skole/sygehus/event), status (new/contacting/won/lost), free-text search. Each lead has score, monthly_dkk, navn, kontakt, tlf, email. Sort by score desc by default.
Top of table: "Månedlig potentiale: {monthly_pot} kr" (sum of leads with score ≥ 75).
Each row has buttons: 📧 Email (calls `POST /api/contract-hunter/generate-email` with `{lead, sender_name: "Mo Jensen", sender_phone: ""}`, shows generated email in modal with copy button) — 📞 Opkaldsscript (calls `POST /api/contract-hunter/generate-call-script`) — ✏️ Edit — 🗑 Delete (`DELETE /api/owner/leads/{id}`).
Top right "+ Ny lead" button opens form modal posting `POST /api/owner/leads`.

**Tab 5 – Kontakter:** From `GET /api/owner/contacts`. Simple table with form submissions from landing page. Mark read/unread.

**Tab 6 – Indstillinger:** Show current PIN (read-only "2121"), backend health from `GET /api/thranw/health`, "Log ud" button calls `POST /api/owner/logout` and clears localStorage.

## API contract — full reference

**Headers for all authenticated calls:**
```
Authorization: Bearer <token>
```
where `<token>` = `localStorage.getItem('driver_token')` or `'owner_token'`.

### Public
- `GET /api/thranw/health` → `{status, agent, ready, city, trips_csv_rows, history_status, ...}`
- `POST /api/contact` body: `{name, email, phone, company, message}` → `{status: "ok"}`

### Driver
- `POST /api/driver/login` body: `{pin}` → `{status, token}` or `{status: "error", message}`
- `POST /api/driver/logout` → `{status: "ok"}`
- `POST /api/thranw/recommend` body: `{lat, lng, city?, current_time?}` →
  ```
  {
    "recommendation_text": "⚡ KØR TIL HORSENS CENTRUM NU",
    "zone_score": 91,
    "zone_name": "Horsens Centrum",
    "reason": "Morgenrush · 14 events i regionen · Regn boost",
    "expected_earnings_per_hour": 280,
    "expected_trips_per_hour": 2.8,
    "go_now": true,
    "distance_km": 0.5,
    "map_link": "https://www.google.com/maps/dir/?api=1&origin=...",
    "weather_note": "10°C, ingen regn",
    "event_note": "AC Horsens kamp – 6,000 gæster (0.8 km)",
    "history_note": "25 kørsler i historik · regn-boost 6.5 pt",
    "confidence": 0.85,
    "alternatives": [
      {"zone": "Horsens Station", "score": 82, "distance_km": 1.2, "earn_dkk_hr": 260}
    ],
    "timestamp": "2026-05-07T10:14:08"
  }
  ```
- `POST /api/feedback` body: `{zone, action, comment}` → `{status: "ok"}`

### Owner
- `POST /api/owner/login` body: `{pin}` → `{status, token}`
- `POST /api/owner/logout` → `{status: "ok"}`
- `GET /api/owner/agents` → `{agents: [{id, navn, ikon, formål, skills, status, besked, progress}]}`
- `GET /api/owner/leads?by=&type=&status=&q=` → `{leads: [...], total, monthly_pot}`
- `POST /api/owner/leads` body: lead object → `{status, lead}`
- `PUT /api/owner/leads/{id}` body: lead object → `{status, lead}`
- `DELETE /api/owner/leads/{id}` → `{status: "ok"}`
- `GET /api/owner/report` → full analyzed report
- `GET /api/owner/contacts` → array of contact submissions
- `POST /api/contract-hunter/generate-email` body: `{lead, sender_name, sender_phone}` → `{subject, body}`
- `POST /api/contract-hunter/generate-call-script` body: `{lead}` → `{script}`
- `POST /api/run` body: `{city}` → `{status: "started", city}`

### Thranw (zone scoring)
- `GET /api/thranw/zones?city=Horsens` →
  ```
  {
    "city": "Horsens",
    "zones": [
      {"id": "horsens_centrum", "name": "Horsens Centrum", "lat": 55.86, "lon": 9.85,
       "score": 82, "grade": "🔥 Høj efterspørgsel", "is_hotspot": true,
       "earn_dkk_hr": 380, "events_near": 2,
       "recommendation": "🔥 KØR TIL HORSENS CENTRUM – høj efterspørgsel",
       "confidence": "Høj"}
    ],
    "top_zone": "Horsens Centrum",
    "top_score": 82,
    "history": {...},
    "timestamp": "..."
  }
  ```

## Tech stack

- React 18 + Vite + TypeScript
- Tailwind CSS (custom theme matching brand colors)
- React Router v6
- `lucide-react` for icons
- `react-leaflet` + `leaflet` for owner map
- Use `fetch` directly (no axios). Wrap in a small `api.ts` helper that auto-adds Authorization header.
- No state management library — `useState` + `useContext` is enough.

## API helper pattern

```ts
// src/lib/api.ts
const API = import.meta.env.VITE_API_URL;

function getToken(role: 'driver' | 'owner'): string | null {
  return localStorage.getItem(`${role}_token`);
}

export async function api<T>(
  path: string,
  opts: { method?: string; body?: any; role?: 'driver' | 'owner' } = {}
): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (opts.role) {
    const tok = getToken(opts.role);
    if (tok) headers.Authorization = `Bearer ${tok}`;
  }
  const r = await fetch(`${API}${path}`, {
    method: opts.method || 'GET',
    headers,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (!r.ok) throw new Error(`API ${path} failed: ${r.status}`);
  return r.json();
}
```

## Deliverables checklist

- [ ] All 5 pages above, fully functional
- [ ] Mobile-first responsive (driver pages MUST work on phone)
- [ ] Desktop-first owner dashboard with sidebar layout
- [ ] All API calls use `Authorization: Bearer <token>` for protected routes
- [ ] GO NOW fullscreen alarm with vibration on driver page
- [ ] Leaflet map on owner dashboard with hotspot markers
- [ ] Loading states + error states everywhere (red box "Netværksfejl – Prøv igen")
- [ ] Auto-refresh: 5 min on driver, 30 sec on owner agents/dashboard
- [ ] Logout clears localStorage and redirects to login
- [ ] All Danish copy, no English in UI
- [ ] Brand colors and dark theme everywhere
- [ ] Build deploys clean to Lovable hosting

Build this NOW.

=== END ===

---

## Hvad du skal gøre i Lovable

1. **Opret nyt projekt** i Lovable.dev
2. **Indsæt prompten ovenfor** (alt mellem START og END)
3. **Vent** mens Lovable genererer
4. **Sæt environment variable**: i Lovable's settings → Environment → tilføj `VITE_API_URL` med din Render-URL (fx `https://zyflex-xxx.onrender.com`)
5. **Test** at frontend kan tale med backend
6. **Deploy** Lovable's auto-genererede URL bliver din chauffør- og ejer-app

## Inden du sender prompten — to ting du SKAL gøre

### 1. Push backend-ændringerne til Render

Jeg har lige opdateret backend så Lovable kan logge ind via token (i stedet for cookie). Push ændringerne:

```
cd C:\Users\omarh\Documents\Claude\Projects\plantire\zyflex-ai
git add backend/main.py backend/driver_auth.py backend/agents/thranw_agent.py backend/thranw_router.py dashboard/driver.html dashboard/driver_login.html
git commit -m "feat: Thranw + driver PIN auth + token-based login for Lovable"
git push
```

Render auto-deployer på 2-3 minutter.

### 2. Find din Render-URL

Den ser ud som `https://zyflex-xxx.onrender.com`. Find den i Render dashboard → din service. Erstat `REPLACE-WITH-MY-RENDER-URL` i prompten med den faktiske URL inden du sender til Lovable.

## Hvis Lovable melder CORS-fejl

Når frontend deployes på fx `https://yourapp.lovable.app`, kan backend's CORS eventuelt blokere. Du har allerede `allow_origins=["*"]` i main.py så det burde virke, men hvis det driller, sig det til mig så fikser jeg det.
