import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


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


def read_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def build_category(result, fields):
    values = []
    for field in fields:
        value = result.get(field)
        if value not in (None, ""):
            values.append(str(value))
    return " / ".join(values)


def result_documents(schema_version, query_id, result_file):
    payload = read_json(result_file)
    query = payload["query"]
    visual = QUERY_VISUALS[query_id]

    documents = []
    for rank, result in enumerate(payload["results"], start=1):
        document = {
            "schema_version": schema_version,
            "query_id": query_id,
            "query_label": query_id.upper(),
            "role": query["role"],
            "question": query["question"],
            "source_collection": query["collection"],
            "rank": rank,
            "category": build_category(result, visual["category_fields"]),
            "primary_metric_name": visual["metric"],
            "primary_metric_value": result.get(visual["metric"]),
            "recommended_title": visual["title"],
            "recommended_chart_type": visual["chart_type"],
        }
        document.update(result)
        documents.append(document)

    return documents


def performance_documents(v1_summary_file, v2_summary_file):
    v1 = {query["id"]: query for query in read_json(v1_summary_file)["queries"]}
    v2 = {query["id"]: query for query in read_json(v2_summary_file)["queries"]}

    documents = []
    for query_id in sorted(QUERY_VISUALS):
        v1_query = v1[query_id]
        v2_query = v2[query_id]
        v1_elapsed = v1_query["elapsed_ms"]
        v2_elapsed = v2_query["elapsed_ms"]
        v1_docs = v1_query["explain_summary"]["total_docs_examined_reported"]
        v2_docs = v2_query["explain_summary"]["total_docs_examined_reported"]

        documents.append(
            {
                "query_id": query_id,
                "query_label": query_id.upper(),
                "role": v1_query["role"],
                "question": v1_query["question"],
                "v1_elapsed_ms": v1_elapsed,
                "v2_elapsed_ms": v2_elapsed,
                "v1_elapsed_seconds": round(v1_elapsed / 1000, 4),
                "v2_elapsed_seconds": round(v2_elapsed / 1000, 4),
                "speedup": round(v1_elapsed / v2_elapsed, 2) if v2_elapsed else None,
                "v1_docs_examined": v1_docs,
                "v2_docs_examined": v2_docs,
                "docs_examined_reduction": round(v1_docs / v2_docs, 2) if v2_docs else None,
            }
        )

    return documents


def replace_collection(db, collection_name, documents):
    collection = db[collection_name]
    collection.drop()
    if documents:
        collection.insert_many(documents)
    return len(documents)


def create_indexes(db, collection_names):
    for collection_name in collection_names:
        collection = db[collection_name]
        collection.create_index([("query_id", 1), ("rank", 1)])
        collection.create_index([("schema_version", 1), ("query_id", 1), ("rank", 1)])
        collection.create_index([("role", 1), ("query_id", 1)])

    db["metabase_performance"].create_index([("query_id", 1)], unique=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Priprema malih MongoDB kolekcija za Metabase vizualizacije."
    )
    parser.add_argument("--uri", default=None, help="MongoDB konekcioni string.")
    parser.add_argument("--db", default=None, help="Naziv MongoDB baze.")
    parser.add_argument(
        "--v1-dir",
        default="outputs/v1_baseline_final",
        help="Folder sa finalnim V1 rezultatima.",
    )
    parser.add_argument(
        "--v2-dir",
        default="outputs/v2_optimized",
        help="Folder sa V2 rezultatima.",
    )
    return parser.parse_args()


def main():
    load_dotenv()
    args = parse_args()

    mongo_uri = args.uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = args.db or os.getenv("MONGODB_DB", "tripadvisor_restaurants")
    v1_dir = Path(args.v1_dir)
    v2_dir = Path(args.v2_dir)

    client = MongoClient(mongo_uri)
    client.admin.command("ping")
    db = client[db_name]

    combined_documents = []
    collection_names = []

    for query_id in sorted(QUERY_VISUALS):
        v1_documents = result_documents("V1 baseline", query_id, v1_dir / "results" / f"{query_id}.json")
        v2_documents = result_documents("V2 optimizovana", query_id, v2_dir / "results" / f"{query_id}.json")

        v1_collection = f"metabase_v1_{query_id}"
        v2_collection = f"metabase_v2_{query_id}"
        replace_collection(db, v1_collection, v1_documents)
        replace_collection(db, v2_collection, v2_documents)
        collection_names.extend([v1_collection, v2_collection])

        combined_documents.extend(v1_documents)
        combined_documents.extend(v2_documents)

    replace_collection(db, "metabase_query_results", combined_documents)
    collection_names.append("metabase_query_results")

    performance = performance_documents(v1_dir / "summary.json", v2_dir / "summary.json")
    replace_collection(db, "metabase_performance", performance)

    create_indexes(db, collection_names)

    print("Pripremljene su sledece kolekcije za Metabase:")
    for collection_name in collection_names:
        print(f"- {collection_name}: {db[collection_name].count_documents({})} dokumenata")
    print(f"- metabase_performance: {db['metabase_performance'].count_documents({})} dokumenata")


if __name__ == "__main__":
    main()
