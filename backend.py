#!/usr/bin/env python3
"""
backend.py

FastAPI backend for a simple labeling app.

Behavior / endpoints summary:
- GET  /register -> create a participant, assign two foundations (balanced across participants), select 10 'original' + 20 'generated' samples for that participant, return participant_id and the shuffled sample list
- GET  /participant/{pid}/samples -> return the assigned samples (id + text + metadata)
- POST /submit -> submit a single rating (participant_id, sample_id, rating 0-4, optional note)
- GET  /admin/assignments -> view foundation assignment counts (admin check)
- GET  /admin/responses -> view responses summary (admin)

Storage: SQLite (file: data.db) created on first run. The backend loads the CSV `MFV130Gen.csv` at startup to build sample pool.

Assumptions & notes:
- A "sample" is a row from the CSV; we assign an internal numeric sample_id (row index) when loading the CSV.
- Chosen two foundations are assigned to each participant by choosing the pair that helps balance counts across participants.
- If not enough originals/generated in the chosen foundations to meet the 10/20 quota, the server will pull from other foundations as fallback.

Run (development):
    pip install -r requirements.txt
    uvicorn backend:app --reload --port 8000

"""

import csv
import json
import random
import sqlite3
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from typing import Dict, List, Tuple

DATA_DIR = Path(__file__).parent
CSV_PATH = DATA_DIR / "MFV130Gen.csv"
DB_PATH = DATA_DIR / "data.db"
SAMPLE_ORIGINAL_COUNT = 10
SAMPLE_GENERATED_COUNT = 20
TOTAL_PER_PARTICIPANT = SAMPLE_ORIGINAL_COUNT + SAMPLE_GENERATED_COUNT

app = FastAPI(title="LabelingApp Backend")

# serve static frontend from ./static at /static and expose index.html at /
STATIC_DIR = DATA_DIR / "static"
if STATIC_DIR.exists():
    # Mount static files under /static so API routes (POST/PUT) are not intercepted by StaticFiles
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "Index not found. Place static files in ./static"}

# In-memory sample pool loaded from CSV
SAMPLES: List[Dict] = []  # each sample: {"id": int, "foundation": str, "label": 'original'|'generated', ...}
FOUNDATIONS: List[str] = []


def load_samples():
    global SAMPLES, FOUNDATIONS
    SAMPLES = []
    if not CSV_PATH.exists():
        raise FileNotFoundError(f"CSV not found at {CSV_PATH}")
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            # Normalize foundation and label
            foundation = (row.get("foundation") or "").strip()
            if foundation == "":
                foundation = "<missing>"
            label = (row.get("label") or "generated").strip().lower()
            if label not in ("original", "generated"):
                label = "generated"
            sample = {
                "id": idx,
                "foundation": foundation,
                "label": label,
                # include useful text fields for the frontend
                "title": row.get("title", ""),
                "description": row.get("description", ""),
                "scenario": row.get("scenario", ""),
                # keep other fields in case needed
                "meta": {k: v for k, v in row.items() if k not in ("title", "description", "scenario", "foundation", "label")},
            }
            SAMPLES.append(sample)
    FOUNDATIONS = sorted(list({s["foundation"] for s in SAMPLES}))


def init_db() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    cur = conn.cursor()
    # participants: id (text), assigned_foundations (json), samples (json list of sample ids), created_at
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS participants(
            id TEXT PRIMARY KEY,
            assigned_foundations TEXT,
            samples_json TEXT,
            created_at TEXT,
            name TEXT
        )
        """
    )
    # responses: id integer primary key, participant_id, sample_id, rating, note, ts
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS responses(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT,
            sample_id INTEGER,
            rating INTEGER,
            note TEXT,
            ts TEXT
        )
        """
    )
    # Ensure older DBs get a `name` column if missing
    cur.execute("PRAGMA table_info(participants)")
    cols = [r[1] for r in cur.fetchall()]
    if "name" not in cols:
        try:
            cur.execute("ALTER TABLE participants ADD COLUMN name TEXT")
        except Exception:
            # best-effort; if this fails, continue
            pass
    conn.commit()
    return conn


DB = init_db()


@app.on_event("startup")
def startup():
    load_samples()


# Helper: get assignment counts per foundation-pair to balance assignments
def get_foundation_pair_counts(conn: sqlite3.Connection) -> Dict[Tuple[str, str], int]:
    cur = conn.cursor()
    cur.execute("SELECT assigned_foundations FROM participants")
    rows = cur.fetchall()
    cnt = Counter()
    for (af,) in rows:
        if not af:
            continue
        try:
            pair = tuple(json.loads(af))
            if len(pair) == 2:
                cnt[tuple(pair)] += 1
        except Exception:
            continue
    return cnt


def choose_balanced_pair(conn: sqlite3.Connection) -> Tuple[str, str]:
    """
    Choose a pair of distinct foundations (a, b) such that pair counts are as balanced as possible.
    We'll consider all unordered pairs and pick the one with minimal count; tie-break randomly.
    """
    pairs = []
    for i in range(len(FOUNDATIONS)):
        for j in range(i + 1, len(FOUNDATIONS)):
            pairs.append((FOUNDATIONS[i], FOUNDATIONS[j]))
    pair_counts = get_foundation_pair_counts(conn)
    min_count = None
    candidates = []
    for p in pairs:
        c = pair_counts.get(p, 0)
        if min_count is None or c < min_count:
            min_count = c
            candidates = [p]
        elif c == min_count:
            candidates.append(p)
    return random.choice(candidates)


def sample_for_pair(pair: Tuple[str, str], desired_original: int, desired_generated: int) -> List[int]:
    # New behavior: randomize only within each foundation block. Do not globally shuffle across foundations.
    fa, fb = pair[0], pair[1]

    # allocate originals/generated evenly across the two foundations
    orig_a = desired_original // 2
    orig_b = desired_original - orig_a
    gen_a = desired_generated // 2
    gen_b = desired_generated - gen_a

    chosen_samples: List[Dict] = []
    already_chosen = set()

    for foundation, need_orig, need_gen in [(fa, orig_a, gen_a), (fb, orig_b, gen_b)]:
        pool_f = [s for s in SAMPLES if s["foundation"] == foundation]
        originals_f = [s for s in pool_f if s["label"] == "original" and s["id"] not in already_chosen]
        generated_f = [s for s in pool_f if s["label"] == "generated" and s["id"] not in already_chosen]

        chosen_orig_f: List[Dict] = []
        if len(originals_f) >= need_orig:
            chosen_orig_f = random.sample(originals_f, need_orig)
        else:
            chosen_orig_f = originals_f.copy()
            needed = need_orig - len(chosen_orig_f)
            # fallback: sample other originals not yet chosen
            others = [s for s in SAMPLES if s["label"] == "original" and s["id"] not in already_chosen and s not in chosen_orig_f]
            if len(others) >= needed:
                chosen_orig_f.extend(random.sample(others, needed))
            else:
                chosen_orig_f.extend(others)

        chosen_gen_f: List[Dict] = []
        if len(generated_f) >= need_gen:
            chosen_gen_f = random.sample(generated_f, need_gen)
        else:
            chosen_gen_f = generated_f.copy()
            needed = need_gen - len(chosen_gen_f)
            others = [s for s in SAMPLES if s["label"] == "generated" and s["id"] not in already_chosen and s not in chosen_gen_f]
            if len(others) >= needed:
                chosen_gen_f.extend(random.sample(others, needed))
            else:
                chosen_gen_f.extend(others)

        # combine and shuffle within this foundation block
        block = chosen_orig_f + chosen_gen_f
        random.shuffle(block)

        # record chosen ids and append block to final list
        for s in block:
            already_chosen.add(s["id"])
            chosen_samples.append(s)

    # If still short, fill from remaining samples (preserve order by shuffling the remaining but appending as extra block)
    if len(chosen_samples) < TOTAL_PER_PARTICIPANT:
        needed = TOTAL_PER_PARTICIPANT - len(chosen_samples)
        pool_remain = [s for s in SAMPLES if s["id"] not in already_chosen]
        if len(pool_remain) >= needed:
            extra = random.sample(pool_remain, needed)
        else:
            extra = pool_remain
        # shuffle extra to avoid deterministic fallback ordering
        random.shuffle(extra)
        for s in extra:
            chosen_samples.append(s)

    # Return ids preserving block order (no cross-foundation shuffling)
    return [s["id"] for s in chosen_samples]


@app.post("/register")
async def register(request: Request):
    """Create a participant and assign them two foundations + 30 samples.

    Accepts optional JSON body: { "name": "Attendee Name" }
    """
    conn = DB
    # parse optional name from request body (frontend may send {name})
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = body.get("name") if isinstance(body, dict) else None

    # choose balanced pair
    pair = choose_balanced_pair(conn)
    pid = str(uuid.uuid4())

    sample_ids = sample_for_pair(pair, SAMPLE_ORIGINAL_COUNT, SAMPLE_GENERATED_COUNT)

    cur = conn.cursor()
    # include name when inserting (nullable)
    cur.execute(
        "INSERT INTO participants(id, assigned_foundations, samples_json, created_at, name) VALUES (?, ?, ?, ?, ?)",
        (pid, json.dumps(list(pair)), json.dumps(sample_ids), datetime.utcnow().isoformat(), name),
    )
    conn.commit()

    # return participant info and sample list (with scenario text)
    samples = [s for s in SAMPLES if s["id"] in sample_ids]
    # maintain order of sample_ids
    id_to_sample = {s["id"]: s for s in samples}
    ordered = [id_to_sample[sid] for sid in sample_ids]
    return {"participant_id": pid, "assigned_foundations": list(pair), "samples": ordered, "name": name}


@app.get("/participant/{pid}/samples")
def get_participant_samples(pid: str):
    cur = DB.cursor()
    cur.execute("SELECT samples_json, assigned_foundations, name FROM participants WHERE id = ?", (pid,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="participant not found")
    samples_json, assigned_foundations, name = row
    sample_ids = json.loads(samples_json)
    samples = [s for s in SAMPLES if s["id"] in sample_ids]
    id_to_sample = {s["id"]: s for s in samples}
    ordered = [id_to_sample[sid] for sid in sample_ids]
    return {"participant_id": pid, "assigned_foundations": json.loads(assigned_foundations), "samples": ordered, "name": name}


@app.post("/submit")
def submit(resp: Dict):
    """Submit a single rating. Expected JSON: {participant_id, sample_id, rating (0-4), note (optional)}"""
    pid = resp.get("participant_id")
    sample_id = resp.get("sample_id")
    rating = resp.get("rating")
    note = resp.get("note", "")
    if pid is None or sample_id is None or rating is None:
        raise HTTPException(status_code=400, detail="participant_id, sample_id, rating required")
    try:
        rating = int(rating)
    except Exception:
        raise HTTPException(status_code=400, detail="rating must be integer")
    if not (0 <= rating <= 4):
        raise HTTPException(status_code=400, detail="rating must be 0..4")

    cur = DB.cursor()
    # Optionally: check participant and that sample belongs to their assigned samples
    cur.execute("SELECT samples_json FROM participants WHERE id = ?", (pid,))
    row = cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="participant not found")
    samples_json = row[0]
    sample_ids = json.loads(samples_json)
    if sample_id not in sample_ids:
        # allow submission but warn
        pass

    # store response without optional note (notes are no longer collected)
    cur.execute(
        "INSERT INTO responses(participant_id, sample_id, rating, ts) VALUES (?, ?, ?, ?)",
        (pid, sample_id, rating, datetime.utcnow().isoformat()),
    )
    DB.commit()
    return {"ok": True}


@app.get("/admin/assignments")
def admin_assignments():
    """Return counts of how many participants have each foundation pair, and counts of each single foundation assignment."""
    cur = DB.cursor()
    cur.execute("SELECT assigned_foundations FROM participants")
    rows = cur.fetchall()
    pair_counts = Counter()
    single_counts = Counter()
    for (af,) in rows:
        if not af:
            continue
        try:
            pair = tuple(json.loads(af))
            if len(pair) == 2:
                pair_counts[pair] += 1
                single_counts[pair[0]] += 1
                single_counts[pair[1]] += 1
        except Exception:
            continue
    return {"pair_counts": dict(pair_counts), "single_counts": dict(single_counts)}


@app.get("/admin/responses")
def admin_responses():
    """Return basic aggregated response info: counts per foundation and per label, and raw responses (limited)."""
    cur = DB.cursor()
    cur.execute("SELECT participant_id, sample_id, rating, ts FROM responses ORDER BY ts DESC LIMIT 2000")
    rows = cur.fetchall()
    # aggregate counts per foundation by looking up sample foundation
    agg = defaultdict(lambda: {"original": 0, "generated": 0, "total": 0})
    raw = []
    for (pid, sample_id, rating, ts) in rows:
        sample = next((s for s in SAMPLES if s["id"] == sample_id), None)
        if sample:
            f = sample["foundation"]
            lab = sample["label"]
            agg[f][lab] += 1
            agg[f]["total"] += 1
        raw.append({"participant_id": pid, "sample_id": sample_id, "rating": rating, "ts": ts})
    return {"aggregates_by_foundation": agg, "recent_responses": raw}


# A simple health endpoint
@app.get("/healthz")
def health():
    return {"ok": True, "samples_loaded": len(SAMPLES), "foundations": FOUNDATIONS}


# If static front-end not present, provide a minimal message
@app.get("/app-info")
def app_info():
    return {"message": "Labeling backend running. If you want the frontend, place files in ./static or use the provided static folder."}


# Serve legacy asset paths so browsers requesting /app.css or /app.js (cached or bookmarked)
# still receive the files even though static files are mounted under /static.
@app.get("/app.css")
def legacy_app_css():
    css_file = STATIC_DIR / "app.css"
    if css_file.exists():
        return FileResponse(str(css_file))
    raise HTTPException(status_code=404, detail="app.css not found")


@app.get("/app.js")
def legacy_app_js():
    js_file = STATIC_DIR / "app.js"
    if js_file.exists():
        return FileResponse(str(js_file))
    raise HTTPException(status_code=404, detail="app.js not found")
