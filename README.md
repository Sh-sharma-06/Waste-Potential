# Waste-Potential

**The potential was always there. We just found it.**

Waste-Potential helps farms, households and industries in India find the best way to turn their waste
into energy or recyclable value. It models seven waste-to-energy processes, classifies waste from
photos, finds nearby buyers and recyclers, and produces a greenhouse-gas (GHG) audit report.

It is a **FastAPI** backend with a **Next.js** frontend, plus a separate **India waste heatmap** app
(its own FastAPI backend and Vite frontend) that is embedded in the Industry pages.

---

## What you can do

| Sector | Flow |
|---|---|
| **Agriculture** (`/explore/agriculture`) | Upload a photo of crop residue → AI identifies it → disposal and reuse advice → follow-up chat |
| **Home** (`/explore/home`) | Upload a photo of household waste → AI identifies it → recycling and disposal advice → follow-up chat |
| **Industry** (`/explore/industry`) | Enter a PIN code → choose **Energy** or **Non-Energy** waste (see below) |

**Industry, Energy recoverable**
1. **Simulator** (`/simulator`): enter daily waste (kg/day) to get:
   - a Monte Carlo ranking of 7 processes: pyrolysis, gasification, anaerobic digestion, hydrothermal carbonisation (HTC), composting, incineration, torrefaction;
   - a physics-model yield estimate for the chosen process;
   - an interactive 3D view of each process's equipment stages;
   - AI explanations: "Why Choose This?" and per-process "Show Details" briefings.
2. **AI Recommendation** tab: Gemini picks one process using your waste category, tonnage, live weather for the PIN and your preferred processing duration.
3. **Energy marketplace** (`/market/energy`): nearby buyers for the product (Google Places search, plus a built-in list of known buyers) → select buyers → **GHG audit report**, which you can print to PDF or download.

**Industry, Non-energy recoverable**
1. **Material breakdown** (`/explore/industry/non-energy`): enter kg/day of plastics, metals, e-waste, paper and glass.
2. **Non-energy marketplace** (`/market/non-energy`): nearby recyclers and indicative scrap prices for each material.

**Across the Industry pages:** a floating **Multilingual AI** chatbot. You can type or speak in English or
10 Indian languages. Sarvam AI handles speech and translation, Gemini answers, and on the simulator it
uses your actual results.

**Other pages:** `/dashboard`, `/compare`, `/assistant`, `/optimize`, `/impact`, `/validation` and
`/explorer` are earlier platform pages that still work.

---

## Architecture

| App | Folder | Port | Purpose |
|---|---|---|---|
| Backend API | `backend/` | 8000 | Simulation engines, pathway ranking, AI, buyers, audit report |
| Frontend | `frontend/` | 3000 | The website. Proxies `/api/*`, `/simulator/*` and `/sarvam/*` to the backend |
| Heatmap API | `backend_heat_map/backend/` | 8001 | Serves CPCB / Data.gov.in waste statistics and PIN boundaries |
| Heatmap UI | `frontend_heat_map/frontend/` | 3001 | Map shown inside the Industry page |

Datasets used by the heatmap are in `Datasets/`; precomputed boundaries are in
`backend_heat_map/backend/cache/`. No database is required. The main backend keeps runs in memory only.

---

## Prerequisites

| Tool | Version |
|---|---|
| Python | 3.12 or newer |
| Node.js | 18 or newer |
| npm | 9 or newer |

---

## Setup

```bash
git clone https://github.com/Sh-sharma-06/Waste-Potential.git
cd Waste-Potential

# Environment variables (see the table below)
cp .env.example .env

# Python environment: main backend + heatmap backend
python -m venv .venv
.\.venv\Scripts\activate            # Windows
# source .venv/bin/activate         # macOS / Linux
pip install -r backend/requirements.txt
pip install -r backend_heat_map/backend/requirements.txt

# Frontends
cd frontend && npm install && cd ..
cd frontend_heat_map/frontend && npm install && cd ../..
```

### Environment variables

Put these in `.env` at the repository root. It is git-ignored, so never commit real keys.
Some keys below are not yet listed in `.env.example`; add them yourself.

| Variable | Used for | If missing |
|---|---|---|
| `GEMINI_MODEL` | Gemini model tried first, e.g. `gemini-3.5-flash` | Defaults to `gemini-3.8-flash`. The app then falls back to `gemini-3.5-flash`, then `gemini-3.5-flash-lite` |
| `GEMINI_API_KEY_RECOMMEND` | AI Recommendation | Tries the other Gemini keys below if this one is out of credit |
| `GEMINI_API_KEY_EXPLAIN` | "Show Details" briefings, "Why Choose This?" | "Why Choose This?" shows built-in template text |
| `GEMINI_API_KEY_VISION` | Photo classification, advice, chatbot | Those features show an error |
| `GEMINI_API_KEY_PARSER`, `_ADVISOR`, `_AUDIT` | AI assistant endpoints (`/api/v1/assistant/*`) | Those endpoints return 503 |
| `GROQ_API_KEY`, `GROQ_MODEL` | Narrative text of the GHG audit report | Report uses a built-in template |
| `SARVAM_API_KEY` (or `SARVAM_API`) | Speech-to-text, translation, read-aloud | Voice and translation fail |
| `GOOGLE_PLACES_API_KEY` | Nearby buyers, recyclers and facilities | Only the built-in buyer list is shown |
| `OPEN_ROUTE_SERVICE_API_KEY` (or `MAPS_ROUTING_API_KEY`) | Road distances to buyers | Straight-line distances |
| `GEOCODE_CONTACT` | Your contact email, sent to OpenStreetMap Nominatim when geocoding PIN codes (its usage policy requires one) | Set it; Nominatim may block anonymous requests |

Frontend (optional, in the shell or `frontend/.env.local`):
- `NEXT_PUBLIC_API_URL`: backend URL, default `http://localhost:8000`.
- `HEATMAP_API_URL`: heatmap API URL, default `http://localhost:8001`.

Weather comes from Open-Meteo and needs no key.

---

## Running

Start all four apps, each in its own terminal, from the repository root with the virtual environment active:

```bash
# 1. Backend API          → http://localhost:8000  (docs: http://localhost:8000/docs)
cd backend && uvicorn app.main:app --reload --port 8000

# 2. Frontend             → http://localhost:3000
cd frontend && npm run dev

# 3. Heatmap API          → http://localhost:8001
cd backend_heat_map/backend && uvicorn main:app --reload --port 8001

# 4. Heatmap UI           → http://localhost:3001
cd frontend_heat_map/frontend && npm run dev
```

On Windows you can start the two heatmap apps with `run_heatmap_backend.bat` and `run_heatmap_frontend.bat`.

The backend reads `.env` only when it starts, so **restart it after changing any key**. Restart the
frontend after changing `frontend/next.config.js`.

---

## Tests

```bash
# Backend, from the repository root
python -m pytest backend -q

# Frontend, from frontend/
npm test              # Vitest component tests
npm run typecheck     # TypeScript
```

Most backend tests mock external services. The live tests in `backend/tests/test_sarvam_router.py`
call the real Sarvam API, so they need network access and Sarvam credit.

### Golden-number check

The anaerobic digestion engine must produce these exact values for default parameters
(`simulate(Params())`), to a relative tolerance of `1e-6`:

| Output | Expected value |
|---|---|
| `e_net_kwh_d` | `76.74057020848` |
| `biogas_nm3_d` | `47.0448` |

CI checks this automatically (`.github/workflows/ci.yml`).

---

## How the numbers are produced

- **Yield:** the backend's physics models (`backend/app/core_engine/`) compute net energy and products per
  tonne of waste. The result is scaled by the user's daily tonnage and shown as a **model estimate**.
- **Ranking:** `POST /pathways/compare` first prices each process by what it sells:
  - electricity for AD, gasification and incineration;
  - heat or fuel for pyrolysis, HTC and torrefaction;
  - compost for composting;
  - plus the gate fee for every process.

  A Monte Carlo pass (500 runs) then varies yield, cost and market price. Each process's **share** is
  the fraction of runs in which it had the highest net value.
- **GHG audit:** baseline dumpsite emissions are compared with each process's emissions and credits
  (IPCC 2006 / 2019 and the GHG Protocol for Project Accounting). Factors and their sources are in
  `backend/data/emission_factors.json`.

---

## Status and limits

- **Location data is a single default.** The waste composition, moisture, prices and energy buyers used
  in the simulator ranking are one record (`default_v1`), the same for every PIN. Only the user's tonnage
  changes the result. The AI Recommendation, buyer search and audit report do use the PIN.
- **Costs are assumed equal** for every process. No verified per-process capex/opex exists in the project,
  so the ranking compares energy and product revenue only; the simulator page says so.
- **Not every process has a model estimate yet.** Only anaerobic digestion has a tested engine (see the
  golden numbers). The other process models are illustrative. For the default (wet) feedstock, pyrolysis,
  gasification, incineration and torrefaction currently return "No model estimate for this feedstock".
- **AI features need API credit.** If Gemini, Groq or Sarvam keys are missing, out of quota or out of
  credit, those features show an error, an "offline" badge, or template text.
- **Buyers and geocoding are unverified candidates** from third-party APIs (Google Places,
  OpenStreetMap Nominatim), not confirmed demand.
- **Photo classification is AI-generated.** It does not measure mass or composition. Check labels before
  relying on them.
- **Nothing here is validated against real plant data.** Do not use outputs for engineering, financial or
  policy decisions without independent verification.
