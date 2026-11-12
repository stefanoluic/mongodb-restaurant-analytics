import argparse
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from generate_performance_charts import build_rows, load_report, load_results
from v1_queries import V1_QUERIES


QUERY_VISUALS = {
    "q01": {
        "metric": "restaurant_count",
        "category_fields": ["city", "country"],
        "title": "Vegetarijanski/veganski restorani po gradovima",
        "chart_type": "bar",
    },
    "q02": {
        "metric": "restaurant_count",
        "category_fields": ["city", "country"],
        "title": "Gluten-free restorani po gradovima",
        "chart_type": "bar",
    },
    "q03": {
        "metric": "avg_value_for_money",
        "category_fields": ["city", "country"],
        "title": "Odnos cene i kvaliteta po gradovima",
        "chart_type": "bar",
    },
    "q04": {
        "metric": "avg_gap",
        "category_fields": ["city", "country"],
        "title": "Razlika hrane i usluge kod skupljih restorana",
        "chart_type": "bar",
    },
    "q05": {
        "metric": "restaurant_count",
        "category_fields": ["city", "cuisine"],
        "title": "Prepoznatljive kuhinje u turistickim gradovima",
        "chart_type": "bar",
    },
    "q06": {
        "metric": "avg_rating",
        "category_fields": ["city", "cuisine"],
        "title": "Dobro ocenjene, slabije zastupljene kuhinje",
        "chart_type": "bar",
    },
    "q07": {
        "metric": "quality_demand_count",
        "category_fields": ["city", "country"],
        "title": "Prostor za premium restorane",
        "chart_type": "bar",
    },
    "q08": {
        "metric": "successful_restaurant_count",
        "category_fields": ["feature"],
        "title": "Karakteristike uspesnih restorana",
        "chart_type": "bar",
    },
    "q09": {
        "metric": "successful_restaurant_count",
        "category_fields": ["tag", "price_segment"],
        "title": "Oznake uspesnih restorana po cenovnom segmentu",
        "chart_type": "bar",
    },
    "q10": {
        "metric": "avg_excellent_ratio",
        "category_fields": ["cuisine"],
        "title": "Kuhinje sa najvecim udelom odlicnih recenzija",
        "chart_type": "bar",
    },
}


def build_category(result, fields):
    return " / ".join(str(result[field]) for field in fields if result.get(field) not in (None, ""))


def result_documents(query, rows):
    visual = QUERY_VISUALS[query["id"]]
    documents = []
    for rank, result in enumerate(rows, start=1):
        document = {
            **result, "query_id": query["id"], "query_label": query["id"].upper(),
            "schema_version": "V1/V2 validated", "validated": True,
            "role": query["role"], "question": query["question"], "rank": rank,
            "category": build_category(result, visual["category_fields"]),
            "primary_metric_name": visual["metric"], "primary_metric_value": result.get(visual["metric"]),
            "recommended_title": visual["title"], "recommended_chart_type": visual["chart_type"],
        }
        documents.append(document)
    return documents


def export_collections(db, report, results, *, replace=False):
    # All report/result files have been verified before any collection is replaced.
    query_definitions = {q["id"]: q for q in V1_QUERIES}
    exports = {f"metabase_{query_id}": result_documents(query_definitions[query_id], rows)
               for query_id, rows in results.items()}
    exports["metabase_query_results"] = [row for rows in exports.values() for row in rows]
    exports["metabase_performance"] = build_rows(report)
    if not replace and any(db[name].estimated_document_count() for name in exports):
        raise ValueError("Metabase export collections already contain data. Use --replace to refresh them.")
    for name, documents in exports.items():
        collection = db[name]
        collection.drop()
        if documents:
            collection.insert_many(documents)
        if name == "metabase_performance":
            collection.create_index([("query_id", 1)], unique=True)
        else:
            collection.create_index([("query_id", 1), ("rank", 1)])
            collection.create_index([("role", 1), ("query_id", 1)])
        print(f"{name}: {len(documents)} documents")
    return {name: len(documents) for name, documents in exports.items()}


def main():
    parser = argparse.ArgumentParser(description="Export validated query results and repeated timings for Metabase.")
    parser.add_argument("--uri")
    parser.add_argument("--db")
    parser.add_argument("--benchmark-dir", type=Path, default=Path("outputs/runs/benchmark"))
    parser.add_argument("--replace", action="store_true", help="Replace existing Metabase export collections only.")
    args = parser.parse_args()
    load_dotenv()
    report = load_report(args.benchmark_dir / "report.json")
    results = load_results(report, args.benchmark_dir / "results")
    with MongoClient(args.uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017"),
                     serverSelectionTimeoutMS=5000) as client:
        db = client[args.db or os.getenv("MONGODB_DB", "restaurant_analytics")]
        export_collections(db, report, results, replace=args.replace)


if __name__ == "__main__":
    main()
