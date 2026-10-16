"""
Parameter registry loader for the B1 Science Core.

Loads docs/parameter_registry.csv and exposes a typed API for querying
parameter metadata.  The registry is the authoritative source of provenance,
units, uncertainty assumptions, and validation status for every Params field.

Environment variable override:
    WP_REGISTRY_PATH  — absolute or relative path to an alternative CSV file.
                        Relative paths are resolved from the repository root
                        (the directory two levels above this file's package).

Typical usage
-------------
    from app.core_engine.registry import load_registry, get, defaults_used
    from app.core_engine.params import Params

    reg = load_registry()           # cached after first call
    entry = reg.get("y_biogas")
    unvalidated = reg.defaults_used(Params())
"""

from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ParameterEntry:
    name: str
    value: str
    unit: str
    mass_basis: str
    status: str
    source: str
    uncertainty: str
    model_version: str
    description: str


# ---------------------------------------------------------------------------
# Registry class
# ---------------------------------------------------------------------------

class Registry:
    """In-memory registry loaded from the CSV file."""

    def __init__(self, entries: List[ParameterEntry]) -> None:
        self._by_name: dict[str, ParameterEntry] = {e.name: e for e in entries}

    # ------------------------------------------------------------------
    def get(self, name: str) -> ParameterEntry:
        """Return the ParameterEntry for *name*.

        Raises
        ------
        KeyError
            If *name* does not appear in the registry.
        """
        if name not in self._by_name:
            known = sorted(self._by_name.keys())
            raise KeyError(
                f"Unknown parameter name '{name}'. "
                f"Known names: {known}"
            )
        return self._by_name[name]

    # ------------------------------------------------------------------
    def all_entries(self) -> List[ParameterEntry]:
        """Return all entries in the order they appear in the CSV."""
        return list(self._by_name.values())

    # ------------------------------------------------------------------
    def defaults_used(self, params: object) -> List[str]:
        """Return a sorted list of Params field names whose registry status
        is not 'validated'.

        This is the list that the API echoes as ``defaults_used_unvalidated``
        to tell downstream consumers which values have not yet been
        cross-checked against real plant data.

        Parameters
        ----------
        params:
            A Params instance (used to enumerate field names via
            ``dataclasses.fields``; the actual values are not read here).
        """
        import dataclasses

        # Enumerate all Params fields
        try:
            param_fields = {f.name for f in dataclasses.fields(params)}  # type: ignore[arg-type]
        except TypeError:
            # Not a dataclass — fall back to __dict__
            param_fields = set(vars(params).keys())

        unvalidated: List[str] = []
        for name in param_fields:
            # BUSWELL_COEFFS is a tuple field — look for the tuple entry itself,
            # not the individual _carbs/_protein/_lipid split rows.
            try:
                entry = self.get(name)
            except KeyError:
                # Field might be represented by sub-entries (e.g. BUSWELL_COEFFS)
                # — treat as unvalidated if any sub-entry is not validated.
                sub_entries = [
                    e for e in self._by_name.values()
                    if e.name.startswith(name + "_")
                ]
                if sub_entries:
                    if any(e.status != "validated" for e in sub_entries):
                        unvalidated.append(name)
                else:
                    # Truly unknown — include conservatively
                    unvalidated.append(name)
                continue

            if entry.status != "validated":
                unvalidated.append(name)

        return sorted(unvalidated)


# ---------------------------------------------------------------------------
# Default CSV path resolution
# ---------------------------------------------------------------------------

def _default_csv_path() -> Path:
    """Resolve the default registry CSV path.

    Order of precedence:
    1. WP_REGISTRY_PATH environment variable (absolute or relative to cwd)
    2. docs/parameter_registry.csv relative to the repository root
       (repo root = 3 levels up from this file: core_engine/ -> app/ -> backend/ -> repo)
    """
    env_path = os.environ.get("WP_REGISTRY_PATH")
    if env_path:
        return Path(env_path).expanduser().resolve()

    # __file__ is backend/app/core_engine/registry.py
    # repo root is three parents up
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / "docs" / "parameter_registry.csv"


# ---------------------------------------------------------------------------
# Public loader (cached)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def load_registry(path: Optional[str] = None) -> Registry:
    """Load and cache the parameter registry from *path* (or the default).

    The result is cached so subsequent calls with the same path are free.
    Pass ``path=None`` (default) to use the environment-variable / repo-root
    default.  Pass an explicit path string to override (useful in tests).

    Parameters
    ----------
    path:
        Filesystem path to the CSV file, or ``None`` for the default.
    """
    csv_path = Path(path).expanduser().resolve() if path else _default_csv_path()

    if not csv_path.exists():
        raise FileNotFoundError(
            f"Parameter registry CSV not found at '{csv_path}'. "
            "Set WP_REGISTRY_PATH or ensure docs/parameter_registry.csv exists."
        )

    entries: List[ParameterEntry] = []
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            entries.append(
                ParameterEntry(
                    name=row["name"].strip(),
                    value=row["value"].strip(),
                    unit=row["unit"].strip(),
                    mass_basis=row["mass_basis"].strip(),
                    status=row["status"].strip(),
                    source=row["source"].strip(),
                    uncertainty=row["uncertainty"].strip(),
                    model_version=row["model_version"].strip(),
                    description=row["description"].strip(),
                )
            )

    return Registry(entries)


# ---------------------------------------------------------------------------
# Module-level convenience helpers (proxy to default registry)
# ---------------------------------------------------------------------------

def get(name: str) -> ParameterEntry:
    """Convenience wrapper: ``registry.get(name)`` on the default registry."""
    return load_registry().get(name)


def all_entries() -> List[ParameterEntry]:
    """Convenience wrapper: ``registry.all_entries()`` on the default registry."""
    return load_registry().all_entries()


def defaults_used(params: object) -> List[str]:
    """Convenience wrapper: ``registry.defaults_used(params)`` on the default registry."""
    return load_registry().defaults_used(params)
