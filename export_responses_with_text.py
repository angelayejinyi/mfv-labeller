#!/usr/bin/env python3
"""
export_responses_with_text.py

Read `data.db` responses table and join with `MFV130Gen.csv` by sample_id (CSV row index).
Writes `responses_export.csv` with columns:
participant_id,sample_id,rating,note,ts,foundation,label,title,scenario,description

Run:
    python3 export_responses_with_text.py
"""
import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).parent
DB = ROOT / "data.db"
CSV = ROOT / "MFV130Gen.csv"
OUT = ROOT / "responses_export.csv"

# load csv into dict by row index
samples = {}
with open(CSV, newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    for idx, row in enumerate(reader):
        samples[idx] = row

conn = sqlite3.connect(str(DB))
cur = conn.cursor()
cur.execute("SELECT participant_id, sample_id, rating, ts FROM responses ORDER BY ts ASC")
rows = cur.fetchall()

with open(OUT, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["participant_id", "sample_id", "rating", "ts", "foundation", "label", "title", "scenario", "description"])
    for participant_id, sample_id, rating, ts in rows:
        s = samples.get(sample_id, {})
        foundation = s.get("foundation", "")
        label = s.get("label", "")
        title = s.get("title", "")
        scenario = s.get("scenario", "")
        description = s.get("description", "")
    writer.writerow([participant_id, sample_id, rating, ts, foundation, label, title, scenario, description])

print(f"Wrote {OUT} with {len(rows)} responses.")
