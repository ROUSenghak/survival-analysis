"""
Step 4 - Parse raw BOAMP files into a flattened interim table.

Reads every data/raw/boamp/boamp_YYYYMM.json file (one at a time, to bound
memory - each file is 100-200MB of raw JSON), extracts the fields needed for
M0 preprocessing, and writes:

  data/interim/boamp_raw_flattened.csv
  reports/tables/boamp_observed_columns.csv

Adaptive parsing: SIRET/SIREN/CPV/duration are recovered from the nested
`donnees` blob with src/utils/boamp_schema.py, which pattern-matches on key
names rather than assuming one fixed schema (see that module's docstring and
reports/run_logs/run_log.md for why).
"""

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.boamp_schema import (  # noqa: E402
    detect_schema_family,
    extract_cpv_codes,
    extract_duration_months,
    extract_siret_siren,
)

RAW_DIR = PROJECT_ROOT / "data" / "raw" / "boamp" / "pdl"
INTERIM_DIR = PROJECT_ROOT / "data" / "interim"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
INTERIM_DIR.mkdir(parents=True, exist_ok=True)
TABLES_DIR.mkdir(parents=True, exist_ok=True)

FLAT_TOP_FIELDS = [
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
    "source_schema", "url_avis", "etat",
]


def join_multivalue(v):
    if v is None:
        return None
    if isinstance(v, list):
        return ";".join(str(x) for x in v if x is not None and x != "")
    return v


def process_file(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        records = json.load(f)

    rows = []
    for rec in records:
        row = {}
        for field in FLAT_TOP_FIELDS:
            row[field] = join_multivalue(rec.get(field))

        donnees_raw = rec.get("donnees") or ""
        row["schema_family"] = detect_schema_family(donnees_raw)

        donnees_obj = None
        if donnees_raw:
            try:
                donnees_obj = json.loads(donnees_raw)
            except json.JSONDecodeError:
                donnees_obj = None

        if donnees_obj is not None:
            sirets, sirens = extract_siret_siren(donnees_obj)
            cpvs = extract_cpv_codes(donnees_obj)
            duration_val, duration_key = extract_duration_months(donnees_obj)
        else:
            sirets, sirens, cpvs = [], [], []
            duration_val, duration_key = None, None

        row["siret_candidates_raw"] = ";".join(sirets) if sirets else None
        row["siren_candidates_raw"] = ";".join(sirens) if sirens else None
        row["cpv_candidates_raw"] = ";".join(cpvs) if cpvs else None
        row["duration_months_raw"] = duration_val
        row["duration_source_key"] = duration_key

        # Traceability fields
        row["notice_id_raw"] = rec.get("idweb")
        row["source_file"] = path.name
        row["raw_record_hash"] = hashlib.sha256(
            json.dumps(rec, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        rows.append(row)
    return rows


def main():
    files = sorted(RAW_DIR.glob("boamp_*.json"))
    if not files:
        raise SystemExit(f"No raw BOAMP files found in {RAW_DIR}. Run download_boamp.py first.")

    print(f"Found {len(files)} raw files")
    out_path = INTERIM_DIR / "boamp_raw_flattened.csv"
    total_rows = 0
    seen_ids = set()
    duplicate_rows = 0
    first_write = True

    for i, path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] parsing {path.name} ...")
        rows = process_file(path)
        if not rows:
            # Some early months (e.g. Jan/Feb 2015, before the corpus's
            # actual 2015-03-02 start) return zero records for a given
            # scope filter - nothing to do for this file.
            print("  -> 0 rows (empty file), skipping")
            continue
        df = pd.DataFrame(rows)

        # cross-file dedupe on notice_id_raw, keep first occurrence
        is_dupe = df["notice_id_raw"].isin(seen_ids)
        duplicate_rows += int(is_dupe.sum())
        df = df.loc[~is_dupe]
        seen_ids.update(df["notice_id_raw"].tolist())

        df.to_csv(out_path, mode="w" if first_write else "a", header=first_write, index=False)
        first_write = False
        total_rows += len(df)
        print(f"  -> {len(df)} new rows (running total {total_rows}, dupes skipped so far {duplicate_rows})")

    print(f"\nWrote {total_rows} rows -> {out_path}")

    # Observed-columns report (read back so dtypes/non-null rates reflect the actual file on disk)
    full = pd.read_csv(out_path, low_memory=False)
    obs_rows = []
    for col in full.columns:
        non_null = full[col].notna().sum()
        sample_vals = full[col].dropna().astype(str).unique()[:3]
        obs_rows.append({
            "column": col,
            "dtype": str(full[col].dtype),
            "non_null_count": int(non_null),
            "non_null_rate": round(non_null / len(full), 4) if len(full) else 0.0,
            "sample_values": " | ".join(sample_vals),
        })
    obs_df = pd.DataFrame(obs_rows)
    obs_path = TABLES_DIR / "boamp_observed_columns.csv"
    obs_df.to_csv(obs_path, index=False)
    print(f"Wrote observed-columns report -> {obs_path}")

    print("\n=== Parse complete ===")
    print(f"Total unique rows: {total_rows}")
    print(f"Duplicate rows skipped: {duplicate_rows}")
    print(f"Date range (dateparution): {full['dateparution'].min()} .. {full['dateparution'].max()}")
    print(full["nature"].value_counts())
    print(full["schema_family"].value_counts())


if __name__ == "__main__":
    main()
