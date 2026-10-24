"""recyclables_service.py — Price loader for GET /recyclables/prices.

Loads recyclable_prices.csv from backend/data/ and validates each row:
  - Rejects rows with non-numeric prices, low > high, missing source or as_of.
  - Flags rows older than 90 days as stale.
  - Reports skipped-row count in the response.

This module is intentionally import-time-safe: it only loads data when
``load_prices()`` is called (not on module import).
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Path is resolved relative to this file:
# backend/app/recyclables/recyclables_service.py → parents[2] = backend/
_CSV_PATH = Path(__file__).resolve().parents[2] / "data" / "recyclable_prices.csv"

_STALE_DAYS = 90

_EMPTY_NOTE = (
    "No price data loaded. "
    "Add rows with a source and date to recyclable_prices.csv."
)
_INDICATIVE_NOTE = (
    "Prices are indicative and not live market rates. "
    "Verify with a current source before trading."
)


@dataclass(frozen=True)
class PriceRow:
    material: str
    sub_type: str
    price_inr_per_kg_low: float
    price_inr_per_kg_high: float
    as_of: str        # ISO date string "YYYY-MM-DD"
    source: str
    region: str
    stale: bool


@dataclass(frozen=True)
class PriceLoadResult:
    rows: list[PriceRow]
    rows_skipped: int
    note: str


def load_prices(material: str, csv_path: Optional[Path] = None) -> PriceLoadResult:
    """Load and validate price rows for *material* from *csv_path*.

    Returns a :class:`PriceLoadResult` with matching, validated rows sorted by
    ``price_inr_per_kg_high`` descending (comparison view).  Invalid rows are
    counted in ``rows_skipped``; the caller never sees them.
    """
    csv_path = Path(csv_path) if csv_path is not None else _CSV_PATH
    today = date.today()
    stale_cutoff = today - timedelta(days=_STALE_DAYS)

    rows: list[PriceRow] = []
    skipped = 0

    try:
        with csv_path.open(newline="", encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            for raw in reader:
                row_material = (raw.get("material") or "").strip().lower()
                if row_material != material.lower():
                    continue  # not our material; skip silently

                sub_type = (raw.get("sub_type") or "").strip()
                source = (raw.get("source") or "").strip()
                as_of_str = (raw.get("as_of") or "").strip()
                region = (raw.get("region") or "").strip()

                # Validate required text fields
                if not source or not as_of_str:
                    logger.debug("Skipping row with missing source or as_of: %r", raw)
                    skipped += 1
                    continue

                # Validate numeric prices
                try:
                    low = float(raw["price_inr_per_kg_low"])
                    high = float(raw["price_inr_per_kg_high"])
                except (KeyError, ValueError, TypeError):
                    logger.debug("Skipping row with non-numeric price: %r", raw)
                    skipped += 1
                    continue

                if low > high:
                    logger.debug("Skipping row where low > high: %r", raw)
                    skipped += 1
                    continue

                # Validate date
                try:
                    as_of_date = date.fromisoformat(as_of_str)
                except ValueError:
                    logger.debug("Skipping row with invalid as_of date: %r", raw)
                    skipped += 1
                    continue

                stale = as_of_date < stale_cutoff

                rows.append(PriceRow(
                    material=row_material,
                    sub_type=sub_type,
                    price_inr_per_kg_low=low,
                    price_inr_per_kg_high=high,
                    as_of=as_of_str,
                    source=source,
                    region=region,
                    stale=stale,
                ))

    except FileNotFoundError:
        logger.warning("recyclable_prices.csv not found at %s", csv_path)
        return PriceLoadResult(rows=[], rows_skipped=0, note=_EMPTY_NOTE)
    except Exception as exc:
        logger.error("Failed to load recyclable_prices.csv: %s", exc)
        return PriceLoadResult(rows=[], rows_skipped=0, note=_EMPTY_NOTE)

    # Sort by price_inr_per_kg_high descending (comparison view)
    rows.sort(key=lambda r: r.price_inr_per_kg_high, reverse=True)

    note = _EMPTY_NOTE if not rows else _INDICATIVE_NOTE
    return PriceLoadResult(rows=rows, rows_skipped=skipped, note=note)
