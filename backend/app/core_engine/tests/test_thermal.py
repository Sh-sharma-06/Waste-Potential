"""
Tests for backend/app/core_engine/thermal.py

Coverage:
  - heat_demand_kwh: zero demand when dT<=0; linear scaling with feed;
    zero wall loss when V=0; reference numbers (feed=972, V=29.16, dT=12);
    negative-input ValueError cases.
  - split_chp_boiler: no boiler when CHP heat is sufficient; boiler grows as
    demand rises; cap triggers heat_deficit=True; chp_fuel+boiler_fuel==c_chem
    always; eta_boiler<=eta_th raises; negative-input ValueError cases.
"""

import math
import pytest

from app.core_engine.thermal import HeatDemand, HeatSplit, heat_demand_kwh, split_chp_boiler


# ===========================================================================
# heat_demand_kwh
# ===========================================================================

class TestHeatDemandKwh:

    # -----------------------------------------------------------------------
    # dT <= 0 → zero demand
    # -----------------------------------------------------------------------

    def test_zero_demand_when_dt_zero(self):
        hd = heat_demand_kwh(1000.0, 0.0, 100.0, 4.0, 0.5)
        assert hd.feed_heating_kwh_d == 0.0
        assert hd.wall_loss_kwh_d == 0.0
        assert hd.total_kwh_d == 0.0

    def test_zero_demand_when_dt_negative(self):
        hd = heat_demand_kwh(1000.0, -5.0, 100.0, 4.0, 0.5)
        assert hd.total_kwh_d == 0.0

    # -----------------------------------------------------------------------
    # Linear scaling with feed
    # -----------------------------------------------------------------------

    def test_feed_heating_scales_linearly(self):
        hd1 = heat_demand_kwh(500.0, 10.0, 0.0, 4.0, 0.5)
        hd2 = heat_demand_kwh(1000.0, 10.0, 0.0, 4.0, 0.5)
        assert math.isclose(hd2.feed_heating_kwh_d, 2 * hd1.feed_heating_kwh_d, rel_tol=1e-9)

    def test_feed_heating_formula(self):
        feed, dt, cp = 972.0, 12.0, 4.0
        expected = feed * cp * dt / 3600.0
        hd = heat_demand_kwh(feed, dt, 0.0, cp, 0.5)
        assert math.isclose(hd.feed_heating_kwh_d, expected, rel_tol=1e-9)

    # -----------------------------------------------------------------------
    # Zero digester volume → zero wall loss
    # -----------------------------------------------------------------------

    def test_zero_volume_gives_zero_wall_loss(self):
        hd = heat_demand_kwh(500.0, 10.0, 0.0, 4.0, 0.5)
        assert hd.wall_loss_kwh_d == 0.0

    # -----------------------------------------------------------------------
    # total == feed_heating + wall_loss
    # -----------------------------------------------------------------------

    def test_total_is_sum_of_components(self):
        hd = heat_demand_kwh(972.0, 12.0, 29.16, 4.0, 0.5)
        assert math.isclose(hd.total_kwh_d,
                             hd.feed_heating_kwh_d + hd.wall_loss_kwh_d,
                             rel_tol=1e-12)

    # -----------------------------------------------------------------------
    # Reference numbers: feed=972, V=29.16, dT=12 within 0.05 kWh/d
    # -----------------------------------------------------------------------

    def test_reference_feed_heating(self):
        hd = heat_demand_kwh(972.0, 12.0, 29.16, 4.0, 0.5)
        assert abs(hd.feed_heating_kwh_d - 12.96) < 0.05, (
            f"feed_heating={hd.feed_heating_kwh_d:.4f}, expected ~12.96"
        )

    def test_reference_wall_loss(self):
        hd = heat_demand_kwh(972.0, 12.0, 29.16, 4.0, 0.5)
        assert abs(hd.wall_loss_kwh_d - 7.55) < 0.05, (
            f"wall_loss={hd.wall_loss_kwh_d:.4f}, expected ~7.55"
        )

    def test_reference_total(self):
        hd = heat_demand_kwh(972.0, 12.0, 29.16, 4.0, 0.5)
        assert abs(hd.total_kwh_d - (12.96 + 7.55)) < 0.10

    # -----------------------------------------------------------------------
    # Wall loss scales with U
    # -----------------------------------------------------------------------

    def test_wall_loss_scales_with_u(self):
        hd1 = heat_demand_kwh(500.0, 10.0, 100.0, 4.0, 0.5)
        hd2 = heat_demand_kwh(500.0, 10.0, 100.0, 4.0, 1.0)
        assert math.isclose(hd2.wall_loss_kwh_d, 2 * hd1.wall_loss_kwh_d, rel_tol=1e-9)

    # -----------------------------------------------------------------------
    # Result is a frozen dataclass
    # -----------------------------------------------------------------------

    def test_returns_frozen_dataclass(self):
        hd = heat_demand_kwh(500.0, 10.0, 100.0, 4.0, 0.5)
        assert isinstance(hd, HeatDemand)
        import dataclasses
        assert dataclasses.is_dataclass(hd)
        with pytest.raises(dataclasses.FrozenInstanceError):
            hd.total_kwh_d = 0.0  # type: ignore[misc]

    # -----------------------------------------------------------------------
    # ValueError on negative inputs
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("kwargs,bad_field", [
        ({"feed_kg_d": -1.0}, "feed_kg_d"),
        ({"digester_m3": -1.0}, "digester_m3"),
        ({"cp_kj_kg_k": -1.0}, "cp_kj_kg_k"),
        ({"u_wall_w_m2k": -1.0}, "u_wall_w_m2k"),
    ])
    def test_negative_input_raises(self, kwargs, bad_field):
        defaults = dict(feed_kg_d=500.0, delta_t_k=10.0, digester_m3=50.0,
                        cp_kj_kg_k=4.0, u_wall_w_m2k=0.5)
        defaults.update(kwargs)
        with pytest.raises(ValueError, match="must be >= 0"):
            heat_demand_kwh(**defaults)


# ===========================================================================
# split_chp_boiler
# ===========================================================================

class TestSplitChpBoiler:

    # -----------------------------------------------------------------------
    # Boiler = 0 when CHP heat alone is sufficient
    # -----------------------------------------------------------------------

    def test_no_boiler_when_chp_sufficient(self):
        # c_chem=100, eta_th=0.45 → CHP heat = 45 kWh/d, demand=40 < 45
        hs = split_chp_boiler(100.0, 40.0, eta_th=0.45, eta_boiler=0.90)
        assert hs.boiler_fuel_kwh_d == 0.0
        assert hs.heat_deficit is False

    def test_no_boiler_when_demand_exactly_met_by_chp(self):
        # demand exactly == CHP heat
        hs = split_chp_boiler(100.0, 45.0, eta_th=0.45, eta_boiler=0.90)
        assert hs.boiler_fuel_kwh_d == 0.0
        assert hs.heat_deficit is False

    # -----------------------------------------------------------------------
    # Boiler grows as demand rises
    # -----------------------------------------------------------------------

    def test_boiler_increases_with_demand(self):
        hs1 = split_chp_boiler(100.0, 60.0, eta_th=0.45, eta_boiler=0.90)
        hs2 = split_chp_boiler(100.0, 80.0, eta_th=0.45, eta_boiler=0.90)
        assert hs2.boiler_fuel_kwh_d > hs1.boiler_fuel_kwh_d

    # -----------------------------------------------------------------------
    # chp_fuel + boiler_fuel == c_chem always
    # -----------------------------------------------------------------------

    @pytest.mark.parametrize("demand", [0.0, 20.0, 45.0, 80.0, 200.0])
    def test_fuel_conservation(self, demand):
        c_chem = 100.0
        hs = split_chp_boiler(c_chem, demand, eta_th=0.45, eta_boiler=0.90)
        assert math.isclose(hs.chp_fuel_kwh_d + hs.boiler_fuel_kwh_d,
                             c_chem, rel_tol=1e-12)

    # -----------------------------------------------------------------------
    # Cap at c_chem triggers heat_deficit=True
    # -----------------------------------------------------------------------

    def test_cap_triggers_heat_deficit(self):
        # demand=200, c_chem=100, eta_th=0.45, eta_boiler=0.90
        # uncapped boiler = (200 - 45) / 0.45 = 344 >> 100 → cap fires
        hs = split_chp_boiler(100.0, 200.0, eta_th=0.45, eta_boiler=0.90)
        assert hs.boiler_fuel_kwh_d == 100.0
        assert hs.chp_fuel_kwh_d == 0.0
        assert hs.heat_deficit is True

    def test_no_deficit_when_boiler_not_capped(self):
        # Demand just barely needs boiler but not capped
        hs = split_chp_boiler(100.0, 60.0, eta_th=0.45, eta_boiler=0.90)
        assert hs.heat_deficit is False
        assert hs.boiler_fuel_kwh_d > 0.0

    def test_boiler_formula_value(self):
        # demand=60, c_chem=100, eta_th=0.45, eta_boiler=0.90
        # boiler = (60 - 45) / (0.90 - 0.45) = 15/0.45 = 33.333...
        hs = split_chp_boiler(100.0, 60.0, eta_th=0.45, eta_boiler=0.90)
        assert math.isclose(hs.boiler_fuel_kwh_d, 15.0 / 0.45, rel_tol=1e-9)

    # -----------------------------------------------------------------------
    # Zero demand → zero boiler, all c_chem to CHP
    # -----------------------------------------------------------------------

    def test_zero_demand_no_boiler(self):
        hs = split_chp_boiler(100.0, 0.0, eta_th=0.45, eta_boiler=0.90)
        assert hs.boiler_fuel_kwh_d == 0.0
        assert hs.chp_fuel_kwh_d == 100.0

    # -----------------------------------------------------------------------
    # Zero c_chem → all deficit
    # -----------------------------------------------------------------------

    def test_zero_c_chem_with_demand_triggers_deficit(self):
        hs = split_chp_boiler(0.0, 50.0, eta_th=0.45, eta_boiler=0.90)
        assert hs.boiler_fuel_kwh_d == 0.0
        assert hs.chp_fuel_kwh_d == 0.0
        assert hs.heat_deficit is True

    # -----------------------------------------------------------------------
    # Result is a frozen dataclass
    # -----------------------------------------------------------------------

    def test_returns_frozen_dataclass(self):
        hs = split_chp_boiler(100.0, 40.0, eta_th=0.45, eta_boiler=0.90)
        assert isinstance(hs, HeatSplit)
        import dataclasses
        assert dataclasses.is_dataclass(hs)
        with pytest.raises(dataclasses.FrozenInstanceError):
            hs.boiler_fuel_kwh_d = 0.0  # type: ignore[misc]

    # -----------------------------------------------------------------------
    # ValueError cases
    # -----------------------------------------------------------------------

    def test_eta_boiler_le_eta_th_raises(self):
        with pytest.raises(ValueError, match="eta_boiler"):
            split_chp_boiler(100.0, 50.0, eta_th=0.50, eta_boiler=0.45)

    def test_eta_boiler_equal_eta_th_raises(self):
        with pytest.raises(ValueError, match="eta_boiler"):
            split_chp_boiler(100.0, 50.0, eta_th=0.45, eta_boiler=0.45)

    def test_negative_c_chem_raises(self):
        with pytest.raises(ValueError, match="c_chem_kwh_d"):
            split_chp_boiler(-1.0, 50.0, eta_th=0.45, eta_boiler=0.90)

    def test_negative_q_demand_raises(self):
        with pytest.raises(ValueError, match="q_demand_kwh_d"):
            split_chp_boiler(100.0, -1.0, eta_th=0.45, eta_boiler=0.90)
