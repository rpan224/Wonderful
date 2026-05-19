"""Stage 4 - SQLite schema and the atomic load.

The daily dump is the *complete* dataset, so the load is a full refresh
(replace everything) rather than an upsert - that is the only way a doctor
removed from MariaCare's database actually disappears from ours. The refresh
runs inside one transaction so readers never see a half-loaded database.
"""
import sqlite3

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS doctors (
    id                TEXT PRIMARY KEY,
    first_name        TEXT NOT NULL,
    last_name         TEXT NOT NULL,
    clinic_name       TEXT,
    location          TEXT,
    county            TEXT,
    speciality        TEXT,
    address           TEXT,
    phone             TEXT,
    email             TEXT,
    postal_code       TEXT,
    years_experience  INTEGER,
    rating            REAL,
    availability      TEXT,
    education         TEXT,
    source_raw        TEXT,
    ingested_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_doctors_location   ON doctors(location);
CREATE INDEX IF NOT EXISTS idx_doctors_speciality ON doctors(speciality);
CREATE INDEX IF NOT EXISTS idx_doctors_county     ON doctors(county);
CREATE INDEX IF NOT EXISTS idx_doctors_last_name  ON doctors(last_name);

CREATE TABLE IF NOT EXISTS doctor_languages (
    doctor_id  TEXT NOT NULL REFERENCES doctors(id) ON DELETE CASCADE,
    language   TEXT NOT NULL,
    PRIMARY KEY (doctor_id, language)
);

CREATE TABLE IF NOT EXISTS ingestion_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at        TEXT NOT NULL,
    finished_at       TEXT,
    status            TEXT,
    records_in        INTEGER,
    records_written   INTEGER,
    records_rejected  INTEGER,
    error             TEXT
);
"""

DOCTOR_COLUMNS = [
    "id", "first_name", "last_name", "clinic_name", "location", "county",
    "speciality", "address", "phone", "email", "postal_code",
    "years_experience", "rating", "availability", "education",
    "source_raw", "ingested_at",
]


def connect(path=DB_PATH) -> sqlite3.Connection:
    # isolation_level=None -> autocommit; we manage transactions explicitly.
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


def start_run(conn: sqlite3.Connection, started_at: str) -> int:
    """Record a run as 'running' immediately, so a crash still leaves a trace."""
    cur = conn.execute(
        "INSERT INTO ingestion_runs (started_at, status) VALUES (?, 'running')",
        (started_at,),
    )
    return cur.lastrowid


def finish_run_success(conn, run_id, finished_at, records_in, written, rejected):
    conn.execute(
        """UPDATE ingestion_runs
              SET finished_at = ?, status = 'success',
                  records_in = ?, records_written = ?, records_rejected = ?
            WHERE id = ?""",
        (finished_at, records_in, written, rejected, run_id),
    )


def finish_run_failed(conn, run_id, finished_at, error):
    conn.execute(
        """UPDATE ingestion_runs
              SET finished_at = ?, status = 'failed', error = ?
            WHERE id = ?""",
        (finished_at, error, run_id),
    )


def load_doctors(conn: sqlite3.Connection, records: list[dict]) -> None:
    """Atomic full refresh of doctors + doctor_languages."""
    placeholders = ", ".join(["?"] * len(DOCTOR_COLUMNS))
    insert_doctor = (
        f"INSERT INTO doctors ({', '.join(DOCTOR_COLUMNS)}) "
        f"VALUES ({placeholders})"
    )
    doctor_rows = [tuple(r.get(c) for c in DOCTOR_COLUMNS) for r in records]
    lang_rows = [
        (r["id"], lang) for r in records for lang in r.get("languages", [])
    ]

    conn.execute("BEGIN")
    try:
        conn.execute("DELETE FROM doctor_languages")
        conn.execute("DELETE FROM doctors")
        conn.executemany(insert_doctor, doctor_rows)
        conn.executemany(
            "INSERT INTO doctor_languages (doctor_id, language) VALUES (?, ?)",
            lang_rows,
        )
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
