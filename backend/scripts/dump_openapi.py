"""dump_openapi.py — write the running app's OpenAPI schema to docs/openapi.snapshot.json.

Usage (from repo root):
    python backend/scripts/dump_openapi.py

The script does not start a server or call any external service; it builds the
FastAPI application in-process and uses its .openapi() method.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure backend/ is on sys.path regardless of cwd.
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.main import create_app  # noqa: E402

_DOCS = Path(__file__).resolve().parents[2] / "docs"
_OUT = _DOCS / "openapi.snapshot.json"


def main() -> None:
    schema = create_app().openapi()
    _DOCS.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(
        json.dumps(schema, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {_OUT.relative_to(Path.cwd())} ({_OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
