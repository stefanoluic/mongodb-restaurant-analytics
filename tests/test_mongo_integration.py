import csv
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from pymongo import MongoClient
from benchmark import benchmark_database
from build_v2 import build_all
from import_v1 import build_documents
from query_runtime import explain_query, run_query
from prepare_metabase_visualizations import export_collections
from validate_results import compare_results, validate_database
from v1_queries import V1_QUERIES
from v2_queries import V2_QUERIES


@unittest.skipUnless(os.getenv("MONGODB_TEST_URI"), "Set MONGODB_TEST_URI for real MongoDB integration tests")
class MongoIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = MongoClient(os.environ["MONGODB_TEST_URI"], serverSelectionTimeoutMS=5000)
        cls.client.admin.command("ping")
        cls.name = "restaurant_analytics_test_" + uuid.uuid4().hex
        cls.db = cls.client[cls.name]
        documents = {name: [] for name in ("restaurants", "restaurant_locations", "restaurant_ratings", "restaurant_classifications")}

        def add(count, **overrides):
            for _ in range(count):
                row = {"restaurant_link": "fixture-" + str(len(documents["restaurants"])), "restaurant_name": "Test",
                       "country": "Fixtureland", "city": "London", "price_level": "$$ - $$$",
                       "avg_rating": 4.6, "total_reviews_count": 200, "excellent": 150,
                       "food": 4.8, "service": 4.2, "value": 4.0, "meals": "Lunch, Dinner",
                       "cuisines": "ScopeCuisine", "features": "Seating, ScopeTest", "top_tags": "ScopeTag",
                       "vegetarian_friendly": "Y", "vegan_options": "Y", "gluten_free": "Y", **overrides}
                for name, document in build_documents(row).items():
                    documents[name].append(document)

        add(120)
        add(6, price_level="$$$$", food=4.9, service=3.5, value=3.5, cuisines="Premium", features="Seating", top_tags="Premium")
        add(10, cuisines="RareCuisine", features="Seating", top_tags="Rare")
        # Unsuccessful and low-review restaurants must not pollute q08/q09/q10 averages.
        add(10, city="Paris", avg_rating=1.5, total_reviews_count=5, excellent=0, value=1.0, features="ScopeTest")
        # More groups than the top-k cutoff, with identical ranking values.
        for number in range(24):
            add(20, country=f"Tie{number:02}", cuisines="TieCuisine", features="Seating", top_tags="Generic")
        for name, rows in documents.items():
            cls.db[name].insert_many(rows)
        try:
            cls.build = build_all(cls.db)
        except BaseException:
            cls.client.drop_database(cls.name)
            cls.client.close()
            raise

    @classmethod
    def tearDownClass(cls):
        if not cls.name.startswith("restaurant_analytics_test_"):
            raise AssertionError("Refusing cleanup of an unrelated database")
        cls.client.drop_database(cls.name)
        cls.client.close()

    def test_all_ten_queries_have_nonempty_equal_ordered_results(self):
        for first, second in zip(V1_QUERIES, V2_QUERIES):
            with self.subTest(query=first["id"]):
                before, _ = run_query(self.db, first)
                after, _ = run_query(self.db, second)
                self.assertGreater(len(before), 0)
                check = compare_results(first["id"], before, after)
                self.assertTrue(check["passed"], check)

    def test_filtered_averages_and_city_counts_use_the_original_population(self):
        feature = next(r for r in run_query(self.db, V2_QUERIES[7])[0] if r["feature"] == "ScopeTest")
        self.assertEqual(feature["avg_rating"], 4.6)
        self.assertEqual(feature["avg_reviews"], 200)
        self.assertEqual(feature["avg_value_rating"], 4.0)
        self.assertEqual(feature["city_count"], 1)
        tag = next(r for r in run_query(self.db, V2_QUERIES[8])[0] if r["tag"] == "ScopeTag" and r["price_segment"] == "srednji")
        self.assertEqual(tag["avg_rating"], 4.6)
        self.assertEqual(tag["avg_reviews"], 200)
        cuisine = next(r for r in run_query(self.db, V2_QUERIES[9])[0] if r["cuisine"] == "ScopeCuisine")
        self.assertEqual(cuisine["restaurant_count"], 120)
        self.assertEqual(cuisine["avg_rating"], 4.6)
        self.assertEqual(cuisine["avg_reviews"], 200)
        self.assertEqual(cuisine["avg_excellent_ratio"], 0.75)

    def test_an_existing_materialization_requires_explicit_replacement(self):
        with self.assertRaises(ValueError):
            build_all(self.db)
        self.assertEqual(self.db.restaurants.count_documents({}), 626)

    def test_empty_source_and_invalid_benchmark_runs_are_rejected(self):
        empty = self.client["analytics_empty_" + uuid.uuid4().hex]
        with self.assertRaises(ValueError):
            validate_database(empty)
        with self.assertRaises(ValueError):
            benchmark_database(self.db, repetitions=1, build_report=self.build)
        with self.assertRaises(ValueError):
            benchmark_database(self.db, build_report={"database": "unrelated"})

    def test_repeated_benchmark_validates_and_collects_real_explain_metrics(self):
        result = benchmark_database(self.db, repetitions=2, warmups=0, build_report=self.build, query_ids=["q08"])
        self.assertTrue(result["passed"])
        self.assertEqual(len(result["queries"][0]["v1"]["samples_ms"]), 2)
        exports = export_collections(self.db, result, {"q08": result["queries"][0]["raw_results"]})
        self.assertEqual(exports["metabase_q08"], result["queries"][0]["result_count"])
        self.assertEqual(self.db.metabase_performance.find_one()["v1_median_ms"], result["queries"][0]["v1"]["median_ms"])
        with self.assertRaises(ValueError):
            export_collections(self.db, result, {"q08": result["queries"][0]["raw_results"]})
        _, explain = explain_query(self.db, V2_QUERIES[7])
        self.assertIsNotNone(explain["total_docs_examined_reported"])

    def test_csv_import_cli_refuses_accidental_append_and_scopes_replacement(self):
        name = "analytics_cli_test_" + uuid.uuid4().hex
        db = self.client[name]
        try:
            db.keep_me.insert_one({"marker": True})
            with tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "restaurants.csv"
                with path.open("w", encoding="utf-8", newline="") as stream:
                    writer = csv.DictWriter(stream, fieldnames=["restaurant_link", "avg_rating"])
                    writer.writeheader()
                    writer.writerows([{"restaurant_link": "one", "avg_rating": 4.5},
                                      {"restaurant_link": "two", "avg_rating": ""}])
                command = [sys.executable, str(Path(__file__).resolve().parents[1] / "src" / "import_v1.py"),
                           "--csv", str(path), "--uri", os.environ["MONGODB_TEST_URI"], "--db", name, "--chunk-size", "1"]
                first = subprocess.run(command, capture_output=True, text=True, timeout=30)
                self.assertEqual(first.returncode, 0, first.stderr)
                self.assertEqual(db.restaurants.count_documents({}), 2)
                second = subprocess.run(command, capture_output=True, text=True, timeout=30)
                self.assertNotEqual(second.returncode, 0)
                self.assertIn("V1 already contains data", second.stderr)
                self.assertEqual(db.restaurants.count_documents({}), 2)
                replacement = subprocess.run(command + ["--drop", "--limit", "1"], capture_output=True, text=True, timeout=30)
                self.assertEqual(replacement.returncode, 0, replacement.stderr)
                for collection in ("restaurants", "restaurant_locations", "restaurant_ratings", "restaurant_classifications"):
                    self.assertEqual(db[collection].count_documents({}), 1)
                self.assertEqual(db.keep_me.count_documents({}), 1)
        finally:
            self.client.drop_database(name)


if __name__ == "__main__":
    unittest.main()
