"""Shared constants and helpers for feedstock handling.

This module centralises the supported feedstock names, normalisation helper,
and error classes used throughout the ML pipeline.
"""

# The single source of truth for supported feedstock names
FEEDSTOCK_NAMES = ("food", "manure", "crop_residue", "mixed")


def normalise_feedstock(label) -> str:
    """Normalize and validate a feedstock label.

    Raises MissingFeedstockError for ``None``, non‑string types, empty or
    whitespace‑only strings. Otherwise returns the stripped, lower‑cased label.
    """
    if label is None or not isinstance(label, str) or not label.strip():
        raise MissingFeedstockError()
    return label.strip().lower()


class MissingFeedstockError(ValueError):
    """Raised when a feedstock label is missing or empty.

    Subclass of ``ValueError`` so the FastAPI router maps it to a ``422``
    response automatically.
    """

    def __init__(self, message: str = "feedstock label is missing; supply feedstock in the request or a classified stream"):
        super().__init__(message)

class UnknownFeedstockError(Exception):
    """Raised when a feedstock label is not present in the trained model bundle."""
    pass
# single import path for all modules.

