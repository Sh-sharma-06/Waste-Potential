"""make_contract.py — generate docs/API_CONTRACT.md from docs/openapi.snapshot.json.

Usage (from repo root):
    python backend/scripts/make_contract.py

Reads the snapshot produced by dump_openapi.py and writes a human-readable
Markdown contract. Does not start a server or call any external service.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
_SNAPSHOT = _REPO / "docs" / "openapi.snapshot.json"
_OUT = _REPO / "docs" / "API_CONTRACT.md"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_ref(ref: str, components: dict[str, Any]) -> dict[str, Any]:
    """Follow a $ref like '#/components/schemas/Foo' into the schema dict."""
    if not ref.startswith("#/components/schemas/"):
        return {}
    name = ref.removeprefix("#/components/schemas/")
    return components.get(name, {})


def _schema_type(schema: dict[str, Any], components: dict[str, Any]) -> str:
    """Return a compact type string for a property schema."""
    if not isinstance(schema, dict):
        return "any"
    if "$ref" in schema:
        ref_schema = _resolve_ref(schema["$ref"], components)
        return ref_schema.get("title", schema["$ref"].split("/")[-1])
    if "anyOf" in schema:
        parts = [_schema_type(s, components) for s in schema["anyOf"]]
        # collapse "string | null" → "string (optional)"
        non_null = [p for p in parts if p != "null"]
        if not non_null:
            return "null"
        base = " | ".join(non_null)
        if "null" in parts:
            return f"{base} (optional)"
        return base
    t = schema.get("type", "")
    if t == "array":
        items = schema.get("items", {})
        return f"array[{_schema_type(items, components)}]"
    if t == "object":
        if "additionalProperties" in schema:
            ap = schema["additionalProperties"]
            if isinstance(ap, dict):
                vtype = _schema_type(ap, components)
                return f"object[string → {vtype}]"
            return "object"
        return "object"
    return t or "any"


def _extract_properties(
    schema: dict[str, Any],
    components: dict[str, Any],
    required_set: set[str],
) -> list[tuple[str, str, bool, str]]:
    """Return list of (name, type, required, description) from a schema object."""
    props = schema.get("properties", {})
    rows = []
    for name, prop in props.items():
        typ = _schema_type(prop, components)
        req = name in required_set
        desc = prop.get("description", "")
        rows.append((name, typ, req, desc))
    return rows


def _schema_for_body(body: dict[str, Any], components: dict[str, Any]) -> dict[str, Any]:
    """Return the resolved schema dict for a requestBody."""
    for content_type, media in body.get("content", {}).items():
        s = media.get("schema", {})
        if "$ref" in s:
            return _resolve_ref(s["$ref"], components)
        return s
    return {}


def _schema_for_response(
    responses: dict[str, Any], code: str, components: dict[str, Any]
) -> dict[str, Any]:
    """Return the resolved schema dict for a given response code."""
    resp = responses.get(code, {})
    for _, media in resp.get("content", {}).items():
        s = media.get("schema", {})
        if "$ref" in s:
            return _resolve_ref(s["$ref"], components)
        if s.get("type") == "array":
            return s
        return s
    return {}


def _format_table(headers: list[str], rows: list[tuple]) -> str:
    if not rows:
        return "_None_\n"
    col_w = [len(h) for h in headers]
    str_rows: list[list[str]] = []
    for row in rows:
        sr = [str(c) for c in row]
        str_rows.append(sr)
        for i, cell in enumerate(sr):
            col_w[i] = max(col_w[i], len(cell))

    def fmt_row(cells: list[str]) -> str:
        return "| " + " | ".join(c.ljust(col_w[i]) for i, c in enumerate(cells)) + " |"

    sep = "| " + " | ".join("-" * w for w in col_w) + " |"
    lines = [fmt_row(headers), sep] + [fmt_row(r) for r in str_rows]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def _render_parameters(params: list[dict[str, Any]], components: dict[str, Any]) -> str:
    if not params:
        return ""
    headers = ["Name", "In", "Type", "Required", "Description"]
    rows = []
    for p in params:
        schema = p.get("schema", {})
        if "$ref" in schema:
            schema = _resolve_ref(schema["$ref"], components)
        typ = _schema_type(schema, components)
        default = schema.get("default")
        desc = p.get("description", schema.get("description", ""))
        if default is not None:
            desc = f"{desc} (default: {default})".strip(". ") + "." if desc else f"default: {default}"
        rows.append((
            p.get("name", ""),
            p.get("in", ""),
            typ,
            "yes" if p.get("required") else "no",
            desc,
        ))
    return "**Query / path parameters**\n\n" + _format_table(headers, rows) + "\n"


def _render_body(body: dict[str, Any], components: dict[str, Any]) -> str:
    if not body:
        return ""
    schema = _schema_for_body(body, components)
    required_set = set(schema.get("required", []))

    # multipart/form-data — content-type key check
    content_types = list(body.get("content", {}).keys())
    is_multipart = any("multipart" in ct for ct in content_types)
    label = "**Request body** (multipart/form-data)\n\n" if is_multipart else "**Request body** (application/json)\n\n"

    rows = _extract_properties(schema, components, required_set)
    if not rows:
        # wrapped array etc.
        return label + "_See schema_\n\n"

    headers = ["Field", "Type", "Required", "Description"]
    table_rows = [(name, typ, "yes" if req else "no", desc) for name, typ, req, desc in rows]
    return label + _format_table(headers, table_rows) + "\n"


def _render_response(
    responses: dict[str, Any], components: dict[str, Any]
) -> str:
    lines = ["**Responses**\n"]
    error_codes = []
    for code, resp_obj in responses.items():
        description = resp_obj.get("description", "")
        if code != "200":
            error_codes.append((code, description))
            continue
        schema = _schema_for_response(responses, "200", components)
        if not schema:
            lines.append(f"- `200` {description}\n")
            continue
        # array of $ref
        if schema.get("type") == "array" and "$ref" in schema.get("items", {}):
            item_schema = _resolve_ref(schema["items"]["$ref"], components)
            schema = item_schema
            array_note = " (array)"
        else:
            array_note = ""
        required_set = set(schema.get("required", []))
        rows = _extract_properties(schema, components, required_set)
        lines.append(f"- `200` {description}{array_note}\n")
        if rows:
            headers = ["Field", "Type", "Required", "Description"]
            table_rows = [(name, typ, "yes" if req else "no", desc) for name, typ, req, desc in rows]
            lines.append(_format_table(headers, table_rows))
    for code, desc in error_codes:
        lines.append(f"- `{code}` {desc}\n")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

_HAND_HEADER = """\
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

"""


def generate(snapshot_path: Path, out_path: Path) -> None:
    schema = json.loads(snapshot_path.read_text(encoding="utf-8"))
    components = schema.get("components", {}).get("schemas", {})
    paths = schema.get("paths", {})
    info = schema.get("info", {})

    lines: list[str] = [_HAND_HEADER]
    lines.append(
        f"*App: **{info.get('title', 'API')}** — version {info.get('version', 'n/a')}*\n\n"
    )
    lines.append("---\n\n")
    lines.append("## Routes\n\n")

    for path, ops in paths.items():
        for method, op in ops.items():
            method_upper = method.upper()
            summary = op.get("summary", "")
            description = op.get("description", "")
            tag = (op.get("tags") or [""])[0]
            operation_id = op.get("operationId", "")

            lines.append(f"### `{method_upper} {path}`\n\n")
            if tag:
                lines.append(f"**Tag:** {tag}  \n")
            lines.append(f"**Summary:** {summary}\n\n")
            if description:
                # Truncate long descriptions to first sentence / 200 chars
                first = description.split("\n")[0][:200]
                if first:
                    lines.append(f"{first}\n\n")

            params = op.get("parameters", [])
            lines.append(_render_parameters(params, components))

            body = op.get("requestBody")
            if body:
                lines.append(_render_body(body, components))

            responses = op.get("responses", {})
            lines.append(_render_response(responses, components))

            lines.append("---\n\n")

    out_path.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {out_path.relative_to(Path.cwd())} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    generate(_SNAPSHOT, _OUT)
