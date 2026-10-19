# backend/data/

This directory holds static reference data loaded at startup.

## recyclable_prices.csv

Columns: `material`, `sub_type`, `price_inr_per_kg_low`, `price_inr_per_kg_high`,
`as_of` (YYYY-MM-DD), `source` (URL or publication name), `region` (e.g. "India").

**To add rows**: obtain prices from a published scrap-dealer rate card or government
gazette, record the exact URL/publication and date, then append one row per sub-type.
Do NOT add rows with invented prices or without a real source and date.

Example:
```
plastic,PET bottles,8.5,12.0,2025-01-10,https://example-scrap.com/rates,India
metal,Mild steel scrap,25.0,30.0,2025-01-10,https://example-scrap.com/rates,India
```
