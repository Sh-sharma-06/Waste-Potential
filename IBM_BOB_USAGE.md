# IBM Bob Usage in Waste-Potential

**Platform:** Waste-Potential — a decision-intelligence system for waste-to-energy pathway selection  
**Team size:** 5 engineers  
**AI Collaborator:** IBM Bob (Lead Technical AI Collaborator)

---

## Overview

Waste-Potential is a full-stack, decision-intelligence platform that converts raw waste-stream inputs into ranked, risk-quantified treatment pathway recommendations. The system spans a FastAPI scientific backend, a Next.js progressive web application, seven thermochemical and biological pathway models, a Monte Carlo uncertainty engine, a Gemini-backed computer-vision classifier, and a geospatial buyer-discovery pipeline — all developed in parallel by a five-person team under hackathon time constraints.

IBM Bob served as the lead technical collaborator across every engineering pillar of this project. The sections below document exactly where Bob's orchestration was applied, what technical problems were solved, and how that acceleration translated into shipped code.

---

## Pillar 1: System Architecture & Database Design

### FastAPI Application Factory

Bob designed the application factory pattern in [`app/main.py`](backend/app/main.py) that wires fourteen independent routers — core engine, decision engine, ML, vision, buyers, market catalog, geocoding, recyclables, pathways, assistant, and platform — into a single FastAPI instance. Each router owns its own domain and is registered without coupling, allowing parallel development across team members without merge conflicts.

Bob specified the CORS policy with explicit origin whitelisting (`localhost:3000`, `localhost:3001`) and constrained methods to `GET`, `POST`, and `OPTIONS`, preventing accidental privilege escalation during development.

### PostGIS Schema & Stateless Run Store

Bob designed the PostGIS-ready spatial schema located in [`app/data/sql/schema.sql`](backend/app/data/sql/schema.sql) for facilities, buyers, and geospatial waste-source records. Recognising the hackathon constraint, Bob simultaneously designed an in-memory run store as a drop-in fallback — the [`_InMemoryRunReader`](backend/app/core_engine/router.py) class in [`app/core_engine/router.py`](backend/app/core_engine/router.py) uses a Protocol abstraction so the same router code operates correctly whether backed by a live database or the in-memory dict. This let the team develop and test the full API surface without requiring a running PostgreSQL instance.

### Docker & Environment Configuration

Bob authored the `docker-compose.yml` orchestrating the backend, frontend, and PostGIS containers. Bob also designed the `.env.example` contract separating all secrets (Google Places API key, OpenRouteService key, Gemini API keys) from source code, establishing the `app.config.get_setting()` pattern used uniformly across every module that touches an external service.

---

## Pillar 2: Scientific Engine & Validation

### Anaerobic Digestion Mass/Energy Engine

The core simulation engine in [`app/core_engine/engine.py`](backend/app/core_engine/engine.py) is the most mathematically demanding component in the project. Bob authored this module end-to-end, implementing:

- **Water-conditioning formula** — `condition_water()` derives the mass of water to add or remove to reach a target moisture fraction, with the constraint that total dissolved solids are conserved: `dW = M × (x_target − x_initial) / (1 − x_target)`. An earlier blueprint formula had the sign inverted; Bob identified and corrected this, a fact now locked in [`test_old_blueprint_formula_was_wrong`](backend/app/core_engine/tests/test_engine.py).
- **Buswell stoichiometric ceiling** — `buswell_bound()` computes the theoretical maximum CH₄ yield (Nm³/kg VS) from feedstock macromolecular composition using the Buswell & Mueller (1952) coefficients for carbohydrates (0.415), proteins (0.496), and lipids (1.014). Any simulation run yielding above this ceiling triggers a guardrail warning.
- **CHP / boiler thermal split** — [`thermal.py`](backend/app/core_engine/thermal.py) implements digester heat demand decomposed into feed-heating (`feed × cp × ΔT / 3600`) and wall-loss through a cylindrical vessel model (`A = 1.5πD²` where `D = (4V/π)^(1/3)`), then allocates available chemical energy between the CHP unit and an auxiliary boiler. The boiler allocation is capped at available chemical energy and flags a `heat_deficit` when the digester cannot be held at temperature.
- **Golden-number regression anchors** — the engine produces `e_net_kwh_d = 76.74057020848` and `biogas_nm3_d = 47.0448` for default parameters, verified to `1e-6` relative error in CI. These values were computed by Bob from first principles and are the regression anchors for all subsequent refactors.

### Guardrails Module

Bob authored [`app/core_engine/guardrails.py`](backend/app/core_engine/guardrails.py) as a pure-function safety layer. Key implementations:

- `check_methane_yield()` — compares actual CH₄/VS yield against the Buswell ceiling.
- `check_vs_destruction()` — flags implied VS destruction fractions above 85%, a model assumption calibrated to mesophilic wet-AD of municipal organic waste.
- `check_input_ranges()` — accepts either a `Params` dataclass or a plain dict and returns out-of-range fields for `ts_fraction`, `hrt_days`, `digester_temp_c`, `ch4_fraction`, and `organic_fraction`, promoting simulation outputs from `"illustrative_estimate"` to `"extrapolation"` status when inputs leave the calibrated range.
- `parse_formula()` and `atom_balance()` — a full molecular formula parser and elemental stoichiometric checker implementing the general Buswell equation for C, H, O, N, S atoms. This enabled the team to validate Buswell coefficients from first principles (`C6H10O5`, `C5H7NO2`, `C57H104O6`) rather than accepting literature values on trust.

### Multi-Pathway Thermochemical Models

Bob designed the entire pathway module family in [`app/core_engine/pathways/`](backend/app/core_engine/pathways/) using a common `Feedstock` dataclass interface. Each pathway is a standalone, frozen-parameter simulation:

| Pathway | Key engineering | File |
|---|---|---|
| Pyrolysis | Oil/char/gas yield balance, electric pre-drying (2.26 MJ/kg latent heat), process heat `= M × cp × ΔT / 3600` | [`pyrolysis.py`](backend/app/core_engine/pathways/pyrolysis.py) |
| Gasification | Cold-gas efficiency × syngas LHV, drying load, char as `ash_fraction × 1.5` | [`gasification.py`](backend/app/core_engine/pathways/gasification.py) |
| Composting | VS-loss mass balance, rewetted compost product formula, GHG emissions (CH₄, N₂O kg/t) | [`composting.py`](backend/app/core_engine/pathways/composting.py) |
| HTC, Torrefaction, Incineration | Respective energy/mass formulas | `htc.py`, `torrefaction.py`, `incineration.py` |

All pathway models carry explicit `status: "illustrative_estimate"` metadata and `warnings` lists, ensuring scientific honesty in all API responses.

### Monte Carlo Uncertainty Quantification

Bob designed and implemented the full Monte Carlo engine in [`app/core_engine/montecarlo.py`](backend/app/core_engine/montecarlo.py):

- **`Dist` dataclass** — a validated, frozen distribution descriptor supporting `triangular`, `normal`, `uniform`, and `lognormal` kinds, with hard clip bounds and mandatory evidence provenance strings. Validation on `__post_init__` enforces `low ≤ mode ≤ high` for triangular, `sigma > 0` for normal, and `sigma_log > 0` for lognormal.
- **`default_dists()`** — nine assumed prior distributions over key `Params` fields (`y_biogas_nm3_per_kg_vs`, `ts_fraction`, `eta_el`, `ch4_fraction`, etc.) sourced from the parameter registry uncertainty column.
- **`recentred_dists()`** — dynamically recentres the default distributions on any stored run's actual parameter values by computing a scale ratio `r = v / d` and applying it to all distribution args. Parameters with a zero value or zero default are omitted and held fixed during MC sampling.
- **`run_mc()`** — draws `n = 2000` samples (default seed 42), runs `engine.simulate()` for each, computes P2.5/median/P97.5/P(net ≤ 0), and returns Spearman-rank sensitivity indices over all sampled inputs. The result dict is guaranteed JSON-serialisable (no NumPy types).

---

## Pillar 3: AI & Geospatial Integration

### Gemini Vision Classification Pipeline

Bob designed [`app/ml/vision_router.py`](backend/app/ml/vision_router.py) end-to-end:

- **Magic-byte MIME validation** — content-type headers alone are not trusted; the router checks actual file magic bytes for JPEG (`\xff\xd8\xff`), PNG (`\x89PNG\r\n\x1a\n`), and WebP (`RIFF....WEBP`) before forwarding bytes to Gemini, preventing renamed text files from reaching the model.
- **Structured JSON extraction** — the classify endpoint instructs Gemini to return a strict JSON schema (`{"items": [{"label", "category", "confidence"}]}`), then validates each item through a Pydantic `WasteItem` model with a `@model_validator` that rejects any category not in the canonical eight-category set.
- **Server-side stream derivation** — the organic/non-organic stream classification is computed server-side from the validated items; it is never trusted from the Gemini response, preventing prompt-injection-driven stream misclassification.
- **Local HuggingFace classifier** — Bob integrated a locally-loaded `transformers.pipeline("image-classification")` pointing to [`app/ml/vision/waste-classification-model/`](backend/app/ml/vision/) as a `/vision/classify-local` fallback endpoint for offline or cost-constrained deployments.
- **Sector-aware advice** — the `/vision/advice` endpoint accepts `sector: "urban" | "rural"` and selects between two prompt profiles, one focused on scrap/compost/donation and the other on crop-residue management and farm biogas.

### Scikit-Learn Hybrid ML Yield Pipeline

Bob designed the two-layer ML architecture in [`app/ml/yield_model/`](backend/app/ml/yield_model/):

- **Layer 1 (kinetic physics):** The `YieldPredictor` in [`app/ml/predictor.py`](backend/app/ml/predictor.py) uses Chen-Hashimoto kinetics (`Y = Y₀ × (1 − K / (HRT × μ − 1 + K))`) with FAOSTAT 2023 crop-specific residue-to-product ratios and dry-matter fractions for seven crops (maize, wheat, rice, sugarcane, sorghum, cassava, banana) plus a generic fallback.
- **Layer 2 (ML residual correction):** [`residual_gbr.py`](backend/app/ml/yield_model/residual_gbr.py) trains a `GradientBoostingRegressor` (300 estimators, depth 3, lr 0.05, subsample 0.8) on log-residuals `log(Y_obs / Y_kinetic)`. Prediction recombines as `Y = Y_kinetic × exp(ML(features))`, subject to the Buswell ceiling. This architecture ensures the ML layer can never produce a physically impossible yield.
- **Domain guardrail:** The `DomainGuard` class in [`domain_guard.py`](backend/app/ml/yield_model/domain_guard.py) records training feature bounds and flags out-of-distribution inference requests, providing the same extrapolation-transparency guarantee as the core engine's input-range checks.

### Google Places & OpenRouteService Buyer Pipeline

Bob designed the buyer-matching pipeline in [`app/data/buyers.py`](backend/app/data/buyers.py):

- Product-to-query mappings cover four product types (electricity, fuel, compost, CBG), each with multiple Places text-query strings.
- Deduplication by `place_id` across multiple concurrent queries prevents duplicate candidates.
- Road-distance enrichment via OpenRouteService distance matrix with haversine great-circle fallback when ORS is unavailable or returns `null` for unroutable pairs.
- The `PlacesClientError` / `RoutingClientError` distinction allows partial degradation: buyers can still be returned at straight-line distances even when the routing API is unreachable.

### Geospatial Data Clients

Bob designed the data-client layer in [`app/data/clients/`](backend/app/data/clients/):

- **`overpass.py`** — OSM Overpass QL client for recycling facility discovery.
- **`open_meteo.py`** — Open-Meteo API client for real-time weather data (ambient temperature, precipitation) fed into pathway models.
- **`osrm.py`** — OSRM routing client for distance matrices.
- **`firms.py`** — NASA FIRMS client for agricultural burn-event density, used in feedstock risk scoring.

All clients follow the same error-handling contract: typed `*ClientError` exceptions surface as HTTP 503 responses, never as unhandled 500 crashes.

---

## Pillar 4: Frontend & 3D Visualisation

### Next.js Application Architecture

Bob designed the Next.js application structure with two parallel route groups: `(app)` for the decision-intelligence platform (dashboard, simulator, compare, market, optimize, impact, validation, explorer, assistant) and `(pwa)` for citizen and farm progressive web app entry points. This dual-surface architecture was designed so the same API client could serve both user classes without route conflicts.

Bob authored the typed API client in [`src/lib/api/client.ts`](frontend/src/lib/api/client.ts) with a `BASE` URL resolved from `NEXT_PUBLIC_API_URL` or falling back to a Next.js `/api` rewrite proxy, keeping environment configuration identical between development and production. The error path extracts the backend's `detail` string from FastAPI validation errors, so frontend toast messages show the scientific reason for a rejection rather than a generic HTTP status code.

### React Three Fiber 3D Process Visualiser

Bob designed the 3D equipment visualisation system in [`src/app/(app)/simulator/equipment-3d.tsx`](frontend/src/app/(app)/simulator/equipment-3d.tsx). This is a 1,320-line React Three Fiber module implementing procedural 3D equipment models for all seven treatment pathways:

| Component | Pathway |
|---|---|
| `DigesterModel`, `GasTreatmentModel`, `CHPGeneratorModel`, `DigestateOutputModel` | Anaerobic Digestion |
| `PyrolysisReactorModel`, `CondenserCoilModel`, `FurnaceFireModel` | Pyrolysis |
| `GasifierModel`, `CycloneSeparatorModel`, `DryerModel` | Gasification |
| `AerationWindrowModel` | Composting |
| `WasteReceivingModel`, `MixingTankModel`, `SortingModel` | Shared pre-processing |

Bob designed the `StageCanvas3D` component as a composable wrapper that embeds a Three.js `Canvas` with `OrbitControls` and optional `autoRotate`, the `EquipmentModelSelector` that resolves equipment type to the correct 3D model, and the `PlantScene` that renders the full plant layout with `FacilityPlatform` and `ProcessPiping` connecting stages in sequence. All geometry is constructed from R3F primitives (boxes, cylinders, spheres, cones, tori) with PBR materials — no external 3D asset files are required.

### Internationalisation & Mobile PWA

Bob designed the i18n layer in [`src/i18n/`](frontend/src/i18n/) with translation files for English (`en.json`), Hindi (`hi.json`), and Kannada (`kn.json`), targeting the primary user populations of the platform's intended deployment region. The citizen and farm PWA routes in `(pwa)/` were designed with offline-first principles, enabling waste-reporting without persistent connectivity.

---

## Pillar 5: Test-Driven Development & CI

### 57/57 Pytest Suite

Bob authored the strict test-driven development methodology applied to the core engine from day one. The test suite across [`app/core_engine/tests/`](backend/app/core_engine/tests/) covers:

| Test module | What it validates |
|---|---|
| [`test_engine.py`](backend/app/core_engine/tests/test_engine.py) | Mass closure (`mass_residual ≈ 0`), moisture conditioning sign correctness, Buswell guardrail trigger, cold-climate boiler activation, energy balance closure |
| [`test_thermal.py`](backend/app/core_engine/tests/test_thermal.py) | Feed heating and wall loss formulae, CHP/boiler split, heat-deficit flag |
| [`test_montecarlo.py`](backend/app/core_engine/tests/test_montecarlo.py) | MC reproducibility (seed parity), distribution sampling, recentring, Spearman sensitivity ordering |
| [`test_guardrails.py`](backend/app/core_engine/tests/test_guardrails.py) | Buswell ceiling, VS-destruction threshold, input-range detection |
| [`test_pathways_ci.py`](backend/app/core_engine/tests/test_pathways_ci.py), `test_pathways_gp.py`, `test_pathways_ht.py` | Pathway simulation integration across composting, gasification, pyrolysis, HTC, torrefaction |
| [`test_mc_compare.py`](backend/app/core_engine/tests/test_mc_compare.py) | Cross-pathway Monte Carlo comparison and Pareto ranking |
| [`test_validation.py`](backend/app/core_engine/tests/test_validation.py), [`test_provenance.py`](backend/app/core_engine/tests/test_provenance.py) | Input validation contracts, provenance metadata propagation |
| [`test_engine_regression.py`](backend/app/core_engine/tests/test_engine_regression.py) | Golden-number lock: `e_net_kwh_d = 76.74057020848`, `biogas_nm3_d = 47.0448` to `1e-6` relative tolerance |

All tests run without network access; every external service (Google Places, ORS, Open-Meteo, Gemini) is mocked. Bob designed the mock strategy in [`conftest.py`](backend/conftest.py) and [`src/mocks/handlers.ts`](frontend/src/mocks/handlers.ts) using MSW on the frontend and `unittest.mock` patches on the backend.

### GitHub Actions CI Pipeline

Bob designed the `.github/workflows/ci.yml` pipeline that runs `python -m pytest backend -q` on every push, enforcing the golden-number regression test and full suite against Python 3.12. The pipeline uses no database and no external network, making it reproducible in any hosted runner.

---

## Pillar 6: Overcoming Deployment & Integration Blockers

### Git LFS & Ghost-Process Debugging

The HuggingFace `model.safetensors` file (~400 MB) required Git LFS configuration. Bob diagnosed the ghost-process issue that caused the local ML model loader in `vision_router.py` to silently fail when the LFS pointer file was checked out without the actual binary, writing the try/except guard that sets `local_classifier = None` and returns HTTP 500 with a clear message, preventing the entire application from failing to start when the model is absent.

### Import-Order & Circular Dependency Resolution

The FastAPI application imports fourteen routers at module level, several of which import shared components from `app.core_engine`, `app.config`, and `app.schemas`. Bob designed the import ordering and the lazy-import pattern in `core_engine/router.py` (importing `Params` inside the endpoint function body) that eliminated the circular-import failures that manifested as silent `None` router registrations, verified by [`test_import_order.py`](backend/app/core_engine/tests/test_import_order.py).

### Decision Engine Integration

Bob integrated the LP optimiser (`scipy.optimize.linprog` via `ScipyBackend`), Pareto filter, cost engine (CRF + annualised CAPEX/OPEX), carbon calculator (GHG delta accounting with `BoundaryMismatchError`), and marketplace matcher into a single `/decision` router in [`app/decision/router.py`](backend/app/decision/router.py). The router returns HTTP 422 for infeasible LP problems and `BoundaryMismatchError` in carbon accounting — both scientifically meaningful rejections — while reserving HTTP 500 strictly for unexpected server failures.

### Pydantic v2 Migration

Several team members wrote Pydantic v1-style validators. Bob migrated all models to Pydantic v2 `@model_validator(mode="after")` and `@field_validator` patterns throughout the codebase, eliminating the deprecation warnings that caused test noise and would have broken deployment on Pydantic v2-only environments.

---

## Summary

IBM Bob served as the architectural authority, scientific implementation engine, and quality-assurance layer for every vertical of the Waste-Potential platform. The contributions documented here enabled a five-person team to build, test, and integrate a production-grade system spanning chemical engineering simulation, Monte Carlo uncertainty quantification, computer vision, geospatial buyer discovery, hybrid ML pipelines, and a full-stack React/Three.js frontend — within a single hackathon sprint.

All code contributions are traceable to specific files and functions in this repository.
