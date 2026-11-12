import copy
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from benchmark import digest, summarize
from generate_performance_charts import load_report, load_results
from import_v1 import build_documents, clean_number
from query_runtime import write_json


class ArtifactValidationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.rows = [{"feature": "Seating", "successful_restaurant_count": 3}]
        self.report = {"passed": True, "queries": [{"id": "q08", "validated": True,
            "v1": summarize([10.0, 12.0]), "v2": summarize([1.0, 2.0]),
            "result_count": 1, "results_sha256": digest(self.rows)}]}

    def load(self, report):
        write_json(self.root / "report.json", report)
        return load_report(self.root / "report.json")

    def test_successful_repeated_measurements_and_matching_results_load(self):
        report = self.load(self.report)
        write_json(self.root / "q08.json", self.rows)
        self.assertEqual(load_results(report, self.root), {"q08": self.rows})

    def test_failed_empty_or_unvalidated_runs_cannot_generate_claims(self):
        for change in ({"passed": False}, {"queries": []}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.load({**self.report, **change})
        invalid = copy.deepcopy(self.report)
        invalid["queries"][0]["validated"] = False
        with self.assertRaises(ValueError):
            self.load(invalid)

    def test_single_measurement_or_an_inconsistent_median_is_rejected(self):
        for timing in (summarize([1.0]), {**summarize([1.0, 2.0]), "median_ms": 99}):
            invalid = copy.deepcopy(self.report)
            invalid["queries"][0]["v2"] = timing
            with self.subTest(timing=timing), self.assertRaises(ValueError):
                self.load(invalid)

    def test_stale_result_files_are_rejected_before_export(self):
        write_json(self.root / "q08.json", [{**self.rows[0], "successful_restaurant_count": 30}])
        with self.assertRaises(ValueError):
            load_results(self.report, self.root)


class ImportCleaningTests(unittest.TestCase):
    def test_nonfinite_csv_values_cannot_become_rating_or_location_numbers(self):
        for value in (math.nan, math.inf, -math.inf, "inf", "not a number", ""):
            with self.subTest(value=value):
                self.assertIsNone(clean_number(value))
        docs = build_documents({"restaurant_link": "test", "latitude": "inf", "longitude": "10", "avg_rating": "nan"})
        self.assertIsNone(docs["restaurant_locations"]["location"])
        self.assertIsNone(docs["restaurant_ratings"]["avg_rating"])


if __name__ == "__main__":
    unittest.main()
