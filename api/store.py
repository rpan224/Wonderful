"""In-memory data store, loaded from SQLite once at API startup.

The dataset is small and refreshed only once a day, so holding it in memory
with pre-built vocabularies is what makes fuzzy search fast: the per-request
work is matching a query against a few dozen distinct values.
"""
import sqlite3
from pathlib import Path

from .config import DB_PATH

# Fields whose distinct values form a fuzzy-search vocabulary.
VOCAB_FIELDS = ["location", "speciality", "clinic_name", "county"]


class DataStore:
    """Holds the doctor records and the vocabularies fuzzy search runs against."""

    def __init__(self) -> None:
        self.doctors: list[dict] = []
        self.by_id: dict[str, dict] = {}
        self.vocabularies: dict[str, list[str]] = {}
        self.languages: list[str] = []
        self.meta: dict = {}

    def load(self, db_path: Path = DB_PATH) -> None:
        """(Re)load everything from SQLite. Called at startup and on /reload."""
        if not Path(db_path).exists():
            raise FileNotFoundError(
                f"Database not found at {db_path}. "
                f"Run the pipeline first: python -m pipeline.ingest"
            )

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        try:
            langs_by_doctor: dict[str, list[str]] = {}
            for row in conn.execute(
                "SELECT doctor_id, language FROM doctor_languages ORDER BY language"
            ):
                langs_by_doctor.setdefault(row["doctor_id"], []).append(
                    row["language"]
                )

            doctors = []
            for row in conn.execute("SELECT * FROM doctors"):
                doc = dict(row)
                doc.pop("source_raw", None)  # audit-only column, not served
                doc["languages"] = langs_by_doctor.get(doc["id"], [])
                doc["full_name"] = f"{doc['first_name']} {doc['last_name']}"
                doctors.append(doc)

            last_run = conn.execute(
                "SELECT * FROM ingestion_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        finally:
            conn.close()

        self.doctors = doctors
        self.by_id = {d["id"]: d for d in doctors}
        self._build_vocabularies()
        self.meta = {
            "total_doctors": len(doctors),
            "last_ingestion": dict(last_run) if last_run else None,
        }

    def _build_vocabularies(self) -> None:
        self.vocabularies = {
            field: sorted({d[field] for d in self.doctors if d.get(field)})
            for field in VOCAB_FIELDS
        }
        self.languages = sorted(
            {lang for d in self.doctors for lang in d["languages"]}
        )


# Module-level singleton shared by the request handlers.
store = DataStore()
