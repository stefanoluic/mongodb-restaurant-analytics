import json
from pathlib import Path

from v1_queries import V1_QUERIES
from v2_queries import V2_QUERIES


OUTPUT_PATH = Path("docs/upiti_mongosh_sintaksa.md")


def to_mongosh(value, indent=0):
    space = " " * indent
    next_space = " " * (indent + 2)

    if isinstance(value, dict):
        if not value:
            return "{}"
        lines = ["{"]
        items = list(value.items())
        for index, (key, nested_value) in enumerate(items):
            comma = "," if index < len(items) - 1 else ""
            key_text = key if is_simple_key(key) else json.dumps(key, ensure_ascii=False)
            lines.append(
                f"{next_space}{key_text}: {to_mongosh(nested_value, indent + 2)}{comma}"
            )
        lines.append(f"{space}}}")
        return "\n".join(lines)

    if isinstance(value, list):
        if not value:
            return "[]"
        lines = ["["]
        for index, nested_value in enumerate(value):
            comma = "," if index < len(value) - 1 else ""
            lines.append(f"{next_space}{to_mongosh(nested_value, indent + 2)}{comma}")
        lines.append(f"{space}]")
        return "\n".join(lines)

    if value is True:
        return "true"
    if value is False:
        return "false"
    if value is None:
        return "null"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def is_simple_key(key):
    if not isinstance(key, str) or not key:
        return False
    if key.startswith("$"):
        return True
    return key.replace("_", "").isalnum()


def query_block(query):
    pipeline = to_mongosh(query["pipeline"], 2)
    return f"db.{query['collection']}.aggregate({pipeline})"


def write_section(lines, title, queries):
    lines.append(f"## {title}")
    lines.append("")
    for query in queries:
        lines.append(f"### {query['id']} - {query['question']}")
        lines.append("")
        lines.append(f"Uloga: {query['role']}")
        lines.append("")
        lines.append(f"Kolekcija: `{query['collection']}`")
        lines.append("")
        lines.append("```js")
        lines.append(query_block(query))
        lines.append("```")
        lines.append("")


def main():
    lines = [
        "# Upiti u MongoDB / mongosh sintaksi",
        "",
        "Ovaj dokument sadrzi iste upite koji se koriste u Python skriptama, ali",
        "prepisane u oblik pogodan za Studio 3T IntelliShell, `mongosh` ili MongoDB",
        "Compass aggregation editor.",
        "",
        "Python je koriscen za automatizaciju merenja, ali logika upita je MongoDB",
        "aggregation pipeline.",
        "",
        "Napomena: upiti su dugi jer su u V1 semi podaci rasporedjeni u vise",
        "kolekcija, pa se koriste `$lookup`, `$unwind`, `$group` i druga agregaciona",
        "stanja.",
        "",
    ]

    write_section(lines, "V1 upiti", V1_QUERIES)
    write_section(lines, "V2 upiti", V2_QUERIES)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Generisan dokument: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
