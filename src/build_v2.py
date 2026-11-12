import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import ASCENDING, DESCENDING, MongoClient

from v1_queries import MAJOR_TOURIST_CITIES


V2_COLLECTIONS = [
    "city_offer_stats",
    "city_cuisine_stats",
    "classification_signal_stats",
    "cuisine_quality_stats",
]


def key(*parts):
    return "||".join(str(part) for part in parts)


def average_where(field, predicate):
    return {"$avg": {"$cond": [predicate, field, None]}}


def empty_city_doc(country, city):
    return {
        "_id": key(country, city),
        "country": country,
        "city": city,
    }


def empty_city_cuisine_doc(country, city, cuisine):
    return {
        "_id": key(country, city, cuisine),
        "country": country,
        "city": city,
        "cuisine": cuisine,
    }


def run_aggregation(db, collection_name, pipeline, label):
    started = time.perf_counter()
    results = list(db[collection_name].aggregate(pipeline, allowDiskUse=True))
    elapsed = round(time.perf_counter() - started, 2)
    print(f"{label}: {len(results)} dokumenata, {elapsed} s")
    return results


def insert_documents(collection, documents):
    if not documents:
        return
    collection.insert_many(list(documents), ordered=False)


def build_city_offer_stats(db):
    docs = {}

    total_pipeline = [
        {"$match": {"country": {"$ne": None}, "city": {"$ne": None}}},
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
                "from": "restaurant_ratings",
                "localField": "_id",
                "foreignField": "_id",
                "as": "rating",
            }
        },
        {"$unwind": "$rating"},
        {
            "$lookup": {
                "from": "restaurant_classifications",
                "localField": "_id",
                "foreignField": "_id",
                "as": "classification",
            }
        },
        {"$unwind": "$classification"},
        {
            "$group": {
                "_id": {"country": "$country", "city": "$city"},
                "total_restaurants": {"$sum": 1},
                "rated_restaurants": {
                    "$sum": {"$cond": [{"$ne": ["$rating.avg_rating", None]}, 1, 0]}
                },
                "avg_city_rating": {"$avg": "$rating.avg_rating"},
                "avg_city_reviews": {"$avg": "$rating.total_reviews_count"},
                "known_price_count_all": {
                    "$sum": {
                        "$cond": [{"$ne": ["$restaurant.price_score", None]}, 1, 0]
                    }
                },
                "low_price_count": {
                    "$sum": {"$cond": [{"$eq": ["$restaurant.price_score", 1]}, 1, 0]}
                },
                "mid_price_count": {
                    "$sum": {"$cond": [{"$eq": ["$restaurant.price_score", 2]}, 1, 0]}
                },
                "high_price_count": {
                    "$sum": {"$cond": [{"$eq": ["$restaurant.price_score", 3]}, 1, 0]}
                },
                "vegetarian_total_count": {
                    "$sum": {
                        "$cond": [{"$eq": ["$classification.vegetarian_friendly", True]}, 1, 0]
                    }
                },
                "vegan_total_count": {
                    "$sum": {
                        "$cond": [{"$eq": ["$classification.vegan_options", True]}, 1, 0]
                    }
                },
                "gluten_free_total_count": {
                    "$sum": {
                        "$cond": [{"$eq": ["$classification.gluten_free", True]}, 1, 0]
                    }
                },
                "lunch_count": {
                    "$sum": {"$cond": [{"$in": ["Lunch", "$classification.meals"]}, 1, 0]}
                },
                "dinner_count": {
                    "$sum": {"$cond": [{"$in": ["Dinner", "$classification.meals"]}, 1, 0]}
                },
                "lunch_dinner_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$in": ["Lunch", "$classification.meals"]},
                                    {"$in": ["Dinner", "$classification.meals"]},
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
                "avg_food_rating": {"$avg": "$rating.category_ratings.food"},
                "avg_service_rating": {"$avg": "$rating.category_ratings.service"},
                "avg_value_rating_all": {"$avg": "$rating.category_ratings.value"},
            }
        },
    ]
    for item in run_aggregation(
        db, "restaurant_locations", total_pipeline, "city_offer_stats total"
    ):
        country = item["_id"]["country"]
        city = item["_id"]["city"]
        doc = docs.setdefault(key(country, city), empty_city_doc(country, city))
        doc["total_restaurants"] = item["total_restaurants"]
        doc["rated_restaurants"] = item["rated_restaurants"]
        doc["avg_city_rating"] = item.get("avg_city_rating")
        doc["avg_city_reviews"] = item.get("avg_city_reviews")
        doc["known_price_count_all"] = item["known_price_count_all"]
        doc["low_price_count"] = item["low_price_count"]
        doc["mid_price_count"] = item["mid_price_count"]
        doc["high_price_count"] = item["high_price_count"]
        doc["vegetarian_total_count"] = item["vegetarian_total_count"]
        doc["vegan_total_count"] = item["vegan_total_count"]
        doc["gluten_free_total_count"] = item["gluten_free_total_count"]
        doc["lunch_count"] = item["lunch_count"]
        doc["dinner_count"] = item["dinner_count"]
        doc["lunch_dinner_count"] = item["lunch_dinner_count"]
        doc["avg_food_rating"] = item.get("avg_food_rating")
        doc["avg_service_rating"] = item.get("avg_service_rating")
        doc["avg_value_rating_all"] = item.get("avg_value_rating_all")

    diet_pipeline = [
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
        {"$match": {"location.country": {"$ne": None}, "location.city": {"$ne": None}}},
        {
            "$group": {
                "_id": {"country": "$location.country", "city": "$location.city"},
                "count": {"$sum": 1},
                "avg_rating": {"$avg": "$rating.avg_rating"},
                "avg_reviews": {"$avg": "$rating.total_reviews_count"},
            }
        },
    ]
    for item in run_aggregation(
        db, "restaurant_classifications", diet_pipeline, "city_offer_stats q01"
    ):
        country = item["_id"]["country"]
        city = item["_id"]["city"]
        doc = docs.setdefault(key(country, city), empty_city_doc(country, city))
        doc["diet_friendly_high_rated_count"] = item["count"]
        doc["diet_friendly_avg_rating"] = item["avg_rating"]
        doc["diet_friendly_avg_reviews"] = item["avg_reviews"]

    gluten_pipeline = [
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
        {"$match": {"location.country": {"$ne": None}, "location.city": {"$ne": None}}},
        {
            "$group": {
                "_id": {"country": "$location.country", "city": "$location.city"},
                "count": {"$sum": 1},
                "avg_rating": {"$avg": "$rating.avg_rating"},
                "avg_reviews": {"$avg": "$rating.total_reviews_count"},
            }
        },
    ]
    for item in run_aggregation(
        db, "restaurant_classifications", gluten_pipeline, "city_offer_stats q02"
    ):
        country = item["_id"]["country"]
        city = item["_id"]["city"]
        doc = docs.setdefault(key(country, city), empty_city_doc(country, city))
        doc["gluten_free_high_rated_count"] = item["count"]
        doc["gluten_free_avg_rating"] = item["avg_rating"]
        doc["gluten_free_avg_reviews"] = item["avg_reviews"]

    value_pipeline = [
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
        {"$match": {"location.country": {"$ne": None}, "location.city": {"$ne": None}}},
        {
            "$addFields": {
                "value_for_money": {
                    "$divide": [
                        {"$avg": ["$rating.avg_rating", "$rating.category_ratings.value"]},
                        "$restaurant.price_score",
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": {"country": "$location.country", "city": "$location.city"},
                "count": {"$sum": 1},
                "avg_rating": {"$avg": "$rating.avg_rating"},
                "avg_value_rating": {"$avg": "$rating.category_ratings.value"},
                "avg_price_score": {"$avg": "$restaurant.price_score"},
                "avg_value_for_money": {"$avg": "$value_for_money"},
            }
        },
    ]
    for item in run_aggregation(
        db, "restaurant_classifications", value_pipeline, "city_offer_stats q03"
    ):
        country = item["_id"]["country"]
        city = item["_id"]["city"]
        doc = docs.setdefault(key(country, city), empty_city_doc(country, city))
        doc["affordable_lunch_dinner_count"] = item["count"]
        doc["affordable_avg_rating"] = item["avg_rating"]
        doc["avg_value_rating"] = item["avg_value_rating"]
        doc["avg_price_score"] = item["avg_price_score"]
        doc["avg_value_for_money"] = item["avg_value_for_money"]

    gap_pipeline = [
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
        {"$match": {"location.country": {"$ne": None}, "location.city": {"$ne": None}}},
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
                "_id": {"country": "$location.country", "city": "$location.city"},
                "count": {"$sum": 1},
                "avg_food": {"$avg": "$category_ratings.food"},
                "avg_service": {"$avg": "$category_ratings.service"},
                "avg_value": {"$avg": "$category_ratings.value"},
                "avg_gap": {"$avg": "$food_service_gap"},
                "avg_reviews": {"$avg": "$total_reviews_count"},
                "avg_price_score": {"$avg": "$restaurant.price_score"},
            }
        },
    ]
    for item in run_aggregation(
        db, "restaurant_ratings", gap_pipeline, "city_offer_stats q04"
    ):
        country = item["_id"]["country"]
        city = item["_id"]["city"]
        doc = docs.setdefault(key(country, city), empty_city_doc(country, city))
        doc["expensive_food_service_gap_count"] = item["count"]
        doc["expensive_avg_food"] = item["avg_food"]
        doc["expensive_avg_service"] = item["avg_service"]
        doc["expensive_avg_value"] = item["avg_value"]
        doc["expensive_avg_gap"] = item["avg_gap"]
        doc["expensive_avg_reviews"] = item["avg_reviews"]
        doc["expensive_avg_price_score"] = item["avg_price_score"]

    premium_pipeline = [
        {"$match": {"avg_rating": {"$gte": 4.2}, "total_reviews_count": {"$gte": 100}}},
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
        {"$match": {"location.country": {"$ne": None}, "location.city": {"$ne": None}}},
        {
            "$group": {
                "_id": {"country": "$location.country", "city": "$location.city"},
                "quality_demand_count": {"$sum": 1},
                "known_price_count": {
                    "$sum": {
                        "$cond": [{"$ne": ["$restaurant.price_score", None]}, 1, 0]
                    }
                },
                "premium_restaurant_count": {
                    "$sum": {
                        "$cond": [{"$eq": ["$restaurant.price_score", 3]}, 1, 0]
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
    ]
    for item in run_aggregation(
        db, "restaurant_ratings", premium_pipeline, "city_offer_stats q07"
    ):
        country = item["_id"]["country"]
        city = item["_id"]["city"]
        doc = docs.setdefault(key(country, city), empty_city_doc(country, city))
        doc["quality_demand_count"] = item["quality_demand_count"]
        doc["known_price_count"] = item["known_price_count"]
        doc["premium_restaurant_count"] = item["premium_restaurant_count"]
        doc["premium_share"] = item.get("premium_share")
        doc["premium_avg_rating"] = item["avg_rating"]
        doc["premium_avg_reviews"] = item["avg_reviews"]

    db.city_offer_stats.drop()
    insert_documents(db.city_offer_stats, docs.values())
    print(f"city_offer_stats upisano: {db.city_offer_stats.estimated_document_count()}")


def build_city_cuisine_stats(db):
    docs = {}

    base_lookup = [
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
            "$lookup": {
                "from": "restaurant_classifications",
                "localField": "_id",
                "foreignField": "_id",
                "as": "classification",
            }
        },
        {"$unwind": "$classification"},
        {"$unwind": "$classification.cuisines"},
    ]

    general_pipeline = [
        {"$match": {"country": {"$ne": None}, "city": {"$in": MAJOR_TOURIST_CITIES}}},
        *base_lookup,
        {
            "$group": {
                "_id": {
                    "country": "$country",
                    "city": "$city",
                    "cuisine": "$classification.cuisines",
                },
                "total_restaurants": {"$sum": 1},
                "rated_restaurants": {
                    "$sum": {"$cond": [{"$ne": ["$rating.avg_rating", None]}, 1, 0]}
                },
                "avg_rating": {"$avg": "$rating.avg_rating"},
                "avg_reviews": {"$avg": "$rating.total_reviews_count"},
                "high_rated_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$gte": ["$rating.avg_rating", 4.2]},
                                    {"$gte": ["$rating.total_reviews_count", 50]},
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
            }
        },
    ]
    for item in run_aggregation(
        db, "restaurant_locations", general_pipeline, "city_cuisine_stats general"
    ):
        country = item["_id"]["country"]
        city = item["_id"]["city"]
        cuisine = item["_id"]["cuisine"]
        doc = docs.setdefault(
            key(country, city, cuisine), empty_city_cuisine_doc(country, city, cuisine)
        )
        doc["total_restaurants"] = item["total_restaurants"]
        doc["rated_restaurants"] = item["rated_restaurants"]
        doc["avg_rating"] = item.get("avg_rating")
        doc["avg_reviews"] = item.get("avg_reviews")
        doc["high_rated_count"] = item["high_rated_count"]

    tourism_pipeline = [
        {"$match": {"country": {"$ne": None}, "city": {"$in": MAJOR_TOURIST_CITIES}}},
        *base_lookup,
        {"$match": {"rating.avg_rating": {"$gte": 4.0}, "rating.total_reviews_count": {"$gte": 30}}},
        {
            "$group": {
                "_id": {"country": "$country", "city": "$city", "cuisine": "$classification.cuisines"},
                "count": {"$sum": 1},
                "avg_rating": {"$avg": "$rating.avg_rating"},
                "avg_reviews": {"$avg": "$rating.total_reviews_count"},
            }
        },
    ]
    for item in run_aggregation(
        db, "restaurant_locations", tourism_pipeline, "city_cuisine_stats q05"
    ):
        country = item["_id"]["country"]
        city = item["_id"]["city"]
        cuisine = item["_id"]["cuisine"]
        doc = docs.setdefault(
            key(country, city, cuisine), empty_city_cuisine_doc(country, city, cuisine)
        )
        doc["tourism_restaurant_count"] = item["count"]
        doc["tourism_avg_rating"] = item["avg_rating"]
        doc["tourism_avg_reviews"] = item["avg_reviews"]

    investor_pipeline = [
        {"$match": {"country": {"$ne": None}, "city": {"$in": MAJOR_TOURIST_CITIES}}},
        *base_lookup,
        {"$match": {"rating.avg_rating": {"$gte": 4.2}, "rating.total_reviews_count": {"$gte": 50}}},
        {
            "$group": {
                "_id": {"country": "$country", "city": "$city", "cuisine": "$classification.cuisines"},
                "count": {"$sum": 1},
                "avg_rating": {"$avg": "$rating.avg_rating"},
                "avg_reviews": {"$avg": "$rating.total_reviews_count"},
            }
        },
    ]
    for item in run_aggregation(
        db, "restaurant_locations", investor_pipeline, "city_cuisine_stats q06"
    ):
        country = item["_id"]["country"]
        city = item["_id"]["city"]
        cuisine = item["_id"]["cuisine"]
        doc = docs.setdefault(
            key(country, city, cuisine), empty_city_cuisine_doc(country, city, cuisine)
        )
        doc["investor_restaurant_count"] = item["count"]
        doc["investor_avg_rating"] = item["avg_rating"]
        doc["investor_avg_reviews"] = item["avg_reviews"]

    city_context = {
        (doc["country"], doc["city"]): doc
        for doc in db.city_offer_stats.find(
            {},
            {
                "_id": 0,
                "country": 1,
                "city": 1,
                "total_restaurants": 1,
                "avg_city_rating": 1,
                "avg_city_reviews": 1,
            },
        )
    }
    for doc in docs.values():
        context = city_context.get((doc["country"], doc["city"]), {})
        doc["city_total_restaurants"] = context.get("total_restaurants")
        doc["city_avg_rating"] = context.get("avg_city_rating")
        doc["city_avg_reviews"] = context.get("avg_city_reviews")

    db.city_cuisine_stats.drop()
    insert_documents(db.city_cuisine_stats, docs.values())
    print(f"city_cuisine_stats upisano: {db.city_cuisine_stats.estimated_document_count()}")


def build_classification_signal_stats(db):
    docs = []
    successful = {"$and": [{"$gte": ["$avg_rating", 4.5]}, {"$gte": ["$total_reviews_count", 100]}]}

    feature_pipeline = [
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
                "total_restaurant_count": {"$sum": 1},
                "rated_restaurant_count": {
                    "$sum": {"$cond": [{"$ne": ["$avg_rating", None]}, 1, 0]}
                },
                "successful_restaurant_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$gte": ["$avg_rating", 4.5]},
                                    {"$gte": ["$total_reviews_count", 100]},
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
                "avg_rating": {"$avg": "$avg_rating"},
                "avg_reviews": {"$avg": "$total_reviews_count"},
                "avg_value_rating": {"$avg": "$category_ratings.value"},
                "cities": {"$addToSet": "$location.city"},
                "successful_avg_rating": average_where("$avg_rating", successful),
                "successful_avg_reviews": average_where("$total_reviews_count", successful),
                "successful_avg_value_rating": average_where("$category_ratings.value", successful),
                "successful_cities": {"$addToSet": {"$cond": [successful, "$location.city", None]}},
            }
        },
        {"$addFields": {
            "city_count": {"$size": "$cities"},
            "successful_city_count": {"$size": {"$setDifference": ["$successful_cities", [None]]}},
        }},
    ]
    for item in run_aggregation(
        db, "restaurant_ratings", feature_pipeline, "classification_signal_stats q08"
    ):
        feature = item["_id"]
        docs.append(
            {
                "_id": key("feature", "major_tourist_cities", feature),
                "signal_type": "feature",
                "signal_value": feature,
                "scope": "major_tourist_cities",
                "total_restaurant_count": item["total_restaurant_count"],
                "rated_restaurant_count": item["rated_restaurant_count"],
                "successful_restaurant_count": item["successful_restaurant_count"],
                "avg_rating": item["avg_rating"],
                "avg_reviews": item["avg_reviews"],
                "avg_value_rating": item.get("avg_value_rating"),
                "city_count": item["city_count"],
                "successful_avg_rating": item["successful_avg_rating"],
                "successful_avg_reviews": item["successful_avg_reviews"],
                "successful_avg_value_rating": item["successful_avg_value_rating"],
                "successful_city_count": item["successful_city_count"],
            }
        )

    tag_pipeline = [
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
                            {"case": {"$eq": ["$restaurant.price_score", 1]}, "then": "nizi"},
                            {"case": {"$eq": ["$restaurant.price_score", 2]}, "then": "srednji"},
                            {"case": {"$eq": ["$restaurant.price_score", 3]}, "then": "visi"},
                        ],
                        "default": "nepoznat",
                    }
                }
            }
        },
        {
            "$group": {
                "_id": {"tag": "$classification.top_tags", "price_segment": "$price_segment"},
                "total_restaurant_count": {"$sum": 1},
                "rated_restaurant_count": {
                    "$sum": {"$cond": [{"$ne": ["$avg_rating", None]}, 1, 0]}
                },
                "successful_restaurant_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$gte": ["$avg_rating", 4.5]},
                                    {"$gte": ["$total_reviews_count", 100]},
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
                "avg_rating": {"$avg": "$avg_rating"},
                "avg_reviews": {"$avg": "$total_reviews_count"},
                "avg_price_score": {"$avg": "$restaurant.price_score"},
                "successful_avg_rating": average_where("$avg_rating", successful),
                "successful_avg_reviews": average_where("$total_reviews_count", successful),
                "successful_avg_price_score": average_where("$restaurant.price_score", successful),
            }
        },
    ]
    for item in run_aggregation(
        db, "restaurant_ratings", tag_pipeline, "classification_signal_stats q09"
    ):
        tag = item["_id"]["tag"]
        price_segment = item["_id"]["price_segment"]
        docs.append(
            {
                "_id": key("top_tag", price_segment, tag),
                "signal_type": "top_tag",
                "signal_value": tag,
                "scope": "all",
                "price_segment": price_segment,
                "total_restaurant_count": item["total_restaurant_count"],
                "rated_restaurant_count": item["rated_restaurant_count"],
                "successful_restaurant_count": item["successful_restaurant_count"],
                "avg_rating": item["avg_rating"],
                "avg_reviews": item["avg_reviews"],
                "avg_price_score": item.get("avg_price_score"),
                "successful_avg_rating": item["successful_avg_rating"],
                "successful_avg_reviews": item["successful_avg_reviews"],
                "successful_avg_price_score": item["successful_avg_price_score"],
            }
        )

    db.classification_signal_stats.drop()
    insert_documents(db.classification_signal_stats, docs)
    print(
        "classification_signal_stats upisano: "
        f"{db.classification_signal_stats.estimated_document_count()}"
    )


def build_cuisine_quality_stats(db):
    qualified = {"$and": [{"$gte": ["$total_reviews_count", 100]}, {"$ne": ["$review_distribution.excellent", None]}]}
    pipeline = [
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
                    "$cond": [
                        {
                            "$and": [
                                {"$ne": ["$review_distribution.excellent", None]},
                                {"$gt": ["$total_reviews_count", 0]},
                            ]
                        },
                        {
                            "$divide": [
                                "$review_distribution.excellent",
                                "$total_reviews_count",
                            ]
                        },
                        None,
                    ]
                }
            }
        },
        {
            "$group": {
                "_id": "$classification.cuisines",
                "total_restaurant_count": {"$sum": 1},
                "restaurant_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$gte": ["$total_reviews_count", 100]},
                                    {"$ne": ["$review_distribution.excellent", None]},
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
                "rated_restaurant_count": {
                    "$sum": {"$cond": [{"$ne": ["$avg_rating", None]}, 1, 0]}
                },
                "high_rated_count": {
                    "$sum": {
                        "$cond": [
                            {
                                "$and": [
                                    {"$gte": ["$avg_rating", 4.2]},
                                    {"$gte": ["$total_reviews_count", 50]},
                                ]
                            },
                            1,
                            0,
                        ]
                    }
                },
                "avg_rating": {"$avg": "$avg_rating"},
                "avg_reviews": {"$avg": "$total_reviews_count"},
                "avg_excellent_ratio": {"$avg": "$excellent_ratio"},
                "qualified_avg_rating": average_where("$avg_rating", qualified),
                "qualified_avg_reviews": average_where("$total_reviews_count", qualified),
                "qualified_avg_excellent_ratio": average_where("$excellent_ratio", qualified),
            }
        },
        {
            "$project": {
                "_id": "$_id",
                "cuisine": "$_id",
                "total_restaurant_count": 1,
                "restaurant_count": 1,
                "rated_restaurant_count": 1,
                "high_rated_count": 1,
                "avg_rating": 1,
                "avg_reviews": 1,
                "avg_excellent_ratio": 1,
                "qualified_avg_rating": 1,
                "qualified_avg_reviews": 1,
                "qualified_avg_excellent_ratio": 1,
            }
        },
    ]
    docs = run_aggregation(
        db, "restaurant_ratings", pipeline, "cuisine_quality_stats q10"
    )
    db.cuisine_quality_stats.drop()
    insert_documents(db.cuisine_quality_stats, docs)
    print(f"cuisine_quality_stats upisano: {db.cuisine_quality_stats.estimated_document_count()}")


def create_indexes(db):
    db.city_offer_stats.create_index(
        [
            ("diet_friendly_high_rated_count", DESCENDING),
            ("diet_friendly_avg_rating", DESCENDING),
            ("country", ASCENDING),
            ("city", ASCENDING),
        ],
        name="q01_diet_city_rank",
    )
    db.city_offer_stats.create_index(
        [
            ("gluten_free_high_rated_count", DESCENDING),
            ("gluten_free_avg_rating", DESCENDING),
            ("country", ASCENDING),
            ("city", ASCENDING),
        ],
        name="q02_gluten_city_rank",
    )
    db.city_offer_stats.create_index(
        [
            ("avg_value_for_money", DESCENDING),
            ("affordable_lunch_dinner_count", DESCENDING),
            ("country", ASCENDING),
            ("city", ASCENDING),
        ],
        name="q03_value_city_rank",
    )
    db.city_offer_stats.create_index(
        [
            ("expensive_avg_gap", DESCENDING),
            ("expensive_avg_value", ASCENDING),
            ("expensive_food_service_gap_count", DESCENDING),
            ("country", ASCENDING),
            ("city", ASCENDING),
        ],
        name="q04_gap_city_rank",
    )
    db.city_offer_stats.create_index(
        [
            ("quality_demand_count", DESCENDING),
            ("premium_share", ASCENDING),
            ("premium_avg_rating", DESCENDING),
            ("country", ASCENDING),
            ("city", ASCENDING),
        ],
        name="q07_premium_city_rank",
    )
    db.city_cuisine_stats.create_index(
        [
            ("tourism_restaurant_count", DESCENDING),
            ("tourism_avg_rating", DESCENDING),
            ("country", ASCENDING),
            ("city", ASCENDING),
            ("cuisine", ASCENDING),
        ],
        name="q05_city_cuisine_rank",
    )
    db.city_cuisine_stats.create_index(
        [
            ("investor_avg_rating", DESCENDING),
            ("investor_avg_reviews", DESCENDING),
            ("country", ASCENDING),
            ("city", ASCENDING),
            ("cuisine", ASCENDING),
        ],
        name="q06_underrepresented_rank",
    )
    db.classification_signal_stats.create_index(
        [
            ("signal_type", ASCENDING),
            ("scope", ASCENDING),
            ("successful_restaurant_count", DESCENDING),
            ("successful_avg_rating", DESCENDING),
            ("signal_value", ASCENDING),
        ],
        name="q08_signal_feature_rank",
    )
    db.classification_signal_stats.create_index(
        [
            ("signal_type", ASCENDING),
            ("successful_restaurant_count", DESCENDING),
            ("successful_avg_rating", DESCENDING),
            ("signal_value", ASCENDING),
            ("price_segment", ASCENDING),
        ],
        name="q09_signal_tag_price_rank",
    )
    db.cuisine_quality_stats.create_index(
        [
            ("qualified_avg_excellent_ratio", DESCENDING),
            ("restaurant_count", DESCENDING),
            ("cuisine", ASCENDING),
        ],
        name="q10_cuisine_quality_rank",
    )
    print("V2 indeksi kreirani")


def build_all(db, *, replace=False, skip_indexes=False):
    existing = [name for name in V2_COLLECTIONS if db[name].estimated_document_count()]
    if existing and not replace:
        raise ValueError("V2 collections already contain data. Use --replace to rebuild derived collections only.")
    source_names = ("restaurants", "restaurant_locations", "restaurant_ratings", "restaurant_classifications")
    source_counts = {name: db[name].count_documents({}) for name in source_names}
    if not source_counts["restaurants"] or len(set(source_counts.values())) != 1:
        raise ValueError("Import a complete V1 dataset before building V2; all four source counts must match.")
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    build_city_offer_stats(db)
    build_city_cuisine_stats(db)
    build_classification_signal_stats(db)
    build_cuisine_quality_stats(db)
    if not skip_indexes:
        create_indexes(db)
    elapsed = time.perf_counter() - started
    return {
        "schema_version": 2, "started_at": started_at, "database": db.name,
        "build_seconds": elapsed, "includes_indexes": not skip_indexes,
        "source_counts": source_counts,
        "materialized_counts": {name: db[name].count_documents({}) for name in V2_COLLECTIONS},
    }


def parse_args():
    parser = argparse.ArgumentParser(description="Izgradnja MongoDB V2 seme.")
    parser.add_argument("--uri", default=None, help="MongoDB konekcioni string.")
    parser.add_argument("--db", default=None, help="Naziv MongoDB baze.")
    parser.add_argument("--skip-indexes", action="store_true")
    parser.add_argument("--replace", action="store_true", help="Replace existing derived V2 collections; V1 is preserved.")
    parser.add_argument("--report", default="outputs/runs/build.json", help="Save build time and collection counts.")
    return parser.parse_args()


def main():
    load_dotenv()
    args = parse_args()

    mongo_uri = args.uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = args.db or os.getenv("MONGODB_DB", "restaurant_analytics")

    with MongoClient(mongo_uri, serverSelectionTimeoutMS=5000) as client:
        client.admin.command("ping")
        report = build_all(client[db_name], replace=args.replace, skip_indexes=args.skip_indexes)
    path = Path(args.report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"V2 built in {report['build_seconds']:.3f} s; report: {path}")


if __name__ == "__main__":
    main()
