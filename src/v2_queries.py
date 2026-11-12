import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from query_runtime import explain_query, run_query, write_json


V2_QUERIES = [
    {
        "id": "q01",
        "role": "Turisticka organizacija",
        "question": (
            "Koji gradovi imaju najjacu ponudu visoko ocenjenih "
            "vegetarijanskih ili veganskih restorana?"
        ),
        "collection": "city_offer_stats",
        "pipeline": [
            {"$match": {"diet_friendly_high_rated_count": {"$gte": 10}}},
            {"$sort": {"diet_friendly_high_rated_count": -1, "diet_friendly_avg_rating": -1, "country": 1, "city": 1}},
            {"$limit": 20},
            {
                "$project": {
                    "_id": 0,
                    "country": 1,
                    "city": 1,
                    "restaurant_count": "$diet_friendly_high_rated_count",
                    "avg_rating": {"$round": ["$diet_friendly_avg_rating", 2]},
                    "avg_reviews": {"$round": ["$diet_friendly_avg_reviews", 1]},
                }
            },
        ],
    },
    {
        "id": "q02",
        "role": "Turisticka organizacija",
        "question": (
            "Koji gradovi imaju najbolju ponudu visoko ocenjenih "
            "gluten-free restorana?"
        ),
        "collection": "city_offer_stats",
        "pipeline": [
            {"$match": {"gluten_free_high_rated_count": {"$gte": 5}}},
            {"$sort": {"gluten_free_high_rated_count": -1, "gluten_free_avg_rating": -1, "country": 1, "city": 1}},
            {"$limit": 20},
            {
                "$project": {
                    "_id": 0,
                    "country": 1,
                    "city": 1,
                    "restaurant_count": "$gluten_free_high_rated_count",
                    "avg_rating": {"$round": ["$gluten_free_avg_rating", 2]},
                    "avg_reviews": {"$round": ["$gluten_free_avg_reviews", 1]},
                }
            },
        ],
    },
    {
        "id": "q03",
        "role": "Turisticka organizacija",
        "question": (
            "Koji gradovi nude najbolji odnos cene i kvaliteta za restorane "
            "koji nude rucak i veceru?"
        ),
        "collection": "city_offer_stats",
        "pipeline": [
            {"$match": {"affordable_lunch_dinner_count": {"$gte": 10}}},
            {"$sort": {"avg_value_for_money": -1, "affordable_lunch_dinner_count": -1, "country": 1, "city": 1}},
            {"$limit": 20},
            {
                "$project": {
                    "_id": 0,
                    "country": 1,
                    "city": 1,
                    "restaurant_count": "$affordable_lunch_dinner_count",
                    "avg_rating": {"$round": ["$affordable_avg_rating", 2]},
                    "avg_value_rating": {"$round": ["$avg_value_rating", 2]},
                    "avg_price_score": {"$round": ["$avg_price_score", 2]},
                    "avg_value_for_money": {"$round": ["$avg_value_for_money", 2]},
                }
            },
        ],
    },
    {
        "id": "q04",
        "role": "Turisticka organizacija",
        "question": (
            "U kojim gradovima skuplji restorani imaju visoko ocenjen "
            "kvalitet hrane, ali slabiju uslugu i slabiji odnos cene i "
            "kvaliteta?"
        ),
        "collection": "city_offer_stats",
        "pipeline": [
            {
                "$match": {
                    "expensive_food_service_gap_count": {"$gte": 5},
                    "expensive_avg_value": {"$lte": 4.0},
                }
            },
            {
                "$sort": {"expensive_avg_gap": -1, "expensive_avg_value": 1, "expensive_food_service_gap_count": -1, "country": 1, "city": 1}
            },
            {"$limit": 20},
            {
                "$project": {
                    "_id": 0,
                    "country": 1,
                    "city": 1,
                    "restaurant_count": "$expensive_food_service_gap_count",
                    "avg_food": {"$round": ["$expensive_avg_food", 2]},
                    "avg_service": {"$round": ["$expensive_avg_service", 2]},
                    "avg_value": {"$round": ["$expensive_avg_value", 2]},
                    "avg_gap": {"$round": ["$expensive_avg_gap", 2]},
                    "avg_reviews": {"$round": ["$expensive_avg_reviews", 1]},
                    "avg_price_score": {"$round": ["$expensive_avg_price_score", 2]},
                }
            },
        ],
    },
    {
        "id": "q05",
        "role": "Turisticka organizacija",
        "question": (
            "Koje kuhinje su najprepoznatljivije u velikim turistickim "
            "gradovima?"
        ),
        "collection": "city_cuisine_stats",
        "pipeline": [
            {"$match": {"tourism_restaurant_count": {"$gte": 20}}},
            {"$sort": {"tourism_restaurant_count": -1, "tourism_avg_rating": -1, "country": 1, "city": 1, "cuisine": 1}},
            {"$limit": 30},
            {
                "$project": {
                    "_id": 0,
                    "country": 1,
                    "city": 1,
                    "cuisine": 1,
                    "restaurant_count": "$tourism_restaurant_count",
                    "avg_rating": {"$round": ["$tourism_avg_rating", 2]},
                    "avg_reviews": {"$round": ["$tourism_avg_reviews", 1]},
                }
            },
        ],
    },
    {
        "id": "q06",
        "role": "Investitor",
        "question": (
            "Koje dobro ocenjene kuhinje su slabije zastupljene u velikim "
            "gradovima?"
        ),
        "collection": "city_cuisine_stats",
        "pipeline": [
            {
                "$match": {
                    "investor_restaurant_count": {"$gte": 5, "$lte": 40},
                    "investor_avg_rating": {"$gte": 4.2},
                }
            },
            {"$sort": {"investor_avg_rating": -1, "investor_avg_reviews": -1, "country": 1, "city": 1, "cuisine": 1}},
            {"$limit": 30},
            {
                "$project": {
                    "_id": 0,
                    "country": 1,
                    "city": 1,
                    "cuisine": 1,
                    "restaurant_count": "$investor_restaurant_count",
                    "avg_rating": {"$round": ["$investor_avg_rating", 2]},
                    "avg_reviews": {"$round": ["$investor_avg_reviews", 1]},
                }
            },
        ],
    },
    {
        "id": "q07",
        "role": "Investitor",
        "question": (
            "U kojim gradovima postoji prostor za premium restorane na osnovu "
            "visoke traznje i malog udela skupih restorana?"
        ),
        "collection": "city_offer_stats",
        "pipeline": [
            {
                "$match": {
                    "quality_demand_count": {"$gte": 100},
                    "known_price_count": {"$gte": 50},
                    "premium_share": {"$lte": 0.08},
                }
            },
            {"$sort": {"quality_demand_count": -1, "premium_share": 1, "premium_avg_rating": -1, "country": 1, "city": 1}},
            {"$limit": 20},
            {
                "$project": {
                    "_id": 0,
                    "country": 1,
                    "city": 1,
                    "quality_demand_count": 1,
                    "known_price_count": 1,
                    "premium_restaurant_count": 1,
                    "premium_share": {"$round": ["$premium_share", 4]},
                    "avg_rating": {"$round": ["$premium_avg_rating", 2]},
                    "avg_reviews": {"$round": ["$premium_avg_reviews", 1]},
                }
            },
        ],
    },
    {
        "id": "q08",
        "role": "Investitor",
        "question": (
            "Koje karakteristike se najcesce javljaju kod uspesnih restorana "
            "u velikim turistickim gradovima i kakvu ocenu vrednosti za novac "
            "imaju ti restorani?"
        ),
        "collection": "classification_signal_stats",
        "pipeline": [
            {
                "$match": {
                    "signal_type": "feature",
                    "scope": "major_tourist_cities",
                    "successful_restaurant_count": {"$gte": 20},
                }
            },
            {"$sort": {"successful_restaurant_count": -1, "successful_avg_rating": -1, "signal_value": 1}},
            {"$limit": 25},
            {
                "$project": {
                    "_id": 0,
                    "feature": "$signal_value",
                    "successful_restaurant_count": 1,
                    "avg_rating": {"$round": ["$successful_avg_rating", 2]},
                    "avg_reviews": {"$round": ["$successful_avg_reviews", 1]},
                    "avg_value_rating": {"$round": ["$successful_avg_value_rating", 2]},
                    "city_count": "$successful_city_count",
                }
            },
        ],
    },
    {
        "id": "q09",
        "role": "Investitor",
        "question": (
            "Koje glavne oznake se najcesce javljaju kod uspesnih restorana "
            "i kako se razlikuju po cenovnom segmentu?"
        ),
        "collection": "classification_signal_stats",
        "pipeline": [
            {
                "$match": {
                    "signal_type": "top_tag",
                    "successful_restaurant_count": {"$gte": 50},
                }
            },
            {"$sort": {"successful_restaurant_count": -1, "successful_avg_rating": -1, "signal_value": 1, "price_segment": 1}},
            {"$limit": 25},
            {
                "$project": {
                    "_id": 0,
                    "tag": "$signal_value",
                    "price_segment": 1,
                    "successful_restaurant_count": 1,
                    "avg_rating": {"$round": ["$successful_avg_rating", 2]},
                    "avg_reviews": {"$round": ["$successful_avg_reviews", 1]},
                    "avg_price_score": {"$round": ["$successful_avg_price_score", 2]},
                }
            },
        ],
    },
    {
        "id": "q10",
        "role": "Investitor",
        "question": "Koje kuhinje imaju najveci udeo odlicnih recenzija?",
        "collection": "cuisine_quality_stats",
        "pipeline": [
            {"$match": {"restaurant_count": {"$gte": 100}}},
            {"$sort": {"qualified_avg_excellent_ratio": -1, "restaurant_count": -1, "cuisine": 1}},
            {"$limit": 25},
            {
                "$project": {
                    "_id": 0,
                    "cuisine": 1,
                    "restaurant_count": 1,
                    "avg_rating": {"$round": ["$qualified_avg_rating", 2]},
                    "avg_reviews": {"$round": ["$qualified_avg_reviews", 1]},
                    "avg_excellent_ratio": {"$round": ["$qualified_avg_excellent_ratio", 4]},
                }
            },
        ],
    },
]


def get_query(query_id):
    for query in V2_QUERIES:
        if query["id"] == query_id:
            return query
    raise ValueError(f"Nepoznat upit: {query_id}")


def selected_queries(query_id):
    if query_id == "all":
        return V2_QUERIES
    return [get_query(query_id)]


def parse_args():
    parser = argparse.ArgumentParser(description="Pokretanje V2 MongoDB upita.")
    parser.add_argument("--uri", default=None, help="MongoDB konekcioni string.")
    parser.add_argument("--db", default=None, help="Naziv MongoDB baze.")
    parser.add_argument("--query", default="all", help="ID upita, na primer q01.")
    parser.add_argument(
        "--mode",
        choices=["run", "explain", "both"],
        default="run",
        help="Da li se pokrece upit, explain ili oba.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/v2_optimized",
        help="Folder za rezultate pokretanja.",
    )
    parser.add_argument("--no-save", action="store_true")
    return parser.parse_args()


def main():
    load_dotenv()
    args = parse_args()

    mongo_uri = args.uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = args.db or os.getenv("MONGODB_DB", "restaurant_analytics")
    output_dir = Path(args.output_dir)

    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[db_name]

    summaries = []
    started_at = datetime.now(timezone.utc).isoformat()

    for query in selected_queries(args.query):
        print(f"\n{query['id']} - {query['question']}")
        query_summary = {
            "id": query["id"],
            "role": query["role"],
            "question": query["question"],
            "collection": query["collection"],
        }

        if args.mode in {"run", "both"}:
            results, elapsed_ms = run_query(db, query)
            print(f"Rezultata: {len(results)}")
            print(f"Vreme izvrsavanja: {elapsed_ms} ms")
            query_summary["result_count"] = len(results)
            query_summary["elapsed_ms"] = elapsed_ms

            if not args.no_save:
                write_json(
                    output_dir / "results" / f"{query['id']}.json",
                    {"query": query_summary, "results": results},
                )

        if args.mode in {"explain", "both"}:
            explain, explain_summary = explain_query(db, query)
            query_summary["explain_summary"] = explain_summary
            print(f"Indeksi: {explain_summary['indexes_used']}")
            print(f"Executed collection-scan stages: {explain_summary['collection_scans']}")
            print(
                "Prijavljeno pregledanih dokumenata: "
                f"{explain_summary['total_docs_examined_reported']}"
            )

            if not args.no_save:
                write_json(output_dir / "explain" / f"{query['id']}.json", explain)

        summaries.append(query_summary)

    if not args.no_save:
        write_json(
            output_dir / "summary.json",
            {
                "database": db_name,
                "mode": args.mode,
                "started_at": started_at,
                "queries": summaries,
            },
        )


if __name__ == "__main__":
    main()
