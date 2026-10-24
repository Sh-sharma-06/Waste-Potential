"""Source-backed market catalogue endpoint."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

router = APIRouter(prefix="/market", tags=["Market"])
_CATALOG_PATH = Path(__file__).resolve().parents[2] / "data" / "market_catalog.json"
_VALID_CATEGORIES = {
    "cbg", "electricity", "compost", "plastic", "glass", "metal", "e_waste"
}


def _load_catalog() -> list[dict[str, Any]]:
    try:
        with _CATALOG_PATH.open("r", encoding="utf-8-sig") as handle:
            records = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=500, detail="Market catalogue could not be loaded."
        ) from exc

    if not isinstance(records, list):
        raise HTTPException(status_code=500, detail="Market catalogue must be a list.")
    return records


@router.get("/catalog", summary="Get source-backed market catalogue")
def get_market_catalog(
    category: str | None = Query(None, description="Optional category filter."),
    pin_code: str | None = Query(None, description="Optional six-digit Indian PIN code."),
) -> dict[str, Any]:
    """Return sourced programme/registry references, not implied local buyers."""
    if category is not None and category not in _VALID_CATEGORIES:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported category; choose from {sorted(_VALID_CATEGORIES)}",
        )

    if pin_code is not None and not re.fullmatch(r"\d{6}", pin_code):
        raise HTTPException(status_code=422, detail="pin_code must be six digits.")

    records = _load_catalog()
    if category:
        records = [record for record in records if record.get("category") == category]

    # Source-only nationwide entries remain visible but are never presented as
    # PIN-matched facilities. Every record carries its nationwide scope/status.
    matched = [
        record for record in records
        if pin_code is None
        or record.get("pin_code") == pin_code
        or record.get("region") == "India (nationwide source)"
    ]

    return {
        "records": matched,
        "count": len(matched),
        "category": category,
        "pin_code": pin_code,
        "note": (
            "Nationwide source references are not local facility matches. "
            "Registry/programme references do not confirm buyer demand. "
            "Null prices mean no verified price is provided."
        ),
    }
