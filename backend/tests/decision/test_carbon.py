"""
Tests for backend/app/decision/carbon.py and emission_factors.py

Coverage:
  - BoundaryValidator: all five IPCC rules (transport symmetry, GWP mismatch,
    missing stream ids, grid credit on baseline, etc.)
  - Sign convention: negative ghg_delta = emission reduction (proposed is better)
  - Dynamic baseline dispatch (landfill vs open_burning vs incineration)
  - Electricity export credit reduces proposed emissions
  - Zero electricity export produces no credit
  - Itemized breakdown keys are present and internally consistent
  - Emission factor lookup: default AR6, regional override, operator override
"""

import math
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.decision.carbon import (
    BaselineScenario,
    BoundaryMismatchError,
    BoundaryValidator,
    CarbonCalculator,
    GHGResult,
    ProposedScenario,
    ProposedTechnology,
    WasteStream,
)
from app.decision.emission_factors import (
    AR6_FACTORS,
    UnknownBaselineTypeError,
    UnknownFactorKeyError,
    get_baseline_factor_key,
    get_factor,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def single_stream_landfill() -> BaselineScenario:
    return BaselineScenario(
        waste_streams=[
            WasteStream(
                stream_id="s0",
                supply_tonnes_yr=10_000.0,
                baseline_type="landfill",
                distance_to_baseline_km=20.0,
            )
        ],
        include_transport=True,
        gwp_period="GWP100",
    )


@pytest.fixture
def single_tech_exporter() -> ProposedScenario:
    """Technology that is a net electricity exporter (produces credit)."""
    return ProposedScenario(
        technologies=[
            ProposedTechnology(
                tech_id="t0",
                direct_emission_factor=50.0,       # kgCO2e / tonne
                net_electricity_kwh_per_tonne=500.0,  # net export
                aux_energy_kwh_per_tonne=10.0,
                distances_to_facility_km={"s0": 15.0},
            )
        ],
        include_transport=True,
        gwp_period="GWP100",
    )


@pytest.fixture
def single_tech_no_export() -> ProposedScenario:
    """Technology with zero electricity export."""
    return ProposedScenario(
        technologies=[
            ProposedTechnology(
                tech_id="t0",
                direct_emission_factor=80.0,
                net_electricity_kwh_per_tonne=0.0,
                aux_energy_kwh_per_tonne=5.0,
                distances_to_facility_km={"s0": 10.0},
            )
        ],
        include_transport=True,
        gwp_period="GWP100",
    )


@pytest.fixture
def full_allocation() -> dict[tuple[str, str], float]:
    return {("s0", "t0"): 10_000.0}


@pytest.fixture
def calc() -> CarbonCalculator:
    return CarbonCalculator()


# ---------------------------------------------------------------------------
# Sign convention tests
# ---------------------------------------------------------------------------

class TestSignConvention:
    def test_emission_reduction_yields_negative_delta(
        self, single_stream_landfill, single_tech_exporter, full_allocation, calc
    ):
        """Landfill baseline emits much more than the proposed technology.
        ghg_delta = proposed - baseline must be negative."""
        result = calc.ghg_delta(
            single_stream_landfill, single_tech_exporter, full_allocation
        )
        assert result.total_delta < 0, (
            f"Expected negative ghg_delta (emission reduction), got {result.total_delta}"
        )

    def test_delta_equals_proposed_minus_baseline(
        self, single_stream_landfill, single_tech_exporter, full_allocation, calc
    ):
        """ghg_delta must exactly equal proposed_total - baseline_total."""
        result = calc.ghg_delta(
            single_stream_landfill, single_tech_exporter, full_allocation
        )
        assert math.isclose(
            result.total_delta,
            result.proposed_total - result.baseline_total,
            rel_tol=1e-9,
        )

    def test_worse_technology_yields_positive_delta(
        self, single_stream_landfill, full_allocation, calc
    ):
        """A technology that emits far more than the baseline should give positive delta."""
        high_emission_tech = ProposedScenario(
            technologies=[
                ProposedTechnology(
                    tech_id="t0",
                    direct_emission_factor=2000.0,   # 2000 kgCO2e/tonne — worse than landfill
                    net_electricity_kwh_per_tonne=0.0,
                    aux_energy_kwh_per_tonne=0.0,
                    distances_to_facility_km={"s0": 0.0},
                )
            ],
            include_transport=False,
        )
        baseline_no_transport = BaselineScenario(
            waste_streams=single_stream_landfill.waste_streams,
            include_transport=False,
        )
        result = calc.ghg_delta(baseline_no_transport, high_emission_tech, full_allocation)
        assert result.total_delta > 0, (
            f"Expected positive delta for a worse-than-baseline technology, got {result.total_delta}"
        )

    def test_identical_scenarios_give_near_zero_delta(self, calc):
        """When proposed exactly replicates baseline emissions, delta ≈ 0."""
        landfill_factor = AR6_FACTORS["landfill_ch4"]
        baseline = BaselineScenario(
            waste_streams=[WasteStream("s0", 1000.0, "landfill", 0.0)],
            include_transport=False,
        )
        proposed = ProposedScenario(
            technologies=[
                ProposedTechnology(
                    tech_id="t0",
                    direct_emission_factor=landfill_factor,
                    net_electricity_kwh_per_tonne=0.0,
                    aux_energy_kwh_per_tonne=0.0,
                )
            ],
            include_transport=False,
        )
        result = calc.ghg_delta(baseline, proposed, {("s0", "t0"): 1000.0})
        assert math.isclose(result.total_delta, 0.0, abs_tol=1e-3)


# ---------------------------------------------------------------------------
# Electricity credit tests
# ---------------------------------------------------------------------------

class TestElectricityCredit:
    def test_net_exporter_credit_reduces_proposed_emissions(
        self, single_stream_landfill, full_allocation, calc
    ):
        """Electricity export credit should lower proposed emissions vs no export."""
        with_export = ProposedScenario(
            technologies=[ProposedTechnology("t0", 50.0, net_electricity_kwh_per_tonne=500.0)],
            include_transport=False,
        )
        without_export = ProposedScenario(
            technologies=[ProposedTechnology("t0", 50.0, net_electricity_kwh_per_tonne=0.0)],
            include_transport=False,
        )
        baseline = BaselineScenario(
            waste_streams=single_stream_landfill.waste_streams,
            include_transport=False,
        )
        res_with = calc.ghg_delta(baseline, with_export, full_allocation)
        res_without = calc.ghg_delta(baseline, without_export, full_allocation)
        assert res_with.proposed_total < res_without.proposed_total, (
            "Electricity export credit should reduce proposed emissions"
        )

    def test_zero_electricity_produces_no_credit(
        self, single_stream_landfill, single_tech_no_export, full_allocation, calc
    ):
        """proposed_electricity_export_credit must be 0.0 when net_electricity == 0."""
        baseline = BaselineScenario(
            waste_streams=single_stream_landfill.waste_streams,
            include_transport=True,
        )
        result = calc.ghg_delta(baseline, single_tech_no_export, full_allocation)
        credit = result.breakdown.get("proposed_electricity_export_credit", None)
        assert credit is not None, "breakdown must contain 'proposed_electricity_export_credit'"
        assert credit == 0.0, f"Expected 0.0 credit for zero export, got {credit}"

    def test_negative_net_electricity_produces_no_credit(
        self, single_stream_landfill, full_allocation, calc
    ):
        """Net consumer (negative net_electricity) must produce zero credit."""
        consumer_tech = ProposedScenario(
            technologies=[
                ProposedTechnology(
                    tech_id="t0",
                    direct_emission_factor=30.0,
                    net_electricity_kwh_per_tonne=-200.0,  # net consumer
                )
            ],
            include_transport=False,
        )
        baseline = BaselineScenario(
            waste_streams=single_stream_landfill.waste_streams,
            include_transport=False,
        )
        result = calc.ghg_delta(baseline, consumer_tech, full_allocation)
        credit = result.breakdown["proposed_electricity_export_credit"]
        assert credit == 0.0


# ---------------------------------------------------------------------------
# Boundary Validator — IPCC Rules
# ---------------------------------------------------------------------------

class TestBoundaryValidator:
    def test_transport_mismatch_raises(
        self, single_stream_landfill, single_tech_exporter, full_allocation, calc
    ):
        """Rule 3: transport included on proposed but excluded from baseline → 422."""
        baseline_no_transport = BaselineScenario(
            waste_streams=single_stream_landfill.waste_streams,
            include_transport=False,
        )
        with pytest.raises(BoundaryMismatchError, match="Rule 3"):
            calc.ghg_delta(baseline_no_transport, single_tech_exporter, full_allocation)

    def test_reverse_transport_mismatch_raises(
        self, single_stream_landfill, full_allocation, calc
    ):
        """Rule 3: transport on baseline but excluded from proposed → error."""
        proposed_no_transport = ProposedScenario(
            technologies=ProposedScenario(
                technologies=[ProposedTechnology("t0", 50.0)],
                include_transport=True,
            ).technologies,
            include_transport=False,
        )
        baseline_with_transport = single_stream_landfill  # include_transport=True
        with pytest.raises(BoundaryMismatchError, match="Rule 3"):
            calc.ghg_delta(baseline_with_transport, proposed_no_transport, full_allocation)

    def test_gwp_period_mismatch_raises(
        self, single_stream_landfill, full_allocation, calc
    ):
        """Rule 5: different GWP period → BoundaryMismatchError."""
        proposed_gwp20 = ProposedScenario(
            technologies=[ProposedTechnology("t0", 50.0)],
            include_transport=True,
            gwp_period="GWP20",
        )
        with pytest.raises(BoundaryMismatchError, match="Rule 5"):
            calc.ghg_delta(single_stream_landfill, proposed_gwp20, full_allocation)

    def test_missing_stream_in_baseline_raises(self, single_tech_exporter, calc):
        """Rule 1: allocation contains a stream_id absent from baseline → error."""
        baseline_only_stream_99 = BaselineScenario(
            waste_streams=[WasteStream("s99", 5000.0, "landfill", 0.0)],
            include_transport=True,
        )
        # allocation references stream s0, which is not in baseline
        with pytest.raises(BoundaryMismatchError, match="Rule 1"):
            calc.ghg_delta(
                baseline_only_stream_99,
                single_tech_exporter,
                {("s0", "t0"): 5000.0},
            )

    def test_matching_boundaries_do_not_raise(
        self, single_stream_landfill, single_tech_exporter, full_allocation, calc
    ):
        """Matching boundaries must not raise any exception."""
        result = calc.ghg_delta(
            single_stream_landfill, single_tech_exporter, full_allocation
        )
        assert isinstance(result, GHGResult)


# ---------------------------------------------------------------------------
# Dynamic baseline dispatch
# ---------------------------------------------------------------------------

class TestDynamicBaseline:
    def test_open_burning_baseline(self, single_tech_exporter, full_allocation, calc):
        """open_burning baseline has higher emissions than landfill → more negative delta."""
        baseline_ob = BaselineScenario(
            waste_streams=[WasteStream("s0", 10_000.0, "open_burning", 5.0)],
            include_transport=True,
        )
        baseline_lf = BaselineScenario(
            waste_streams=[WasteStream("s0", 10_000.0, "landfill", 5.0)],
            include_transport=True,
        )
        res_ob = calc.ghg_delta(baseline_ob, single_tech_exporter, full_allocation)
        res_lf = calc.ghg_delta(baseline_lf, single_tech_exporter, full_allocation)
        # open_burning factor (1550) > landfill_ch4 (467)
        assert res_ob.baseline_total > res_lf.baseline_total
        assert res_ob.total_delta < res_lf.total_delta, (
            "Open burning baseline should give a more negative delta"
        )

    def test_incineration_no_recovery_baseline(
        self, single_tech_exporter, full_allocation, calc
    ):
        """incineration_no_recovery baseline is registered and dispatches correctly."""
        baseline_inc = BaselineScenario(
            waste_streams=[WasteStream("s0", 10_000.0, "incineration_no_recovery", 0.0)],
            include_transport=False,
        )
        proposed_no_transport = ProposedScenario(
            technologies=single_tech_exporter.technologies,
            include_transport=False,
        )
        result = calc.ghg_delta(baseline_inc, proposed_no_transport, full_allocation)
        assert isinstance(result, GHGResult)

    def test_unknown_baseline_type_raises(self, calc):
        """An unregistered baseline_type must raise UnknownBaselineTypeError."""
        with pytest.raises(UnknownBaselineTypeError):
            get_baseline_factor_key("plasma_gasification_v3")

    def test_unknown_baseline_type_in_calculator_raises(self, calc):
        """Unknown baseline_type propagates through the calculator."""
        baseline_bad = BaselineScenario(
            waste_streams=[WasteStream("s0", 1000.0, "not_a_real_type", 0.0)],
            include_transport=False,
        )
        proposed = ProposedScenario(
            technologies=[ProposedTechnology("t0", 10.0)],
            include_transport=False,
        )
        with pytest.raises(UnknownBaselineTypeError):
            calc.ghg_delta(baseline_bad, proposed, {("s0", "t0"): 1000.0})


# ---------------------------------------------------------------------------
# Itemized breakdown completeness
# ---------------------------------------------------------------------------

class TestItemizedBreakdown:
    EXPECTED_KEYS = {
        "baseline_disposal",
        "baseline_transport",
        "proposed_direct_process",
        "proposed_electricity_export_credit",
        "proposed_auxiliary_energy",
        "proposed_transport",
    }

    def test_all_breakdown_keys_present(
        self, single_stream_landfill, single_tech_exporter, full_allocation, calc
    ):
        result = calc.ghg_delta(
            single_stream_landfill, single_tech_exporter, full_allocation
        )
        for key in self.EXPECTED_KEYS:
            assert key in result.breakdown, f"Missing breakdown key: '{key}'"

    def test_breakdown_is_internally_consistent(
        self, single_stream_landfill, single_tech_exporter, full_allocation, calc
    ):
        """Sum of breakdown components must reconcile with totals."""
        result = calc.ghg_delta(
            single_stream_landfill, single_tech_exporter, full_allocation
        )
        bd = result.breakdown
        expected_baseline = bd["baseline_disposal"] + bd["baseline_transport"]
        expected_proposed = (
            bd["proposed_direct_process"]
            + bd["proposed_electricity_export_credit"]  # already negative
            + bd["proposed_auxiliary_energy"]
            + bd["proposed_transport"]
        )
        assert math.isclose(result.baseline_total, expected_baseline, rel_tol=1e-9)
        assert math.isclose(result.proposed_total, expected_proposed, rel_tol=1e-9)

    def test_itemized_breakdown_convenience_method(
        self, single_stream_landfill, single_tech_exporter, full_allocation, calc
    ):
        """itemized_breakdown() must return the same dict as ghg_delta().breakdown."""
        full_result = calc.ghg_delta(
            single_stream_landfill, single_tech_exporter, full_allocation
        )
        shortcut = calc.itemized_breakdown(
            single_stream_landfill, single_tech_exporter, full_allocation
        )
        assert shortcut == full_result.breakdown


# ---------------------------------------------------------------------------
# Emission factor registry
# ---------------------------------------------------------------------------

class TestEmissionFactors:
    def test_ar6_default_grid_electricity(self):
        assert math.isclose(get_factor("grid_electricity"), 0.233, rel_tol=1e-6)

    def test_regional_override_takes_precedence_over_ar6(self):
        us_val = get_factor("grid_electricity", region="US")
        assert math.isclose(us_val, 0.386, rel_tol=1e-6)

    def test_operator_override_takes_precedence_over_regional(self):
        val = get_factor(
            "grid_electricity",
            region="US",
            operator_overrides={"grid_electricity": 0.111},
        )
        assert math.isclose(val, 0.111, rel_tol=1e-6)

    def test_unknown_key_raises(self):
        with pytest.raises(UnknownFactorKeyError):
            get_factor("this_key_does_not_exist")

    def test_all_ar6_factors_are_positive(self):
        for key, val in AR6_FACTORS.items():
            assert val > 0, f"AR6 factor '{key}' = {val} is not positive"
