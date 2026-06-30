import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt


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


def read_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


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


def plot_query_result(input_file, schema_label, output_file):
    payload = read_json(input_file)
    query_id = payload["query"]["id"]
    visual = QUERY_VISUALS[query_id]
    rows = payload["results"]

    metric = visual["metric"]
    rows = [row for row in rows if row.get(metric) is not None]
    labels = [shorten(category_label(row, visual["category_fields"])) for row in rows]
    values = [float(row[metric]) for row in rows]

    height = max(6, len(rows) * 0.34)
    fig, ax = plt.subplots(figsize=(12, height))
    positions = list(range(len(rows)))
    bars = ax.barh(positions, values, color="#3d7f8f")

    ax.set_title(f"{query_id.upper()} - {visual['title']} ({schema_label})")
    ax.set_xlabel(visual["ylabel"])
    ax.set_yticks(positions)
    ax.set_yticklabels(labels, fontsize=8)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.25)
    autolabel(ax, bars)

    question = payload["query"]["question"]
    fig.text(0.01, 0.01, question, fontsize=8, color="#555555")
    fig.tight_layout(rect=(0, 0.04, 1, 1))
    fig.savefig(output_file, dpi=180)
    plt.close(fig)


def parse_args():
    parser = argparse.ArgumentParser(description="Generisanje grafika rezultata upita.")
    parser.add_argument("--v1-dir", default="outputs/v1_baseline_final")
    parser.add_argument("--v2-dir", default="outputs/v2_optimized")
    parser.add_argument("--output-dir", default="outputs/query_result_charts")
    return parser.parse_args()


def main():
    args = parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    generated = []
    for query_id in sorted(QUERY_VISUALS):
        for schema_prefix, schema_label, base_dir in [
            ("v1", "V1 baseline", Path(args.v1_dir)),
            ("v2", "V2 optimizovana", Path(args.v2_dir)),
        ]:
            input_file = base_dir / "results" / f"{query_id}.json"
            output_file = output_dir / f"{schema_prefix}_{query_id}_rezultat.png"
            plot_query_result(input_file, schema_label, output_file)
            generated.append(output_file)

    print("Generisani grafici rezultata:")
    for path in generated:
        print(f"- {path}")


if __name__ == "__main__":
    main()
