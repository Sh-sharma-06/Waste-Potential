"""Unit tests for dataset.py (data loader and quality auditor)."""

import os
import unittest
import pandas as pd

from app.ml.yield_model.dataset import load_bmp_dataset, audit_bmp_dataframe


class TestDataset(unittest.TestCase):
    """Test suite for BMP dataset loading and data quality audit rules."""

    @classmethod
    def setUpClass(cls):
        cls.fixture_path = os.path.join(
            os.path.dirname(__file__),
            "fixtures",
            "test_bmp_table.csv"
        )

    def test_missing_file_raises_filenotfound_with_datasets_md(self):
        """Missing dataset file must raise FileNotFoundError pointing to docs/DATASETS.md."""
        with self.assertRaises(FileNotFoundError) as ctx:
            load_bmp_dataset("nonexistent_path/fake_bmp_table.csv")
        self.assertIn("docs/DATASETS.md", str(ctx.exception))

    def test_fixture_loading_and_audit(self):
        """Loads test fixture and audits every rule accurately."""
        clean_df, report = load_bmp_dataset(self.fixture_path)

        # 15 input rows total in test_bmp_table.csv
        self.assertEqual(report.total_input_rows, 15)
        # Exactly 4 clean valid rows (rows 0, 1, 2, 3)
        self.assertEqual(report.clean_rows, 4)
        self.assertEqual(report.dropped_count, 11)

        # 1. Duplicates: Row 4 is duplicate of Row 0
        self.assertIn(4, report.dropped_rows)
        self.assertTrue(any("duplicate" in r for r in report.dropped_rows[4]))

        # 2. Missing study_id: Row 5
        self.assertIn(5, report.dropped_rows)
        self.assertTrue(any("study_id" in r for r in report.dropped_rows[5]))

        # 3. Unknown basis: Row 6 (per_dry_matter)
        self.assertIn(6, report.dropped_rows)
        self.assertTrue(any("unknown_yield_basis" in r for r in report.dropped_rows[6]))

        # 4. Missing fractions: Row 7 (per_ts missing vs_of_ts), Row 8 (per_fresh missing ts_fraction)
        self.assertIn(7, report.dropped_rows)
        self.assertIn(8, report.dropped_rows)
        self.assertTrue(any("missing_or_invalid_vs_of_ts" in r for r in report.dropped_rows[7]))
        self.assertTrue(any("missing_or_invalid_ts_fraction" in r for r in report.dropped_rows[8]))

        # 5. Temperature out of plausible range (10 - 80 C): Row 9 (5 C), Row 10 (95 C)
        self.assertIn(9, report.dropped_rows)
        self.assertIn(10, report.dropped_rows)
        self.assertTrue(any("temperature_out_of_plausible_range" in r for r in report.dropped_rows[9]))
        self.assertTrue(any("temperature_out_of_plausible_range" in r for r in report.dropped_rows[10]))

        # 6. Non-positive values: Row 11 (negative yield), Row 12 (negative HRT)
        self.assertIn(11, report.dropped_rows)
        self.assertIn(12, report.dropped_rows)
        self.assertTrue(any("non_positive_yield" in r for r in report.dropped_rows[11]))
        self.assertTrue(any("non_positive_hrt" in r for r in report.dropped_rows[12]))

        # 7. Invalid CH4 fraction: Row 13 (1.20)
        self.assertIn(13, report.dropped_rows)
        self.assertTrue(any("invalid_ch4_fraction" in r for r in report.dropped_rows[13]))

        # 8. Buswell ceiling exceeded: Row 14 (CH4 yield 0.90 > 0.551)
        self.assertIn(14, report.dropped_rows)
        self.assertTrue(any("buswell_bound" in r for r in report.dropped_rows[14]))

    def test_multi_study_clean_file_keeps_all_study_ids(self):
        """Clean valid output preserves all distinct study_ids for GroupKFold."""
        clean_df, report = load_bmp_dataset(self.fixture_path)
        distinct_studies = set(clean_df["study_id"].unique())
        expected_studies = {"study_1", "study_2", "study_3"}
        self.assertEqual(distinct_studies, expected_studies)

    def test_clean_output_has_standardized_columns_and_conversions(self):
        """Clean output has y_biogas_nm3_per_kg_vs, y_ch4_nm3_per_kg_vs and basis='per kg VS'."""
        clean_df, _ = load_bmp_dataset(self.fixture_path)

        self.assertIn("y_biogas_nm3_per_kg_vs", clean_df.columns)
        self.assertIn("y_ch4_nm3_per_kg_vs", clean_df.columns)
        self.assertIn("basis", clean_df.columns)
        self.assertTrue((clean_df["basis"] == "per kg VS").all())

        # Check conversion values
        row0 = clean_df.iloc[0]  # food, 0.55 per_vs
        self.assertAlmostEqual(row0["y_biogas_nm3_per_kg_vs"], 0.55, places=5)
        self.assertAlmostEqual(row0["y_ch4_nm3_per_kg_vs"], 0.33, places=5)

        row1 = clean_df.iloc[1]  # crop, 0.44 per_ts, vs_of_ts=0.88 -> 0.44 / 0.88 = 0.50
        self.assertAlmostEqual(row1["y_biogas_nm3_per_kg_vs"], 0.50, places=5)
        self.assertAlmostEqual(row1["y_ch4_nm3_per_kg_vs"], 0.30, places=5)

        row2 = clean_df.iloc[2]  # manure, 0.08316 per_fresh, ts=0.27, vs/ts=0.88 -> 0.35
        self.assertAlmostEqual(row2["y_biogas_nm3_per_kg_vs"], 0.35, places=4)
        self.assertAlmostEqual(row2["y_ch4_nm3_per_kg_vs"], 0.21, places=4)

    def test_optional_features_nan_kept(self):
        """Optional features (olr, c_n) with NaN are retained and reported in missing_optional_features."""
        clean_df, report = load_bmp_dataset(self.fixture_path)

        # Row 2 (study_2) had empty olr and c_n
        row2 = clean_df[clean_df["study_id"] == "study_2"].iloc[0]
        self.assertTrue(pd.isna(row2["olr"]))
        self.assertTrue(pd.isna(row2["c_n"]))
        self.assertEqual(report.missing_optional_features.get("olr", 0), 1)
        self.assertEqual(report.missing_optional_features.get("c_n", 0), 1)

    def test_csv_without_comments(self):
        """Loader works seamlessly on CSVs without comment lines."""
        raw_csv = (
            "study_id,feedstock,yield_value,yield_basis,ts_fraction,vs_of_ts,ch4_fraction,temperature_c,hrt_days,olr,c_n,method,source\n"
            "study_10,food,0.50,per_vs,,,0.60,37.0,28.0,3.0,20.0,Batch,LabX\n"
        )
        temp_csv = os.path.join(os.path.dirname(__file__), "fixtures", "temp_no_comment.csv")
        try:
            with open(temp_csv, "w") as f:
                f.write(raw_csv)
            clean_df, report = load_bmp_dataset(temp_csv)
            self.assertEqual(report.total_input_rows, 1)
            self.assertEqual(report.clean_rows, 1)
            self.assertEqual(clean_df.iloc[0]["study_id"], "study_10")
        finally:
            if os.path.exists(temp_csv):
                os.remove(temp_csv)


if __name__ == "__main__":
    unittest.main()
