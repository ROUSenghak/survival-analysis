"""Flatten raw BOAMP monthly JSON files into one interim table.

Extracted from scripts/parse_boamp.py (logic unchanged). Reads every
boamp_YYYYMM.json in cfg.paths.raw_boamp_dir (one at a time to bound
memory), recovers SIRET/SIREN/CPV/duration from the nested `donnees` blob
via utils.boamp_schema (adaptive to the LEGACY and EFORMS schema families),
dedupes across files on idweb, and writes cfg.paths.interim_flattened.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from utils.boamp_schema import (
    detect_schema_family,
    extract_cpv_codes,
    extract_duration_months,
    extract_siret_siren,
)

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


def process_file(path: Path) -> list[dict]:
    with open(path, "r", encoding="utf-8") as f:
        records = json.load(f)

    rows = []
    for rec in records:
        row = {field: join_multivalue(rec.get(field)) for field in FLAT_TOP_FIELDS}

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

        row["notice_id_raw"] = rec.get("idweb")
        row["source_file"] = path.name
        row["raw_record_hash"] = hashlib.sha256(
            json.dumps(rec, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

        rows.append(row)
    return rows


def flatten_notices(cfg, verbose: bool = True) -> dict:
    """Flatten every raw monthly JSON to cfg.paths.interim_flattened.

    Returns a summary dict: n_files, n_rows, n_duplicates_skipped.
    """
    raw_dir = cfg.paths.raw_boamp_dir
    out_path = cfg.paths.interim_flattened
    out_path.parent.mkdir(parents=True, exist_ok=True)

    files = sorted(raw_dir.glob("boamp_*.json"))
    if not files:
        raise FileNotFoundError(
            f"No raw BOAMP files found in {raw_dir}. Run scripts/download_boamp.py first."
        )

    total_rows = 0
    seen_ids: set = set()
    duplicate_rows = 0
    first_write = True

    for i, path in enumerate(files, 1):
        if verbose:
            print(f"[{i}/{len(files)}] parsing {path.name} ...", flush=True)
        rows = process_file(path)
        if not rows:
            # Empty months (e.g. Jan/Feb 2015, before the corpus start) are normal.
            continue
        df = pd.DataFrame(rows)
        is_dupe = df["notice_id_raw"].isin(seen_ids)
        duplicate_rows += int(is_dupe.sum())
        df = df.loc[~is_dupe]
        seen_ids.update(df["notice_id_raw"].tolist())
        df.to_csv(out_path, mode="w" if first_write else "a", header=first_write, index=False)
        first_write = False
        total_rows += len(df)

    return {
        "n_files": len(files),
        "n_rows": total_rows,
        "n_duplicates_skipped": duplicate_rows,
        "output": str(out_path),
    }
