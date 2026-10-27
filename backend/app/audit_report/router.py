"""audit_report/router.py — GHG feasibility audit report endpoint.

Endpoints:
  - POST /api/audit-report: runs the selected conversion process, computes
    baseline vs. proposed GHG emissions, and returns the narrative report with
    ``summary_metrics`` at the top level of the response.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, HTTPException

from app.audit_report.audit_data import build_audit_payload
from app.audit_report.ghg import normalize_process
from app.audit_report.report_writer import make_report
from app.core_engine.engine import Params
from app.schemas.simulation import AuditRequest

router = APIRouter(prefix="/api/audit-report", tags=["Audit Report"])

_DEFAULT_MASS_KG_D = 1000.0
_DEFAULT_TRANSPORT_KM = 25.0


def _resolve_transport_km(req: AuditRequest) -> float:
    """Explicit transport_km wins; otherwise average the selected factories' distances."""
    if req.transport_km is not None:
        return req.transport_km
    distances = []
    for fac in req.selected_factories:
        if isinstance(fac, dict) and "distance_km" in fac:
            try:
                distances.append(float(fac["distance_km"]))
            except (ValueError, TypeError):
                pass
    return round(sum(distances) / len(distances), 1) if distances else _DEFAULT_TRANSPORT_KM


@router.post("")
def handle_audit_report(req: AuditRequest):
    try:
        process = normalize_process(req.process)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    if req.weight_kg is not None:
        mass = req.weight_kg
    elif req.total_mass_kg_d is not None:
        mass = req.total_mass_kg_d
    else:
        mass = _DEFAULT_MASS_KG_D
    location = req.location or (f"PIN {req.pincode}, India" if req.pincode else "Industrial Hub")
    transport = _resolve_transport_km(req)

    p = replace(
        Params(),
        total_mass_kg_d=float(mass),
        organic_fraction=req.organic_fraction,
        suitable_fraction=req.suitable_fraction,
        ambient_temp_c=req.ambient_temp_c,
    )
    payload = build_audit_payload(
        p, location, transport, process=process, parameter_status=req.parameter_status
    )
    payload["pincode"] = req.pincode or ""
    payload["transport_km"] = transport
    payload["selected_factories"] = req.selected_factories

    report = make_report(payload)
    ghg = payload["ghg"]
    report["pincode"] = req.pincode or ""
    report["process"] = process
    report["weight_kg"] = mass
    report["selected_factories"] = req.selected_factories
    report["transport_km"] = transport
    report["summary_metrics"] = {
        "baseline_kgco2e_d": round(ghg["baseline_kgco2e_d"], 2),
        "proposed_kgco2e_d": round(ghg["proposed_kgco2e_d"], 2),
        "delta_kgco2e_d": round(ghg["delta_kgco2e_d"], 2),
        "annual_co2e_avoided_tonnes": round(ghg["delta_kgco2e_d"] * 365 / 1000, 2),
    }
    return report
