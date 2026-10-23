# Waste-Potential

A research tool for modelling waste treatment pathways, classifying waste from
photos, and finding nearby recyclers and buyers. It is a FastAPI backend with a
Next.js frontend.

---

## Prerequisites

| Tool | Minimum version |
|------|----------------|
| Python | 3.12 |
| Node.js | 18 |
| npm | 9 |

All Python runtime dependencies are in `backend/requirements.txt`. No database
is required; the backend is stateless except for an in-memory run store.

---

## Setup

### 1. Clone and enter the repository

```bash
git clone <repo-url>
cd Waste-Potential
```

### 2. Copy and edit environment variables

```bash
cp .env.example .env
# Open .env and fill in the API keys described in each comment.
```

`.env` is git-ignored; never commit real keys.

### 3. Create a Python virtual environment and install dependencies

```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r backend/requirements.txt
```

### 4. Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

---

## Running

### Backend

From the `backend/` directory:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is then available at `http://localhost:8000`. Interactive docs are at
`http://localhost:8000/docs`.

### Frontend

From the `frontend/` directory:

```bash
npm run dev
```

The UI is then available at `http://localhost:3000`.

---

## Tests

Run the full backend test suite from the **repo root**:

```bash
python -m pytest backend -q
```

All tests must pass with no network access; external services are mocked.

### Golden-number check

The anaerobic digestion engine must produce these exact values for default
parameters (`simulate(Params())`):

| Output | Expected value |
|--------|---------------|
| `e_net_kwh_d` | `76.74057020848` |
| `biogas_nm3_d` | `47.0448` |

Tolerance: `1e-6` relative error. This is verified automatically in CI (see
`.github/workflows/ci.yml`).

---

## Status and limits

- **Only anaerobic digestion has a tested simulation engine.** Pyrolysis and
  gasification parameter values are illustrative estimates only and have not
  been validated against real plant data.
- **All model parameters are illustrative estimates** taken from published
  literature ranges. They are not calibrated to any specific installation.
- **Places and geocoding results are unverified candidates.** The `/buyers`,
  `/recyclables/buyers`, and `/geocode` endpoints return data from third-party
  APIs (Google Places, Nominatim). Results have not been field-verified.
- **Vision classification is AI-generated from a photo.** It does not measure
  mass or composition. Labels should be verified before use.
- **Nothing in this project is validated on real plant data.** Do not use
  outputs for engineering, financial, or policy decisions without independent
  verification.
