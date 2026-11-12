"""Plot repeated timings only after the paired query results have been validated."""

import argparse
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from query_runtime import json_default, write_json


def load_report(path):
    report = json.loads(Path(path).read_text(encoding="utf-8"))
    queries = report.get("queries", [])
    if report.get("passed") is not True or not queries or any(q.get("validated") is not True for q in queries):
        raise ValueError("A successful correctness-gated benchmark report is required.")
    if len({q["id"] for q in queries}) != len(queries):
        raise ValueError("The report contains duplicate query IDs.")
    for query in queries:
        for version in ("v1", "v2"):
            samples = query[version]["samples_ms"]
            if len(samples) < 2 or any(not math.isfinite(n) or n <= 0 for n in samples):
                raise ValueError("At least two positive, finite timing samples are required.")
            if not math.isclose(statistics.median(samples), query[version]["median_ms"]):
                raise ValueError("Recorded median does not match the timing samples.")
    return report


def build_rows(report):
    rows = []
    for query in sorted(report["queries"], key=lambda q: q["id"]):
        row = {"query_id": query["id"], "result_count": query["result_count"]}
        for version in ("v1", "v2"):
            timing = query[version]
            for name in ("median_ms", "min_ms", "max_ms"):
                row[f"{version}_{name}"] = timing[name]
            plan = timing["explain_summary"]
            row[f"{version}_docs_examined"] = plan["total_docs_examined_reported"]
            row[f"{version}_indexes"] = ", ".join(plan["indexes_used"])
        row["read_speedup"] = row["v1_median_ms"] / row["v2_median_ms"]
        rows.append(row)
    return rows


def load_results(report, results_dir):
    """Reject stale/mixed result files before producing charts or dashboard data."""
    results = {}
    for query in report["queries"]:
        rows = json.loads((Path(results_dir) / f"{query['id']}.json").read_text(encoding="utf-8"))
        encoded = json.dumps(rows, sort_keys=True, ensure_ascii=False, default=json_default, allow_nan=False).encode("utf-8")
        if len(rows) != query["result_count"] or hashlib.sha256(encoded).hexdigest() != query["results_sha256"]:
            raise ValueError(f"Result file does not match the validated benchmark: {query['id']}")
        results[query["id"]] = rows
    return results


def paired_chart(rows, path, *, metric, title, ylabel, log=False, timing=False, footer="", v2_label="V2 materialized + indexes"):
    fig, ax = plt.subplots(figsize=(12, 6))
    positions = list(range(len(rows)))
    for version, offset, label, color in (("v1", -0.19, "V1 normalized", "#2563a6"),
                                          ("v2", 0.19, v2_label, "#d67b20")):
        values = [row[f"{version}_{metric}"] for row in rows]
        errors = None
        if timing:
            errors = [[row[f"{version}_median_ms"] - row[f"{version}_min_ms"] for row in rows],
                      [row[f"{version}_max_ms"] - row[f"{version}_median_ms"] for row in rows]]
        # Missing explain counters are unknown, rather than zero work.
        x = [i + offset for i, value in zip(positions, values) if value is not None]
        y = [value for value in values if value is not None]
        bars = ax.bar(x, y, 0.36, label=label, color=color, yerr=errors, capsize=3)
        if not log and timing:
            for bar, value in zip(bars, y):
                ax.annotate(f"{value:,.1f}", (bar.get_x() + bar.get_width()/2, value),
                            xytext=(0, 5), textcoords="offset points", ha="center", fontsize=7, rotation=60)
    if log:
        ax.set_yscale("log")
    else:
        ax.margins(y=0.25)
    ax.set(ylabel=ylabel, xlabel="Query")
    ax.set_title(title, pad=40)
    ax.set_xticks(positions, [row["query_id"].upper() for row in rows])
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.0), ncol=2, frameon=False)
    ax.grid(axis="y", alpha=0.18)
    ax.set_axisbelow(True)
    fig.text(0.02, 0.015, footer, fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.055, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def plot_speedup(rows, path, footer):
    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.bar([r["query_id"].upper() for r in rows], [r["read_speedup"] for r in rows], color="#2563a6")
    for bar in bars:
        ax.annotate(f"{bar.get_height():,.0f}x", (bar.get_x()+bar.get_width()/2, bar.get_height()),
                    xytext=(0, 4), textcoords="offset points", ha="center", fontsize=8)
    ax.set(title="Read-time ratio: V1 / V2", ylabel="Ratio of median query times", xlabel="Query")
    ax.margins(y=0.17)
    ax.grid(axis="y", alpha=0.18)
    ax.set_axisbelow(True)
    fig.text(0.02, 0.015, footer, fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.055, 1, 1))
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-report", type=Path, default=Path("outputs/runs/benchmark/report.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/performance_charts"))
    args = parser.parse_args()
    report = load_report(args.benchmark_report)
    rows = build_rows(report)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with (args.output_dir / "performance_comparison.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_json(args.output_dir / "benchmark_report.json", report)
    method = report["methodology"]
    v2_label = "V2 materialized + indexes" if report["build"]["includes_indexes"] else "V2 materialized"
    footer = (f"{method['repetitions']} measured runs per version; {method['warmups_per_query_version']} untimed warmup; "
              f"cache not flushed. V2 preparation: {report['build']['build_seconds']:.1f} s, excluded from read times.")
    paired_chart(rows, args.output_dir / "v1_v2_vreme_izvrsavanja.png", metric="median_ms",
                 title="Median query time (whiskers: observed min-max)", ylabel="Time [ms]", timing=True, footer=footer, v2_label=v2_label)
    paired_chart(rows, args.output_dir / "v1_v2_vreme_izvrsavanja_log.png", metric="median_ms",
                 title="Median query time (log scale; whiskers: observed min-max)", ylabel="Time [ms, log scale]",
                 timing=True, log=True, footer=footer, v2_label=v2_label)
    paired_chart(rows, args.output_dir / "v1_v2_broj_dokumenata.png", metric="docs_examined",
                 title="Documents examined by execution plans", ylabel="Documents examined [log scale]", log=True,
                 footer="Explain collected outside timed runs. Counts cover the source cursor and separately reported lookup work.", v2_label=v2_label)
    plot_speedup(rows, args.output_dir / "v1_v2_ubrzanje.png", footer)
    print(f"Charts, CSV and validated report saved to {args.output_dir}")


if __name__ == "__main__":
    main()
