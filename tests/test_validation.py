import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from benchmark import summarize
from query_runtime import collect_explain_summary
from validate_results import compare_results


class ResultComparisonTests(unittest.TestCase):
    def setUp(self):
        self.row = {"country": "Test", "city": "London", "restaurant_count": 10, "avg_rating": 4.5}

    def test_dictionary_field_order_does_not_change_a_result(self):
        self.assertTrue(compare_results("q01", [self.row], [dict(reversed(list(self.row.items())))])["passed"])

    def test_small_float_representation_difference_is_tolerated(self):
        self.assertTrue(compare_results("q01", [self.row], [{**self.row, "avg_rating": 4.500000000000001}])["passed"])

    def test_missing_extra_and_changed_fields_are_detected(self):
        for changed in ({k: v for k, v in self.row.items() if k != "avg_rating"},
                        {**self.row, "unexpected": 1}, {**self.row, "avg_rating": 3.8},
                        {**self.row, "restaurant_count": 11}, {**self.row, "avg_rating": "4.5"}):
            with self.subTest(changed=changed):
                self.assertFalse(compare_results("q01", [self.row], [changed])["passed"])

    def test_order_length_and_duplicate_groups_are_checked(self):
        other = {**self.row, "city": "Paris"}
        self.assertFalse(compare_results("q01", [self.row, other], [other, self.row])["passed"])
        self.assertFalse(compare_results("q01", [self.row], [])["passed"])
        self.assertFalse(compare_results("q01", [self.row, self.row], [self.row, self.row])["passed"])

    def test_nonfinite_values_are_not_valid_results(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                row = {**self.row, "avg_rating": value}
                self.assertFalse(compare_results("q01", [row], [row])["passed"])

    def test_paired_query_identity_must_be_present(self):
        self.assertFalse(compare_results("q09", [{"tag": "A"}], [{"tag": "A"}])["passed"])


class ExplainSummaryTests(unittest.TestCase):
    def test_top_level_counters_are_not_added_to_child_counters(self):
        result = collect_explain_summary({
            "queryPlanner": {"winningPlan": {"stage": "FETCH", "inputStage": {"stage": "IXSCAN", "indexName": "winner"}},
                             "rejectedPlans": [{"stage": "IXSCAN", "indexName": "rejected"}]},
            "executionStats": {"totalDocsExamined": 100, "totalKeysExamined": 120,
                               "executionStages": {"stage": "FETCH", "totalDocsExamined": 100}},
        })
        self.assertEqual(result["total_docs_examined_reported"], 100)
        self.assertEqual(result["total_keys_examined_reported"], 120)
        self.assertEqual(result["indexes_used"], ["winner"])

    def test_separate_cursor_and_lookup_counts_are_added_once(self):
        result = collect_explain_summary({"stages": [
            {"$cursor": {"executionStats": {"totalDocsExamined": 20, "totalKeysExamined": 0,
                                           "executionStages": {"stage": "COLLSCAN", "totalDocsExamined": 20}}}},
            {"$lookup": {"from": "other"}, "totalDocsExamined": 5, "totalKeysExamined": 7,
             "collectionScans": 0, "indexesUsed": ["_id_"], "nested": {"totalDocsExamined": 5}},
        ]})
        self.assertEqual(result["total_docs_examined_reported"], 25)
        self.assertEqual(result["total_keys_examined_reported"], 7)
        self.assertEqual(result["collection_scans"], 1)
        self.assertEqual(result["metric_scope"], "cursor_plus_lookup")

    def test_shards_are_added_only_without_a_coordinator_total(self):
        shards = {"a": {"executionStats": {"totalDocsExamined": 3, "totalKeysExamined": 1}},
                  "b": {"executionStats": {"totalDocsExamined": 4, "totalKeysExamined": 2}}}
        self.assertEqual(collect_explain_summary({"shards": shards})["total_docs_examined_reported"], 7)
        self.assertEqual(collect_explain_summary({"shards": shards, "executionStats": {
            "totalDocsExamined": 7, "totalKeysExamined": 3}})["total_docs_examined_reported"], 7)

    def test_unknown_is_distinct_from_a_covered_zero_document_read(self):
        self.assertIsNone(collect_explain_summary({})["total_docs_examined_reported"])
        self.assertEqual(collect_explain_summary({"executionStats": {
            "totalDocsExamined": 0, "totalKeysExamined": 10}})["total_docs_examined_reported"], 0)


class TimingSummaryTests(unittest.TestCase):
    def test_median_and_range_use_all_samples(self):
        result = summarize([8.0, 2.0, 5.0])
        self.assertEqual(result["median_ms"], 5.0)
        self.assertEqual(result["min_ms"], 2.0)
        self.assertEqual(result["max_ms"], 8.0)

    def test_invalid_samples_are_rejected(self):
        for values in ([], [0.0], [-1.0], [math.inf], [math.nan]):
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    summarize(values)


if __name__ == "__main__":
    unittest.main()
