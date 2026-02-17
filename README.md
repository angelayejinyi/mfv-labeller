Labeling app (minimal)

Overview
--------
This is a minimal labeling app for rating vignettes. It includes:

- A FastAPI backend (`backend.py`) which:
  - loads `MFV130Gen.csv` as the sample pool,
  - assigns each participant two foundations (balanced across participants),
  - selects 10 original + 20 generated samples for the participant (randomized order),
  - stores participant metadata and responses in SQLite (`data.db`),
  - provides admin endpoints for checking assignments and responses.

- A tiny frontend in `static/` (HTML/JS/CSS) which:
  - registers a participant (/register),
  - shows the 30 items one-by-one, lets participants rate 0-4 with an optional note,
  - submits responses to the backend (/submit).

Files added
-----------
- `backend.py` — FastAPI backend
- `static/index.html`, `static/app.js`, `static/app.css` — frontend
- `requirements.txt` — Python dependencies

How to run locally (development)
--------------------------------
1. Create a virtualenv and install dependencies:

   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt

2. Start the backend (serves static files too):

   uvicorn backend:app --reload --host 0.0.0.0 --port 8000

3. Open the frontend in your browser at: http://localhost:8000/static/index.html
   (or simply http://localhost:8000/ which will serve index if static mounted)

Admin & checking
----------------
- GET /admin/assignments — returns counts of foundation-pair assignments and single foundation counts
- GET /admin/responses — returns recent responses and aggregates by foundation
- GET /healthz — basic health (number of samples loaded, foundations)

Data storage
------------
- SQLite DB file `data.db` created in the project root. Tables:
  - participants(id TEXT PRIMARY KEY, assigned_foundations TEXT (JSON), samples_json TEXT, created_at TEXT)
  - responses(id INTEGER PK AUTOINCREMENT, participant_id, sample_id, rating, note, ts)

Security & deployment notes
---------------------------
- This is a simple demo. For production you should:
  - add authentication for admin endpoints,
  - run behind an HTTPS reverse proxy (nginx),
  - use a production-ready database if concurrent writes and scaling are necessary,
  - add rate limiting / CSRF protections for the frontend as needed.

Potential extensions
--------------------
- Pre-register participants and display progress/resume
- Allow participants to select foundations (the backend currently assigns them to keep balance)
- Export aggregated CSV summaries
- Add basic tests for backend endpoints

If you'd like, I can deploy this to a small VM, Dockerize it, or adapt the frontend to a React app. Tell me which option you prefer.