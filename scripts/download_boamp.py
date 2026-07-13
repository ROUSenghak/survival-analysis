"""
Step 3 - Retrieve BOAMP data.

Source: DILA Opendatasoft Explore API v2.1, dataset `boamp`.
  https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/

This was chosen over the raw DILA yearly/monthly XML archive
(https://echanges.dila.gouv.fr/OPENDATA/BOAMP/) because it is queryable by
date range, returns structured JSON directly, and was confirmed live and
responsive during source discovery (see reports/run_logs/run_log.md).

Retrieval strategy:
  - Query the `.../records/exports/json` bulk-export endpoint (no 10,000-row
    offset cap, unlike the paginated `/records` endpoint).
  - Chunk requests by calendar month, so each request stays small, failures
    are isolated and retryable, and raw files are never overwritten.
  - `select=` drops the redundant `gestion` block (duplicates top-level
    fields) but keeps `donnees`, which holds CPV/SIRET/duration/attribution
    detail parsed later by scripts/parse_boamp.py.
  - Retries with backoff on network/HTTP errors.
  - Deduplicates on `idweb` across all downloaded months before writing the
    download summary (the API does not guarantee no overlap at month
    boundaries).

Study period: 2015-01-01 to the latest available date. See
reports/run_logs/run_log.md (Run 2) for the rationale.

Geographic scope: Pays de la Loire only (buyer department in {44, 49, 53,
72, 85}), applied server-side via `code_departement in (...)` in the `where`
clause. `code_departement` is the notice/buyer department (confirmed
multivalued, e.g. "30;34" after this project's list-join flattening);
`code_departement_prestation` (place of performance) is 100% null in the
retrieved data and unusable as a filter. This filter was verified live
against the API before relying on it for the full bulk run (see run_log.md
Run 2): national Jan-2024 baseline 8,728 records vs. 531 with this filter
applied (~6.1%), and the full 2015-01-01..latest period with this filter
returns 84,623 total records - tractable, unlike the full national archive
(~1.69M) or even a full-national multi-year window.

Raw files are written to data/raw/boamp/pdl/ (a scope-tagged subdirectory)
rather than data/raw/boamp/ directly, because the previous national,
2024-2026-only download used the exact same `boamp_YYYYMM.json` filename
pattern for overlapping months - without a separate directory, the
"skip if exists" logic below would silently keep the stale unfiltered
national content for 2024-01..2026-07 instead of re-fetching the
Pays-de-la-Loire-filtered version. The old national files were moved (not
deleted) to data/raw/boamp_national_2024_2026_archive/.
"""

import calendar
import datetime as dt
import json
import time
from pathlib import Path

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "boamp" / "pdl"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
RAW_DIR.mkdir(parents=True, exist_ok=True)
TABLES_DIR.mkdir(parents=True, exist_ok=True)

API_BASE = "https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp"
EXPORT_URL = f"{API_BASE}/exports/json"

SELECT_FIELDS = ",".join([
    "idweb", "id", "objet", "filename", "famille", "famille_libelle",
    "code_departement", "code_departement_prestation",
    "dateparution", "datefindiffusion", "datelimitereponse",
    "nomacheteur", "titulaire", "perimetre",
    "type_procedure", "soustype_procedure", "procedure_libelle",
    "nature", "sousnature", "nature_libelle", "sousnature_libelle",
    "nature_categorise", "nature_categorise_libelle",
    "descripteur_code", "descripteur_libelle",
    "type_marche", "type_marche_facette", "type_avis",
    "annonce_lie", "annonces_anterieures",
    "source_schema", "donnees", "url_avis", "etat",
])

STUDY_START = dt.date(2015, 1, 1)
STUDY_END = dt.date.today()  # "latest available", recorded as of run date

SCOPE_TAG = "pays_de_la_loire"
PDL_DEPARTMENTS = ["44", "49", "53", "72", "85"]
_DEPT_CLAUSE = "code_departement in (" + ",".join(f'"{d}"' for d in PDL_DEPARTMENTS) + ")"

MAX_RETRIES = 5
BACKOFF_SECONDS = 5
REQUEST_TIMEOUT = 180


def month_ranges(start: dt.date, end: dt.date):
    """Yield (year, month, first_day, last_day) covering [start, end]."""
    cur = dt.date(start.year, start.month, 1)
    while cur <= end:
        last_dom = calendar.monthrange(cur.year, cur.month)[1]
        month_end = min(dt.date(cur.year, cur.month, last_dom), end)
        month_start = max(cur, start)
        yield cur.year, cur.month, month_start, month_end
        if cur.month == 12:
            cur = dt.date(cur.year + 1, 1, 1)
        else:
            cur = dt.date(cur.year, cur.month + 1, 1)


def fetch_month(year: int, month: int, start: dt.date, end: dt.date) -> list:
    where = (f"dateparution in [date'{start.isoformat()}'..date'{end.isoformat()}'] "
              f"and {_DEPT_CLAUSE}")
    params = {"where": where, "select": SELECT_FIELDS}

    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(EXPORT_URL, params=params, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            if not isinstance(data, list):
                raise ValueError(f"Unexpected payload type: {type(data)}")
            return data
        except Exception as exc:  # noqa: BLE001 - broad on purpose, retried below
            last_exc = exc
            wait = BACKOFF_SECONDS * attempt
            print(f"  [retry {attempt}/{MAX_RETRIES}] {year}-{month:02d} failed "
                  f"({exc!r}); waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Failed to fetch {year}-{month:02d} after {MAX_RETRIES} "
                        f"attempts: {last_exc!r}")


def main():
    download_started_at = dt.datetime.now().isoformat(timespec="seconds")
    months = list(month_ranges(STUDY_START, STUDY_END))

    per_month_summary = []
    all_ids_seen = set()
    duplicate_count = 0
    failed_requests = []
    total_raw_records = 0

    for year, month, start, end in months:
        out_path = RAW_DIR / f"boamp_{year}{month:02d}.json"
        if out_path.exists():
            with open(out_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            print(f"[skip existing] {out_path.name}: {len(data)} records already on disk")
        else:
            print(f"[fetch] {year}-{month:02d} ({start} .. {end})")
            try:
                data = fetch_month(year, month, start, end)
            except RuntimeError as exc:
                print(f"  GAVE UP: {exc}")
                failed_requests.append({"year": year, "month": month, "error": str(exc)})
                continue
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            print(f"  saved {len(data)} records -> {out_path.name}")

        month_new = 0
        month_dupe = 0
        for rec in data:
            rid = rec.get("idweb")
            if rid in all_ids_seen:
                month_dupe += 1
            else:
                all_ids_seen.add(rid)
                month_new += 1
        duplicate_count += month_dupe
        total_raw_records += len(data)

        per_month_summary.append({
            "year": year, "month": month,
            "file": out_path.name,
            "record_count": len(data),
            "new_ids": month_new,
            "duplicate_ids_vs_prior_months": month_dupe,
        })

    retained_notice_count = len(all_ids_seen)

    metadata = {
        "source_url": EXPORT_URL,
        "source_dataset": "boamp (DILA Opendatasoft Explore API v2.1)",
        "catalog_url": f"{API_BASE}",
        "extraction_date": download_started_at,
        "requested_period": {"start": STUDY_START.isoformat(), "end": STUDY_END.isoformat()},
        "actual_period_note": "actual per-record dateparution range computed in parse_boamp.py "
                               "from the retrieved data; requested period above is the query bound",
        "scope_tag": SCOPE_TAG,
        "departments": PDL_DEPARTMENTS,
        "geographic_field": "code_departement",
        "select_fields": SELECT_FIELDS.split(","),
        "raw_file_count": len(per_month_summary),
        "raw_notice_count_with_dupes": total_raw_records,
        "duplicate_notice_count": duplicate_count,
        "retained_notice_count": retained_notice_count,
        "failed_requests": failed_requests,
        "per_month_summary": per_month_summary,
    }
    meta_path = RAW_DIR / "download_metadata.json"
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)
    print(f"\nWrote metadata -> {meta_path}")

    import pandas as pd
    summary_row = {
        "source_url": EXPORT_URL,
        "extraction_date": download_started_at,
        "requested_period_start": STUDY_START.isoformat(),
        "requested_period_end": STUDY_END.isoformat(),
        "scope_tag": SCOPE_TAG,
        "departments": ";".join(PDL_DEPARTMENTS),
        "raw_file_count": len(per_month_summary),
        "raw_notice_count": total_raw_records,
        "duplicate_count": duplicate_count,
        "retained_notice_count": retained_notice_count,
        "failed_requests": len(failed_requests),
        "schema_notes": ("JOUE-family notices use the EU eForms/UBL JSON structure from "
                          "~late 2023 onward; FNS/MAPA/DSP-family notices use the legacy "
                          "BOAMP XSD-derived JSON structure throughout. Both are handled by "
                          "an adaptive recursive extractor in scripts/parse_boamp.py."),
        "warnings": ("None" if not failed_requests
                     else f"{len(failed_requests)} month(s) failed after retries; see download_metadata.json"),
    }
    pd.DataFrame([summary_row]).to_csv(TABLES_DIR / "boamp_download_summary.csv", index=False)
    print(f"Wrote summary -> {TABLES_DIR / 'boamp_download_summary.csv'}")

    print("\n=== Download complete ===")
    print(f"Raw files: {len(per_month_summary)}")
    print(f"Raw notices (with cross-month dupes): {total_raw_records}")
    print(f"Retained unique notices: {retained_notice_count}")
    print(f"Failed months: {len(failed_requests)}")


if __name__ == "__main__":
    main()
