"""Typo-tolerant matching of query terms against canonical values.

The typos live in the *query* (speech-to-text errors in the agent that calls
this API), not in MariaCare's data. So matching runs at query time against
vocabularies built from the clean, canonical stored values.
"""
from dataclasses import dataclass

from rapidfuzz import fuzz, process, utils

from .config import FUZZY_THRESHOLD


@dataclass
class Match:
    query: str     # what the caller asked for
    matched: str   # the canonical value we resolved it to
    score: float   # 0-100 similarity
    method: str    # "exact" or "fuzzy"


def resolve(
    query: str,
    vocabulary: list[str],
    threshold: int = FUZZY_THRESHOLD,
) -> Match | None:
    """Resolve a query term to a canonical value from ``vocabulary``.

    Three tiers: exact (case-insensitive) -> best fuzzy match above the
    threshold -> ``None`` when nothing is confident enough.
    """
    q = (query or "").strip()
    if not q:
        return None

    # Tier 1: exact match (case-insensitive) - the fast, common path.
    by_lower = {value.lower(): value for value in vocabulary}
    if q.lower() in by_lower:
        return Match(query=q, matched=by_lower[q.lower()], score=100.0,
                     method="exact")

    # Tier 2: fuzzy match. WRatio is a robust general scorer; default_process
    # lowercases and strips punctuation from both sides before comparing.
    result = process.extractOne(
        q, vocabulary,
        scorer=fuzz.WRatio,
        processor=utils.default_process,
        score_cutoff=threshold,
    )
    if result is None:
        return None  # Tier 3: no confident match

    matched, score, _ = result
    return Match(query=q, matched=matched, score=round(score, 1), method="fuzzy")


def score_name(query: str, *names: str) -> float:
    """Best fuzzy score of ``query`` against any of the given name strings.

    Names need per-doctor scoring (not vocabulary resolution): many doctors
    share a surname, and a search for one should return all of them.

    Uses plain edit-distance ``ratio`` rather than ``WRatio``: a name is a
    single token mistyped at the character level, so partial/token-based
    scoring (which WRatio adds) only causes over-matching of similar-but-
    different surnames. We score against first, last and full name
    separately so that both "Dumitrescu" and "Ionut Dumitrescu" queries work.
    """
    candidates = [n for n in names if n]
    if not candidates:
        return 0.0
    return max(
        fuzz.ratio(query, name, processor=utils.default_process)
        for name in candidates
    )
