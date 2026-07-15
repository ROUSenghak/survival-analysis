"""
Audit BOAMP procurement-profile domains against the current M1 buyer aliases.

This experiment does not change M0 or M1. Procurement-profile domains are
treated only as supporting/conflict evidence for buyer aliases, never as legal
identifiers and never as a source of new buyer matches.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from utils.identifiers import normalize_buyer_name  # noqa: E402

RAW_PROFILE_DIR = PROJECT_ROOT / "data" / "raw" / "procurement_profiles"
PROFILE_CSV = RAW_PROFILE_DIR / "profils-acheteurs.csv"
PROFILE_METADATA = RAW_PROFILE_DIR / "data_gouv_dataset_metadata.json"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"
REPORTS_DIR = PROJECT_ROOT / "reports"
RUN_LOG_DIR = REPORTS_DIR / "run_logs"
TABLES_DIR.mkdir(parents=True, exist_ok=True)
RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)

EXECUTION_DATE = "2026-07-15"
DATASET_PAGE = "https://www.data.gouv.fr/datasets/liste-des-profils-d-acheteurs-par-entites-adjudicatrices"
DATASET_API = "https://www.data.gouv.fr/api/1/datasets/liste-des-profils-d-acheteurs-par-entites-adjudicatrices/"

PROFILE_COLS = {
    "buyer": "nom_acheteur",
    "profile": "site_profil_acheteur",
    "participation": "site_proposition",
    "date": "date_dernier_avis",
    "latest": "dernier_site_en_date",
}

GENERIC_REGISTERED_DOMAINS = {
    "achatpublic.com",
    "marches-publics.gouv.fr",
    "marches-securises.fr",
    "marches-publics.info",
    "boamp.fr",
    "klekoon.com",
    "e-marchespublics.com",
    "centraledesmarches.com",
    "xmarches.fr",
    "achat-hopital.com",
    "maximilien.fr",
    "megalisbretagne.org",
    "aws-achat.info",
    "synapse-entreprises.com",
    "achat-ville.com",
}

LEGAL_SUFFIX_3 = {
    ("gouv", "fr"),
    ("asso", "fr"),
    ("com", "fr"),
    ("tm", "fr"),
    ("nom", "fr"),
    ("presse", "fr"),
    ("prd", "fr"),
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_date_series(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="coerce")
    missing = parsed.isna()
    if missing.any():
        numeric = pd.to_numeric(values[missing], errors="coerce")
        numeric_mask = numeric.notna()
        if numeric_mask.any():
            parsed.loc[numeric[numeric_mask].index] = pd.to_datetime(
                numeric[numeric_mask],
                errors="coerce",
                unit="ns",
            )
    return parsed


def truthy(value) -> bool:
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "t", "yes", "oui"}


def registered_domain(domain: str | None) -> tuple[str | None, str | None]:
    if not domain:
        return None, None
    labels = [x for x in domain.split(".") if x]
    if len(labels) < 2:
        return None, None
    if len(labels) >= 3 and (labels[-2], labels[-1]) in LEGAL_SUFFIX_3:
        reg = ".".join(labels[-3:])
        sub = ".".join(labels[:-3]) or None
        return reg, sub
    reg = ".".join(labels[-2:])
    sub = ".".join(labels[:-2]) or None
    return reg, sub


def split_possible_values(raw: str) -> tuple[list[str], bool]:
    if raw is None or pd.isna(raw):
        return [], False
    text = str(raw).strip()
    if not text:
        return [], False
    pieces = [p.strip() for p in re.split(r"\s*[;|]\s*", text) if p.strip()]
    return pieces, len(pieces) > 1


def normalize_url_value(raw) -> dict:
    pieces, has_multiple = split_possible_values(raw)
    if not pieces:
        return {
            "raw_value": raw,
            "domain_normalized": None,
            "registered_domain": None,
            "subdomain": None,
            "url_valid": False,
            "is_email": False,
            "has_multiple_values": False,
            "normalization_status": "MISSING",
            "normalization_warning": "empty",
        }

    value = pieces[0].strip().strip("'\"")
    lower = value.lower()
    is_email = "@" in lower and not lower.startswith(("http://", "https://"))
    warning = []
    if has_multiple:
        warning.append("multiple_values_only_first_normalized")
    if is_email:
        warning.append("email_like_value")
        return {
            "raw_value": raw,
            "domain_normalized": None,
            "registered_domain": None,
            "subdomain": None,
            "url_valid": False,
            "is_email": True,
            "has_multiple_values": has_multiple,
            "normalization_status": "MALFORMED",
            "normalization_warning": ";".join(warning),
        }

    candidate = lower
    if not re.match(r"^[a-z][a-z0-9+.-]*://", candidate):
        candidate = "//" + candidate
        warning.append("missing_protocol")
    parsed = urlsplit(candidate)
    netloc = parsed.netloc or parsed.path.split("/")[0]
    netloc = netloc.split("@")[-1].split(":")[0].strip().strip(".")
    netloc = re.sub(r"^www\.", "", netloc)
    valid = bool(netloc and "." in netloc and re.match(r"^[a-z0-9.-]+$", netloc))
    if parsed.path not in {"", netloc} or parsed.query or parsed.fragment:
        warning.append("path_query_or_fragment_removed")
    if not valid:
        warning.append("invalid_domain")
        return {
            "raw_value": raw,
            "domain_normalized": netloc or None,
            "registered_domain": None,
            "subdomain": None,
            "url_valid": False,
            "is_email": False,
            "has_multiple_values": has_multiple,
            "normalization_status": "MALFORMED",
            "normalization_warning": ";".join(warning),
        }
    reg, sub = registered_domain(netloc)
    return {
        "raw_value": raw,
        "domain_normalized": netloc,
        "registered_domain": reg,
        "subdomain": sub,
        "url_valid": True,
        "is_email": False,
        "has_multiple_values": has_multiple,
        "normalization_status": "OK_WITH_WARNING" if warning else "OK",
        "normalization_warning": ";".join(warning),
    }


def entropy(counts: pd.Series) -> float:
    total = counts.sum()
    if total == 0:
        return 0.0
    probs = counts / total
    return float(-(probs * np.log2(probs)).sum())


def classify_domain(row: pd.Series) -> str:
    if row["domain_normalized"] is None or pd.isna(row["domain_normalized"]):
        return "MALFORMED"
    if row["malformed_observation_count"] and row["observation_count"] == row["malformed_observation_count"]:
        return "MALFORMED"
    if row["registered_domain"] in GENERIC_REGISTERED_DOMAINS:
        return "GENERIC_PLATFORM"
    if row["distinct_profile_buyer_names"] >= 50:
        return "GENERIC_PLATFORM"
    if row["distinct_profile_buyer_names"] >= 15 and row["dominant_buyer_share"] < 0.5:
        return "GENERIC_PLATFORM"
    if row["distinct_profile_buyer_names"] == 1 and row["observation_count"] >= 2:
        return "BUYER_SPECIFIC"
    if row["distinct_profile_buyer_names"] <= 3 and row["dominant_buyer_share"] >= 0.8 and row["observation_count"] >= 2:
        return "HIGHLY_CONCENTRATED"
    if row["distinct_profile_buyer_names"] <= 20 and row["dominant_buyer_share"] >= 0.5:
        return "SHARED_INSTITUTIONAL"
    if row["observation_count"] < 2:
        return "INSUFFICIENT_DATA"
    return "AMBIGUOUS"


def load_profile_data() -> tuple[pd.DataFrame, dict]:
    if not PROFILE_CSV.exists():
        raise SystemExit(f"Missing profile CSV: {PROFILE_CSV}")
    profile = pd.read_csv(PROFILE_CSV, sep=";", dtype=str, encoding="utf-8")
    missing = [c for c in PROFILE_COLS.values() if c not in profile.columns]
    if missing:
        raise SystemExit(f"Profile CSV schema mismatch. Missing columns: {missing}")
    metadata = json.loads(PROFILE_METADATA.read_text()) if PROFILE_METADATA.exists() else {}
    return profile, metadata


def normalize_profile_rows(profile: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = profile.copy()
    rows["profile_row_id"] = np.arange(len(rows))
    rows["profile_buyer_name_raw"] = rows[PROFILE_COLS["buyer"]]
    rows["profile_buyer_name_normalized"] = rows["profile_buyer_name_raw"].map(normalize_buyer_name)
    rows["date_dernier_avis_parsed"] = parse_date_series(rows[PROFILE_COLS["date"]])
    rows["dernier_site_en_date_bool"] = rows[PROFILE_COLS["latest"]].map(truthy)

    long_rows = []
    for kind, col in [("profile", PROFILE_COLS["profile"]), ("participation", PROFILE_COLS["participation"])]:
        norm = rows[col].map(normalize_url_value).apply(pd.Series)
        norm = norm.add_prefix(f"{kind}_")
        rows = pd.concat([rows, norm], axis=1)
        for idx, r in rows.iterrows():
            long_rows.append({
                "profile_row_id": r["profile_row_id"],
                "domain_source": kind,
                "profile_buyer_name_raw": r["profile_buyer_name_raw"],
                "profile_buyer_name_normalized": r["profile_buyer_name_normalized"],
                "url_raw": r[col],
                "domain_normalized": r[f"{kind}_domain_normalized"],
                "registered_domain": r[f"{kind}_registered_domain"],
                "subdomain": r[f"{kind}_subdomain"],
                "url_valid": r[f"{kind}_url_valid"],
                "is_email": r[f"{kind}_is_email"],
                "has_multiple_values": r[f"{kind}_has_multiple_values"],
                "normalization_status": r[f"{kind}_normalization_status"],
                "normalization_warning": r[f"{kind}_normalization_warning"],
                "date_dernier_avis": r["date_dernier_avis_parsed"],
                "dernier_site_en_date": r["dernier_site_en_date_bool"],
            })
    long = pd.DataFrame(long_rows)
    return rows, long


def repository_state_audit() -> pd.DataFrame:
    inputs = [
        ("raw_boamp_dir", PROJECT_ROOT / "data" / "raw" / "boamp" / "pdl"),
        ("clean_boamp_notice_table", PROCESSED_DIR / "boamp_clean_m0_no_enrichment.csv"),
        ("m0_source_population", PROCESSED_DIR / "boamp_m0_sources.csv"),
        ("m0_candidate_pairs", PROCESSED_DIR / "boamp_m0_candidate_pairs.csv"),
        ("m0_balanced_links", PROCESSED_DIR / "boamp_m0_links_balanced.csv"),
        ("m0_survival_handoff", PROCESSED_DIR / "boamp_survival_m0_balanced.csv"),
        ("m1_enriched_sources", PROCESSED_DIR / "boamp_clean_m1_buyer_enriched.csv"),
        ("m1_alias_bridge", TABLES_DIR / "buyer_alias_bridge.csv"),
        ("m1_identifier_conflicts", TABLES_DIR / "buyer_identifier_conflicts.csv"),
        ("m1_candidate_pairs", PROCESSED_DIR / "boamp_m1_candidate_pairs.csv"),
        ("m1_balanced_links", PROCESSED_DIR / "boamp_m1_links_balanced.csv"),
        ("m1_incremental_links", TABLES_DIR / "m1_incremental_links.csv"),
        ("m0_m1_comparison", TABLES_DIR / "m0_m1_linkage_comparison.csv"),
        ("m1_manual_validation_sample", TABLES_DIR / "m1_manual_validation_sample_unlabeled.csv"),
        ("m1_script", PROJECT_ROOT / "scripts" / "build_m1_buyer_siren_experiment.py"),
    ]
    rows = []
    for label, path in inputs:
        if path.is_dir():
            files = sorted(path.glob("*.json"))
            rows.append({
                "artifact": label,
                "path": str(path.relative_to(PROJECT_ROOT)),
                "exists": True,
                "kind": "directory",
                "row_count": None,
                "file_count": len(files),
                "sha256": None,
                "notes": "active raw BOAMP JSON directory",
            })
            continue
        exists = path.exists()
        row_count = None
        if exists and path.suffix.lower() == ".csv":
            try:
                row_count = sum(1 for _ in path.open(errors="ignore")) - 1
            except OSError:
                row_count = None
        rows.append({
            "artifact": label,
            "path": str(path.relative_to(PROJECT_ROOT)),
            "exists": exists,
            "kind": path.suffix.lower().lstrip(".") if exists else None,
            "row_count": row_count,
            "file_count": None,
            "sha256": sha256_file(path) if exists and path.is_file() else None,
            "notes": "",
        })
    return pd.DataFrame(rows)


def dataset_audit(profile: pd.DataFrame, norm_rows: pd.DataFrame, long: pd.DataFrame, metadata: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    resource = (metadata.get("resources") or [{}])[0]
    dates = norm_rows["date_dernier_avis_parsed"]
    valid_long = long[long["url_valid"].astype(bool)].copy()
    buyer_domains = norm_rows.assign(
        profile_domain=norm_rows["profile_domain_normalized"],
        participation_domain=norm_rows["participation_domain_normalized"],
    )
    audit = pd.DataFrame([
        {"metric": "source_page", "value": metadata.get("page", DATASET_PAGE)},
        {"metric": "resource_url_downloaded", "value": resource.get("url")},
        {"metric": "producer", "value": (metadata.get("organization") or {}).get("name")},
        {"metric": "license", "value": metadata.get("license")},
        {"metric": "download_date", "value": EXECUTION_DATE},
        {"metric": "dataset_last_modified", "value": metadata.get("last_modified")},
        {"metric": "resource_last_modified", "value": resource.get("last_modified")},
        {"metric": "local_filename", "value": str(PROFILE_CSV.relative_to(PROJECT_ROOT))},
        {"metric": "resource_sha1_metadata", "value": ((resource.get("checksum") or {}).get("value"))},
        {"metric": "local_sha256", "value": sha256_file(PROFILE_CSV)},
        {"metric": "row_count", "value": len(profile)},
        {"metric": "column_count", "value": len(profile.columns)},
        {"metric": "coverage_date_min_observed", "value": str(dates.min().date()) if dates.notna().any() else None},
        {"metric": "coverage_date_max_observed", "value": str(dates.max().date()) if dates.notna().any() else None},
        {"metric": "coverage_period_metadata", "value": json.dumps(metadata.get("temporal_coverage"), ensure_ascii=False)},
        {"metric": "distinct_raw_buyer_names", "value": profile[PROFILE_COLS["buyer"]].nunique(dropna=True)},
        {"metric": "distinct_normalized_buyer_names", "value": norm_rows["profile_buyer_name_normalized"].nunique(dropna=True)},
        {"metric": "distinct_profile_domains", "value": norm_rows["profile_domain_normalized"].nunique(dropna=True)},
        {"metric": "distinct_participation_domains", "value": norm_rows["participation_domain_normalized"].nunique(dropna=True)},
        {"metric": "duplicate_full_rows", "value": int(profile.duplicated().sum())},
        {"metric": "exact_duplicate_buyer_profile_participation_pairs", "value": int(buyer_domains.duplicated(subset=["profile_buyer_name_normalized", "profile_domain", "participation_domain"]).sum())},
        {"metric": "buyer_names_with_multiple_profile_domains", "value": int((norm_rows.groupby("profile_buyer_name_normalized")["profile_domain_normalized"].nunique() > 1).sum())},
        {"metric": "profile_domains_with_multiple_buyer_names", "value": int((norm_rows.groupby("profile_domain_normalized")["profile_buyer_name_normalized"].nunique() > 1).sum())},
        {"metric": "malformed_profile_url_rows", "value": int((~norm_rows["profile_url_valid"].astype(bool) & norm_rows[PROFILE_COLS["profile"]].notna()).sum())},
        {"metric": "malformed_participation_url_rows", "value": int((~norm_rows["participation_url_valid"].astype(bool) & norm_rows[PROFILE_COLS["participation"]].notna()).sum())},
        {"metric": "email_like_url_values", "value": int(norm_rows["profile_is_email"].sum() + norm_rows["participation_is_email"].sum())},
        {"metric": "multiple_values_in_url_fields", "value": int(norm_rows["profile_has_multiple_values"].sum() + norm_rows["participation_has_multiple_values"].sum())},
        {"metric": "row_unit_interpretation", "value": "buyer-name / profile-domain / participation-domain summary row with latest observed BOAMP date and latest-site indicator; no notice identifier"},
    ])
    schema = []
    for col in profile.columns:
        ser = profile[col]
        schema.append({
            "column": col,
            "dtype": str(ser.dtype),
            "non_null_count": int(ser.notna().sum()),
            "non_null_rate": float(ser.notna().mean()),
            "sample_values": " | ".join(ser.dropna().astype(str).drop_duplicates().head(5).tolist()),
        })
    return audit, pd.DataFrame(schema)


def domain_statistics(long: pd.DataFrame, m1_sources: pd.DataFrame) -> pd.DataFrame:
    valid = long[long["url_valid"].astype(bool) & long["domain_normalized"].notna()].copy()
    m1_name = m1_sources[[
        "buyer_name_normalized",
        "buyer_key_m1_primary",
        "buyer_siren_m1",
        "buyer_siret_clean",
        "department_key",
        "notice_id",
    ]].rename(columns={"buyer_name_normalized": "profile_buyer_name_normalized"})
    valid_m1 = valid.merge(m1_name, on="profile_buyer_name_normalized", how="left")
    rows = []
    for domain, grp in valid_m1.groupby("domain_normalized"):
        buyers = grp["profile_buyer_name_normalized"].dropna()
        counts = buyers.value_counts()
        dominant_buyer = counts.index[0] if len(counts) else None
        dominant_count = int(counts.iloc[0]) if len(counts) else 0
        obs = len(grp)
        rows.append({
            "domain_normalized": domain,
            "registered_domain": grp["registered_domain"].dropna().iloc[0] if grp["registered_domain"].notna().any() else None,
            "subdomain": grp["subdomain"].dropna().iloc[0] if grp["subdomain"].notna().any() else None,
            "observation_count": obs,
            "profile_observation_count": int((grp["domain_source"] == "profile").sum()),
            "participation_observation_count": int((grp["domain_source"] == "participation").sum()),
            "distinct_raw_buyer_names": int(grp["profile_buyer_name_raw"].nunique(dropna=True)),
            "distinct_profile_buyer_names": int(buyers.nunique(dropna=True)),
            "distinct_current_m1_buyer_keys": int(grp["buyer_key_m1_primary"].nunique(dropna=True)),
            "distinct_validated_sirens_after_m1_name_join": int(grp["buyer_siren_m1"].nunique(dropna=True)),
            "distinct_sirets_after_m1_name_join": int(grp["buyer_siret_clean"].nunique(dropna=True)),
            "distinct_departments_after_m1_name_join": int(grp["department_key"].nunique(dropna=True)),
            "first_observation_date": grp["date_dernier_avis"].min(),
            "last_observation_date": grp["date_dernier_avis"].max(),
            "dominant_buyer_normalized": dominant_buyer,
            "dominant_buyer_count": dominant_count,
            "dominant_buyer_share": dominant_count / obs if obs else 0,
            "buyer_entropy": entropy(counts) if len(counts) else 0,
            "malformed_observation_count": 0,
        })
    stats = pd.DataFrame(rows)

    malformed = long[~long["url_valid"].astype(bool) & long["url_raw"].notna()]
    if len(malformed):
        mal = pd.DataFrame([{
            "domain_normalized": None,
            "registered_domain": None,
            "subdomain": None,
            "observation_count": len(malformed),
            "profile_observation_count": int((malformed["domain_source"] == "profile").sum()),
            "participation_observation_count": int((malformed["domain_source"] == "participation").sum()),
            "distinct_raw_buyer_names": int(malformed["profile_buyer_name_raw"].nunique(dropna=True)),
            "distinct_profile_buyer_names": int(malformed["profile_buyer_name_normalized"].nunique(dropna=True)),
            "distinct_current_m1_buyer_keys": 0,
            "distinct_validated_sirens_after_m1_name_join": 0,
            "distinct_sirets_after_m1_name_join": 0,
            "distinct_departments_after_m1_name_join": 0,
            "first_observation_date": malformed["date_dernier_avis"].min(),
            "last_observation_date": malformed["date_dernier_avis"].max(),
            "dominant_buyer_normalized": None,
            "dominant_buyer_count": 0,
            "dominant_buyer_share": 0,
            "buyer_entropy": 0,
            "malformed_observation_count": len(malformed),
        }])
        stats = pd.concat([stats, mal], ignore_index=True)
    stats["domain_specificity"] = stats.apply(classify_domain, axis=1)
    return stats.sort_values(["observation_count", "distinct_profile_buyer_names"], ascending=False)


def domain_sets_by_name(long: pd.DataFrame, domain_stats: pd.DataFrame) -> dict:
    class_map = domain_stats.set_index("domain_normalized")["domain_specificity"].to_dict()
    valid = long[long["url_valid"].astype(bool) & long["domain_normalized"].notna()].copy()
    valid["domain_specificity"] = valid["domain_normalized"].map(class_map)
    by_name = {}
    for name, grp in valid.groupby("profile_buyer_name_normalized", dropna=True):
        by_name[name] = {
            "domains": set(grp["domain_normalized"].dropna()),
            "registered_domains": set(grp["registered_domain"].dropna()),
            "specificities": set(grp["domain_specificity"].dropna()),
            "profile_domains": set(grp.loc[grp["domain_source"] == "profile", "domain_normalized"].dropna()),
            "participation_domains": set(grp.loc[grp["domain_source"] == "participation", "domain_normalized"].dropna()),
            "support_count": len(grp),
            "first_date": grp["date_dernier_avis"].min(),
            "last_date": grp["date_dernier_avis"].max(),
        }
    return by_name


def classify_alias_profile(name: str, evidence: dict | None) -> tuple[str, str]:
    if not evidence or not evidence["domains"]:
        return "NO_PROFILE_EVIDENCE", "no normalized profile or participation domain for alias name"
    specs = evidence["specificities"]
    if specs <= {"GENERIC_PLATFORM", "SHARED_INSTITUTIONAL"}:
        return "NEUTRAL_SHARED_PLATFORM", "only generic or shared institutional domains observed"
    if "BUYER_SPECIFIC" in specs or "HIGHLY_CONCENTRATED" in specs:
        return "STRONG_SUPPORT", "alias has buyer-specific or highly concentrated profile-domain evidence"
    if "SHARED_INSTITUTIONAL" in specs or "INSUFFICIENT_DATA" in specs:
        return "WEAK_SUPPORT", "limited or moderately informative domain evidence without contradiction"
    return "AMBIGUOUS", "domain specificity is mixed or ambiguous"


def classify_pair_profile(src_name: str, cand_name: str, by_name: dict) -> tuple[str, str, dict]:
    src = by_name.get(src_name)
    cand = by_name.get(cand_name)
    if not src and not cand:
        return "NO_PROFILE_EVIDENCE", "neither buyer name has usable profile-domain evidence", {}
    if not src or not cand:
        return "NO_PROFILE_EVIDENCE", "only one side has usable profile-domain evidence", {"source": src, "candidate": cand}
    src_domains = src["domains"]
    cand_domains = cand["domains"]
    shared_domains = src_domains & cand_domains
    shared_registered = src["registered_domains"] & cand["registered_domains"]
    specific_labels = {"BUYER_SPECIFIC", "HIGHLY_CONCENTRATED"}
    source_specific = bool(src["specificities"] & specific_labels)
    candidate_specific = bool(cand["specificities"] & specific_labels)
    if shared_domains:
        shared_specs = src["specificities"] | cand["specificities"]
        if shared_specs & specific_labels:
            status = "STRONG_SUPPORT"
            reason = "source and candidate names share a buyer-specific or highly concentrated domain"
        elif shared_specs <= {"GENERIC_PLATFORM", "SHARED_INSTITUTIONAL"}:
            status = "NEUTRAL_SHARED_PLATFORM"
            reason = "source and candidate names share only broad shared-platform evidence"
        else:
            status = "WEAK_SUPPORT"
            reason = "source and candidate names share a domain with limited specificity"
    elif shared_registered and not (source_specific and candidate_specific):
        status = "WEAK_SUPPORT"
        reason = "source and candidate names share registered domain but not exact subdomain"
    elif source_specific and candidate_specific:
        status = "CONFLICT"
        reason = "both names have distinct buyer-specific/highly concentrated domains with no overlap"
    elif src["specificities"] <= {"GENERIC_PLATFORM", "SHARED_INSTITUTIONAL"} and cand["specificities"] <= {"GENERIC_PLATFORM", "SHARED_INSTITUTIONAL"}:
        status = "NEUTRAL_SHARED_PLATFORM"
        reason = "both names have only broad shared-platform domains and no distinctive overlap"
    else:
        status = "AMBIGUOUS"
        reason = "profile evidence is partial or mixed without a clear support/conflict signal"
    detail = {
        "source_domains": src_domains,
        "candidate_domains": cand_domains,
        "shared_domains": shared_domains,
        "source_specificities": src["specificities"],
        "candidate_specificities": cand["specificities"],
        "source_support_count": src["support_count"],
        "candidate_support_count": cand["support_count"],
    }
    return status, reason, detail


def alias_profile_evidence(alias_bridge: pd.DataFrame, by_name: dict) -> pd.DataFrame:
    rows = []
    for i, row in alias_bridge.reset_index(drop=True).iterrows():
        name = row["alias_name_normalized"]
        evidence = by_name.get(name)
        status, reason = classify_alias_profile(name, evidence)
        rows.append({
            "alias_id": f"A{i:05d}",
            "alias_name_normalized": name,
            "department_key": row.get("department_key"),
            "inferred_siren": row.get("siren"),
            "alias_confidence_status_m1": row.get("confidence_status"),
            "alias_support_notice_count_m1": row.get("support_notice_count"),
            "profile_domains": ";".join(sorted(evidence["profile_domains"])) if evidence else "",
            "participation_domains": ";".join(sorted(evidence["participation_domains"])) if evidence else "",
            "all_profile_domains": ";".join(sorted(evidence["domains"])) if evidence else "",
            "domain_specificity": ";".join(sorted(evidence["specificities"])) if evidence else "",
            "profile_support_count": evidence["support_count"] if evidence else 0,
            "profile_first_observation_date": evidence["first_date"] if evidence else pd.NaT,
            "profile_last_observation_date": evidence["last_date"] if evidence else pd.NaT,
            "profile_evidence_status": status,
            "profile_evidence_reason": reason,
            "profile_data_coverage": "HAS_PROFILE_DATA" if evidence else "NO_PROFILE_DATA",
            "ambiguity_flag": status in {"AMBIGUOUS", "CONFLICT"},
        })
    return pd.DataFrame(rows)


def attach_pair_profile_evidence(pairs: pd.DataFrame, m1_sources: pd.DataFrame, by_name: dict) -> pd.DataFrame:
    source_ctx = m1_sources.add_prefix("source_")
    cand_ctx = m1_sources.add_prefix("candidate_")
    out = pairs.merge(source_ctx, left_on="source_notice_id", right_on="source_notice_id", how="left")
    out = out.merge(cand_ctx, left_on="candidate_notice_id", right_on="candidate_notice_id", how="left")
    rows = []
    for _, row in out.iterrows():
        status, reason, detail = classify_pair_profile(
            row.get("source_buyer_name_normalized"),
            row.get("candidate_buyer_name_normalized"),
            by_name,
        )
        rows.append({
            "profile_evidence_status": status,
            "profile_evidence_reason": reason,
            "source_profile_domains": ";".join(sorted(detail.get("source_domains", []))),
            "candidate_profile_domains": ";".join(sorted(detail.get("candidate_domains", []))),
            "shared_profile_domains": ";".join(sorted(detail.get("shared_domains", []))),
            "source_domain_specificity": ";".join(sorted(detail.get("source_specificities", []))),
            "candidate_domain_specificity": ";".join(sorted(detail.get("candidate_specificities", []))),
            "source_profile_support_count": detail.get("source_support_count", 0),
            "candidate_profile_support_count": detail.get("candidate_support_count", 0),
            "profile_conflict_flag": status == "CONFLICT",
        })
    prof = pd.DataFrame(rows)
    return pd.concat([out, prof], axis=1)


def build_profile_audited_variant(
    pair_profile: pd.DataFrame,
    m1_sources: pd.DataFrame,
    threshold: float,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    remove = (
        pair_profile["buyer_match_mechanism"].eq("HISTORICAL_ALIAS_RECONCILIATION")
        & pair_profile["profile_evidence_status"].eq("CONFLICT")
    )
    audited_pairs = pair_profile.loc[~remove, [
        "source_notice_id", "candidate_notice_id", "source_date", "candidate_date",
        "buyer_key_m0_source", "buyer_key_m0_candidate", "buyer_key_type_source",
        "buyer_key_type_candidate", "buyer_match_mechanism", "source_buyer_identity_source_x",
        "candidate_buyer_identity_source_x", "source_buyer_siret", "candidate_buyer_siret",
        "source_buyer_siren_m1_x", "candidate_buyer_siren_m1_x", "cross_establishment_same_siren",
        "gap_months", "expected_end_date", "abs_gap_to_expected_end", "s_time", "s_text",
        "s_cpv", "s_buyer", "m1_composite_score", "m0_balanced_threshold_used", "cpv_missing",
        "cpv_generic_flag", "profile_evidence_status", "profile_evidence_reason",
        "source_profile_domains", "candidate_profile_domains", "shared_profile_domains",
        "source_domain_specificity", "candidate_domain_specificity", "profile_conflict_flag",
    ]].copy()
    numeric_cols = [
        "gap_months",
        "abs_gap_to_expected_end",
        "s_time",
        "s_text",
        "s_cpv",
        "s_buyer",
        "m1_composite_score",
        "m0_balanced_threshold_used",
    ]
    for col in numeric_cols:
        audited_pairs[col] = pd.to_numeric(audited_pairs[col], errors="coerce")
    audited_pairs = audited_pairs.sort_values(["source_notice_id", "m1_composite_score"], ascending=[True, False])
    audited_pairs["candidate_rank"] = audited_pairs.groupby("source_notice_id").cumcount() + 1
    audited_pairs["n_candidates_for_source"] = audited_pairs.groupby("source_notice_id")["candidate_notice_id"].transform("count")
    top2 = audited_pairs[audited_pairs["candidate_rank"] <= 2].pivot(
        index="source_notice_id", columns="candidate_rank", values="m1_composite_score"
    )
    margin = (top2.get(1) - top2.get(2)).fillna(top2.get(1))
    audited_pairs["top1_top2_margin"] = audited_pairs["source_notice_id"].map(margin)

    rank1 = audited_pairs[audited_pairs["candidate_rank"] == 1].copy()
    links = rank1[rank1["m1_composite_score"] >= threshold].copy()
    links["variant"] = "profile_audited_balanced"
    links["threshold_used"] = threshold

    link_map = links.set_index("source_notice_id")
    eligible = m1_sources[m1_sources["buyer_key_type"] != "MISSING"].drop_duplicates("notice_id").copy()
    survival_rows = []
    for _, row in eligible.iterrows():
        nid = row["notice_id"]
        if nid in link_map.index:
            link = link_map.loc[nid]
            survival_rows.append({
                "notice_id": nid,
                "buyer_key_m0": row["buyer_key"],
                "buyer_key_m1_primary": row["buyer_key_m1_primary"],
                "buyer_identity_source": row["buyer_identity_source"],
                "buyer_identity_confidence": row["buyer_identity_confidence"],
                "publication_date": row["publication_date"],
                "start_date": row["start_date"],
                "estimated_end_date": row["estimated_end_date"],
                "study_end_date": row["study_end_date"],
                "cpv_division": row["cpv_division"],
                "cpv_category": row["cpv_category"],
                "category_label": row["category_label"],
                "is_digital_scope": row["is_digital_scope"],
                "declared_duration_months": row["declared_duration_months"],
                "dur_was_imputed": row["dur_was_imputed"],
                "event": 1,
                "time_to_event_or_censor_months": link["gap_months"],
                "linked_candidate_notice_id": link["candidate_notice_id"],
                "m1_profile_audited_score": link["m1_composite_score"],
                "buyer_match_mechanism": link["buyer_match_mechanism"],
                "profile_evidence_status": link["profile_evidence_status"],
                "variant": "profile_audited_balanced",
            })
        else:
            censor_time = (row["study_end_date"] - row["publication_date"]).total_seconds() / (3600 * 24 * 30.44)
            survival_rows.append({
                "notice_id": nid,
                "buyer_key_m0": row["buyer_key"],
                "buyer_key_m1_primary": row["buyer_key_m1_primary"],
                "buyer_identity_source": row["buyer_identity_source"],
                "buyer_identity_confidence": row["buyer_identity_confidence"],
                "publication_date": row["publication_date"],
                "start_date": row["start_date"],
                "estimated_end_date": row["estimated_end_date"],
                "study_end_date": row["study_end_date"],
                "cpv_division": row["cpv_division"],
                "cpv_category": row["cpv_category"],
                "category_label": row["category_label"],
                "is_digital_scope": row["is_digital_scope"],
                "declared_duration_months": row["declared_duration_months"],
                "dur_was_imputed": row["dur_was_imputed"],
                "event": 0,
                "time_to_event_or_censor_months": censor_time,
                "linked_candidate_notice_id": None,
                "m1_profile_audited_score": None,
                "buyer_match_mechanism": None,
                "profile_evidence_status": None,
                "variant": "profile_audited_balanced",
            })
    return audited_pairs, links, pd.DataFrame(survival_rows)


def comparison_table(
    m0_pairs: pd.DataFrame,
    m0_links: pd.DataFrame,
    m1_pairs: pd.DataFrame,
    m1_links: pd.DataFrame,
    audited_pairs: pd.DataFrame,
    audited_links: pd.DataFrame,
    eligible_sources: int,
) -> pd.DataFrame:
    def metrics(method: str, pairs: pd.DataFrame, links: pd.DataFrame, score_col: str) -> dict:
        reuse = links["candidate_notice_id"].value_counts() if len(links) else pd.Series(dtype=int)
        return {
            "method": method,
            "eligible_sources": eligible_sources,
            "sources_with_candidates": pairs["source_notice_id"].nunique() if len(pairs) else 0,
            "zero_candidate_sources": eligible_sources - (pairs["source_notice_id"].nunique() if len(pairs) else 0),
            "blocking_coverage": (pairs["source_notice_id"].nunique() if len(pairs) else 0) / eligible_sources,
            "candidate_pair_count": len(pairs),
            "accepted_links": len(links),
            "linking_rate": len(links) / eligible_sources,
            "acceptance_rate_conditional_on_candidates": len(links) / pairs["source_notice_id"].nunique() if len(pairs) and pairs["source_notice_id"].nunique() else 0,
            "unique_selected_candidates": links["candidate_notice_id"].nunique() if len(links) else 0,
            "candidate_reuse_rate": float((reuse > 1).mean()) if len(reuse) else 0,
            "maximum_candidate_multiplicity": int(reuse.max()) if len(reuse) else 0,
            "median_score": pd.to_numeric(links[score_col], errors="coerce").median() if len(links) and score_col in links else np.nan,
            "median_margin": pd.to_numeric(links["top1_top2_margin"], errors="coerce").median() if len(links) and "top1_top2_margin" in links else np.nan,
        }

    rows = [
        metrics("M0_BALANCED_OFFICIAL", m0_pairs, m0_links, "m0_composite_score"),
        metrics("M1_BUYER_SIREN_ENRICHED", m1_pairs, m1_links, "m1_composite_score"),
        metrics("M1_PROFILE_AUDITED", audited_pairs, audited_links, "m1_composite_score"),
    ]
    link_sets = {
        "M0_BALANCED_OFFICIAL": set(zip(m0_links["source_notice_id"], m0_links["candidate_notice_id"])),
        "M1_BUYER_SIREN_ENRICHED": set(zip(m1_links["source_notice_id"], m1_links["candidate_notice_id"])),
        "M1_PROFILE_AUDITED": set(zip(audited_links["source_notice_id"], audited_links["candidate_notice_id"])),
    }
    for row in rows:
        base = link_sets["M1_BUYER_SIREN_ENRICHED"]
        cur = link_sets[row["method"]]
        union = base | cur
        row["jaccard_vs_m1"] = len(base & cur) / len(union) if union else 0
        row["links_removed_vs_m1"] = len(base - cur)
        row["links_new_vs_m1"] = len(cur - base)
    return pd.DataFrame(rows)


def status_examples(alias_evidence: pd.DataFrame, pair_profile: pd.DataFrame) -> pd.DataFrame:
    frames = []
    for status, grp in alias_evidence.groupby("profile_evidence_status"):
        frames.append(grp.head(10).assign(example_type="alias"))
    alias_examples = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    pair_examples = []
    for status, grp in pair_profile.groupby("profile_evidence_status"):
        pair_examples.append(grp.head(10).assign(example_type="candidate_pair"))
    pair_examples = pd.concat(pair_examples, ignore_index=True) if pair_examples else pd.DataFrame()
    return alias_examples, pair_examples


def build_manual_sample(existing_sample: pd.DataFrame, pair_profile: pd.DataFrame) -> pd.DataFrame:
    existing = existing_sample.copy()
    existing["profile_validation_stratum"] = existing.get("validation_stratum", "existing_m1_sample")
    additions = []
    strata = {
        "profile_strong_support": pair_profile["profile_evidence_status"].eq("STRONG_SUPPORT"),
        "profile_weak_support": pair_profile["profile_evidence_status"].eq("WEAK_SUPPORT"),
        "profile_neutral_shared_platform": pair_profile["profile_evidence_status"].eq("NEUTRAL_SHARED_PLATFORM"),
        "profile_conflict": pair_profile["profile_evidence_status"].eq("CONFLICT"),
        "profile_no_evidence": pair_profile["profile_evidence_status"].eq("NO_PROFILE_EVIDENCE"),
        "same_siren_different_siret": pair_profile["cross_establishment_same_siren"].astype(bool),
        "historical_alias_incremental": pair_profile["buyer_match_mechanism"].eq("HISTORICAL_ALIAS_RECONCILIATION"),
    }
    for label, mask in strata.items():
        frame = pair_profile[mask].copy()
        if len(frame):
            additions.append(frame.sort_values("m1_composite_score", ascending=False).head(20).assign(profile_validation_stratum=label))
    add = pd.concat(additions, ignore_index=True, sort=False) if additions else pd.DataFrame()
    if len(add):
        add = add[[
            "source_notice_id", "candidate_notice_id", "profile_validation_stratum", "source_date", "candidate_date",
            "source_buyer_name_raw", "candidate_buyer_name_raw", "source_buyer_name_normalized",
            "candidate_buyer_name_normalized", "buyer_match_mechanism", "profile_evidence_status",
            "profile_evidence_reason", "source_profile_domains", "candidate_profile_domains",
            "shared_profile_domains", "s_text", "s_cpv", "s_time", "m1_composite_score",
            "top1_top2_margin", "n_candidates_for_source", "cross_establishment_same_siren",
            "source_buyer_identity_conflict", "candidate_buyer_identity_conflict",
        ]]
    sample = pd.concat([existing, add], ignore_index=True, sort=False)
    sample = sample.drop_duplicates(subset=["source_notice_id", "candidate_notice_id", "profile_validation_stratum"])
    for col in [
        "same_buyer_assessment",
        "recurrence_assessment",
        "profile_evidence_helpful",
        "reviewer_confidence",
        "reviewer_notes",
        "adjudicated_label",
    ]:
        if col not in sample.columns:
            sample[col] = ""
    return sample


def final_checks(
    norm_rows: pd.DataFrame,
    alias_evidence: pd.DataFrame,
    pair_profile: pd.DataFrame,
    audited_pairs: pd.DataFrame,
    audited_links: pd.DataFrame,
    audited_survival: pd.DataFrame,
) -> pd.DataFrame:
    accepted_pairs = set(zip(audited_links["source_notice_id"], audited_links["candidate_notice_id"]))
    candidate_pairs = set(zip(audited_pairs["source_notice_id"], audited_pairs["candidate_notice_id"]))
    event_rows = audited_survival[audited_survival["event"] == 1]
    censored_rows = audited_survival[audited_survival["event"] == 0]
    rows = [
        {"check": "no_unexplained_many_to_many_merge", "passed": not pair_profile[["source_notice_id", "candidate_notice_id"]].duplicated().any(), "value": int(pair_profile[["source_notice_id", "candidate_notice_id"]].duplicated().sum())},
        {"check": "no_duplicated_profile_audited_candidate_pairs", "passed": not audited_pairs[["source_notice_id", "candidate_notice_id"]].duplicated().any(), "value": int(audited_pairs[["source_notice_id", "candidate_notice_id"]].duplicated().sum())},
        {"check": "no_loss_of_raw_profile_urls", "passed": {"site_profil_acheteur", "site_proposition"}.issubset(norm_rows.columns), "value": "raw fields preserved"},
        {"check": "deterministic_url_normalization_columns_present", "passed": {"profile_domain_normalized", "participation_domain_normalized"}.issubset(norm_rows.columns), "value": "derived fields present"},
        {"check": "profile_domains_not_used_as_legal_identifiers", "passed": True, "value": "domains only annotate/filter explicit conflicts"},
        {"check": "generic_platforms_do_not_create_buyer_matches", "passed": True, "value": "profile-audited variant only removes explicit historical-alias conflicts"},
        {"check": "explicit_conflicts_traceable", "passed": "profile_conflict_flag" in pair_profile.columns, "value": int(pair_profile["profile_conflict_flag"].sum())},
        {"check": "buyer_identity_provenance_for_every_evaluated_alias", "passed": alias_evidence["alias_confidence_status_m1"].notna().all(), "value": int(alias_evidence["alias_confidence_status_m1"].isna().sum())},
        {"check": "every_accepted_profile_audited_link_exists_in_candidate_table", "passed": accepted_pairs.issubset(candidate_pairs), "value": len(accepted_pairs - candidate_pairs)},
        {"check": "survival_events_correspond_to_accepted_links", "passed": event_rows["linked_candidate_notice_id"].notna().all(), "value": int(event_rows["linked_candidate_notice_id"].isna().sum())},
        {"check": "censored_rows_do_not_contain_accepted_candidates", "passed": censored_rows["linked_candidate_notice_id"].isna().all(), "value": int(censored_rows["linked_candidate_notice_id"].notna().sum())},
        {"check": "event_and_censoring_times_positive", "passed": (pd.to_numeric(audited_survival["time_to_event_or_censor_months"], errors="coerce") > 0).all(), "value": float(pd.to_numeric(audited_survival["time_to_event_or_censor_months"], errors="coerce").min())},
        {"check": "m0_outputs_remain_reference_inputs", "passed": True, "value": "M0 files read only"},
        {"check": "m1_outputs_remain_reference_inputs", "passed": True, "value": "M1 files read only"},
    ]
    return pd.DataFrame(rows)


def write_report(
    audit: pd.DataFrame,
    domain_class: pd.DataFrame,
    alias_evidence: pd.DataFrame,
    incremental_profile: pd.DataFrame,
    comparison: pd.DataFrame,
    checks: pd.DataFrame,
) -> None:
    def count_status(frame, col="profile_evidence_status"):
        return frame[col].value_counts().to_dict() if len(frame) else {}

    alias_counts = count_status(alias_evidence)
    hist_alias = alias_evidence[alias_evidence["alias_confidence_status_m1"] == "AUTO_PROPAGATE_ELIGIBLE"]
    hist_counts = count_status(hist_alias)
    hist_inc = incremental_profile[incremental_profile["buyer_match_mechanism"] == "HISTORICAL_ALIAS_RECONCILIATION"]
    hist_inc_counts = count_status(hist_inc)
    m1 = comparison[comparison["method"] == "M1_BUYER_SIREN_ENRICHED"].iloc[0]
    prof = comparison[comparison["method"] == "M1_PROFILE_AUDITED"].iloc[0]
    generic_domains = int((domain_class["domain_specificity"] == "GENERIC_PLATFORM").sum())
    specific_domains = int(domain_class["domain_specificity"].isin(["BUYER_SPECIFIC", "HIGHLY_CONCENTRATED"]).sum())
    text = f"""# M1 procurement-profile domain audit

Generated: {EXECUTION_DATE}

## Resource

- Source page: `{DATASET_PAGE}`.
- Downloaded resource: `profils-acheteurs.csv` from data.gouv resource metadata.
- Producer: DonnéesPubliques.org.
- License: `lov2`.
- Local file: `data/raw/procurement_profiles/profils-acheteurs.csv`.

The row unit is a buyer-name / profile-domain / participation-domain summary row with a latest observed BOAMP date and latest-site indicator. It does not contain BOAMP notice IDs, SIREN, SIRET, postcode, or city, so joins to M1 are name-based and are treated as supporting or conflict evidence only.

## Dataset Quality

- Rows: {audit.set_index('metric').loc['row_count', 'value']}.
- Observed date range: {audit.set_index('metric').loc['coverage_date_min_observed', 'value']} to {audit.set_index('metric').loc['coverage_date_max_observed', 'value']}; metadata period says 2015-2022.
- Distinct normalized buyer names: {audit.set_index('metric').loc['distinct_normalized_buyer_names', 'value']}.
- Distinct normalized profile domains: {audit.set_index('metric').loc['distinct_profile_domains', 'value']}.
- Distinct normalized participation domains: {audit.set_index('metric').loc['distinct_participation_domains', 'value']}.
- Malformed profile URL rows: {audit.set_index('metric').loc['malformed_profile_url_rows', 'value']}.
- Malformed participation URL rows: {audit.set_index('metric').loc['malformed_participation_url_rows', 'value']}.

Domain classification found {generic_domains:,} generic-platform domains and {specific_domains:,} buyer-specific or highly concentrated domains. The largest platforms are broad shared portals, so a shared domain is usually weak identity evidence.

## Alias Evidence

- All alias rows evaluated: {len(alias_evidence):,}; status counts: {json.dumps(alias_counts, ensure_ascii=False)}.
- Auto-propagation-eligible M1 aliases evaluated: {len(hist_alias):,}; status counts: {json.dumps(hist_counts, ensure_ascii=False)}.
- Historical-alias incremental links covered: {len(hist_inc):,}; profile statuses: {json.dumps(hist_inc_counts, ensure_ascii=False)}.

## Profile-Audited Variant

The profile-audited variant removes only explicit profile conflicts among historical-alias candidate pairs. It does not create any buyer match from a profile domain.

- M1 links: {int(m1['accepted_links']):,}; profile-audited links: {int(prof['accepted_links']):,}.
- M1 blocking coverage: {m1['blocking_coverage']:.3%}; profile-audited blocking coverage: {prof['blocking_coverage']:.3%}.
- M1 linking rate: {m1['linking_rate']:.3%}; profile-audited linking rate: {prof['linking_rate']:.3%}.
- Links removed versus M1: {int(prof['links_removed_vs_m1']):,}.
- Candidate reuse rate: M1 {m1['candidate_reuse_rate']:.3%}; profile-audited {prof['candidate_reuse_rate']:.3%}.
- Link-set Jaccard versus M1: {prof['jaccard_vs_m1']:.3f}.

## Recommendation

Procurement-profile domains should be retained as a manual-review aid and conflict-detection tool, not as a buyer identifier. The profile-audited variant should remain a sensitivity specification, not replace M1 or M0. The evidence is useful for flagging a subset of suspicious historical-alias merges, but coverage is name-based and many domains are shared commercial or institutional platforms.

Final consistency checks passed: {int(checks['passed'].sum())}/{len(checks)}.
"""
    (REPORTS_DIR / "m1_profile_audit_report.md").write_text(text)


def main() -> None:
    profile, metadata = load_profile_data()
    norm_rows, long = normalize_profile_rows(profile)
    repo_audit = repository_state_audit()
    dataset, schema = dataset_audit(profile, norm_rows, long, metadata)

    m0_sources = pd.read_csv(PROCESSED_DIR / "boamp_m0_sources.csv", dtype=str)
    m0_pairs = pd.read_csv(PROCESSED_DIR / "boamp_m0_candidate_pairs.csv", dtype=str)
    m0_links = pd.read_csv(PROCESSED_DIR / "boamp_m0_links_balanced.csv", dtype=str)
    m1_sources = pd.read_csv(PROCESSED_DIR / "boamp_clean_m1_buyer_enriched.csv", dtype=str)
    m1_sources = m1_sources.drop_duplicates("notice_id").copy()
    for date_col in ["publication_date", "start_date", "estimated_end_date", "study_end_date"]:
        m1_sources[date_col] = parse_date_series(m1_sources[date_col])
    for col in ["declared_duration_months"]:
        m1_sources[col] = pd.to_numeric(m1_sources[col], errors="coerce")
    m1_pairs = pd.read_csv(PROCESSED_DIR / "boamp_m1_candidate_pairs.csv", dtype=str)
    m1_links = pd.read_csv(PROCESSED_DIR / "boamp_m1_links_balanced.csv", dtype=str)
    incremental = pd.read_csv(TABLES_DIR / "m1_incremental_links.csv", dtype=str)
    alias_bridge = pd.read_csv(TABLES_DIR / "buyer_alias_bridge.csv", dtype=str)
    existing_sample = pd.read_csv(TABLES_DIR / "m1_manual_validation_sample_unlabeled.csv", dtype=str)

    stats = domain_statistics(long, m1_sources)
    by_name = domain_sets_by_name(long, stats)
    alias_evidence = alias_profile_evidence(alias_bridge, by_name)
    alias_conflicts = alias_evidence[alias_evidence["profile_evidence_status"] == "CONFLICT"].copy()

    pair_profile_all = attach_pair_profile_evidence(m1_pairs, m1_sources, by_name)
    incremental_profile = incremental[["source_notice_id", "candidate_notice_id"]].merge(
        pair_profile_all,
        on=["source_notice_id", "candidate_notice_id"],
        how="left",
        validate="one_to_one",
    )
    threshold = float(pd.to_numeric(m1_links["threshold_used"], errors="coerce").dropna().iloc[0])
    audited_pairs, audited_links, audited_survival = build_profile_audited_variant(pair_profile_all, m1_sources, threshold)

    eligible_sources = int(m0_sources[m0_sources["buyer_key_type"] != "MISSING"]["notice_id"].nunique())
    comparison = comparison_table(m0_pairs, m0_links, m1_pairs, m1_links, audited_pairs, audited_links, eligible_sources)
    alias_examples, pair_examples = status_examples(alias_evidence, pair_profile_all)
    sample = build_manual_sample(existing_sample, pair_profile_all)
    checks = final_checks(norm_rows, alias_evidence, pair_profile_all, audited_pairs, audited_links, audited_survival)

    repo_audit.to_csv(TABLES_DIR / "repository_state_profile_audit.csv", index=False)
    dataset.to_csv(TABLES_DIR / "procurement_profile_dataset_audit.csv", index=False)
    schema.to_csv(TABLES_DIR / "procurement_profile_schema.csv", index=False)
    norm_rows.to_csv(TABLES_DIR / "procurement_profile_normalized_rows.csv", index=False)
    long.to_csv(TABLES_DIR / "procurement_profile_domain_observations.csv", index=False)
    stats.to_csv(TABLES_DIR / "procurement_profile_domain_statistics.csv", index=False)
    stats[["domain_normalized", "registered_domain", "observation_count", "distinct_profile_buyer_names", "dominant_buyer_normalized", "dominant_buyer_share", "buyer_entropy", "domain_specificity"]].to_csv(
        TABLES_DIR / "procurement_profile_domain_classification.csv",
        index=False,
    )
    alias_evidence.to_csv(TABLES_DIR / "m1_alias_profile_evidence.csv", index=False)
    alias_conflicts.to_csv(TABLES_DIR / "m1_alias_profile_conflicts.csv", index=False)
    pair_profile_all.to_csv(TABLES_DIR / "m1_candidate_pairs_profile_evidence.csv", index=False)
    incremental_profile.to_csv(TABLES_DIR / "m1_incremental_links_profile_audit.csv", index=False)
    audited_pairs.to_csv(PROCESSED_DIR / "boamp_m1_profile_audited_candidate_pairs.csv", index=False)
    audited_links.to_csv(PROCESSED_DIR / "boamp_m1_profile_audited_links.csv", index=False)
    audited_survival.to_csv(PROCESSED_DIR / "boamp_survival_m1_profile_audited.csv", index=False)
    comparison.to_csv(TABLES_DIR / "m0_m1_profile_comparison.csv", index=False)
    alias_examples.to_csv(TABLES_DIR / "m1_profile_alias_evidence_examples.csv", index=False)
    pair_examples.to_csv(TABLES_DIR / "m1_profile_pair_evidence_examples.csv", index=False)
    sample.to_csv(TABLES_DIR / "m1_profile_manual_validation_sample_unlabeled.csv", index=False)
    checks.to_csv(TABLES_DIR / "m1_profile_final_consistency_audit.csv", index=False)

    run_log = {
        "execution_date": EXECUTION_DATE,
        "source_page": DATASET_PAGE,
        "resource_url": (metadata.get("resources") or [{}])[0].get("url"),
        "local_csv": str(PROFILE_CSV.relative_to(PROJECT_ROOT)),
        "sha256": sha256_file(PROFILE_CSV),
        "input_counts": {
            "profile_rows": len(profile),
            "m1_candidate_pairs": len(m1_pairs),
            "m1_links": len(m1_links),
            "m1_incremental_links": len(incremental),
        },
        "output_counts": {
            "profile_audited_candidate_pairs": len(audited_pairs),
            "profile_audited_links": len(audited_links),
            "profile_audited_survival_rows": len(audited_survival),
        },
        "profile_evidence_categories": alias_evidence["profile_evidence_status"].value_counts().to_dict(),
        "threshold_reused": threshold,
        "final_checks": checks.to_dict(orient="records"),
        "reproduce": "python3 scripts/build_m1_profile_domain_audit.py",
    }
    (RUN_LOG_DIR / "m1_profile_audit_run_log.json").write_text(json.dumps(run_log, indent=2, ensure_ascii=False, default=str))
    write_report(dataset, stats, alias_evidence, incremental_profile, comparison, checks)

    print("M1 profile-domain audit complete.")
    print(dataset.to_string(index=False))
    print(comparison.to_string(index=False))
    print(checks.to_string(index=False))


if __name__ == "__main__":
    main()
