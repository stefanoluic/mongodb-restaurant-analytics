import argparse
import json
import math
import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from pymongo import MongoClient
from tqdm import tqdm


V1_COLLECTIONS = [
    "restaurants",
    "restaurant_locations",
    "restaurant_ratings",
    "restaurant_classifications",
]

PRICE_SCORE_BY_LENGTH = {
    1: 1,
    4: 3,
}


def clean_value(value):
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return value


def clean_number(value):
    value = clean_value(value)
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def clean_bool(value):
    value = clean_value(value)
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"y", "yes", "true", "1", "claimed"}:
        return True
    if normalized in {"n", "no", "false", "0", "unclaimed"}:
        return False
    return None


def split_list(value):
    value = clean_value(value)
    if value is None:
        return []
    return [part.strip() for part in str(value).split(",") if part.strip()]


def parse_json_or_original(value):
    value = clean_value(value)
    if value is None:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return value


def price_score(price_level):
    price_level = clean_value(price_level)
    if price_level is None:
        return None
    if "-" in price_level:
        return 2
    return PRICE_SCORE_BY_LENGTH.get(len(price_level))


def geojson_point(latitude, longitude):
    if latitude is None or longitude is None:
        return None
    return {
        "type": "Point",
        "coordinates": [longitude, latitude],
    }


def build_documents(row):
    restaurant_id = clean_value(row.get("restaurant_link"))
    if restaurant_id is None:
        return None

    latitude = clean_number(row.get("latitude"))
    longitude = clean_number(row.get("longitude"))
    claimed_status = clean_value(row.get("claimed"))
    price_level = clean_value(row.get("price_level"))

    restaurants = {
        "_id": restaurant_id,
        "restaurant_id": restaurant_id,
        "restaurant_name": clean_value(row.get("restaurant_name")),
        "claimed_status": claimed_status,
        "is_claimed": clean_bool(claimed_status),
        "price_level": price_level,
        "price_score": price_score(price_level),
        "price_range": clean_value(row.get("price_range")),
        "awards": split_list(row.get("awards")),
        "original_open_hours": parse_json_or_original(row.get("original_open_hours")),
        "open_days_per_week": clean_number(row.get("open_days_per_week")),
        "open_hours_per_week": clean_number(row.get("open_hours_per_week")),
        "working_shifts_per_week": clean_number(row.get("working_shifts_per_week")),
    }

    locations = {
        "_id": restaurant_id,
        "restaurant_id": restaurant_id,
        "country": clean_value(row.get("country")),
        "region": clean_value(row.get("region")),
        "province": clean_value(row.get("province")),
        "city": clean_value(row.get("city")),
        "address": clean_value(row.get("address")),
        "latitude": latitude,
        "longitude": longitude,
        "location": geojson_point(latitude, longitude),
    }

    ratings = {
        "_id": restaurant_id,
        "restaurant_id": restaurant_id,
        "avg_rating": clean_number(row.get("avg_rating")),
        "total_reviews_count": clean_number(row.get("total_reviews_count")),
        "default_language": clean_value(row.get("default_language")),
        "reviews_count_in_default_language": clean_number(
            row.get("reviews_count_in_default_language")
        ),
        "review_distribution": {
            "excellent": clean_number(row.get("excellent")),
            "very_good": clean_number(row.get("very_good")),
            "average": clean_number(row.get("average")),
            "poor": clean_number(row.get("poor")),
            "terrible": clean_number(row.get("terrible")),
        },
        "category_ratings": {
            "food": clean_number(row.get("food")),
            "service": clean_number(row.get("service")),
            "value": clean_number(row.get("value")),
            "atmosphere": clean_number(row.get("atmosphere")),
        },
    }

    classifications = {
        "_id": restaurant_id,
        "restaurant_id": restaurant_id,
        "top_tags": split_list(row.get("top_tags")),
        "meals": split_list(row.get("meals")),
        "cuisines": split_list(row.get("cuisines")),
        "special_diets": split_list(row.get("special_diets")),
        "features": split_list(row.get("features")),
        "vegetarian_friendly": clean_bool(row.get("vegetarian_friendly")),
        "vegan_options": clean_bool(row.get("vegan_options")),
        "gluten_free": clean_bool(row.get("gluten_free")),
        "keywords": split_list(row.get("keywords")),
    }

    return {
        "restaurants": restaurants,
        "restaurant_locations": locations,
        "restaurant_ratings": ratings,
        "restaurant_classifications": classifications,
    }


def insert_batch(db, rows):
    grouped_documents = {collection: [] for collection in V1_COLLECTIONS}

    for row in rows:
        documents = build_documents(row)
        if documents is None:
            continue
        for collection_name, document in documents.items():
            grouped_documents[collection_name].append(document)

    inserted = 0
    for collection_name, documents in grouped_documents.items():
        if documents:
            db[collection_name].insert_many(documents, ordered=False)
            inserted = max(inserted, len(documents))
    return inserted


def parse_args():
    parser = argparse.ArgumentParser(description="Uvoz CSV skupa u MongoDB V1 semu.")
    parser.add_argument("--csv", default=None, help="Putanja do CSV fajla.")
    parser.add_argument("--uri", default=None, help="MongoDB konekcioni string.")
    parser.add_argument("--db", default=None, help="Naziv MongoDB baze.")
    parser.add_argument("--chunk-size", type=int, default=10000)
    parser.add_argument("--limit", type=int, default=None, help="Probni uvoz samo prvih N redova.")
    parser.add_argument("--drop", action="store_true", help="Obrisi V1 kolekcije pre uvoza.")
    args = parser.parse_args()
    if args.chunk_size <= 0 or (args.limit is not None and args.limit <= 0):
        parser.error("Chunk size and an optional row limit must be positive.")
    return args


def main():
    load_dotenv()
    args = parse_args()

    csv_path = Path(
        args.csv or os.getenv("CSV_PATH", "data/tripadvisor_european_restaurants.csv")
    )
    mongo_uri = args.uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
    db_name = args.db or os.getenv("MONGODB_DB", "restaurant_analytics")

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV fajl nije pronadjen: {csv_path}")

    if "restaurant_link" not in pd.read_csv(csv_path, nrows=0).columns:
        raise ValueError("CSV must contain the restaurant_link identifier column.")
    with MongoClient(mongo_uri, serverSelectionTimeoutMS=5000) as client:
        client.admin.command("ping")
        db = client[db_name]
        if not args.drop and any(db[name].estimated_document_count() for name in V1_COLLECTIONS):
            raise ValueError("V1 already contains data. Choose an empty database or use --drop to replace V1.")
        if args.drop:
            for collection_name in V1_COLLECTIONS:
                db[collection_name].drop()

        total_rows = 0
        inserted_rows = 0
        with pd.read_csv(csv_path, chunksize=args.chunk_size, low_memory=False) as reader:
            with tqdm(desc="Importing V1", unit="rows") as progress:
                for chunk in reader:
                    if args.limit is not None:
                        remaining = args.limit - total_rows
                        if remaining <= 0:
                            break
                        chunk = chunk.head(remaining)
                    rows = chunk.to_dict("records")
                    inserted_rows += insert_batch(db, rows)
                    total_rows += len(rows)
                    progress.update(len(rows))

        print(f"Processed rows: {total_rows}; imported: {inserted_rows}; skipped without an ID: {total_rows - inserted_rows}")
        print(f"Database: {db_name}")
        for name in V1_COLLECTIONS:
            print(f"- {name}: {db[name].estimated_document_count()}")
        print("Rebuild V2 after importing or replacing source data.")


if __name__ == "__main__":
    main()
