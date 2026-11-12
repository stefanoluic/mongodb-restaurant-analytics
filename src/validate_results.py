"""Compare ordered V1/V2 rows, including fields, group identity and numeric values."""

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from query_runtime import run_query, write_json
from v1_queries import V1_QUERIES
from v2_queries import V2_QUERIES


IDENTITIES = {
    **{f"q{i:02}": ("country", "city") for i in (1, 2, 3, 4, 7)},
    "q05": ("country", "city", "cuisine"), "q06": ("country", "city", "cuisine"),
    "q08": ("feature",), "q09": ("tag", "price_segment"), "q10": ("cuisine",),
}


def compare_results(query_id, left, right):
    differences = []

    def note(path, reason):
        if len(differences) < 5:
            differences.append({"path": path, "reason": reason})

    def compare(a, b, path):
        if isinstance(a, dict) and isinstance(b, dict):
            if a.keys() != b.keys():
                note(path, f"different fields: {sorted(a)} versus {sorted(b)}")
            for key in sorted(a.keys() & b.keys()):
                compare(a[key], b[key], path + "." + key)
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b):
                note(path, f"different lengths: {len(a)} versus {len(b)}")
            for index, (first, second) in enumerate(zip(a, b)):
                compare(first, second, f"{path}[{index}]")
        elif isinstance(a, bool) or isinstance(b, bool):
            if type(a) is not type(b) or a != b:
                note(path, "different boolean values")
        elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
            equal = a == b if isinstance(a, int) and isinstance(b, int) else (
                math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9))
            if not equal:
                note(path, f"different numbers: {a!r} versus {b!r}")
        elif type(a) is not type(b) or a != b:
            note(path, f"different values: {a!r} versus {b!r}")

    for name, rows in (("v1", left), ("v2", right)):
        fields = IDENTITIES[query_id]
        seen = set()
        for row in rows:
            if not isinstance(row, dict) or any(field not in row for field in fields):
                note(name, "missing group identity")
                continue
            identity = tuple(row[field] for field in fields)
            if identity in seen:
                note(name, "duplicate group identity")
            seen.add(identity)
    compare(left, right, query_id)
    return {"query_id": query_id, "passed": not differences, "v1_count": len(left), "v2_count": len(right), "differences": differences}


def validate_database(db, query_ids=None):
    selected = set(query_ids) if query_ids is not None else set(IDENTITIES)
    if not selected or not selected.issubset(IDENTITIES):
        raise ValueError("Select at least one known query.")
    validate_source(db)
    results = []
    for first, second in zip(V1_QUERIES, V2_QUERIES):
        if first["id"] not in selected:
            continue
        v1, _ = run_query(db, first)
        v2, _ = run_query(db, second)
        check = compare_results(first["id"], v1, v2)
        results.append(check)
        print(f"{first['id']}: {'PASS' if check['passed'] else 'FAIL'} ({len(v1)} / {len(v2)} rows)", flush=True)
    return {"validated_at": datetime.now(timezone.utc).isoformat(), "passed": all(q["passed"] for q in results), "queries": results}


def validate_source(db):
    names = ("restaurants", "restaurant_locations", "restaurant_ratings", "restaurant_classifications")
    counts = {name: db[name].count_documents({}) for name in names}
    if not counts["restaurants"] or len(set(counts.values())) != 1:
        raise ValueError("V1 must contain matching, nonempty source collections; import the dataset first.")
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri")
    parser.add_argument("--db")
    parser.add_argument("--output", default="outputs/runs/validation.json")
    parser.add_argument("--v1-results", type=Path, help="Optionally validate saved results folders instead of executing queries.")
    parser.add_argument("--v2-results", type=Path)
    args = parser.parse_args()
    load_dotenv()
    if bool(args.v1_results) != bool(args.v2_results):
        parser.error("Provide both saved result folders, or neither.")
    if args.v1_results:
        checks = [compare_results(q, json.loads((args.v1_results / f"{q}.json").read_text(encoding="utf-8"))["results"],
                                  json.loads((args.v2_results / f"{q}.json").read_text(encoding="utf-8"))["results"])
                  for q in IDENTITIES]
        report = {"passed": all(q["passed"] for q in checks), "queries": checks}
    else:
        with MongoClient(args.uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=5000) as client:
            report = validate_database(client[args.db or os.getenv("MONGODB_DB", "restaurant_analytics")])
    write_json(args.output, report)
    print(f"Validation {'passed' if report['passed'] else 'failed'}; report: {args.output}")
    raise SystemExit(0 if report["passed"] else 1)


if __name__ == "__main__":
    main()
