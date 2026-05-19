"""Search, filter, sort and paginate doctors; aggregate clinics.

Fuzzy resolution happens here: a (possibly mistyped) query term is resolved
to a canonical value, which is then used as an exact filter.
"""
from .config import FUZZY_THRESHOLD
from .fuzzy import Match, resolve, score_name
from .store import DataStore

# search parameter -> doctor field / vocabulary key
_VOCAB_PARAMS = {
    "location": "location",
    "speciality": "speciality",
    "clinic": "clinic_name",
    "county": "county",
}


def _match_dict(query: str, match: Match | None) -> dict:
    """The 'did you mean' block returned to the caller."""
    if match is None:
        return {"query": query, "matched": None, "score": 0.0,
                "method": "no_match"}
    return {"query": match.query, "matched": match.matched,
            "score": match.score, "method": match.method}


def _empty(interpretation: dict) -> dict:
    return {"count": 0, "total": 0,
            "query_interpretation": interpretation, "results": []}


def search_doctors(
    store: DataStore, *, name=None, location=None, speciality=None,
    clinic=None, county=None, language=None, min_rating=None,
    min_experience=None, max_experience=None, sort_by=None, order="desc",
    limit=20, offset=0,
) -> dict:
    results = list(store.doctors)
    interpretation: dict[str, dict] = {}

    # Fuzzy-resolved exact filters: resolve the term, then filter exactly.
    for param, value in (("location", location), ("speciality", speciality),
                         ("clinic", clinic), ("county", county)):
        if not value:
            continue
        field = _VOCAB_PARAMS[param]
        match = resolve(value, store.vocabularies.get(field, []))
        interpretation[param] = _match_dict(value, match)
        if match is None:
            return _empty(interpretation)  # no confident match -> no results
        results = [d for d in results if d.get(field) == match.matched]

    if language:
        match = resolve(language, store.languages)
        interpretation["language"] = _match_dict(language, match)
        if match is None:
            return _empty(interpretation)
        results = [d for d in results if match.matched in d["languages"]]

    # Name uses per-doctor scoring so all doctors sharing a surname match.
    name_scores: dict[str, float] = {}
    if name:
        matched_docs = []
        for d in results:
            s = score_name(name, d["first_name"], d["last_name"],
                           d["full_name"])
            if s >= FUZZY_THRESHOLD:
                name_scores[d["id"]] = s
                matched_docs.append(d)
        results = matched_docs
        interpretation["name"] = {
            "query": name,
            "interpreted_as": "fuzzy name search",
            "name_matches": len(results),
        }

    # Numeric filters - exact comparisons, no fuzzing.
    if min_rating is not None:
        results = [d for d in results if (d.get("rating") or 0) >= min_rating]
    if min_experience is not None:
        results = [d for d in results
                   if (d.get("years_experience") or 0) >= min_experience]
    if max_experience is not None:
        results = [d for d in results
                   if (d.get("years_experience") or 0) <= max_experience]

    _sort_doctors(results, sort_by, order, name_scores, name is not None)

    total = len(results)
    page = results[offset:offset + limit]
    return {"count": len(page), "total": total,
            "query_interpretation": interpretation, "results": page}


def _sort_doctors(results, sort_by, order, name_scores, name_searched):
    reverse = order != "asc"
    if sort_by == "rating":
        results.sort(key=lambda d: d.get("rating") or 0, reverse=reverse)
    elif sort_by == "experience":
        results.sort(key=lambda d: d.get("years_experience") or 0,
                     reverse=reverse)
    elif sort_by == "name":
        results.sort(key=lambda d: d["full_name"].lower(), reverse=reverse)
    elif name_searched:
        # default when searching by name: best name match first
        results.sort(key=lambda d: name_scores.get(d["id"], 0.0), reverse=True)
    else:
        # default: highest rated first
        results.sort(key=lambda d: d.get("rating") or 0, reverse=True)


def list_clinics(store: DataStore, *, name=None, location=None,
                 limit=20, offset=0) -> dict:
    """A 'clinic' is a distinct clinic_name aggregated from doctor records."""
    groups: dict[str, list[dict]] = {}
    for d in store.doctors:
        if d.get("clinic_name"):
            groups.setdefault(d["clinic_name"], []).append(d)

    interpretation: dict[str, dict] = {}
    selected = set(groups.keys())

    if name:
        match = resolve(name, sorted(groups.keys()))
        interpretation["name"] = _match_dict(name, match)
        if match is None:
            return _empty(interpretation)
        selected &= {match.matched}

    if location:
        match = resolve(location, store.vocabularies.get("location", []))
        interpretation["location"] = _match_dict(location, match)
        if match is None:
            return _empty(interpretation)
        selected &= {c for c, docs in groups.items()
                     if any(x.get("location") == match.matched for x in docs)}

    clinics = []
    for cname in sorted(selected):
        docs = groups[cname]
        ratings = [x["rating"] for x in docs if x.get("rating") is not None]
        clinics.append({
            "clinic_name": cname,
            "location": docs[0].get("location"),
            "county": docs[0].get("county"),
            "doctor_count": len(docs),
            "specialities": sorted({x["speciality"] for x in docs
                                    if x.get("speciality")}),
            "avg_rating": (round(sum(ratings) / len(ratings), 2)
                           if ratings else None),
        })

    total = len(clinics)
    page = clinics[offset:offset + limit]
    return {"count": len(page), "total": total,
            "query_interpretation": interpretation, "results": page}
