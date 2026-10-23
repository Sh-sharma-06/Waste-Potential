"""catalog_loader.py — Load process catalog from docs/process_catalog_extra.json.

Provides:
  - ``load_catalog()``   : returns the full catalog dict (cached after first load).
  - ``scale_inputs()``   : scales numeric values in the ``"inputs"`` sub-dict by
                           ``waste_kg / 1000.0``. Null values and strings are left
                           untouched.
"""

from __future__ import annotations

import json
from pathlib import Path

# Path is resolved relative to this file so it works regardless of cwd.
# catalog_loader.py lives at backend/app/pathways/catalog_loader.py
# parents[0] = backend/app/pathways
# parents[1] = backend/app
# parents[2] = backend
# parents[3] = Waste-Potential  (project root, where docs/ lives)
_CATALOG_PATH = Path(__file__).resolve().parents[3] / "docs" / "process_catalog_extra.json"

_catalog: dict | None = None


def load_catalog() -> dict:
    """Return the full process catalog.  Loaded once and cached in-process."""
    global _catalog
    if _catalog is None:
        with _CATALOG_PATH.open(encoding="utf-8") as fh:
            _catalog = json.load(fh)
    return _catalog


def scale_inputs(process_data: dict, waste_kg: float) -> dict:
    """Return a copy of *process_data* with numeric ``inputs`` values scaled.

    The multiplier is ``waste_kg / 1000.0``, so 1000 kg → multiplier 1.0 (no
    change), 500 kg → 0.5, 2000 kg → 2.0.

    Only the ``"inputs"`` dictionary is modified.  Any value that is ``None``
    or not a ``float``/``int`` is left as-is.  All other top-level keys
    (``"name"``, ``"description"``, ``"outputs"``, ``"category"``, …) are
    copied without modification.
    """
    multiplier = waste_kg / 1000.0
    result = dict(process_data)

    raw_inputs = process_data.get("inputs", {})
    scaled = {}
    for key, value in raw_inputs.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            scaled[key] = value * multiplier
        else:
            scaled[key] = value

    result["inputs"] = scaled
    return result
