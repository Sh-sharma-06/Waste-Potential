"""Tests for provenance.py.

Covers:
- Provenance dataclass validation (invalid status, missing source, missing notes)
- build_provenance() completeness:
    * AD Params count == 22
    * Every pathway params field appears exactly once
    * No duplicate (applies_to, name) pairs
    * Buswell rows carry status "derived"
- coverage_summary() totals add up
- to_csv() round-trips correctly (via tempdir)
- registry_gaps() only returns "illustrative_estimate" names
"""
from __future__ import annotations

import csv
import dataclasses
import tempfile
import unittest
from pathlib import Path

from app.core_engine.provenance import (
    Provenance,
    build_provenance,
    coverage_summary,
    registry_gaps,
    to_csv,
)

# ---------------------------------------------------------------------------
# Shared fixture — build once for the class (classmethods)
# ---------------------------------------------------------------------------


class _WithRegistry(unittest.TestCase):
    """Base class that builds the registry once per test class."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.records = build_provenance()


# ---------------------------------------------------------------------------
# 1. Provenance dataclass validation
# ---------------------------------------------------------------------------


class TestProvenanceValidation(unittest.TestCase):

    def test_invalid_status_raises(self):
        with self.assertRaises(ValueError) as ctx:
            Provenance(
                name="x", value=1.0, unit="", status="unknown_status",
                source="TBD", basis="", applies_to="all",
            )
        self.assertIn("status", str(ctx.exception))

    def test_sourced_without_source_raises(self):
        with self.assertRaises(ValueError) as ctx:
            Provenance(
                name="x", value=1.0, unit="kJ", status="sourced",
                source="TBD", basis="", applies_to="all",
            )
        self.assertIn("TBD", str(ctx.exception))

    def test_sourced_with_empty_source_raises(self):
        with self.assertRaises(ValueError):
            Provenance(
                name="x", value=1.0, unit="", status="sourced",
                source="", basis="", applies_to="all",
            )

    def test_validated_without_source_raises(self):
        with self.assertRaises(ValueError):
            Provenance(
                name="x", value=1.0, unit="", status="validated",
                source="TBD", basis="", applies_to="all",
            )

    def test_derived_without_notes_raises(self):
        with self.assertRaises(ValueError) as ctx:
            Provenance(
                name="x", value=1.0, unit="", status="derived",
                source="some source", basis="", applies_to="all",
                notes="",
            )
        self.assertIn("notes", str(ctx.exception))

    def test_illustrative_with_tbd_source_is_valid(self):
        p = Provenance(
            name="x", value=1.0, unit="", status="illustrative_estimate",
            source="TBD", basis="", applies_to="all",
        )
        self.assertEqual(p.status, "illustrative_estimate")

    def test_sourced_with_real_source_is_valid(self):
        p = Provenance(
            name="y", value=9.94, unit="kWh/Nm³", status="sourced",
            source="Lide (CRC Handbook, 2007)", basis="per Nm³", applies_to="all",
        )
        self.assertEqual(p.status, "sourced")

    def test_derived_with_notes_is_valid(self):
        p = Provenance(
            name="z", value=0.415, unit="Nm³/kg VS", status="derived",
            source="Buswell (1952)", basis="per kg VS", applies_to="all",
            notes="From Buswell stoichiometric equation CnHaOb",
        )
        self.assertEqual(p.status, "derived")

    def test_all_valid_statuses_accepted(self):
        for st in ("illustrative_estimate", "sourced", "derived", "validated"):
            kwargs = dict(
                name="t", value=0.0, unit="", status=st,
                source="Real source" if st in {"sourced", "validated"} else "TBD",
                basis="", applies_to="all",
                notes="formula x=y" if st == "derived" else "",
            )
            p = Provenance(**kwargs)
            self.assertEqual(p.status, st)

    def test_provenance_is_frozen(self):
        p = Provenance(
            name="x", value=1.0, unit="", status="illustrative_estimate",
            source="TBD", basis="", applies_to="all",
        )
        with self.assertRaises((dataclasses.FrozenInstanceError, AttributeError)):
            p.name = "y"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. build_provenance() — completeness and structure
# ---------------------------------------------------------------------------


class TestBuildProvenanceStructure(_WithRegistry):

    def test_returns_list(self):
        self.assertIsInstance(self.records, list)

    def test_all_provenance_instances(self):
        for r in self.records:
            self.assertIsInstance(r, Provenance)

    def test_no_duplicate_applies_to_name(self):
        keys = [(r.applies_to, r.name) for r in self.records]
        self.assertEqual(len(keys), len(set(keys)),
                         "Duplicate (applies_to, name) pairs found")

    def test_ad_params_count_is_22(self):
        ad_rows = [r for r in self.records if r.applies_to == "anaerobic_digestion"
                   and r.status == "illustrative_estimate"
                   and "AD Params default" in r.notes]
        self.assertEqual(len(ad_rows), 22,
                         f"Expected 22 AD Params rows, got {len(ad_rows)}")

    def test_all_statuses_are_valid(self):
        valid = {"illustrative_estimate", "sourced", "derived", "validated"}
        for r in self.records:
            self.assertIn(r.status, valid,
                          f"Invalid status {r.status!r} on {r.name!r}")

    def test_sourced_rows_have_non_tbd_source(self):
        for r in self.records:
            if r.status == "sourced":
                self.assertTrue(r.source and r.source != "TBD",
                                f"sourced row {r.name!r} has TBD source")

    def test_derived_rows_have_notes(self):
        for r in self.records:
            if r.status == "derived":
                self.assertTrue(r.notes.strip(),
                                f"derived row {r.name!r} has empty notes")

    def test_buswell_rows_are_derived(self):
        buswell_rows = [r for r in self.records if "BUSWELL" in r.name.upper()]
        self.assertGreater(len(buswell_rows), 0, "No Buswell rows found")
        for r in buswell_rows:
            self.assertEqual(r.status, "derived",
                             f"Buswell row {r.name!r} has status {r.status!r}")

    def test_buswell_notes_mention_stoichiometry(self):
        for r in self.records:
            if "BUSWELL" in r.name.upper():
                self.assertIn("stoichiometric", r.notes.lower(),
                              f"Buswell row {r.name!r} notes do not mention stoichiometry")

    def test_lhv_ch4_present(self):
        names = {r.name for r in self.records}
        self.assertTrue(
            "LHV_CH4_KWH_NM3" in names or "LHV_CH4" in names,
            "No LHV_CH4 row found"
        )


# ---------------------------------------------------------------------------
# 3. Pathway params fields — every field appears exactly once
# ---------------------------------------------------------------------------


class TestPathwayParamsCoverage(_WithRegistry):
    """Every default dataclass field of every pathway params class appears exactly once."""

    def _check_pathway(self, pathway_name: str, params_instance: object) -> None:
        for f in dataclasses.fields(params_instance):  # type: ignore[arg-type]
            matches = [
                r for r in self.records
                if r.applies_to == pathway_name and r.name == f.name
            ]
            self.assertEqual(
                len(matches), 1,
                f"{pathway_name}/{f.name}: expected 1 row, got {len(matches)}"
            )

    def test_composting_params_all_present(self):
        from app.core_engine.pathways.composting import CompostingParams
        self._check_pathway("composting", CompostingParams())

    def test_incineration_params_all_present(self):
        from app.core_engine.pathways.incineration import IncinerationParams
        self._check_pathway("incineration", IncinerationParams())

    def test_gasification_params_all_present(self):
        from app.core_engine.pathways.gasification import GasificationParams
        self._check_pathway("gasification", GasificationParams())

    def test_pyrolysis_params_all_present(self):
        from app.core_engine.pathways.pyrolysis import PyrolysisParams
        self._check_pathway("pyrolysis", PyrolysisParams())

    def test_htc_params_all_present(self):
        from app.core_engine.pathways.htc import HTCParams
        self._check_pathway("htc", HTCParams())

    def test_torrefaction_params_all_present(self):
        from app.core_engine.pathways.torrefaction import TorrefactionParams
        self._check_pathway("torrefaction", TorrefactionParams())


# ---------------------------------------------------------------------------
# 4. coverage_summary()
# ---------------------------------------------------------------------------


class TestCoverageSummary(_WithRegistry):

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.summary = coverage_summary(cls.records)

    def test_total_matches_record_count(self):
        self.assertEqual(self.summary["total"], len(self.records))

    def test_by_status_counts_add_up(self):
        total = sum(self.summary["by_status"].values())
        self.assertEqual(total, self.summary["total"])

    def test_by_applies_to_counts_add_up(self):
        total = sum(self.summary["by_applies_to"].values())
        self.assertEqual(total, self.summary["total"])

    def test_summary_keys_present(self):
        self.assertIn("total", self.summary)
        self.assertIn("by_status", self.summary)
        self.assertIn("by_applies_to", self.summary)

    def test_no_negative_counts(self):
        for v in self.summary["by_status"].values():
            self.assertGreaterEqual(v, 0)
        for v in self.summary["by_applies_to"].values():
            self.assertGreaterEqual(v, 0)

    def test_illustrative_estimate_count_positive(self):
        self.assertGreater(
            self.summary["by_status"].get("illustrative_estimate", 0), 0
        )

    def test_calls_build_when_none(self):
        # coverage_summary with no arg should also work
        s2 = coverage_summary()
        self.assertEqual(s2["total"], self.summary["total"])


# ---------------------------------------------------------------------------
# 5. registry_gaps()
# ---------------------------------------------------------------------------


class TestRegistryGaps(_WithRegistry):

    def test_returns_list(self):
        gaps = registry_gaps(self.records)
        self.assertIsInstance(gaps, list)

    def test_only_illustrative_names_in_gaps(self):
        gaps = registry_gaps(self.records)
        ill_names = {r.name for r in self.records if r.status == "illustrative_estimate"}
        for name in gaps:
            self.assertIn(name, ill_names,
                          f"gap name {name!r} is not illustrative_estimate")

    def test_no_sourced_or_derived_in_gaps(self):
        gaps_set = set(registry_gaps(self.records))
        for r in self.records:
            if r.status in {"sourced", "derived", "validated"}:
                self.assertNotIn(r.name, gaps_set,
                                 f"{r.name!r} ({r.status}) appeared in gaps")

    def test_calls_build_when_none(self):
        gaps1 = registry_gaps(self.records)
        gaps2 = registry_gaps()  # no arg
        self.assertEqual(sorted(gaps1), sorted(gaps2))


# ---------------------------------------------------------------------------
# 6. to_csv() round-trip
# ---------------------------------------------------------------------------


class TestToCSV(_WithRegistry):

    def test_writes_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = to_csv(Path(tmpdir) / "prov.csv", self.records)
            self.assertTrue(out.exists())

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = to_csv(Path(tmpdir) / "sub" / "dir" / "prov.csv", self.records)
            self.assertTrue(out.exists())

    def test_csv_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = to_csv(Path(tmpdir) / "prov.csv", self.records)
            with out.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                rows = list(reader)
            self.assertEqual(len(rows), len(self.records))

    def test_csv_header_matches_fields(self):
        expected_headers = [f.name for f in dataclasses.fields(Provenance)]
        with tempfile.TemporaryDirectory() as tmpdir:
            out = to_csv(Path(tmpdir) / "prov.csv", self.records)
            with out.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                self.assertEqual(list(reader.fieldnames or []), expected_headers)

    def test_csv_values_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = to_csv(Path(tmpdir) / "prov.csv", self.records)
            with out.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                csv_rows = list(reader)
            for orig, csv_row in zip(self.records, csv_rows):
                self.assertEqual(csv_row["name"], orig.name)
                self.assertEqual(csv_row["status"], orig.status)
                self.assertEqual(csv_row["applies_to"], orig.applies_to)

    def test_to_csv_accepts_docs_path(self):
        """Smoke-test the documented docs/ path used in production."""
        with tempfile.TemporaryDirectory() as tmpdir:
            docs_path = Path(tmpdir) / "docs" / "provenance_registry.csv"
            out = to_csv(docs_path, self.records)
            self.assertTrue(out.exists())

    def test_csv_no_duplicates_after_round_trip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out = to_csv(Path(tmpdir) / "prov.csv", self.records)
            with out.open(newline="", encoding="utf-8") as fh:
                reader = csv.DictReader(fh)
                keys = [(row["applies_to"], row["name"]) for row in reader]
            self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
