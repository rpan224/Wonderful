"""Stage 1 - Fetch.

Today this reads a local JSON file that stands in for MariaCare's endpoint.
When the real HTTP endpoint is available, only this module changes.

Parsing is deliberately defensive: the dump we were given was malformed
(trailing comma, missing closing bracket), so we repair-and-retry rather
than trust the input.
"""
import json
from pathlib import Path

from .config import SOURCE_PATH


def _repair_json(text: str) -> str:
    """Fix the two malformations seen in MariaCare's dump."""
    text = text.strip()
    if not text.startswith("["):
        text = "[" + text
    text = text.rstrip()
    if text.endswith(","):          # trailing comma before the (missing) close
        text = text[:-1].rstrip()
    if not text.endswith("]"):      # missing closing bracket
        text = text + "]"
    return text


def fetch_source(path: Path = SOURCE_PATH) -> list[dict]:
    """Return the raw dump as a list of dicts. Repairs malformed JSON."""
    text = Path(path).read_text(encoding="utf-8")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = json.loads(_repair_json(text))

    if not isinstance(data, list):
        raise ValueError("Expected the dump to be a JSON array of records")
    return data
