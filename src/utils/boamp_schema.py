"""
Adaptive extraction helpers for the nested `donnees` JSON blob inside each
BOAMP notice.

Why "adaptive": BOAMP notices do not share one fixed schema. During source
discovery (reports/run_logs/run_log.md) we found that `JOUE`-family notices
(EU-threshold) switched from a legacy BOAMP-XSD-derived JSON structure to the
EU eForms/UBL JSON structure around the EU eForms mandate (Oct 2023), while
`FNS`/`MAPA`/`DSP`-family notices (French national thresholds) keep using the
legacy structure throughout 2015-2026. Rather than hardcoding one fixed set
of JSON paths per family/period (fragile, and liable to silently miss fields
if the schema shifts again), this module walks the nested structure
generically and pattern-matches on key names and value shapes.

This is intentionally best-effort and documented as such: recovered
SIRET/SIREN/CPV/duration values are only as complete as what a given notice
actually published, and the recursive search may occasionally miss a value
buried under an unanticipated key name. Coverage is reported empirically in
reports/tables/boamp_observed_columns.csv and the M0 quality-check tables,
not assumed.
"""

import re
from typing import Iterator, Optional

_SIRET_PARENT_HINTS = re.compile(
    r"siret|companyid|legalentity", re.IGNORECASE
)
_SIREN_PARENT_HINTS = re.compile(r"siren", re.IGNORECASE)
_ID_CONTEXT_HINTS = re.compile(
    r"identite|identity|organization|acheteur|company|pouvoiradjudicateur",
    re.IGNORECASE,
)
_CPV_HINTS = re.compile(r"cpv", re.IGNORECASE)
_DUREE_MOIS_HINT = re.compile(r"dureemois|nbmois", re.IGNORECASE)
_DURATION_MEASURE_HINT = re.compile(r"durationmeasure", re.IGNORECASE)


def walk(obj, path=()) -> Iterator[tuple]:
    """Yield (path_tuple, scalar_value) for every leaf in a nested dict/list."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, path + (k,))
    elif isinstance(obj, list):
        for item in obj:
            yield from walk(item, path)
    else:
        if obj is not None and obj != "":
            yield path, obj


def _path_str(path) -> str:
    return "/".join(str(p) for p in path)


def extract_siret_siren(donnees_obj) -> tuple[list, list]:
    """Return (siret_candidates, siren_candidates) as lists of raw strings,
    found via key-name pattern matching anywhere in the nested structure."""
    sirets, sirens = [], []
    for path, value in walk(donnees_obj):
        if not isinstance(value, str):
            continue
        v = value.strip()
        if not v.isdigit():
            continue
        parent_key = str(path[-1]) if path else ""
        ctx = _path_str(path)
        if len(v) == 14 and (
            _SIRET_PARENT_HINTS.search(parent_key) or _ID_CONTEXT_HINTS.search(ctx)
        ):
            sirets.append(v)
        elif len(v) == 9 and (
            _SIREN_PARENT_HINTS.search(parent_key) or (
                parent_key.lower() in {"id", "companyid"} and _ID_CONTEXT_HINTS.search(ctx)
            )
        ):
            sirens.append(v)
    # de-duplicate, preserve order
    return list(dict.fromkeys(sirets)), list(dict.fromkeys(sirens))


def extract_cpv_codes(donnees_obj) -> list:
    """Return CPV-looking 8-digit codes found near a key containing 'cpv',
    plus the legacy-schema `CPV.objetPrincipal.classPrincipale` shape."""
    codes = []
    for path, value in walk(donnees_obj):
        if not isinstance(value, str):
            continue
        v = value.strip()
        if re.fullmatch(r"\d{8}", v):
            ctx = _path_str(path)
            if _CPV_HINTS.search(ctx):
                codes.append(v)
    return list(dict.fromkeys(codes))


_UNIT_TO_MONTHS = {
    "DAY": 1 / 30.0, "JOU": 1 / 30.0,
    "MON": 1.0, "MOI": 1.0,
    "YEAR": 12.0, "ANN": 12.0,
}


def extract_duration_months(donnees_obj) -> tuple[Optional[float], Optional[str]]:
    """Return (duration_in_months, source_key) using the first duration-like
    field found. Legacy schema: `dureeMois` / `dureeLot.nbMois` (already in
    months). eForms/UBL schema: `DurationMeasure` with a sibling unit code."""
    # Pass 1: direct month fields (legacy schema) - most reliable, prefer these.
    for path, value in walk(donnees_obj):
        parent_key = str(path[-1]) if path else ""
        if _DUREE_MOIS_HINT.search(parent_key) and isinstance(value, str):
            v = value.strip().replace(",", ".")
            try:
                return float(v), _path_str(path)
            except ValueError:
                continue

    # Pass 2: eForms-style DurationMeasure + unit code, walked as raw dict tree
    # (not flattened by `walk`, since we need the unit-code sibling).
    for path, value in _walk_dicts(donnees_obj):
        for key, val in value.items():
            if _DURATION_MEASURE_HINT.search(str(key)):
                inner = val if isinstance(val, dict) else {"#text": val}
                text = inner.get("#text") if isinstance(inner, dict) else None
                unit = inner.get("@unitCode") if isinstance(inner, dict) else None
                if text is None:
                    continue
                try:
                    n = float(str(text).strip())
                except ValueError:
                    continue
                factor = _UNIT_TO_MONTHS.get(str(unit).upper(), None) if unit else None
                if factor is None:
                    factor = 1.0  # unit unknown: assume months as a documented fallback
                return n * factor, _path_str(path) + "/" + str(key)
    return None, None


def _walk_dicts(obj, path=()):
    """Yield (path, dict) for every dict node (not leaves) in the structure."""
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from _walk_dicts(v, path + (k,))
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_dicts(item, path)


def detect_schema_family(donnees_raw: str) -> str:
    """Cheap prefix check to label which JSON structure a notice uses."""
    if not donnees_raw:
        return "MISSING"
    stripped = donnees_raw.lstrip()
    if stripped.startswith('{"EFORMS"') or '"EFORMS"' in stripped[:30]:
        return "EFORMS"
    return "LEGACY"
