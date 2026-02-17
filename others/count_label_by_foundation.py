#!/usr/bin/env python3
"""
count_label_by_foundation.py

Count frequencies of 'original' and 'generated' labels across the 'foundation' column
in a CSV produced by `expand_json_to_csv.py`.

Usage examples:
  python3 count_label_by_foundation.py /path/to/MFV130Gen.csv
  python3 count_label_by_foundation.py /path/to/MFV130Gen.csv -o /path/to/foundation_counts.csv
"""

import argparse
import csv
import sys
from collections import defaultdict, OrderedDict
from typing import Dict


def count_labels_by_foundation(input_csv: str) -> Dict[str, Dict[str, int]]:
    counts: Dict[str, Dict[str, int]] = defaultdict(lambda: {"original": 0, "generated": 0})
    with open(input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            foundation = row.get("foundation", "").strip()
            if foundation == "":
                foundation = "<missing>"

            label = row.get("label", "").strip().lower()
            if label not in ("original", "generated"):
                label = "generated"

            counts[foundation][label] += 1
    return counts


def print_table(counts: Dict[str, Dict[str, int]]):
    ordered = OrderedDict(sorted(counts.items(), key=lambda kv: kv[0].lower()))
    headers = ["foundation", "original", "generated", "total"]
    col_w = {
        "foundation": max(10, max((len(k) for k in ordered.keys()), default=10)),
        "original": len("original"),
        "generated": len("generated"),
        "total": len("total"),
    }
    for k, v in ordered.items():
        col_w["original"] = max(col_w["original"], len(str(v.get("original", 0))))
        col_w["generated"] = max(col_w["generated"], len(str(v.get("generated", 0))))
        col_w["total"] = max(col_w["total"], len(str(v.get("original", 0) + v.get("generated", 0))))

    print(f"{headers[0]:<{col_w['foundation']}}  {headers[1]:>{col_w['original']}}  {headers[2]:>{col_w['generated']}}  {headers[3]:>{col_w['total']}}")
    print("-" * (col_w['foundation'] + col_w['original'] + col_w['generated'] + col_w['total'] + 6))
    grand_original = grand_generated = 0
    for foundation, v in ordered.items():
        o = v.get("original", 0)
        g = v.get("generated", 0)
        total = o + g
        grand_original += o
        grand_generated += g
        print(f"{foundation:<{col_w['foundation']}}  {o:>{col_w['original']}}  {g:>{col_w['generated']}}  {total:>{col_w['total']}}")

    print("-" * (col_w['foundation'] + col_w['original'] + col_w['generated'] + col_w['total'] + 6))
    grand_total = grand_original + grand_generated
    print(f"{'TOTAL':<{col_w['foundation']}}  {grand_original:>{col_w['original']}}  {grand_generated:>{col_w['generated']}}  {grand_total:>{col_w['total']}}")


def write_summary_csv(counts: Dict[str, Dict[str, int]], out_csv: str):
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["foundation", "original", "generated", "total"])
        for foundation, v in sorted(counts.items(), key=lambda kv: kv[0].lower()):
            o = v.get("original", 0)
            g = v.get("generated", 0)
            writer.writerow([foundation, o, g, o + g])


def main(argv=None):
    p = argparse.ArgumentParser(description="Count original/generated labels per foundation")
    p.add_argument("input", help="Path to the input CSV (e.g., MFV130Gen.csv)")
    p.add_argument("-o", "--output", help="Path to output summary CSV (optional)")
    p.add_argument("--format", choices=["table", "csv"], default="table",
                   help="Output format when writing to stdout (default: table). If --output is provided, a CSV will be written regardless.")
    args = p.parse_args(argv)

    counts = count_labels_by_foundation(args.input)

    if args.output:
        write_summary_csv(counts, args.output)
        print(f"Wrote summary CSV to: {args.output}")

    if args.format == "table":
        print_table(counts)
    else:
        writer = csv.writer(sys.stdout)
        writer.writerow(["foundation", "original", "generated", "total"])
        for foundation, v in sorted(counts.items(), key=lambda kv: kv[0].lower()):
            o = v.get("original", 0)
            g = v.get("generated", 0)
            writer.writerow([foundation, o, g, o + g])


if __name__ == "__main__":
    main()
