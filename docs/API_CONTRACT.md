# API Contract

> **Generated from `docs/openapi.snapshot.json`.**  
> To regenerate: `python backend/scripts/dump_openapi.py && python backend/scripts/make_contract.py`

---

## Conventions

- **Unit-suffixed field names** — every numeric field whose name contains a unit
  suffix (`_kg`, `_kwh`, `_d`, `_y`, `_km`, `_inr`, `_nm3`, `_ha`) is
  expressed in that unit. No implicit conversions.
- **Run status values** — `illustrative_estimate` | `extrapolation`.  
  `illustrative_estimate` means the inputs are within the training / reference
  domain; `extrapolation` means at least one input lies outside it.
- **Pathway feasibility** — `feasible` | `rejected` | `uncertain`.  
  `rejected` means at least one hard physical or distance constraint was
  violated; `uncertain` means feasibility could not be determined from the
  available data.
- **Data kinds** — `measured` | `reported` | `estimated` | `simulated`.  
  Fields whose provenance is not specified are `simulated` unless stated
  otherwise.
- **Null semantics** — `null` means "not specified"; it never encodes zero. Use
  `0` explicitly when the value is known to be zero.
- **Energy basis** — thermal and electrical energy are distinct. Fields named
  `_kwh` are electrical; fields named `_mj_th` or `_kwh_th` are thermal unless
  annotated otherwise.
- **Places disclaimer** — results from `/buyers`, `/recyclables/buyers` and
  `/facilities` come from the Google Places API and are **unverified
  candidates**. They have not been field-verified and may be incomplete or
  inaccurate.

---

*App: **Waste-Potential API** — version 0.1.0*

---

## Routes

### `POST /api/v1/assistant/advise`

**Tag:** AI Assistant  
**Summary:** Advise

Explain a question using context supplied by the caller.

**Request body** (application/json)

| Field    | Type   | Required | Description |
| -------- | ------ | -------- | ----------- |
| context  | object | no       |             |
| question | string | yes      |             |

**Responses**

- `200` Successful Response

- `422` Validation Error

---

### `POST /api/v1/assistant/audit`

**Tag:** AI Assistant  
**Summary:** Audit

Generate a narrative grounded in supplied results and limitations.

**Request body** (application/json)

| Field       | Type          | Required | Description |
| ----------- | ------------- | -------- | ----------- |
| assumptions | array[string] | no       |             |
| limitations | array[string] | no       |             |
| results     | object        | yes      |             |

**Responses**

- `200` Successful Response

- `422` Validation Error

---

### `POST /api/v1/assistant/parse`

**Tag:** AI Assistant  
**Summary:** Parse Waste

Extract structured waste information from a free-form description.

**Request body** (application/json)

| Field       | Type   | Required | Description |
| ----------- | ------ | -------- | ----------- |
| description | string | yes      |             |

**Responses**

- `200` Successful Response

- `422` Validation Error

---

### `GET /buyers`

**Tag:** Buyers  
**Summary:** Search for nearby buyers of a waste-derived product

Return candidate buyers for a product near the supplied coordinates.

**Query / path parameters**

| Name      | In    | Type   | Required | Description                                               |
| --------- | ----- | ------ | -------- | --------------------------------------------------------- |
| lat       | query | number | yes      | Decimal latitude of the waste source.                     |
| lng       | query | number | yes      | Decimal longitude of the waste source.                    |
| product   | query | string | yes      | Product to sell: electricity, fuel, compost, or cbg.      |
| radius_km | query | number | no       | Search radius in km (1–200). Default 50. (default: 50.0). |

**Responses**

- `200` Successful Response (array)

| Field          | Type   | Required | Description                                                       |
| -------------- | ------ | -------- | ----------------------------------------------------------------- |
| data_quality   | string | yes      | Data quality note.                                                |
| distance_basis | string | yes      | 'road' when computed by ORS, 'straight_line' on routing fallback. |
| distance_km    | number | yes      | Distance from the query origin in km.                             |
| lat            | number | yes      | Decimal latitude of the buyer.                                    |
| lng            | number | yes      | Decimal longitude of the buyer.                                   |
| name           | string | yes      | Display name of the buyer.                                        |
| place_id       | string | yes      | Unique Google Place ID.                                           |
| product        | string | yes      | Product type queried.                                             |

- `422` Invalid product or out-of-range radius_km.

- `503` Google Places or ORS is unreachable or denied.

---

### `POST /decision/carbon/package`

**Tag:** Decision Engine  
**Summary:** Carbon Package

Compute itemized GHG delta for a proposed vs. baseline waste scenario.

**Request body** (application/json)

| Field                 | Type                    | Required | Description                                                |
| --------------------- | ----------------------- | -------- | ---------------------------------------------------------- |
| allocation            | object[string → number] | yes      | Flat dict: key = 'stream_id|tech_id', value = tonnes/year. |
| gwp_period            | string                  | no       |                                                            |
| include_transport     | boolean                 | no       |                                                            |
| operator_overrides    | object[string → number] | no       |                                                            |
| proposed_technologies | array[ProposedTechIn]   | yes      |                                                            |
| region                | string (optional)       | no       |                                                            |
| waste_streams         | array[WasteStreamIn]    | yes      |                                                            |

**Responses**

- `200` Successful Response

| Field          | Type                    | Required | Description |
| -------------- | ----------------------- | -------- | ----------- |
| baseline_total | number                  | yes      |             |
| breakdown      | object[string → number] | yes      |             |
| proposed_total | number                  | yes      |             |
| total_delta    | number                  | yes      |             |

- `422` Validation Error

---

### `POST /decision/costs`

**Tag:** Decision Engine  
**Summary:** Compute Costs

Compute CRF-based annualised cost coefficients for a list of technologies.

**Request body** (application/json)

_See schema_

**Responses**

- `200` Successful Response

| Field        | Type                  | Required | Description |
| ------------ | --------------------- | -------- | ----------- |
| coefficients | array[LPCostCoeffOut] | yes      |             |

- `422` Validation Error

---

### `POST /decision/marketplace/match`

**Tag:** Decision Engine  
**Summary:** Marketplace Match

Match a facility's product output to eligible buyers.

**Request body** (application/json)

| Field    | Type                  | Required | Description |
| -------- | --------------------- | -------- | ----------- |
| buyers   | array[BuyerProfileIn] | yes      |             |
| facility | FacilityOutputIn      | yes      |             |

**Responses**

- `200` Successful Response

| Field             | Type                    | Required | Description |
| ----------------- | ----------------------- | -------- | ----------- |
| facility_id       | string                  | yes      |             |
| filter_reasons    | object[string → string] | yes      |             |
| matches           | array[BuyerMatchOut]    | yes      |             |
| n_eligible_buyers | integer                 | yes      |             |
| n_filtered_buyers | integer                 | yes      |             |
| remaining_volume  | number                  | yes      |             |
| total_allocated   | number                  | yes      |             |
| total_available   | number                  | yes      |             |

- `422` Validation Error

---

### `POST /decision/optimize`

**Tag:** Decision Engine  
**Summary:** Optimize

Run the LP allocation optimizer, then apply the Pareto filter.

**Request body** (application/json)

| Field                  | Type                                      | Required | Description                                                                                                            |
| ---------------------- | ----------------------------------------- | -------- | ---------------------------------------------------------------------------------------------------------------------- |
| capacity               | object[string → number]                   | yes      | tech_id (str) → treatment capacity tonnes/year                                                                         |
| compatibility_matrix   | object[string → integer]                  | yes      | JSON-safe flat dict: key = 'stream_id|tech_id' (e.g. 'stream_1|tech_A'), value = 1 (compatible) or 0 (incompatible).   |
| objective_coefficients | object[string → number]                   | yes      | Flat dict: key = 'stream_id|tech_id', value = pre-computed per-tonne LP objective coefficient.                         |
| pareto_weight_sweep    | array[object[string → number]] (optional) | no       | Optional list of weight dicts for a Pareto sweep. Each dict must contain w_cost, w_carbon, w_transport summing to 1.0. |
| supply                 | object[string → number]                   | yes      | stream_id (str) → available supply tonnes/year                                                                         |
| w_carbon               | number                                    | no       |                                                                                                                        |
| w_cost                 | number                                    | no       |                                                                                                                        |
| w_transport            | number                                    | no       |                                                                                                                        |

**Responses**

- `200` Successful Response

| Field           | Type                                 | Required | Description |
| --------------- | ------------------------------------ | -------- | ----------- |
| allocation      | object[string → number]              | yes      |             |
| is_feasible     | boolean                              | yes      |             |
| n_pareto        | integer (optional)                   | no       |             |
| objective_value | number (optional)                    | yes      |             |
| pareto_front    | array[ParetoCandidateOut] (optional) | no       |             |
| solver_status   | string                               | yes      |             |

- `422` Validation Error

---

### `GET /facilities`

**Tag:** External Data  
**Summary:** Search for nearby waste facilities via Google Places

Return nearby waste treatment and recycling facilities from Google Places.

**Query / path parameters**

| Name     | In    | Type    | Required | Description                                                                   |
| -------- | ----- | ------- | -------- | ----------------------------------------------------------------------------- |
| lat      | query | number  | yes      | Decimal latitude of the site.                                                 |
| lon      | query | number  | yes      | Decimal longitude of the site.                                                |
| radius_m | query | integer | no       | Search radius in metres (1–50 000). Default 50 000 (50 km). (default: 50000). |

**Responses**

- `200` Successful Response (array)

| Field     | Type          | Required | Description                    |
| --------- | ------------- | -------- | ------------------------------ |
| latitude  | number        | yes      | Decimal latitude.              |
| longitude | number        | yes      | Decimal longitude.             |
| name      | string        | yes      | Display name of the facility.  |
| place_id  | string        | yes      | Unique Google Place ID.        |
| types     | array[string] | no       | Google place type labels.      |
| vicinity  | string        | yes      | Short address / neighbourhood. |

- `422` Validation Error

- `503` Google Places is unreachable, the API key is missing / invalid, or the request was otherwise denied.

---

### `GET /geocode`

**Tag:** Geocoding  
**Summary:** Geocode a postal code to lat/lng

Convert a postal code to approximate lat/lng coordinates via Nominatim.

**Query / path parameters**

| Name    | In    | Type   | Required | Description                                      |
| ------- | ----- | ------ | -------- | ------------------------------------------------ |
| pincode | query | string | yes      | Postal / PIN code to geocode.                    |
| country | query | string | no       | Country name (default: India). (default: India). |

**Responses**

- `200` Successful Response

| Field        | Type    | Required | Description                                             |
| ------------ | ------- | -------- | ------------------------------------------------------- |
| cached       | boolean | yes      | True if the result was served from the in-memory cache. |
| display_name | string  | yes      | Human-readable location name from Nominatim.            |
| lat          | number  | yes      | Decimal latitude.                                       |
| lng          | number  | yes      | Decimal longitude.                                      |
| precision    | string  | no       | Precision statement for the returned coordinates.       |
| source       | string  | no       | Data source and licence.                                |

- `404` No result found for the given pincode and country.

- `422` Pincode fails country-specific validation rules.

- `503` Nominatim is unreachable, timed out, or returned an error.

---

### `GET /health`

**Tag:** Platform  
**Summary:** Health

**Responses**

- `200` Successful Response

| Field       | Type   | Required | Description |
| ----------- | ------ | -------- | ----------- |
| environment | string | yes      |             |
| status      | string | yes      |             |

---

### `GET /parameters`

**Summary:** List parameter registry entries

Returns rows from docs/parameter_registry.csv. Pass `?status=illustrative_estimate` (or any status string) to filter.

**Query / path parameters**

| Name   | In    | Type              | Required | Description |
| ------ | ----- | ----------------- | -------- | ----------- |
| status | query | string (optional) | no       |             |

**Responses**

- `200` Successful Response (array)

| Field         | Type   | Required | Description |
| ------------- | ------ | -------- | ----------- |
| description   | string | yes      |             |
| mass_basis    | string | yes      |             |
| model_version | string | yes      |             |
| name          | string | yes      |             |
| source        | string | yes      |             |
| status        | string | yes      |             |
| uncertainty   | string | yes      |             |
| unit          | string | yes      |             |
| value         | string | yes      |             |

- `422` Validation Error

---

### `GET /pathways/catalog/{process_id}`

**Tag:** Pathways Screening  
**Summary:** Retrieve a scaled process catalog entry

Returns the catalog entry for *process_id* from ``docs/process_catalog_extra.json``, with numeric ``inputs`` values scaled by ``waste_kg / 1000.0``. Raises 404 if the process is not in the catalog.

**Query / path parameters**

| Name       | In    | Type   | Required | Description                                                         |
| ---------- | ----- | ------ | -------- | ------------------------------------------------------------------- |
| process_id | path  | string | yes      |                                                                     |
| waste_kg   | query | number | no       | Waste mass in kg (default 1000 kg = no scaling). (default: 1000.0). |

**Responses**

- `200` Successful Response

- `422` Validation Error

---

### `POST /pathways/compare`

**Tag:** Pathways Screening  
**Summary:** Screen and compare waste treatment pathways

Runs a coarse feasibility screening pass followed by a Monte Carlo uncertainty analysis for each requested pathway. Returns one PathwayResult per pathway. Rejected pathways have feasible=False with po

**Request body** (application/json)

| Field                     | Type                     | Required | Description                                                                                                                                            |
| ------------------------- | ------------------------ | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| area_ha                   | number (optional)        | no       | Cultivated area in hectares. Required when crop_type is set.                                                                                           |
| asset_life_yr             | object[string → integer] | no       | Asset life in years per pathway (default: 20).                                                                                                         |
| capacity_tpd              | object[string → number]  | no       | Maximum treatment capacity in tonnes/day per pathway.                                                                                                  |
| capex_inr                 | object[string → number]  | no       | Total capital expenditure in INR per pathway.                                                                                                          |
| crop_type                 | string (optional)        | no       | Crop type for ML-based yield prediction via YieldPredictor. When provided together with area_ha, overrides waste_tpd with the predicted daily biomass. |
| direct_ghg_kg_per_tonne   | object[string → number]  | no       | Direct GHG emissions in kgCO2e per tonne processed.                                                                                                    |
| discount_rate             | number                   | no       | Shared discount rate for CAPEX annualisation (default 7 %).                                                                                            |
| distance_km               | number                   | no       | One-way road distance from the waste source to the facility (km).                                                                                      |
| electricity_price_inr_kwh | number                   | no       | INR per kWh for electricity export (revenue) or import (cost).                                                                                         |
| farm_id                   | string                   | yes      | Unique identifier of the source farm / waste stream.                                                                                                   |
| gate_fee_inr_t            | object[string → number]  | no       | Tipping / gate fee received per tonne of waste (INR/tonne).                                                                                            |
| location_id               | string                   | no       | Site identifier used to look up feedstock and location context from the P3 data service layer.                                                         |
| max_distance_km           | number                   | no       | Hard upper-limit: pathways whose nearest facility exceeds this distance are rejected as infeasible (default 200 km).                                   |
| mc_cost_cv                | number                   | no       | Coefficient of variation applied to annualised cost in MC runs.                                                                                        |
| mc_runs                   | integer                  | no       | Number of Monte Carlo iterations for uncertainty quantification.                                                                                       |
| mc_seed                   | integer                  | no       | Random seed for reproducible Monte Carlo draws (default 42).                                                                                           |
| mc_yield_cv               | number                   | no       | Coefficient of variation applied to electricity yield in MC runs.                                                                                      |
| net_kwh_per_tonne         | object[string → number]  | no       | Net kWh exported per tonne of waste processed (per pathway).                                                                                           |
| operator_overrides        | object[string → number]  | no       | Operator-supplied emission factor overrides (factor_key → kgCO2e/unit).                                                                                |
| opex_inr_yr               | object[string → number]  | no       | Annual operating expenditure in INR per pathway.                                                                                                       |
| pathways                  | array[string]            | yes      | Ordered list of pathway IDs to evaluate.                                                                                                               |
| region                    | string (optional)        | no       | ISO 3166-1 alpha-2 region code for regional grid emission factors.                                                                                     |
| soil_index                | number (optional)        | no       | Soil quality index in [0, 1]. Used by YieldPredictor when crop_type and area_ha are provided (default 0.75 if omitted).                                |
| waste_tpd                 | number                   | yes      | Available waste feedstock in tonnes per day.                                                                                                           |

**Responses**

- `200` Successful Response (array)

| Field                | Type                    | Required | Description                                                                                                           |
| -------------------- | ----------------------- | -------- | --------------------------------------------------------------------------------------------------------------------- |
| annual_net_value_inr | number                  | no       | Net annual value: revenue_inr_y − cost_inr_y.                                                                         |
| cost_inr_y           | number                  | no       | Estimated annual cost in INR (annualised CAPEX + OPEX).                                                               |
| e_net_kwh_d          | number                  | no       | Net kWh/day exported (negative = net electricity consumer).                                                           |
| feasible             | boolean                 | yes      | True iff the pathway passed all coarse checks.                                                                        |
| model_status         | string (optional)       | no       | Optional status tag from the ML model or simulation engine, e.g. 'converged', 'fallback', 'extrapolated'.             |
| optimality_note      | string (optional)       | no       | Explanatory note about the optimality share.                                                                          |
| optimality_share     | number (optional)       | no       | Fraction of MC runs in which this pathway had the highest annual net value among deterministically feasible pathways. |
| outputs              | object[string → number] | no       | Key technical outputs, e.g. {'biogas_m3_d': 420.0, 'compost_t_d': 2.1}.                                               |
| pathway              | string                  | yes      | Pathway identifier (mirrors request).                                                                                 |
| reasons              | array[string]           | no       | Rejection reasons (populated when feasible=False).                                                                    |
| revenue_inr_y        | number                  | no       | Estimated annual revenue in INR.                                                                                      |
| status               | string                  | yes      | One of: 'feasible', 'rejected', 'uncertain'.                                                                          |
| warnings             | array[string]           | no       | Non-fatal caveats, e.g. parameter assumptions or data gaps.                                                           |
| win_count            | integer (optional)      | no       | Number of MC runs in which this pathway was the winner.                                                               |

- `422` Validation Error

---

### `POST /pathways/explain`

**Tag:** Pathways Screening  
**Summary:** Explain why a pathway ranks where it does

Return a short narrative explaining the ranking of a single pathway.

**Request body** (application/json)

| Field   | Type                   | Required | Description                              |
| ------- | ---------------------- | -------- | ---------------------------------------- |
| pathway | string                 | yes      | Pathway identifier to explain.           |
| results | array[PathwayRowInput] | yes      | List returned by POST /pathways/compare. |

**Responses**

- `200` Successful Response

| Field               | Type          | Required | Description |
| ------------------- | ------------- | -------- | ----------- |
| disclaimer          | string        | yes      |             |
| facts               | object        | yes      |             |
| grounded            | boolean       | yes      |             |
| source              | string        | yes      |             |
| text                | string        | yes      |             |
| unsupported_numbers | array[number] | yes      |             |

- `422` Pathway not found in the supplied results list.

---

### `GET /recyclables/buyers`

**Tag:** Recyclables  
**Summary:** Find nearby recyclers for a material

Return nearby recyclers for the given material, sorted by distance.

**Query / path parameters**

| Name      | In    | Type   | Required | Description                                               |
| --------- | ----- | ------ | -------- | --------------------------------------------------------- |
| lat       | query | number | yes      | Decimal latitude of the waste source.                     |
| lng       | query | number | yes      | Decimal longitude of the waste source.                    |
| material  | query | string | yes      | Material type: plastic, glass, metal, or e_waste.         |
| radius_km | query | number | no       | Search radius in km (1–200). Default 50. (default: 50.0). |

**Responses**

- `200` Successful Response (array)

| Field          | Type   | Required | Description |
| -------------- | ------ | -------- | ----------- |
| distance_basis | string | yes      |             |
| distance_km    | number | yes      |             |
| lat            | number | yes      |             |
| lng            | number | yes      |             |
| material       | string | yes      |             |
| name           | string | yes      |             |
| place_id       | string | yes      |             |

- `422` Unknown material.

- `503` Google Places or ORS unreachable.

---

### `GET /recyclables/prices`

**Tag:** Recyclables  
**Summary:** Get indicative scrap prices for a material

Return indicative price ranges for the given material from the local CSV.

**Query / path parameters**

| Name     | In    | Type   | Required | Description                                       |
| -------- | ----- | ------ | -------- | ------------------------------------------------- |
| material | query | string | yes      | Material type: plastic, glass, metal, or e_waste. |

**Responses**

- `200` Successful Response

| Field        | Type                    | Required | Description |
| ------------ | ----------------------- | -------- | ----------- |
| note         | string                  | yes      |             |
| prices       | array[PriceRowResponse] | yes      |             |
| rows_skipped | integer                 | yes      |             |

- `422` Unknown material.

---

### `GET /runs`

**Tag:** Platform  
**Summary:** List stored runs

**Query / path parameters**

| Name  | In    | Type    | Required | Description                            |
| ----- | ----- | ------- | -------- | -------------------------------------- |
| limit | query | integer | no       | Maximum runs to return. (default: 20). |

**Responses**

- `200` Successful Response (array)

| Field                     | Type                    | Required | Description |
| ------------------------- | ----------------------- | -------- | ----------- |
| audit_hash                | string                  | yes      |             |
| defaults_used_unvalidated | array[string]           | yes      |             |
| id                        | string                  | yes      |             |
| inputs                    | object                  | yes      |             |
| missing_inputs            | array[string]           | no       |             |
| model_version             | string                  | yes      |             |
| notes                     | object                  | no       |             |
| params                    | object                  | yes      |             |
| results                   | SimResults              | yes      |             |
| status                    | string                  | yes      |             |
| warnings_detail           | array[RuleWarningModel] | no       |             |

- `422` Validation Error

---

### `GET /runs/{run_id}`

**Tag:** Platform  
**Summary:** Get a stored run

**Query / path parameters**

| Name   | In   | Type   | Required | Description |
| ------ | ---- | ------ | -------- | ----------- |
| run_id | path | string | yes      |             |

**Responses**

- `200` Successful Response

| Field                     | Type                    | Required | Description |
| ------------------------- | ----------------------- | -------- | ----------- |
| audit_hash                | string                  | yes      |             |
| defaults_used_unvalidated | array[string]           | yes      |             |
| id                        | string                  | yes      |             |
| inputs                    | object                  | yes      |             |
| missing_inputs            | array[string]           | no       |             |
| model_version             | string                  | yes      |             |
| notes                     | object                  | no       |             |
| params                    | object                  | yes      |             |
| results                   | SimResults              | yes      |             |
| status                    | string                  | yes      |             |
| warnings_detail           | array[RuleWarningModel] | no       |             |

- `404` Run not found.

- `422` Validation Error

---

### `POST /simulations`

**Tag:** Platform  
**Summary:** Run a simulation

Identical requests return the same stored run (same id and audit_hash).

**Request body** (application/json)

| Field             | Type                               | Required | Description |
| ----------------- | ---------------------------------- | -------- | ----------- |
| location_id       | string (optional)                  | no       |             |
| operating         | object[string → number] (optional) | no       |             |
| organic_fraction  | number (optional)                  | no       |             |
| overrides         | object[string → number]            | no       |             |
| process           | string                             | no       |             |
| suitable_fraction | number (optional)                  | no       |             |
| use_ml_yield      | boolean                            | no       |             |
| waste_mass_kg_day | number (optional)                  | no       |             |

**Responses**

- `200` Successful Response

| Field                     | Type                    | Required | Description |
| ------------------------- | ----------------------- | -------- | ----------- |
| audit_hash                | string                  | yes      |             |
| defaults_used_unvalidated | array[string]           | yes      |             |
| id                        | string                  | yes      |             |
| inputs                    | object                  | yes      |             |
| missing_inputs            | array[string]           | no       |             |
| model_version             | string                  | yes      |             |
| notes                     | object                  | no       |             |
| params                    | object                  | yes      |             |
| results                   | SimResults              | yes      |             |
| status                    | string                  | yes      |             |
| warnings_detail           | array[RuleWarningModel] | no       |             |

- `422` Request validation failed (detail is a list), or the inputs cannot be simulated (detail is a string): missing waste mass, invalid or non-finite parameters, unsupported process, or use_ml_yield=true (ML yield not yet supported).

---

### `POST /simulations/{run_id}/uncertainty`

**Summary:** Monte Carlo uncertainty for a stored run

Loads the stored run, rebuilds Params from run['params'], calls run_mc(params, n=..., seed=...) and returns the result. Returns 404 for an unknown run_id.

**Query / path parameters**

| Name   | In   | Type   | Required | Description |
| ------ | ---- | ------ | -------- | ----------- |
| run_id | path | string | yes      |             |

**Request body** (application/json)

| Field                  | Type              | Required | Description |
| ---------------------- | ----------------- | -------- | ----------- |
| distribution_overrides | object (optional) | no       |             |
| n                      | integer           | no       |             |
| seed                   | integer           | no       |             |

**Responses**

- `200` Successful Response

| Field              | Type                    | Required | Description |
| ------------------ | ----------------------- | -------- | ----------- |
| assumptions_note   | string                  | yes      |             |
| centred_on         | object                  | no       |             |
| clipped_samples    | integer                 | no       |             |
| distributions      | object                  | yes      |             |
| fixed_inputs       | array[string]           | no       |             |
| median             | number                  | yes      |             |
| n                  | integer                 | yes      |             |
| p2_5               | number                  | yes      |             |
| p97_5              | number                  | yes      |             |
| p_net_nonpositive  | number                  | yes      |             |
| recentred          | boolean                 | no       |             |
| runs_with_warnings | integer                 | yes      |             |
| seed               | integer                 | yes      |             |
| sensitivity        | array[_SensitivityItem] | yes      |             |

- `422` Validation Error

---

### `GET /validation/summary`

**Summary:** Parameter validation summary

Returns parameter counts by status, number of unvalidated defaults, the fixed limitations list, and an empirical-validation placeholder.

**Responses**

- `200` Successful Response

---

### `POST /vision/advice`

**Tag:** Vision  
**Summary:** Get disposal advice for classified waste items

Return short, contextual waste-disposal guidance for the given sector.

**Request body** (application/json)

| Field  | Type          | Required | Description |
| ------ | ------------- | -------- | ----------- |
| items  | array[string] | yes      |             |
| sector | string        | yes      |             |

**Responses**

- `200` Successful Response

| Field | Type   | Required | Description |
| ----- | ------ | -------- | ----------- |
| text  | string | yes      |             |

- `422` Unknown sector.

- `503` Gemini key missing or API failure.

---

### `POST /vision/classify`

**Tag:** Vision  
**Summary:** Classify waste from a photo

Classify waste items in the uploaded image using Gemini vision.

**Request body** (multipart/form-data)

| Field | Type   | Required | Description                        |
| ----- | ------ | -------- | ---------------------------------- |
| file  | string | yes      | JPEG, PNG or WebP image, max 5 MB. |

**Responses**

- `200` Successful Response

| Field      | Type             | Required | Description |
| ---------- | ---------------- | -------- | ----------- |
| disclaimer | string           | yes      |             |
| items      | array[WasteItem] | yes      |             |
| model      | string           | yes      |             |
| stream     | string           | yes      |             |
| timestamp  | string           | yes      |             |

- `422` File too large, wrong MIME type, or bad upload.

- `502` Gemini returned malformed JSON.

- `503` Gemini key missing or API failure.

---

### `GET /weather`

**Tag:** External Data  
**Summary:** Get current ambient weather for a location

Return the latest hourly ambient temperature and relative humidity

**Query / path parameters**

| Name | In    | Type   | Required | Description                      |
| ---- | ----- | ------ | -------- | -------------------------------- |
| lat  | query | number | yes      | Decimal latitude (−90 to 90).    |
| lon  | query | number | yes      | Decimal longitude (−180 to 180). |

**Responses**

- `200` Successful Response

| Field             | Type   | Required | Description                             |
| ----------------- | ------ | -------- | --------------------------------------- |
| ambient_temp_c    | number | yes      | Air temperature at 2 m (°C).            |
| latitude          | number | yes      | Latitude echoed from Open-Meteo.        |
| longitude         | number | yes      | Longitude echoed from Open-Meteo.       |
| relative_humidity | number | yes      | Relative humidity as a fraction [0, 1]. |

- `422` Validation Error

- `503` Open-Meteo is unreachable or returned an error.

---

