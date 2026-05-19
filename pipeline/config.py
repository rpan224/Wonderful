"""Shared paths. Kept in one place because the API layer reads the same DB."""
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

# The local JSON file that stands in for MariaCare's "raw dump" endpoint.
SOURCE_PATH = DATA_DIR / "source_dump.json"

# The SQLite database the pipeline writes and the API reads.
DB_PATH = DATA_DIR / "mariacare.db"
