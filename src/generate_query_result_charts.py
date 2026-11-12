import argparse
from pathlib import Path

import matplotlib.pyplot as plt

from generate_performance_charts import load_report, load_results
from v1_queries import V1_QUERIES


QUERY_VISUALS = {
    "q01": {
        "metric": "restaurant_count",
        "category_fields": ["city", "country"],
        "title": "Vegetarijanski/veganski restorani po gradovima",
        "ylabel": "Broj restorana",
    },
    "q02": {
        "metric": "restaurant_count",
        "category_fields": ["city", "country"],
        "title": "Gluten-free restorani po gradovima",
        "ylabel": "Broj restorana",
    },
    "q03": {
        "metric": "avg_value_for_money",
        "category_fields": ["city", "country"],
        "title": "Odnos cene i kvaliteta po gradovima",
        "ylabel": "Prosecna vrednost",
    },
    "q04": {
        "metric": "avg_gap",
        "category_fields": ["city", "country"],
        "title": "Razlika hrane i usluge kod skupljih restorana",
        "ylabel": "Prosecna razlika",
    },
    "q05": {
        "metric": "restaurant_count",
        "category_fields": ["city", "cuisine"],
        "title": "Prepoznatljive kuhinje u turistickim gradovima",
        "ylabel": "Broj restorana",
    },
    "q06": {
        "metric": "avg_rating",
        "category_fields": ["city", "cuisine"],
        "title": "Dobro ocenjene, slabije zastupljene kuhinje",
        "ylabel": "Prosecna ocena",
    },
    "q07": {
        "metric": "quality_demand_count",
        "category_fields": ["city", "country"],
        "title": "Prostor za premium restorane",
        "ylabel": "Broj restorana traznje",
    },
    "q08": {
        "metric": "successful_restaurant_count",
        "category_fields": ["feature"],
        "title": "Karakteristike uspesnih restorana",
        "ylabel": "Broj uspesnih restorana",
    },
    "q09": {
        "metric": "successful_restaurant_count",
        "category_fields": ["tag", "price_segment"],
        "title": "Oznake uspesnih restorana po cenovnom segmentu",
        "ylabel": "Broj uspesnih restorana",
    },
    "q10": {
        "metric": "avg_excellent_ratio",
        "category_fields": ["cuisine"],
        "title": "Kuhinje sa najvecim udelom odlicnih recenzija",
        "ylabel": "Udeo odlicnih recenzija",
    },
}


def category_label(row, fields):
    values = []
    for field in fields:
        value = row.get(field)
        if value not in (None, ""):
            values.append(str(value))
    return " / ".join(values)


def shorten(label, max_length=32):
    if len(label) <= max_length:
        return label
    return label[: max_length - 3] + "..."


def autolabel(ax, bars):
    for bar in bars:
        width = bar.get_width()
        ax.annotate(
            f"{width:.2f}" if width < 10 else f"{width:.0f}",
            xy=(width, bar.get_y() + bar.get_height() / 2),
            xytext=(4, 0),
            textcoords="offset points",
            ha="left",
            va="center",
            fontsize=8,
        )


def plot_query_result(query, rows, output_file):
    query_id = query["id"]
    visual = QUERY_VISUALS[query_id]

    metric = visual["metric"]
    rows = [row for row in rows if row.get(metric) is not None]
    labels = [shorten(category_label(row, visual["category_fields"])) for row in rows]
    values = [float(row[metric]) for row in rows]

    height = max(6, len(rows) * 0.34)
    fig, ax = plt.subplots(figsize=(12, height))
    positions = list(range(len(rows)))
    bars = ax.barh(positions, values, color="#3d7f8f")

    ax.set_title(f"{query_id.upper()} - {visual['title']} (V1/V2 validated)")
    ax.set_xlabel(visual["ylabel"])
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.25)
    autolabel(ax, bars)

    question = query["question"]
    fig.text(0.01, 0.01, question, fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_file, dpi=180)
    plt.close(fig)


def parse_args():
    parser = argparse.ArgumentParser(description="Generisanje grafika rezultata upita.")
    parser.add_argument("--benchmark-dir", type=Path, default=Path("outputs/runs/benchmark"))
    parser.add_argument("--output-dir", default="outputs/query_result_charts")
    return parser.parse_args()


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    report = load_report(args.benchmark_dir / "report.json")
    results = load_results(report, args.benchmark_dir / "results")
    generated = []
    for query in V1_QUERIES:
        if query["id"] in results:
            output_file = output_dir / f"{query['id']}.png"
            plot_query_result(query, results[query["id"]], output_file)
            generated.append(output_file)

    print("Generisani grafici rezultata:")
    for path in generated:
        print(f"- {path}")


if __name__ == "__main__":
    main()
