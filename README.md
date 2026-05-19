# MariaCare Doctor Search API

A data pipeline and search API that turns MariaCare's raw JSON database dump
into a fast, **typo-tolerant** search service for doctors and clinics.

---

## Test it in 1 minute

**Prerequisite:** Python 3.11 or newer.

```bash
git clone https://github.com/rpan224/Wonderful.git
cd Wonderful
pip install -r requirements.txt
uvicorn api.main:app
```

Then open **http://127.0.0.1:8000/docs**

That page is an interactive UI — you can run every endpoint from the browser,
no tools needed. There is **no database setup step**: the API builds its
database automatically the first time it starts.

### Run a search — a worked example

A search is just a URL: the path `/doctors` with a `?parameter=value` on the
end. Say you want to find doctors in a city — there are two ways to run it.

**Option A — paste a URL in your browser.** Put this in the address bar:

```
http://127.0.0.1:8000/doctors?location=Iasi
```

You get back JSON: the doctors in that city, plus a `query_interpretation`
block that shows how the city name was understood.

**Option B — the interactive page.** Open `http://127.0.0.1:8000/docs`, click
**`GET /doctors`**, click **"Try it out"**, type a city into the `location`
box, and click **"Execute"** — the result appears right below.

**The interesting part — typos still work.** The API is built for a voice
agent, so a *misspelled* city still resolves to the right one:

```
http://127.0.0.1:8000/doctors?location=Temisoara
```

returns doctors in **Timisoara**, and the response explains itself:

```json
"query_interpretation": {
  "location": { "query": "Temisoara", "matched": "Timisoara",
                "score": 88.9, "method": "fuzzy" }
}
```

### Searches to try

With the server running, paste any of these into your browser:

| Type this | What happens |
|-----------|--------------|
| `http://127.0.0.1:8000/doctors?location=Iasi` | exact match by city |
| `http://127.0.0.1:8000/doctors?location=Temisoara` | typo → finds **Timisoara** |
| `http://127.0.0.1:8000/doctors?location=Konstanta` | typo → finds **Constanta** |
| `http://127.0.0.1:8000/doctors?speciality=Cardiologi` | typo → finds **Cardiology** |
| `http://127.0.0.1:8000/doctors?name=Dumitresku` | typo → finds **Dumitrescu** |
| `http://127.0.0.1:8000/doctors?location=Buzau&min_rating=4.5` | filter: top-rated doctors in a city |
| `http://127.0.0.1:8000/clinics?location=Konstanta` | clinics in a (typo'd) city |
| `http://127.0.0.1:8000/meta` | when the data was last refreshed |

> **Tip for short city names:** four-letter names like `Iasi` or `Arad` need
> near-exact spelling — one wrong letter is too large a change in such a short
> word to match confidently. Typo tolerance works best on normal-length names
> like `Temisoara` or `Konstanta`.

### Alternative: run with Docker

```bash
docker build -t mariacare-api . && docker run -p 8000:8000 mariacare-api
```

### Alternative: a hosted URL

`render.yaml` is included for a one-click cloud deploy — see
[Deployment](#deployment) at the bottom.

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

### Run the pipeline on its own

The API auto-builds the database, but the pipeline is also a standalone job
(this is what a daily cron would run):

```bash
python -m pipeline.ingest
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
