"""Pydantic response models - they also drive the OpenAPI schema at /docs."""
from pydantic import BaseModel


class Doctor(BaseModel):
    id: str
    first_name: str
    last_name: str
    full_name: str
    clinic_name: str | None = None
    location: str | None = None
    county: str | None = None
    speciality: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
    postal_code: str | None = None
    years_experience: int | None = None
    rating: float | None = None
    availability: str | None = None
    education: str | None = None
    languages: list[str] = []
    ingested_at: str | None = None


class DoctorSearchResponse(BaseModel):
    count: int                                  # results on this page
    total: int                                  # total matches before paging
    query_interpretation: dict[str, dict] = {}  # how each term was resolved
    results: list[Doctor]


class Clinic(BaseModel):
    clinic_name: str
    location: str | None = None
    county: str | None = None
    doctor_count: int
    specialities: list[str] = []
    avg_rating: float | None = None


class ClinicSearchResponse(BaseModel):
    count: int
    total: int
    query_interpretation: dict[str, dict] = {}
    results: list[Clinic]


class MetaResponse(BaseModel):
    total_doctors: int
    last_ingestion: dict | None = None
