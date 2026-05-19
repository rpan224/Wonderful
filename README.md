# MariaCare Doctor Search API

A data pipeline and search API that turns MariaCare's raw JSON database dump
into a fast, **typo-tolerant** search service for doctors and clinics.

Built to sit behind a future voice agent — so search terms are matched even
when speech-to-text mistranscribes them (e.g. `Temisoara` resolves to
`Timisoara`).

---

## The problem

MariaCare (a healthcare company) has no API for filtering or searching their
data. The only thing they expose is **one endpoint that dumps every database
record as raw JSON**. This project is the bridge:

1. a **pipeline** that loads that dump and stores it cleanly, and
2. an **API** that serves it with searching and filtering.

> The AI agent itself is out of scope — it will be built on top of this API.

---

## Architecture

```
 MariaCare dump            once a day                  always running
 (raw JSON)      ──►   PIPELINE   ──►   SQLite   ──►   FastAPI   ──►  clients
                       fetch +          (durable      in-memory      (the agent)
                       normalize +      store)        index +
                       load                           fuzzy search
```

The **pipeline** and the **API** are separate processes; SQLite is the contract
between them. The pipeline can fail and retry on its own daily schedule without
touching the live API, and the API can restart instantly from SQLite without
re-pulling from MariaCare.

---

## Why these choices

**SQLite as the store.** The data is small (one clinic directory) and refreshed
only once a day, so a database *server* (Postgres) would be infrastructure for
its own sake. SQLite is a single file, needs zero setup, and is still a real
relational database. Postgres is the documented scale-up path if the data ever
grows large or needs concurrent writers.

**The pipeline is a full atomic refresh, not an upsert.** The daily dump is the
*complete* dataset — a doctor removed from MariaCare's database simply vanishes
from the dump. Only replacing everything (inside one transaction) reflects
deletions correctly.

**Deterministic IDs.** The source has no ID, so each doctor gets one from a
hash of a composite natural key (name + clinic + address + speciality). Because
it is deterministic, re-running the pipeline produces the *same* IDs — the load
is idempotent, and the agent on top can safely cache a doctor's ID.

**Fuzzy matching happens at query time, not load time.** The typos are not in
MariaCare's data — they are in the *query* (speech-to-text errors). You cannot
pre-compute matches for queries you have not received yet. So load time builds
an in-memory index of clean canonical values; query time matches the (possibly
mistyped) term against it. The dataset is tiny, so this is microsecond-fast.

**`rapidfuzz` for matching.** Edit-distance based, C++-backed. Each query term
is resolved in three tiers: exact match → best fuzzy match above a score
threshold (80/100) → no confident match (returns nothing rather than guessing).

---

## Quickstart

Requires Python 3.11+.

```bash
pip install -r requirements.txt
uvicorn api.main:app --reload
```

The API builds the SQLite database from the sample dump on first start, so
there is no separate setup step. Then open:

- **http://127.0.0.1:8000/docs** — interactive Swagger UI (try it here)
- **http://127.0.0.1:8000/health** — liveness check

### Run with Docker

```bash
docker build -t mariacare-api .
docker run -p 8000:8000 mariacare-api
```

### Run the pipeline on its own

The API auto-builds the database, but the pipeline is also a standalone job
(this is what a daily cron would run):

```bash
python -m pipeline.ingest
```

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/doctors` | Search / filter doctors |
| `GET`  | `/doctors/{id}` | Fetch one doctor by ID |
| `GET`  | `/clinics` | List clinics (aggregated from doctor records) |
| `GET`  | `/meta` | Data freshness — last ingestion run |
| `GET`  | `/health` | Liveness check |
| `POST` | `/reload` | Re-read the database (for daily refresh) |
| `GET`  | `/docs` | Interactive API documentation |

### `GET /doctors` parameters

All text parameters are **typo-tolerant**.

| Parameter | Description |
|-----------|-------------|
| `name` | Doctor name (first, last, or full) |
| `location` | City / location |
| `speciality` | Medical speciality |
| `clinic` | Clinic name |
| `county` | County |
| `language` | Language spoken |
| `min_rating` | Minimum rating (0–5) |
| `min_experience` / `max_experience` | Years of experience range |
| `sort_by` | `rating`, `experience`, or `name` |
| `order` | `asc` or `desc` (default `desc`) |
| `limit` / `offset` | Pagination (default 20, max 100) |

### Example requests

```bash
# Exact search
curl "http://127.0.0.1:8000/doctors?location=Brasov"

# Typo-tolerant: "Temisoara" resolves to "Timisoara"
curl "http://127.0.0.1:8000/doctors?location=Temisoara"

# Typo + filter: "Nurology" -> "Neurology", rated 4+
curl "http://127.0.0.1:8000/doctors?speciality=Nurology&min_rating=4"

# Clinics in a city
curl "http://127.0.0.1:8000/clinics?location=Buzau"
```

### How the response shows its work

Every search response includes a `query_interpretation` block that reports how
each term was resolved — so the caller (the agent) can confirm *"showing results
for Timisoara"* instead of silently guessing:

```json
{
  "count": 2,
  "total": 2,
  "query_interpretation": {
    "location": {
      "query": "Temisoara",
      "matched": "Timisoara",
      "score": 88.9,
      "method": "fuzzy"
    }
  },
  "results": [ ... ]
}
```

---

## Project structure

```
pipeline/              Daily ingest: raw JSON -> SQLite
  fetch.py             Stage 1 - fetch + repair malformed JSON
  transform.py         Stage 2/3 - validate, normalize, deterministic IDs
  db.py                Stage 4 - schema + atomic full-refresh load
  ingest.py            Orchestrator  (python -m pipeline.ingest)
api/                   FastAPI search service
  store.py             In-memory store + fuzzy-search vocabularies
  fuzzy.py             Typo-tolerant matching (rapidfuzz)
  search.py            Search / filter / sort / clinic aggregation
  models.py            Response schemas
  main.py              Endpoints  (uvicorn api.main:app)
data/
  source_dump.json     Sample dump — stands in for MariaCare's endpoint
scripts/
  prepare_source_data.py   One-off repair of the original (malformed) dump
Dockerfile / render.yaml   Deployment
```

---

## Known limitations & future work

- **Name matching can be slightly loose.** Edit-distance cannot perfectly
  separate a real typo from a genuinely similar surname (e.g. `Dumitresku`
  matches both `Dumitrescu` and `Dumitru`). Results are ranked best-match-first
  to mitigate this; an absolute edit-distance cap or phonetic matching would
  tighten it.
- **Edit-distance only.** Heavily garbled transcriptions (a 4+ character change)
  are intentionally rejected. Phonetic matching (Soundex/Metaphone) is the
  natural next step for sound-alike errors.
- **Single-node, in-memory.** Perfect for this data size; a larger dataset
  would move filtering into SQL or Postgres with a trigram index.

---

## Deployment

`render.yaml` is included for a one-click deploy: in [Render](https://render.com),
choose **New → Blueprint** and connect this repository — it builds the
`Dockerfile` and serves the API at a public HTTPS URL.
