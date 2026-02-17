#!/usr/bin/env python3
"""
expand_json_to_csv.py

Read a JSON file (object or array of objects), flatten nested structures and write a CSV.

Behavior:
- If the top-level JSON is a dict it's treated as a single row.
- Nested dicts are flattened with dot-separated keys: {"a": {"b": 1}} -> column "a.b".
- Lists of primitives are joined with a configurable separator (default "|").
- Lists of dicts are expanded using numeric indices: "items.0.name", "items.1.name", etc.

Usage:
    python expand_json_to_csv.py input.json -o output.csv

This is a small, dependency-free script (Python 3.7+).
"""
import argparse
import json
import csv
import sys
from typing import Any, Dict, List


def flatten(obj: Any, parent_key: str = "", sep: str = ".", list_primitive_sep: str = "|") -> Dict[str, Any]:
    """Flatten a JSON object into a flat dict of key->value.

    - parent_key: prefix for keys
    - sep: separator between key parts
    - list_primitive_sep: how to join lists of primitives
    """
    items: Dict[str, Any] = {}

    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            items.update(flatten(v, new_key, sep, list_primitive_sep))
    elif isinstance(obj, list):
        # If list of primitives, join them into one column
        if all(not isinstance(x, (dict, list)) for x in obj):
            joined = list_primitive_sep.join(str(x) for x in obj)
            items[parent_key] = joined
        else:
            # List contains dicts or nested lists -> expand by index
            for idx, val in enumerate(obj):
                idx_key = f"{parent_key}{sep}{idx}" if parent_key else str(idx)
                items.update(flatten(val, idx_key, sep, list_primitive_sep))
    else:
        # Primitive value
        items[parent_key] = obj

    return items


def read_json(path: str) -> List[Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    else:
        return [data]


def explode_rows(obj: Any) -> List[Dict[str, Any]]:
    """Given a top-level object, if it contains a list of dicts (e.g. 'scenarios'),
    explode that list so each element becomes its own row merged with parent metadata.

    Heuristics:
    - If the object is a list, return it (each element is a row).
    - If it's a dict and has a key 'scenarios' which is a list of dicts, use that.
    - Otherwise, find all keys whose values are lists of dicts. If one found, use it.
    - If multiple are found, pick the longest list.
    - If none found, return the object as a single-row list.
    """
    if isinstance(obj, list):
        return obj

    if not isinstance(obj, dict):
        return [obj]

    # Find candidate list-of-dicts keys
    list_keys = [k for k, v in obj.items() if isinstance(v, list) and v and all(isinstance(x, dict) for x in v)]

    chosen_key = None
    if "scenarios" in obj and isinstance(obj["scenarios"], list) and obj["scenarios"] and all(isinstance(x, dict) for x in obj["scenarios"]):
        chosen_key = "scenarios"
    elif len(list_keys) == 1:
        chosen_key = list_keys[0]
    elif len(list_keys) > 1:
        # choose the longest list
        chosen_key = max(list_keys, key=lambda k: len(obj[k]))

    if chosen_key is None:
        return [obj]

    parent = {k: v for k, v in obj.items() if k != chosen_key}
    rows: List[Dict[str, Any]] = []
    for item in obj[chosen_key]:
        # Merge parent metadata with the child item; child keys take precedence
        merged = {}
        merged.update(parent)
        if isinstance(item, dict):
            merged.update(item)
        else:
            # if list contains primitives (unexpected here), store under the list key
            merged[chosen_key] = item
        rows.append(merged)

    return rows


def write_csv(rows: List[Dict[str, Any]], out_path: str):
    # compute header as union of all keys in order
    header = []
    seen = set()
    for r in rows:
        for k in r.keys():
            if k not in seen:
                seen.add(k)
                header.append(k)

    # Ensure we have a 'label' column appended (we'll compute per-row)
    if 'label' not in header:
        header.append('label')

    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        for r in rows:
            # Determine label: if any classifications.* key has a non-empty value -> 'original'
            has_classification = any(
                k.startswith('classifications.') and r.get(k) not in (None, "") and str(r.get(k)).strip() != ""
                for k in r.keys()
            )
            label_value = "original" if has_classification else "generated"

            # Build row values (inject label_value for the 'label' column)
            row = [label_value if k == 'label' else r.get(k, "") for k in header]

            # Convert any non-string values to JSON string for safe CSV and remove newlines
            normalized = []
            for v in row:
                if isinstance(v, (dict, list)):
                    # stringify complex types and remove newlines
                    normalized.append(json.dumps(v, ensure_ascii=False).replace("\n", " ").replace("\r", " "))
                elif v is None:
                    normalized.append("")
                else:
                    # remove newlines from strings to keep one CSV row per item
                    normalized.append(str(v).replace("\n", " ").replace("\r", " "))
            writer.writerow(normalized)


def main(argv=None):
    p = argparse.ArgumentParser(description="Flatten JSON to CSV")
    p.add_argument("input", help="Path to input JSON file")
    p.add_argument("-o", "--output", help="Path to output CSV file (default: stdout)")
    p.add_argument("--sep", default=".", help="Separator to use when flattening keys (default '.')")
    p.add_argument("--listsep", default="|", help="Separator to join lists of primitives (default '|')")
    args = p.parse_args(argv)

    data = read_json(args.input)

    # Explode any top-level list-of-dicts (e.g., a 'scenarios' list) so each scenario becomes its own row.
    rows: List[Dict[str, Any]] = []
    for top in data:
        exploded = explode_rows(top)
        rows.extend(exploded)

    # Now flatten each resulting row
    flattened_rows = [flatten(item, parent_key="", sep=args.sep, list_primitive_sep=args.listsep) for item in rows]

    if args.output:
        write_csv(flattened_rows, args.output)
    else:
        # write to stdout
        writer = csv.writer(sys.stdout)
        header = []
        seen = set()
        for r in flattened_rows:
            for k in r.keys():
                if k not in seen:
                    seen.add(k)
                    header.append(k)
        writer.writerow(header)
        for r in flattened_rows:
            # Determine label for stdout path as well
            has_classification = any(
                k.startswith('classifications.') and r.get(k) not in (None, "") and str(r.get(k)).strip() != ""
                for k in r.keys()
            )
            label_value = "original" if has_classification else "generated"

            row = [label_value if k == 'label' else r.get(k, "") for k in header]
            normalized = []
            for v in row:
                if isinstance(v, (dict, list)):
                    normalized.append(json.dumps(v, ensure_ascii=False))
                elif v is None:
                    normalized.append("")
                else:
                    normalized.append(str(v))
            writer.writerow(normalized)


if __name__ == "__main__":
    main()
