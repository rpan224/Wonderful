"""Pipeline entry point - orchestrates the four stages.

Run once a day (the brief says daily refresh is enough):

    python -m pipeline.ingest

It is idempotent: deterministic IDs + full refresh mean running it twice
on the same dump yields an identical database.
"""
import json
import logging
from datetime import datetime, timezone

from . import db
from .fetch import fetch_source
from .transform import disambiguate_id, make_id, normalize_record, validate

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
)
log = logging.getLogger("pipeline")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def run_ingest() -> None:
    started = _now()
    conn = db.connect()
    db.init_db(conn)
    run_id = db.start_run(conn, started)
    log.info("ingestion run %s started", run_id)

    try:
        raw_records = fetch_source()
        records_in = len(raw_records)
        log.info("fetched %d raw records", records_in)

        valid_records: list[dict] = []
        rejected = 0
        ids_seen: dict[str, int] = {}

        for idx, raw in enumerate(raw_records):
            if not isinstance(raw, dict):
                rejected += 1
                log.warning("record %d rejected: not a JSON object", idx)
                continue

            rec = normalize_record(raw)
            error = validate(rec)
            if error:
                rejected += 1
                log.warning("record %d rejected: %s", idx, error)
                continue

            rec_id = make_id(rec)
            if rec_id in ids_seen:
                rec_id = disambiguate_id(rec_id, rec, ids_seen)
                log.warning("record %d: ID collision, disambiguated", idx)
            ids_seen[rec_id] = idx

            rec["id"] = rec_id
            rec["source_raw"] = json.dumps(raw, ensure_ascii=False)
            rec["ingested_at"] = started
            valid_records.append(rec)

        db.load_doctors(conn, valid_records)
        db.finish_run_success(
            conn, run_id, _now(), records_in, len(valid_records), rejected
        )
        log.info(
            "ingestion run %s success: %d written, %d rejected",
            run_id, len(valid_records), rejected,
        )
    except Exception as exc:
        db.finish_run_failed(conn, run_id, _now(), str(exc))
        log.error("ingestion run %s failed: %s", run_id, exc)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_ingest()
