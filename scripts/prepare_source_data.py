"""
One-off helper: turn the raw dump we received from MariaCare into a clean,
valid JSON file that we can treat as the "source" endpoint for development.

The raw file we were given is *almost* a JSON array, but it is malformed:
  - it has a trailing comma after the last object
  - it is missing the closing `]`

This script repairs those syntax issues WITHOUT changing any data values
(normalisation of the values themselves is the pipeline's job, not this step).
"""
import json
from pathlib import Path

RAW_INPUT = Path(r"C:\Users\ragha\OneDrive\Desktop\File with data.txt")
CLEAN_OUTPUT = Path(__file__).resolve().parents[1] / "data" / "source_dump.json"


def repair_json(text: str) -> str:
    """Fix the two known syntax problems in the raw dump."""
    text = text.strip()
    if not text.startswith("["):
        text = "[" + text
    text = text.rstrip()
    if text.endswith(","):          # drop trailing comma
        text = text[:-1].rstrip()
    if not text.endswith("]"):      # add missing close bracket
        text = text + "]"
    return text


def main() -> None:
    raw = RAW_INPUT.read_text(encoding="utf-8")
    repaired = repair_json(raw)

    records = json.loads(repaired)  # raises if still invalid

    CLEAN_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    CLEAN_OUTPUT.write_text(
        json.dumps(records, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # quick summary so we understand what we are working with
    print(f"Records parsed       : {len(records)}")
    print(f"Fields per record    : {sorted(records[0].keys())}")
    print(f"Distinct specialities: {len(set(r['speciality'] for r in records))}")
    print(f"Distinct locations   : {len(set(r['location'] for r in records))}")
    print(f"Distinct clinics     : {len(set(r['clinic_name'] for r in records))}")
    print(f"Distinct counties    : {len(set(r['county'] for r in records))}")
    print(f"Written to           : {CLEAN_OUTPUT}")


if __name__ == "__main__":
    main()
