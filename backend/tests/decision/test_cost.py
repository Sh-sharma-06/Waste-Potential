"""
Tests for backend/app/decision/cost.py

Coverage:
  - CRF: mathematical validation against known values
  - CRF: rejects invalid inputs (r ≤ 0, n ≤ 0)
  - cost_per_kwh: returns None when net_electricity ≤ 0 (zero and negative)
  - cost_per_kwh: returns a positive float when net_electricity > 0
  - cost_per_tonne: positive, scales with capex
  - LP coefficient assembly: all fields present, net_cost_per_tonne is correct
  - Parameter registry override: different r/n produces different result
  - Grid import cost applied when net_electricity < 0
  - Gate fee reduces net_cost_per_tonne
  - Electricity revenue increases net_cost_per_tonne reduction
"""

import math
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.decision.cost import (
    CostEngine,
    DEFAULT_ASSET_LIFE_YEARS,
    DEFAULT_DISCOUNT_RATE,
    LPCostCoeff,
    TechnologyParams,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def engine() -> CostEngine:
    return CostEngine(electricity_export_price=0.12)


@pytest.fixture
def standard_tech() -> TechnologyParams:
    """A technology with positive electricity export."""
    return TechnologyParams(
        tech_id="t0",
        capex=10_000_000.0,
        opex_annual=500_000.0,
        throughput_tonnes_yr=50_000.0,
        net_electricity_kwh_yr=2_000_000.0,
        gate_fee_per_tonne=20.0,
    )


@pytest.fixture
def zero_elec_tech() -> TechnologyParams:
    return TechnologyParams(
        tech_id="t1",
        capex=5_000_000.0,
        opex_annual=200_000.0,
        throughput_tonnes_yr=10_000.0,
        net_electricity_kwh_yr=0.0,
    )


@pytest.fixture
def negative_elec_tech() -> TechnologyParams:
    return TechnologyParams(
        tech_id="t2",
        capex=3_000_000.0,
        opex_annual=100_000.0,
        throughput_tonnes_yr=8_000.0,
        net_electricity_kwh_yr=-500_000.0,
    )


# ---------------------------------------------------------------------------
# Capital Recovery Factor mathematical validation
# ---------------------------------------------------------------------------

class TestCRF:
    """CRF(r, n) = r·(1+r)^n / [(1+r)^n - 1]"""

    # Known values computed independently
    KNOWN_VALUES = [
        (0.07, 20, 0.09439293),   # 7 %, 20 years
        (0.05, 30, 0.06505144),   # 5 %, 30 years
        (0.10, 10, 0.16274539),   # 10 %, 10 years
        (0.03, 40, 0.04326238),   # 3 %, 40 years
        (0.08, 25, 0.09367878),   # 8 %, 25 years
    ]

    @pytest.mark.parametrize("r,n,expected", KNOWN_VALUES)
    def test_crf_known_values(self, r, n, expected):
        result = CostEngine.crf(r, n)
        assert math.isclose(result, expected, rel_tol=1e-5), (
            f"CRF({r}, {n}) = {result}, expected {expected}"
        )

    def test_crf_rejects_zero_rate(self):
        with pytest.raises(ValueError, match="discount_rate"):
            CostEngine.crf(0.0, 20)

    def test_crf_rejects_negative_rate(self):
        with pytest.raises(ValueError, match="discount_rate"):
            CostEngine.crf(-0.01, 20)

    def test_crf_rejects_zero_life(self):
        with pytest.raises(ValueError, match="asset_life_years"):
            CostEngine.crf(0.07, 0)

    def test_crf_rejects_negative_life(self):
        with pytest.raises(ValueError, match="asset_life_years"):
            CostEngine.crf(0.07, -5)

    def test_crf_times_capex_gives_annualised_capex(self):
        """annualized_capex = capex × CRF(r, n)."""
        capex = 1_000_000.0
        r, n = 0.07, 20
        expected = capex * CostEngine.crf(r, n)
        result = CostEngine.annualized_capex(capex, r, n)
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_higher_rate_increases_annualised_cost(self):
        """A higher discount rate → higher CRF → higher annual repayment."""
        low = CostEngine.crf(0.05, 20)
        high = CostEngine.crf(0.10, 20)
        assert high > low

    def test_longer_life_decreases_annual_repayment(self):
        """Longer asset life → more years to repay → lower annual payment."""
        short = CostEngine.crf(0.07, 10)
        long_ = CostEngine.crf(0.07, 30)
        assert long_ < short


# ---------------------------------------------------------------------------
# cost_per_kwh sentinel behaviour
# ---------------------------------------------------------------------------

class TestCostPerKwh:
    def test_positive_electricity_returns_float(self, engine, standard_tech):
        result = engine.cost_per_kwh(standard_tech)
        assert result is not None
        assert isinstance(result, float)
        assert result > 0

    def test_zero_electricity_returns_none(self, engine, zero_elec_tech):
        result = engine.cost_per_kwh(zero_elec_tech)
        assert result is None, (
            "cost_per_kwh must return None when net_electricity_kwh_yr == 0"
        )

    def test_negative_electricity_returns_none(self, engine, negative_elec_tech):
        result = engine.cost_per_kwh(negative_elec_tech)
        assert result is None, (
            "cost_per_kwh must return None when net_electricity_kwh_yr < 0"
        )

    def test_cost_per_kwh_is_total_annual_cost_over_net_kwh(self, engine, standard_tech):
        """Verify the formula: cost_per_kwh = total_annual_cost / net_electricity."""
        r = DEFAULT_DISCOUNT_RATE
        n = DEFAULT_ASSET_LIFE_YEARS
        ann_capex = CostEngine.annualized_capex(standard_tech.capex, r, n)
        total_annual = ann_capex + standard_tech.opex_annual
        expected = total_annual / standard_tech.net_electricity_kwh_yr
        result = engine.cost_per_kwh(standard_tech)
        assert math.isclose(result, expected, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# cost_per_tonne
# ---------------------------------------------------------------------------

class TestCostPerTonne:
    def test_cost_per_tonne_is_positive(self, engine, standard_tech):
        result = engine.cost_per_tonne(standard_tech)
        assert result > 0

    def test_cost_per_tonne_formula(self, engine, standard_tech):
        """Verify: cost_per_tonne = (annualized_capex + opex) / throughput."""
        r = DEFAULT_DISCOUNT_RATE
        n = DEFAULT_ASSET_LIFE_YEARS
        ann_capex = CostEngine.annualized_capex(standard_tech.capex, r, n)
        expected = (ann_capex + standard_tech.opex_annual) / standard_tech.throughput_tonnes_yr
        result = engine.cost_per_tonne(standard_tech)
        assert math.isclose(result, expected, rel_tol=1e-9)

    def test_higher_capex_increases_cost_per_tonne(self, engine):
        base = TechnologyParams("t0", 5_000_000.0, 200_000.0, 10_000.0)
        high = TechnologyParams("t1", 10_000_000.0, 200_000.0, 10_000.0)
        assert engine.cost_per_tonne(high) > engine.cost_per_tonne(base)

    def test_higher_throughput_decreases_cost_per_tonne(self, engine):
        small = TechnologyParams("t0", 5_000_000.0, 200_000.0, throughput_tonnes_yr=5_000.0)
        large = TechnologyParams("t1", 5_000_000.0, 200_000.0, throughput_tonnes_yr=50_000.0)
        assert engine.cost_per_tonne(large) < engine.cost_per_tonne(small)


# ---------------------------------------------------------------------------
# LP coefficient assembly
# ---------------------------------------------------------------------------

class TestLPCoefficients:
    def test_all_fields_present(self, engine, standard_tech):
        coeffs = engine.lp_coefficients([standard_tech])
        coeff = coeffs[standard_tech.tech_id]
        assert isinstance(coeff, LPCostCoeff)
        assert coeff.tech_id == standard_tech.tech_id
        assert coeff.cost_per_tonne > 0
        assert coeff.gate_fee_per_tonne == standard_tech.gate_fee_per_tonne
        assert coeff.electricity_revenue_per_tonne >= 0
        assert coeff.grid_import_cost_per_tonne >= 0

    def test_net_cost_per_tonne_formula(self, engine, standard_tech):
        """net_cost = cost - gate_fee - elec_revenue + grid_import."""
        coeff = engine.lp_coefficients([standard_tech])[standard_tech.tech_id]
        expected = (
            coeff.cost_per_tonne
            + coeff.grid_import_cost_per_tonne
            - coeff.gate_fee_per_tonne
            - coeff.electricity_revenue_per_tonne
        )
        assert math.isclose(coeff.net_cost_per_tonne, expected, rel_tol=1e-9)

    def test_zero_electricity_fields(self, engine, zero_elec_tech):
        coeff = engine.lp_coefficients([zero_elec_tech])[zero_elec_tech.tech_id]
        assert coeff.cost_per_kwh is None
        assert coeff.electricity_revenue_per_tonne == 0.0

    def test_negative_electricity_adds_import_cost(self, engine, negative_elec_tech):
        coeff = engine.lp_coefficients([negative_elec_tech])[negative_elec_tech.tech_id]
        assert coeff.cost_per_kwh is None
        assert coeff.electricity_revenue_per_tonne == 0.0
        assert coeff.grid_import_cost_per_tonne > 0.0

    def test_gate_fee_reduces_net_cost(self, engine):
        no_fee = TechnologyParams("t0", 5_000_000.0, 100_000.0, 10_000.0, gate_fee_per_tonne=0.0)
        with_fee = TechnologyParams("t1", 5_000_000.0, 100_000.0, 10_000.0, gate_fee_per_tonne=30.0)
        c_no = engine.lp_coefficients([no_fee])["t0"]
        c_fee = engine.lp_coefficients([with_fee])["t1"]
        assert c_fee.net_cost_per_tonne < c_no.net_cost_per_tonne

    def test_electricity_revenue_reduces_net_cost(self, engine):
        no_elec = TechnologyParams("t0", 5_000_000.0, 100_000.0, 10_000.0, net_electricity_kwh_yr=0.0)
        with_elec = TechnologyParams("t1", 5_000_000.0, 100_000.0, 10_000.0, net_electricity_kwh_yr=1_000_000.0)
        c_no = engine.lp_coefficients([no_elec])["t0"]
        c_elec = engine.lp_coefficients([with_elec])["t1"]
        assert c_elec.net_cost_per_tonne < c_no.net_cost_per_tonne


# ---------------------------------------------------------------------------
# Parameter registry override
# ---------------------------------------------------------------------------

class TestParameterOverride:
    def test_custom_discount_rate_changes_cost(self, engine):
        default_tech = TechnologyParams("t0", 5_000_000.0, 100_000.0, 10_000.0)
        override_tech = TechnologyParams(
            "t1", 5_000_000.0, 100_000.0, 10_000.0,
            cost_params={"discount_rate": 0.12},
        )
        default_cpt = engine.cost_per_tonne(default_tech)
        override_cpt = engine.cost_per_tonne(override_tech)
        assert not math.isclose(default_cpt, override_cpt, rel_tol=1e-4), (
            "Custom discount rate must produce a different cost_per_tonne"
        )

    def test_custom_asset_life_changes_cost(self, engine):
        default_tech = TechnologyParams("t0", 5_000_000.0, 100_000.0, 10_000.0)
        override_tech = TechnologyParams(
            "t1", 5_000_000.0, 100_000.0, 10_000.0,
            cost_params={"asset_life_years": 10},
        )
        default_cpt = engine.cost_per_tonne(default_tech)
        override_cpt = engine.cost_per_tonne(override_tech)
        assert not math.isclose(default_cpt, override_cpt, rel_tol=1e-4)
        # Shorter life → higher CRF → higher annual repayment → higher cost_per_tonne
        assert override_cpt > default_cpt

    def test_override_grid_import_price(self):
        expensive_engine = CostEngine(electricity_export_price=0.12)
        tech = TechnologyParams(
            "t0", 3_000_000.0, 100_000.0, 8_000.0,
            net_electricity_kwh_yr=-500_000.0,
            cost_params={"grid_import_price": 0.50},  # expensive import
        )
        cheap_tech = TechnologyParams(
            "t1", 3_000_000.0, 100_000.0, 8_000.0,
            net_electricity_kwh_yr=-500_000.0,
            cost_params={"grid_import_price": 0.10},  # cheap import
        )
        c_expensive = expensive_engine.lp_coefficients([tech])["t0"]
        c_cheap = expensive_engine.lp_coefficients([cheap_tech])["t1"]
        assert c_expensive.grid_import_cost_per_tonne > c_cheap.grid_import_cost_per_tonne


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_negative_capex_raises(self):
        with pytest.raises(ValueError, match="capex"):
            TechnologyParams("t0", -1.0, 100_000.0, 10_000.0)

    def test_zero_throughput_raises(self):
        with pytest.raises(ValueError, match="throughput"):
            TechnologyParams("t0", 1_000_000.0, 100_000.0, 0.0)

    def test_negative_throughput_raises(self):
        with pytest.raises(ValueError, match="throughput"):
            TechnologyParams("t0", 1_000_000.0, 100_000.0, -500.0)

    def test_negative_electricity_export_price_raises(self):
        with pytest.raises(ValueError):
            CostEngine(electricity_export_price=-0.01)
