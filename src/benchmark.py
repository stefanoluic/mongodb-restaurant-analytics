"""Repeated, correctness-gated comparison of normalized V1 and materialized V2 queries."""

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import platform
import statistics
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from build_v2 import V2_COLLECTIONS, build_all
from query_runtime import explain_query, json_default, run_query, write_json
from validate_results import compare_results, validate_source
from v1_queries import V1_QUERIES
from v2_queries import V2_QUERIES


def summarize(samples):
    if not samples or any(not math.isfinite(v) or v <= 0 for v in samples):
        raise ValueError("Expected positive finite timing samples.")
    return {"samples_ms": samples, "median_ms": statistics.median(samples),
            "min_ms": min(samples), "max_ms": max(samples), "stdev_ms": statistics.pstdev(samples)}


def digest(rows):
    encoded = json.dumps(rows, sort_keys=True, ensure_ascii=False, default=json_default, allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def require_equal(query_id, first, second):
    check = compare_results(query_id, first, second)
    if not check["passed"]:
        raise ValueError("V1/V2 mismatch; no speedup is published: " + json.dumps(check, ensure_ascii=False))
    return check


def benchmark_database(db, *, repetitions=3, warmups=1, build_report, query_ids=None):
    if repetitions < 2 or warmups < 0:
        raise ValueError("Use at least two repetitions and a nonnegative number of warmups.")
    counts = validate_source(db)
    if build_report.get("database") != db.name or build_report.get("source_counts") != counts:
        raise ValueError("Build report must describe this database and its current source counts. Rebuild V2 first.")
    if any(db[name].count_documents({}) != build_report["materialized_counts"][name] for name in V2_COLLECTIONS):
        raise ValueError("Materialized counts changed since the recorded build.")
    selected = set(query_ids) if query_ids else {q["id"] for q in V1_QUERIES}
    if not selected.issubset(q["id"] for q in V1_QUERIES):
        raise ValueError("Unknown query selection.")
    report = {
        "format_version": 1, "started_at": datetime.now(timezone.utc).isoformat(), "passed": False,
        "database": db.name, "source_counts": counts, "build": build_report,
        "environment": {"python": platform.python_version(), "client_os": platform.system(),
                        "pymongo": importlib.metadata.version("pymongo"), "mongodb": db.client.server_info()["version"]},
        "methodology": {"repetitions": repetitions, "warmups_per_query_version": warmups,
                        "timed_operation": "aggregate and fully consume the result cursor",
                        "cache_policy": "cache not flushed; untimed warmups; version order alternates within each query",
                        "v1": "normalized collections with existing indexes",
                        "v2": "materialized collections with indexes" if build_report["includes_indexes"] else "materialized collections without added indexes",
                        "explain": "collected separately after timed runs",
                        "validation": "ordered rows, identity, fields and values checked on every paired run"},
        "pipeline_sha256": {version: {q["id"]: digest(q["pipeline"]) for q in queries if q["id"] in selected}
                            for version, queries in (("v1", V1_QUERIES), ("v2", V2_QUERIES))},
        "indexes": {name: db[name].index_information() for name in (*counts, *V2_COLLECTIONS)},
        "queries": [],
    }
    for number, (first, second) in enumerate(zip(V1_QUERIES, V2_QUERIES)):
        query_id = first["id"]
        if query_id not in selected:
            continue
        if query_id != second["id"]:
            raise ValueError("Query definitions are not paired by identifier.")
        definitions = {"v1": first, "v2": second}
        timings = {"v1": [], "v2": []}
        expected = None
        for iteration in range(warmups + repetitions):
            order = ("v1", "v2") if (number + iteration) % 2 == 0 else ("v2", "v1")
            results = {}
            for version in order:
                results[version], elapsed = run_query(db, definitions[version])
                if iteration >= warmups:
                    timings[version].append(elapsed)
            require_equal(query_id, results["v1"], results["v2"])
            if expected is not None:
                require_equal(query_id, expected, results["v1"])
            expected = results["v1"]
            print(f"{query_id}: {'warmup' if iteration < warmups else 'measured'} {iteration + 1}/{warmups + repetitions}, results match", flush=True)
        entry = {"id": query_id, "result_count": len(expected), "results_sha256": digest(expected), "validated": True,
                 "raw_results": expected}
        for version in ("v1", "v2"):
            raw, summary = explain_query(db, definitions[version])
            entry[version] = {**summarize(timings[version]), "explain_summary": summary}
            # Keep the full plan in the ignored run output, not in the compact published report.
            entry[version]["raw_explain"] = raw
        entry["read_speedup"] = entry["v1"]["median_ms"] / entry["v2"]["median_ms"]
        report["queries"].append(entry)
        print(f"{query_id}: PASS, medians {entry['v1']['median_ms']:.3f} / {entry['v2']['median_ms']:.3f} ms", flush=True)
    if validate_source(db) != counts:
        raise ValueError("Source counts changed during the benchmark. Run against a static dataset.")
    saved_ms = sum(q["v1"]["median_ms"] - q["v2"]["median_ms"] for q in report["queries"])
    report["read_only_break_even_workload_repetitions"] = (
        math.ceil(build_report["build_seconds"] * 1000 / saved_ms) if saved_ms > 0 else None)
    report["break_even_scope"] = "build cost divided by saved median read time for one execution of each selected query; excludes future refreshes"
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["passed"] = True
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uri")
    parser.add_argument("--db")
    parser.add_argument("--query", default="all", help="all or a comma-separated list such as q01,q08")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--rebuild", action="store_true", help="Replace derived V2 collections and measure their build cost.")
    parser.add_argument("--build-report", type=Path, default=Path("outputs/runs/build.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/runs/benchmark"))
    parser.add_argument("--dataset", type=Path, help="Optionally record the source CSV filename and SHA-256.")
    args = parser.parse_args()
    if args.repetitions < 2 or args.warmups < 0:
        parser.error("Use at least two repetitions and a nonnegative number of warmups.")
    load_dotenv()
    dataset = None
    if args.dataset:
        checksum = hashlib.sha256()
        with args.dataset.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                checksum.update(block)
        dataset = {"filename": args.dataset.name, "sha256": checksum.hexdigest(), "bytes": args.dataset.stat().st_size}
    try:
        with MongoClient(args.uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=5000) as client:
            db = client[args.db or os.getenv("MONGODB_DB", "restaurant_analytics")]
            if args.rebuild:
                build = build_all(db, replace=True)
                write_json(args.build_report, build)
            else:
                build = json.loads(args.build_report.read_text(encoding="utf-8"))
            report = benchmark_database(db, repetitions=args.repetitions, warmups=args.warmups, build_report=build,
                                        query_ids=None if args.query == "all" else args.query.split(","))
            report["dataset"] = dataset
        for query in report["queries"]:
            write_json(args.output_dir / "results" / f"{query['id']}.json", query.pop("raw_results"))
            for version in ("v1", "v2"):
                write_json(args.output_dir / "explain" / version / f"{query['id']}.json", query[version].pop("raw_explain"))
        write_json(args.output_dir / "report.json", report)
        print(f"PASS: report saved to {args.output_dir / 'report.json'}")
    except (ValueError, OSError, PyMongoError) as error:
        write_json(args.output_dir / "report.json", {"passed": False, "error": str(error)})
        raise SystemExit(str(error)) from error


if __name__ == "__main__":
    main()
