import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient


MAJOR_TOURIST_CITIES = [
    "Amsterdam",
    "Athens",
    "Barcelona",
    "Berlin",
    "Brussels",
    "Budapest",
    "Copenhagen",
    "Dublin",
    "Florence",
    "Lisbon",
    "London",
    "Madrid",
    "Milan",
    "Munich",
    "Naples",
    "Nice",
    "Paris",
    "Porto",
    "Prague",
    "Rome",
    "Seville",
    "Stockholm",
    "Valencia",
    "Venice",
    "Vienna",
    "Warsaw",
    "Zurich",
]


V1_QUERIES = [
    {
        "id": "q01",
        "role": "Turisticka organizacija",
        "question": (
            "Koji gradovi imaju najjacu ponudu visoko ocenjenih "
            "vegetarijanskih ili veganskih restorana?"
        ),
        "collection": "restaurant_classifications",
        "pipeline": [
            {
                "$match": {
                    "$or": [
                        {"vegetarian_friendly": True},
                        {"vegan_options": True},
                    ]
                }
            },
            {
                "$lookup": {
                    "from": "restaurant_ratings",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "rating",
                }
            },
            {"$unwind": "$rating"},
            {
                "$match": {
                    "rating.avg_rating": {"$gte": 4.2},
                    "rating.total_reviews_count": {"$gte": 50},
                }
            },
            {
                "$lookup": {
                    "from": "restaurant_locations",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "location",
                }
            },
            {"$unwind": "$location"},
            {
                "$match": {
                    "location.country": {"$ne": None},
                    "location.city": {"$ne": None},
                }
            },
            {
                "$group": {
                    "_id": {
                        "country": "$location.country",
                        "city": "$location.city",
                    },
                    "restaurant_count": {"$sum": 1},
                    "avg_rating": {"$avg": "$rating.avg_rating"},
                    "avg_reviews": {"$avg": "$rating.total_reviews_count"},
                }
            },
            {"$match": {"restaurant_count": {"$gte": 10}}},
            {"$sort": {"restaurant_count": -1, "avg_rating": -1}},
            {"$limit": 20},
            {
                "$project": {
                    "_id": 0,
                    "country": "$_id.country",
                    "city": "$_id.city",
                    "restaurant_count": 1,
                    "avg_rating": {"$round": ["$avg_rating", 2]},
                    "avg_reviews": {"$round": ["$avg_reviews", 1]},
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
        "collection": "restaurant_classifications",
        "pipeline": [
            {"$match": {"gluten_free": True}},
            {
                "$lookup": {
                    "from": "restaurant_ratings",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "rating",
                }
            },
            {"$unwind": "$rating"},
            {
                "$match": {
                    "rating.avg_rating": {"$gte": 4.2},
                    "rating.total_reviews_count": {"$gte": 50},
                }
            },
            {
                "$lookup": {
                    "from": "restaurant_locations",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "location",
                }
            },
            {"$unwind": "$location"},
            {
                "$match": {
                    "location.country": {"$ne": None},
                    "location.city": {"$ne": None},
                }
            },
            {
                "$group": {
                    "_id": {
                        "country": "$location.country",
                        "city": "$location.city",
                    },
                    "restaurant_count": {"$sum": 1},
                    "avg_rating": {"$avg": "$rating.avg_rating"},
                    "avg_reviews": {"$avg": "$rating.total_reviews_count"},
                }
            },
            {"$match": {"restaurant_count": {"$gte": 5}}},
            {"$sort": {"restaurant_count": -1, "avg_rating": -1}},
            {"$limit": 20},
            {
                "$project": {
                    "_id": 0,
                    "country": "$_id.country",
                    "city": "$_id.city",
                    "restaurant_count": 1,
                    "avg_rating": {"$round": ["$avg_rating", 2]},
                    "avg_reviews": {"$round": ["$avg_reviews", 1]},
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
        "collection": "restaurant_classifications",
        "pipeline": [
            {"$match": {"meals": {"$all": ["Lunch", "Dinner"]}}},
            {
                "$lookup": {
                    "from": "restaurants",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "restaurant",
                }
            },
            {"$unwind": "$restaurant"},
            {"$match": {"restaurant.price_score": {"$in": [1, 2]}}},
            {
                "$lookup": {
                    "from": "restaurant_ratings",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "rating",
                }
            },
            {"$unwind": "$rating"},
            {
                "$match": {
                    "rating.avg_rating": {"$gte": 4.0},
                    "rating.total_reviews_count": {"$gte": 30},
                    "rating.category_ratings.value": {"$ne": None},
                }
            },
            {
                "$lookup": {
                    "from": "restaurant_locations",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "location",
                }
            },
            {"$unwind": "$location"},
            {
                "$match": {
                    "location.country": {"$ne": None},
                    "location.city": {"$ne": None},
                }
            },
            {
                "$addFields": {
                    "value_for_money": {
                        "$divide": [
                            {
                                "$avg": [
                                    "$rating.avg_rating",
                                    "$rating.category_ratings.value",
                                ]
                            },
                            "$restaurant.price_score",
                        ]
                    }
                }
            },
            {
                "$group": {
                    "_id": {
                        "country": "$location.country",
                        "city": "$location.city",
                    },
                    "restaurant_count": {"$sum": 1},
                    "avg_rating": {"$avg": "$rating.avg_rating"},
                    "avg_value_rating": {
                        "$avg": "$rating.category_ratings.value"
                    },
                    "avg_price_score": {"$avg": "$restaurant.price_score"},
                    "avg_value_for_money": {"$avg": "$value_for_money"},
                }
            },
            {"$match": {"restaurant_count": {"$gte": 10}}},
            {"$sort": {"avg_value_for_money": -1, "restaurant_count": -1}},
            {"$limit": 20},
            {
                "$project": {
                    "_id": 0,
                    "country": "$_id.country",
                    "city": "$_id.city",
                    "restaurant_count": 1,
                    "avg_rating": {"$round": ["$avg_rating", 2]},
                    "avg_value_rating": {"$round": ["$avg_value_rating", 2]},
                    "avg_price_score": {"$round": ["$avg_price_score", 2]},
                    "avg_value_for_money": {
                        "$round": ["$avg_value_for_money", 2]
                    },
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
        "collection": "restaurant_ratings",
        "pipeline": [
            {
                "$match": {
                    "total_reviews_count": {"$gte": 30},
                    "category_ratings.food": {"$gte": 4.5},
                    "category_ratings.service": {"$ne": None},
                    "category_ratings.value": {"$ne": None},
                    "$expr": {
                        "$gte": [
                            {
                                "$subtract": [
                                    "$category_ratings.food",
                                    "$category_ratings.service",
                                ]
                            },
                            0.5,
                        ]
                    },
                }
            },
            {
                "$lookup": {
                    "from": "restaurants",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "restaurant",
                }
            },
            {"$unwind": "$restaurant"},
            {"$match": {"restaurant.price_score": {"$in": [2, 3]}}},
            {
                "$lookup": {
                    "from": "restaurant_locations",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "location",
                }
            },
            {"$unwind": "$location"},
            {
                "$match": {
                    "location.country": {"$ne": None},
                    "location.city": {"$ne": None},
                }
            },
            {
                "$addFields": {
                    "food_service_gap": {
                        "$subtract": [
                            "$category_ratings.food",
                            "$category_ratings.service",
                        ]
                    }
                }
            },
            {
                "$group": {
                    "_id": {
                        "country": "$location.country",
                        "city": "$location.city",
                    },
                    "restaurant_count": {"$sum": 1},
                    "avg_food": {"$avg": "$category_ratings.food"},
                    "avg_service": {"$avg": "$category_ratings.service"},
                    "avg_value": {"$avg": "$category_ratings.value"},
                    "avg_gap": {"$avg": "$food_service_gap"},
                    "avg_reviews": {"$avg": "$total_reviews_count"},
                    "avg_price_score": {"$avg": "$restaurant.price_score"},
                }
            },
            {
                "$match": {
                    "restaurant_count": {"$gte": 5},
                    "avg_value": {"$lte": 4.0},
                }
            },
            {"$sort": {"avg_gap": -1, "avg_value": 1, "restaurant_count": -1}},
            {"$limit": 20},
            {
                "$project": {
                    "_id": 0,
                    "country": "$_id.country",
                    "city": "$_id.city",
                    "restaurant_count": 1,
                    "avg_food": {"$round": ["$avg_food", 2]},
                    "avg_service": {"$round": ["$avg_service", 2]},
                    "avg_value": {"$round": ["$avg_value", 2]},
                    "avg_gap": {"$round": ["$avg_gap", 2]},
                    "avg_reviews": {"$round": ["$avg_reviews", 1]},
                    "avg_price_score": {"$round": ["$avg_price_score", 2]},
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
        "collection": "restaurant_locations",
        "pipeline": [
            {
                "$match": {
                    "country": {"$ne": None},
                    "city": {"$in": MAJOR_TOURIST_CITIES},
                }
            },
            {
                "$lookup": {
                    "from": "restaurant_ratings",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "rating",
                }
            },
            {"$unwind": "$rating"},
            {
                "$match": {
                    "rating.avg_rating": {"$gte": 4.0},
                    "rating.total_reviews_count": {"$gte": 30},
                }
            },
            {
                "$lookup": {
                    "from": "restaurant_classifications",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "classification",
                }
            },
            {"$unwind": "$classification"},
            {"$unwind": "$classification.cuisines"},
            {
                "$group": {
                    "_id": {
                        "country": "$country",
                        "city": "$city",
                        "cuisine": "$classification.cuisines",
                    },
                    "restaurant_count": {"$sum": 1},
                    "avg_rating": {"$avg": "$rating.avg_rating"},
                    "avg_reviews": {"$avg": "$rating.total_reviews_count"},
                }
            },
            {"$match": {"restaurant_count": {"$gte": 20}}},
            {"$sort": {"restaurant_count": -1, "avg_rating": -1}},
            {"$limit": 30},
            {
                "$project": {
                    "_id": 0,
                    "country": "$_id.country",
                    "city": "$_id.city",
                    "cuisine": "$_id.cuisine",
                    "restaurant_count": 1,
                    "avg_rating": {"$round": ["$avg_rating", 2]},
                    "avg_reviews": {"$round": ["$avg_reviews", 1]},
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
        "collection": "restaurant_locations",
        "pipeline": [
            {
                "$match": {
                    "country": {"$ne": None},
                    "city": {"$in": MAJOR_TOURIST_CITIES},
                }
            },
            {
                "$lookup": {
                    "from": "restaurant_ratings",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "rating",
                }
            },
            {"$unwind": "$rating"},
            {
                "$match": {
                    "rating.avg_rating": {"$gte": 4.2},
                    "rating.total_reviews_count": {"$gte": 50},
                }
            },
            {
                "$lookup": {
                    "from": "restaurant_classifications",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "classification",
                }
            },
            {"$unwind": "$classification"},
            {"$unwind": "$classification.cuisines"},
            {
                "$group": {
                    "_id": {
                        "country": "$country",
                        "city": "$city",
                        "cuisine": "$classification.cuisines",
                    },
                    "restaurant_count": {"$sum": 1},
                    "avg_rating": {"$avg": "$rating.avg_rating"},
                    "avg_reviews": {"$avg": "$rating.total_reviews_count"},
                }
            },
            {
                "$match": {
                    "restaurant_count": {"$gte": 5, "$lte": 40},
                    "avg_rating": {"$gte": 4.2},
                }
            },
            {"$sort": {"avg_rating": -1, "avg_reviews": -1}},
            {"$limit": 30},
            {
                "$project": {
                    "_id": 0,
                    "country": "$_id.country",
                    "city": "$_id.city",
                    "cuisine": "$_id.cuisine",
                    "restaurant_count": 1,
                    "avg_rating": {"$round": ["$avg_rating", 2]},
                    "avg_reviews": {"$round": ["$avg_reviews", 1]},
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
        "collection": "restaurant_ratings",
        "pipeline": [
            {
                "$match": {
                    "avg_rating": {"$gte": 4.2},
                    "total_reviews_count": {"$gte": 100},
                }
            },
            {
                "$lookup": {
                    "from": "restaurants",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "restaurant",
                }
            },
            {"$unwind": "$restaurant"},
            {
                "$lookup": {
                    "from": "restaurant_locations",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "location",
                }
            },
            {"$unwind": "$location"},
            {
                "$match": {
                    "location.country": {"$ne": None},
                    "location.city": {"$ne": None},
                }
            },
            {
                "$group": {
                    "_id": {
                        "country": "$location.country",
                        "city": "$location.city",
                    },
                    "quality_demand_count": {"$sum": 1},
                    "known_price_count": {
                        "$sum": {
                            "$cond": [
                                {"$ne": ["$restaurant.price_score", None]},
                                1,
                                0,
                            ]
                        }
                    },
                    "premium_restaurant_count": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$restaurant.price_score", 3]},
                                1,
                                0,
                            ]
                        }
                    },
                    "avg_rating": {"$avg": "$avg_rating"},
                    "avg_reviews": {"$avg": "$total_reviews_count"},
                }
            },
            {
                "$addFields": {
                    "premium_share": {
                        "$cond": [
                            {"$gt": ["$known_price_count", 0]},
                            {
                                "$divide": [
                                    "$premium_restaurant_count",
                                    "$known_price_count",
                                ]
                            },
                            None,
                        ]
                    }
                }
            },
            {
                "$match": {
                    "quality_demand_count": {"$gte": 100},
                    "known_price_count": {"$gte": 50},
                    "premium_share": {"$lte": 0.08},
                }
            },
            {
                "$sort": {
                    "quality_demand_count": -1,
                    "premium_share": 1,
                    "avg_rating": -1,
                }
            },
            {"$limit": 20},
            {
                "$project": {
                    "_id": 0,
                    "country": "$_id.country",
                    "city": "$_id.city",
                    "quality_demand_count": 1,
                    "known_price_count": 1,
                    "premium_restaurant_count": 1,
                    "premium_share": {"$round": ["$premium_share", 4]},
                    "avg_rating": {"$round": ["$avg_rating", 2]},
                    "avg_reviews": {"$round": ["$avg_reviews", 1]},
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
        "collection": "restaurant_ratings",
        "pipeline": [
            {
                "$match": {
                    "avg_rating": {"$gte": 4.5},
                    "total_reviews_count": {"$gte": 100},
                }
            },
            {
                "$lookup": {
                    "from": "restaurant_locations",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "location",
                }
            },
            {"$unwind": "$location"},
            {"$match": {"location.city": {"$in": MAJOR_TOURIST_CITIES}}},
            {
                "$lookup": {
                    "from": "restaurant_classifications",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "classification",
                }
            },
            {"$unwind": "$classification"},
            {"$unwind": "$classification.features"},
            {
                "$group": {
                    "_id": "$classification.features",
                    "successful_restaurant_count": {"$sum": 1},
                    "avg_rating": {"$avg": "$avg_rating"},
                    "avg_reviews": {"$avg": "$total_reviews_count"},
                    "avg_value_rating": {
                        "$avg": "$category_ratings.value"
                    },
                    "cities": {"$addToSet": "$location.city"},
                }
            },
            {"$match": {"successful_restaurant_count": {"$gte": 20}}},
            {"$addFields": {"city_count": {"$size": "$cities"}}},
            {"$sort": {"successful_restaurant_count": -1, "avg_rating": -1}},
            {"$limit": 25},
            {
                "$project": {
                    "_id": 0,
                    "feature": "$_id",
                    "successful_restaurant_count": 1,
                    "avg_rating": {"$round": ["$avg_rating", 2]},
                    "avg_reviews": {"$round": ["$avg_reviews", 1]},
                    "avg_value_rating": {"$round": ["$avg_value_rating", 2]},
                    "city_count": 1,
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
        "collection": "restaurant_ratings",
        "pipeline": [
            {
                "$match": {
                    "avg_rating": {"$gte": 4.5},
                    "total_reviews_count": {"$gte": 100},
                }
            },
            {
                "$lookup": {
                    "from": "restaurants",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "restaurant",
                }
            },
            {"$unwind": "$restaurant"},
            {"$match": {"restaurant.price_score": {"$ne": None}}},
            {
                "$lookup": {
                    "from": "restaurant_classifications",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "classification",
                }
            },
            {"$unwind": "$classification"},
            {"$unwind": "$classification.top_tags"},
            {
                "$addFields": {
                    "price_segment": {
                        "$switch": {
                            "branches": [
                                {
                                    "case": {
                                        "$eq": ["$restaurant.price_score", 1]
                                    },
                                    "then": "nizi",
                                },
                                {
                                    "case": {
                                        "$eq": ["$restaurant.price_score", 2]
                                    },
                                    "then": "srednji",
                                },
                                {
                                    "case": {
                                        "$eq": ["$restaurant.price_score", 3]
                                    },
                                    "then": "visi",
                                },
                            ],
                            "default": "nepoznat",
                        }
                    }
                }
            },
            {
                "$group": {
                    "_id": {
                        "tag": "$classification.top_tags",
                        "price_segment": "$price_segment",
                    },
                    "successful_restaurant_count": {"$sum": 1},
                    "avg_rating": {"$avg": "$avg_rating"},
                    "avg_reviews": {"$avg": "$total_reviews_count"},
                    "avg_price_score": {"$avg": "$restaurant.price_score"},
                }
            },
            {"$match": {"successful_restaurant_count": {"$gte": 50}}},
            {"$sort": {"successful_restaurant_count": -1, "avg_rating": -1}},
            {"$limit": 25},
            {
                "$project": {
                    "_id": 0,
                    "tag": "$_id.tag",
                    "price_segment": "$_id.price_segment",
                    "successful_restaurant_count": 1,
                    "avg_rating": {"$round": ["$avg_rating", 2]},
                    "avg_reviews": {"$round": ["$avg_reviews", 1]},
                    "avg_price_score": {"$round": ["$avg_price_score", 2]},
                }
            },
        ],
    },
    {
        "id": "q10",
        "role": "Investitor",
        "question": "Koje kuhinje imaju najveci udeo odlicnih recenzija?",
        "collection": "restaurant_ratings",
        "pipeline": [
            {
                "$match": {
                    "total_reviews_count": {"$gte": 100},
                    "review_distribution.excellent": {"$ne": None},
                }
            },
            {
                "$lookup": {
                    "from": "restaurant_classifications",
                    "localField": "_id",
                    "foreignField": "_id",
                    "as": "classification",
                }
            },
            {"$unwind": "$classification"},
            {"$unwind": "$classification.cuisines"},
            {
                "$addFields": {
                    "excellent_ratio": {
                        "$divide": [
                            "$review_distribution.excellent",
                            "$total_reviews_count",
                        ]
                    }
                }
            },
            {
                "$group": {
                    "_id": "$classification.cuisines",
                    "restaurant_count": {"$sum": 1},
                    "avg_rating": {"$avg": "$avg_rating"},
                    "avg_reviews": {"$avg": "$total_reviews_count"},
                    "avg_excellent_ratio": {"$avg": "$excellent_ratio"},
                }
            },
            {"$match": {"restaurant_count": {"$gte": 100}}},
            {"$sort": {"avg_excellent_ratio": -1, "restaurant_count": -1}},
            {"$limit": 25},
            {
                "$project": {
                    "_id": 0,
                    "cuisine": "$_id",
                    "restaurant_count": 1,
                    "avg_rating": {"$round": ["$avg_rating", 2]},
                    "avg_reviews": {"$round": ["$avg_reviews", 1]},
                    "avg_excellent_ratio": {
                        "$round": ["$avg_excellent_ratio", 4]
                    },
                }
            },
        ],
    },
]


def get_query(query_id):
    for query in V1_QUERIES:
        if query["id"] == query_id:
            return query
    raise ValueError(f"Nepoznat upit: {query_id}")


def selected_queries(query_id):
    if query_id == "all":
        return V1_QUERIES
    return [get_query(query_id)]


def collect_explain_summary(explain):
    summary = {
        "indexes_used": set(),
        "collection_scans": 0,
        "total_docs_examined_reported": 0,
        "total_keys_examined_reported": 0,
    }

    def walk(value):
        if isinstance(value, dict):
            stage = value.get("stage")
            if stage == "COLLSCAN":
                summary["collection_scans"] += 1

            index_name = value.get("indexName")
            if index_name:
                summary["indexes_used"].add(index_name)

            indexes_used = value.get("indexesUsed")
            if isinstance(indexes_used, list):
                for index in indexes_used:
                    summary["indexes_used"].add(str(index))

            docs_examined = value.get("totalDocsExamined")
            if isinstance(docs_examined, (int, float)):
                summary["total_docs_examined_reported"] += docs_examined

            keys_examined = value.get("totalKeysExamined")
            if isinstance(keys_examined, (int, float)):
                summary["total_keys_examined_reported"] += keys_examined

            collection_scans = value.get("collectionScans")
            if isinstance(collection_scans, (int, float)):
                summary["collection_scans"] += collection_scans

            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(explain)
    summary["indexes_used"] = sorted(summary["indexes_used"])
    return summary


def json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2, default=json_default)


def run_query(db, query):
    started = time.perf_counter()
    results = list(
        db[query["collection"]].aggregate(query["pipeline"], allowDiskUse=True)
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    return results, elapsed_ms


def explain_query(db, query):
    command = {
        "aggregate": query["collection"],
        "pipeline": query["pipeline"],
        "cursor": {},
        "allowDiskUse": True,
    }
    explain = db.command("explain", command, verbosity="executionStats")
    return explain, collect_explain_summary(explain)


def parse_args():
    parser = argparse.ArgumentParser(description="Pokretanje V1 MongoDB upita.")
    parser.add_argument("--uri", default=None, help="MongoDB konekcioni string.")
    parser.add_argument("--db", default=None, help="Naziv MongoDB baze.")
    parser.add_argument(
        "--query",
        default="all",
        help="ID upita koji se pokrece, na primer q01. Podrazumevano: all.",
    )
    parser.add_argument(
        "--mode",
        choices=["run", "explain", "both"],
        default="run",
        help="Da li se pokrece upit, explain ili oba.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/v1_baseline",
        help="Folder za rezultate pokretanja.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Prikazi rezultate bez cuvanja JSON fajlova.",
    )
    return parser.parse_args()


def main():
    load_dotenv()
    args = parse_args()

    mongo_uri = args.uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = args.db or os.getenv("MONGODB_DB", "tripadvisor_restaurants")
    output_dir = Path(args.output_dir)

    client = MongoClient(mongo_uri)
    client.admin.command("ping")
    db = client[db_name]

    started_at = datetime.now(timezone.utc).isoformat()
    summaries = []

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
                    {
                        "query": query_summary,
                        "results": results,
                    },
                )

        if args.mode in {"explain", "both"}:
            explain, explain_summary = explain_query(db, query)
            query_summary["explain_summary"] = explain_summary
            print(f"Indeksi: {explain_summary['indexes_used']}")
            print(f"COLLSCAN broj: {explain_summary['collection_scans']}")
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
