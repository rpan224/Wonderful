"""Stage 2 & 3 - Validate / normalize a raw record, and generate its ID.

Normalization here only standardizes the *stored* data (trimming, casing,
type coercion). Typo-tolerant matching of user *queries* is a separate
concern handled at query time by the API.
"""
import hashlib

# Fields copied straight across as cleaned strings.
STRING_FIELDS = [
    "first_name", "last_name", "clinic_name", "location", "county",
    "speciality", "address", "phone", "email", "postal_code",
    "availability", "education",
]

# A record cannot be useful without a name, so these are mandatory.
REQUIRED_FIELDS = ["first_name", "last_name"]

# Fields combined into the deterministic ID. Chosen because they are always
# present and together uniquely identify a doctor-at-a-clinic. Email/phone are
# deliberately excluded - they are the fields most likely to be corrected
# between daily dumps, and identity should stay stable.
ID_KEY_FIELDS = ["first_name", "last_name", "clinic_name", "address", "speciality"]


def _clean_str(value) -> str | None:
    """Trim and collapse internal whitespace; empty becomes None."""
    if value is None:
        return None
    cleaned = " ".join(str(value).split())
    return cleaned or None


def _clean_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clean_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean_languages(value) -> list[str]:
    """Return a de-duplicated list of cleaned language strings."""
    if not isinstance(value, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        lang = _clean_str(item)
        if lang and lang.lower() not in seen:
            seen.add(lang.lower())
            out.append(lang)
    return out


def normalize_record(raw: dict) -> dict:
    """Produce a normalized record dict (without an ID)."""
    rec = {field: _clean_str(raw.get(field)) for field in STRING_FIELDS}
    if rec["email"]:
        rec["email"] = rec["email"].lower()
    rec["years_experience"] = _clean_int(raw.get("years_experience"))
    rec["rating"] = _clean_float(raw.get("rating"))
    rec["languages"] = _clean_languages(raw.get("languages"))
    return rec


def validate(rec: dict) -> str | None:
    """Return an error message if the normalized record is invalid, else None."""
    missing = [f for f in REQUIRED_FIELDS if not rec.get(f)]
    if missing:
        return f"missing required field(s): {', '.join(missing)}"
    return None


def make_id(rec: dict) -> str:
    """Deterministic, stable-across-runs ID from a composite natural key."""
    key = "|".join((rec.get(f) or "") for f in ID_KEY_FIELDS).lower()
    key = " ".join(key.split())
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    return f"doc_{digest}"


def disambiguate_id(base_id: str, rec: dict, taken) -> str:
    """Resolve the (rare) case of two records hashing to the same ID."""
    extra = rec.get("phone") or rec.get("email") or ""
    suffix = hashlib.sha256(extra.encode("utf-8")).hexdigest()[:6]
    candidate = f"{base_id}_{suffix}"
    counter = 1
    while candidate in taken:
        candidate = f"{base_id}_{suffix}_{counter}"
        counter += 1
    return candidate
