"""Execution and explain helpers shared by both query versions."""

import json
import time
from datetime import datetime
from pathlib import Path


def json_default(value):
    return value.isoformat() if isinstance(value, datetime) else str(value)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=json_default, allow_nan=False), encoding="utf-8")


def run_query(db, query):
    started = time.perf_counter()
    results = list(db[query["collection"]].aggregate(query["pipeline"], allowDiskUse=True))
    return results, (time.perf_counter() - started) * 1000


def explain_query(db, query):
    result = db.command("explain", {
        "aggregate": query["collection"], "pipeline": query["pipeline"], "cursor": {}, "allowDiskUse": True,
    }, verbosity="executionStats")
    return result, collect_explain_summary(result)


def collect_explain_summary(explain):
    """Use authoritative totals once, not totals repeated in nested execution nodes.

    A classic aggregation can report separate cursor and lookup counters. SBE can
    report a top-level total instead. Index names come from winning/executed plans.
    Unknown counters remain None, rather than being presented as zero work.
    """
    indexes = set()
    scan_stages = 0
    lookup_scans = 0

    def plan_indexes(node):
        if isinstance(node, dict):
            if isinstance(node.get("indexName"), str):
                indexes.add(node["indexName"])
            for key, child in node.items():
                if key not in ("rejectedPlans", "allPlansExecution"):
                    plan_indexes(child)
        elif isinstance(node, list):
            for child in node:
                plan_indexes(child)

    def executed_scans(node):
        if isinstance(node, dict):
            return int(node.get("stage") in ("COLLSCAN", "scan")) + sum(executed_scans(v) for v in node.values())
        if isinstance(node, list):
            return sum(executed_scans(v) for v in node)
        return 0

    def counter(stats, name):
        value = stats.get(name)
        return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def add_totals(totals):
        return tuple(sum(items) if all(v is not None for v in items) else None for items in zip(*totals))

    def inspect(node):
        nonlocal scan_stages, lookup_scans
        planner = node.get("queryPlanner", {})
        plan_indexes(planner.get("winningPlan", {}))
        stats = node.get("executionStats")
        if isinstance(stats, dict):
            tree = stats.get("executionStages", {})
            plan_indexes(tree)
            scan_stages += executed_scans(tree)
            return (counter(stats, "totalDocsExamined"), counter(stats, "totalKeysExamined")), "top_level"

        totals = []
        for stage in node.get("stages", []):
            if "$cursor" in stage:
                values, _ = inspect(stage["$cursor"])
                totals.append(values)
            if "$lookup" in stage or "$graphLookup" in stage:
                indexes.update(stage.get("indexesUsed", []))
                lookup_scans += stage.get("collectionScans", 0)
                totals.append((counter(stage, "totalDocsExamined"), counter(stage, "totalKeysExamined")))
        if totals:
            return add_totals(totals), "cursor_plus_lookup"

        shards = node.get("shards")
        if isinstance(shards, dict) and shards:
            return add_totals([inspect(shard)[0] for shard in shards.values()]), "shard_totals"
        return (None, None), "unavailable"

    (documents, keys), scope = inspect(explain)
    return {
        "indexes_used": sorted(indexes), "collection_scans": scan_stages,
        "lookup_collection_scans": lookup_scans,
        "total_docs_examined_reported": documents, "total_keys_examined_reported": keys,
        "metric_scope": scope,
    }
