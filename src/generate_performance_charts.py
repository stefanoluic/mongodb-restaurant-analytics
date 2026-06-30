import argparse
import csv
import json
from pathlib import Path

import matplotlib.pyplot as plt


def load_summary(path):
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    return {query["id"]: query for query in data["queries"]}


def docs_examined(query):
    return query.get("explain_summary", {}).get("total_docs_examined_reported", 0)


def indexes_used(query):
    return ", ".join(query.get("explain_summary", {}).get("indexes_used", []))


def build_rows(v1_summary, v2_summary):
    rows = []
    for query_id in sorted(v1_summary):
        v1 = v1_summary[query_id]
        v2 = v2_summary[query_id]
        v1_ms = float(v1["elapsed_ms"])
        v2_ms = float(v2["elapsed_ms"])
        v1_docs = int(docs_examined(v1))
        v2_docs = int(docs_examined(v2))

        rows.append(
            {
                "query_id": query_id,
                "v1_time_ms": v1_ms,
                "v2_time_ms": v2_ms,
                "v1_time_s": v1_ms / 1000,
                "v2_time_s": v2_ms / 1000,
                "time_speedup": v1_ms / v2_ms if v2_ms else None,
                "time_reduction_percent": (1 - (v2_ms / v1_ms)) * 100,
                "v1_docs_examined": v1_docs,
                "v2_docs_examined": v2_docs,
                "docs_reduction_percent": (
                    (1 - (v2_docs / v1_docs)) * 100 if v1_docs else None
                ),
                "v1_indexes": indexes_used(v1),
                "v2_indexes": indexes_used(v2),
            }
        )
    return rows


def write_csv(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
    except PermissionError:
        print(f"CSV nije prepisan jer je fajl zakljucan: {path}")


def autolabel(ax, bars, fmt):
    for bar in bars:
        height = bar.get_height()
        ax.annotate(
            fmt(height),
            xy=(bar.get_x() + bar.get_width() / 2, height),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=8,
            rotation=90,
        )


def plot_time_comparison(rows, path):
    labels = [row["query_id"] for row in rows]
    v1 = [row["v1_time_s"] for row in rows]
    v2 = [row["v2_time_s"] for row in rows]
    x = range(len(rows))
    width = 0.38

    fig, ax = plt.subplots(figsize=(13, 7))
    bars1 = ax.bar([i - width / 2 for i in x], v1, width, label="V1 bez optimizacije")
    bars2 = ax.bar([i + width / 2 for i in x], v2, width, label="V2 + indeksi")

    ax.set_title("Poredjenje vremena izvrsavanja upita")
    ax.set_xlabel("Upit")
    ax.set_ylabel("Vreme izvrsavanja [s]")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.legend()
    ax.grid(axis="y", alpha=0.25)

    autolabel(ax, bars1, lambda value: f"{value:.1f}s")
    autolabel(ax, bars2, lambda value: f"{value * 1000:.1f}ms")

    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_time_log_comparison(rows, path):
    labels = [row["query_id"] for row in rows]
    v1 = [row["v1_time_ms"] for row in rows]
    v2 = [row["v2_time_ms"] for row in rows]
    x = range(len(rows))
    width = 0.38

    fig, ax = plt.subplots(figsize=(13, 7))
    ax.bar([i - width / 2 for i in x], v1, width, label="V1 bez optimizacije")
    ax.bar([i + width / 2 for i in x], v2, width, label="V2 + indeksi")

    ax.set_title("Poredjenje vremena izvrsavanja upita - log skala")
    ax.set_xlabel("Upit")
    ax.set_ylabel("Vreme izvrsavanja [ms]")
    ax.set_yscale("log")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.legend()
    ax.grid(axis="y", alpha=0.25, which="major")
    ax.minorticks_off()

    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_docs_comparison(rows, path):
    labels = [row["query_id"] for row in rows]
    v1 = [row["v1_docs_examined"] for row in rows]
    v2 = [row["v2_docs_examined"] for row in rows]
    x = range(len(rows))
    width = 0.38

    fig, ax = plt.subplots(figsize=(13, 7))
    ax.bar([i - width / 2 for i in x], v1, width, label="V1 bez optimizacije")
    ax.bar([i + width / 2 for i in x], v2, width, label="V2 + indeksi")

    ax.set_title("Poredjenje broja pregledanih dokumenata")
    ax.set_xlabel("Upit")
    ax.set_ylabel("Broj pregledanih dokumenata")
    ax.set_yscale("log")
    ax.set_xticks(list(x))
    ax.set_xticklabels(labels)
    ax.legend()
    ax.grid(axis="y", alpha=0.25, which="major")
    ax.minorticks_off()

    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def plot_speedup(rows, path):
    labels = [row["query_id"] for row in rows]
    speedups = [row["time_speedup"] for row in rows]

    fig, ax = plt.subplots(figsize=(13, 7))
    bars = ax.bar(labels, speedups)
    ax.set_title("Ubrzanje V2 upita u odnosu na V1")
    ax.set_xlabel("Upit")
    ax.set_ylabel("Ubrzanje [x]")
    ax.grid(axis="y", alpha=0.25)
    autolabel(ax, bars, lambda value: f"{value:.0f}x")

    fig.tight_layout()
    fig.savefig(path, dpi=180)
    plt.close(fig)


def parse_args():
    parser = argparse.ArgumentParser(description="Generisanje grafika performansi.")
    parser.add_argument(
        "--v1-summary",
        default="outputs/v1_baseline_final/summary.json",
        help="Putanja do V1 summary.json fajla.",
    )
    parser.add_argument(
        "--v2-summary",
        default="outputs/v2_optimized/summary.json",
        help="Putanja do V2 summary.json fajla.",
    )
    parser.add_argument(
        "--output-dir",
        default="outputs/performance_charts",
        help="Folder za CSV i PNG grafike.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    v1_summary = load_summary(Path(args.v1_summary))
    v2_summary = load_summary(Path(args.v2_summary))
    rows = build_rows(v1_summary, v2_summary)

    write_csv(rows, output_dir / "performance_comparison.csv")
    plot_time_comparison(rows, output_dir / "v1_v2_vreme_izvrsavanja.png")
    plot_time_log_comparison(rows, output_dir / "v1_v2_vreme_izvrsavanja_log.png")
    plot_docs_comparison(rows, output_dir / "v1_v2_broj_dokumenata.png")
    plot_speedup(rows, output_dir / "v1_v2_ubrzanje.png")

    print("Generisani fajlovi:")
    for path in sorted(output_dir.iterdir()):
        print(f"- {path}")


if __name__ == "__main__":
    main()
