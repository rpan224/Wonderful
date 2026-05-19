"""FastAPI app: typo-tolerant search over MariaCare's doctor directory.

Run locally:   uvicorn api.main:app --reload
Interactive docs:   http://127.0.0.1:8000/docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from .config import DB_PATH, DEFAULT_LIMIT, MAX_LIMIT
from .models import ClinicSearchResponse, Doctor, DoctorSearchResponse, MetaResponse
from .search import list_clinics, search_doctors
from .store import store


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Build the database on first run so a fresh clone (or container) works
    # with no setup step. Normally the pipeline runs on its own daily schedule.
    if not DB_PATH.exists():
        from pipeline.ingest import run_ingest
        run_ingest()
    # Load the dataset into memory once, when the server starts.
    store.load()
    yield


app = FastAPI(
    title="MariaCare Doctor Search API",
    description=(
        "Typo-tolerant search over MariaCare's doctor & clinic directory. "
        "Built to sit behind a voice agent, so location/name/speciality "
        "terms are matched even when speech-to-text mistranscribes them "
        "(e.g. `Bukalest` resolves to `Bucharest`)."
    ),
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def root():
    return {"service": "MariaCare Doctor Search API", "docs": "/docs"}


@app.get("/health", tags=["ops"])
def health():
    """Liveness check."""
    return {"status": "ok", "doctors_loaded": len(store.doctors)}


@app.get("/meta", response_model=MetaResponse, tags=["ops"])
def meta():
    """Data freshness: when the pipeline last ran and how much it loaded."""
    return store.meta


@app.post("/reload", tags=["ops"])
def reload():
    """Re-read the database - lets the daily pipeline refresh data live."""
    store.load()
    return {"status": "reloaded", "total_doctors": len(store.doctors)}


@app.get("/doctors", response_model=DoctorSearchResponse, tags=["search"])
def get_doctors(
    name: str | None = Query(None, description="Doctor name (typo-tolerant)"),
    location: str | None = Query(None, description="City / location (typo-tolerant)"),
    speciality: str | None = Query(None, description="Medical speciality (typo-tolerant)"),
    clinic: str | None = Query(None, description="Clinic name (typo-tolerant)"),
    county: str | None = Query(None, description="County (typo-tolerant)"),
    language: str | None = Query(None, description="Language spoken (typo-tolerant)"),
    min_rating: float | None = Query(None, ge=0, le=5, description="Minimum rating"),
    min_experience: int | None = Query(None, ge=0, description="Minimum years of experience"),
    max_experience: int | None = Query(None, ge=0, description="Maximum years of experience"),
    sort_by: str | None = Query(None, pattern="^(rating|experience|name)$"),
    order: str = Query("desc", pattern="^(asc|desc)$"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    """Search doctors. Text terms are matched even with small typos; the
    `query_interpretation` block shows what each term resolved to."""
    return search_doctors(
        store, name=name, location=location, speciality=speciality,
        clinic=clinic, county=county, language=language, min_rating=min_rating,
        min_experience=min_experience, max_experience=max_experience,
        sort_by=sort_by, order=order, limit=limit, offset=offset,
    )


@app.get("/doctors/{doctor_id}", response_model=Doctor, tags=["search"])
def get_doctor(doctor_id: str):
    """Fetch a single doctor by their stable ID."""
    doctor = store.by_id.get(doctor_id)
    if doctor is None:
        raise HTTPException(status_code=404,
                            detail=f"No doctor with id '{doctor_id}'")
    return doctor


@app.get("/clinics", response_model=ClinicSearchResponse, tags=["search"])
def get_clinics(
    name: str | None = Query(None, description="Clinic name (typo-tolerant)"),
    location: str | None = Query(None, description="City / location (typo-tolerant)"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0),
):
    """List clinics (aggregated from doctor records) with doctor counts."""
    return list_clinics(store, name=name, location=location,
                        limit=limit, offset=offset)
