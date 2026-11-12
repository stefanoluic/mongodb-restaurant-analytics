import json
from pathlib import Path

from v1_queries import V1_QUERIES
from v2_queries import V2_QUERIES


OUTPUT_DIR = Path("queries")


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
        lines.append(f"Role: {query['role']}")
        lines.append("")
        lines.append(f"Collection: `{query['collection']}`")
        lines.append("")
        lines.append("```js")
        lines.append(query_block(query))
        lines.append("```")
        lines.append("")


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for version, queries in (("v1", V1_QUERIES), ("v2", V2_QUERIES)):
        lines = [f"# {version.upper()} aggregation pipelines", "",
                 "Generated from the Python query definitions. Run with mongosh against the imported database.",
                 "Query questions retain the original Serbian wording.", ""]
        write_section(lines, "Queries", queries)
        path = OUTPUT_DIR / f"{version}.md"
        path.write_text("\n".join(lines), encoding="utf-8")
        print(f"Generated: {path}")


if __name__ == "__main__":
    main()
