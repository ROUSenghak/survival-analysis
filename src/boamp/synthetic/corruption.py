"""Observation and corruption mechanisms (Phase 6): clean_notices ->
observed_notices, following Lam et al.'s "gold-standard-and-corruption"
design. Every mechanism below is driven by a per-notice latent quality class
(missingness.py) so identifier, CPV, duration, text and linked-notice
corruption co-occur rather than being sampled independently per field
(Phase 6.7).

Column-name convention on observed_notices matches the real prepared BOAMP
corpus (src/boamp/data/prepare.py) where meaningful (buyer_siret_raw,
buyer_siren_raw, buyer_name_raw, code_departement, cpv_clean,
declared_duration_months, objet_clean) so the existing Layer 1/Layer 2
linkage code can consume it with minimal adaptation (Phase 12 compatibility
checks) — but no truth column is ever present (schemas.assert_no_truth_leakage).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from boamp.synthetic.missingness import assign_quality_class, severity_multiplier
from boamp.synthetic.text_generation import apply_next_cycle_drift, generate_hard_negative_text

GENERIC_NAME_POOL: dict[str, list[str]] = {
    "COMMUNE": ["Mairie", "Commune"],
    "EPCI": ["Communauté de communes", "Collectivité territoriale"],
    "DEPARTEMENT": ["Conseil départemental", "Collectivité territoriale"],
    "ETABLISSEMENT_PUBLIC": ["Établissement public", "Centre hospitalier"],
    "AUTRE": ["Collectivité territoriale", "Établissement public"],
}

_ABBREVIATIONS = {
    "Communauté de communes": "CC", "Communauté d'agglomération": "CA",
    "Conseil départemental": "CD", "Centre hospitalier": "CH",
}


def _weighted_outcome(base_rates: dict[str, float], mult: float, rng: np.random.Generator) -> str:
    """Draw one outcome from {**base_rates scaled by mult, 'OK': remainder}."""
    weights = {k: min(0.98, v * mult) for k, v in base_rates.items()}
    total = sum(weights.values())
    if total > 1.0:
        weights = {k: v / total for k, v in weights.items()}
        total = 1.0
    weights["OK"] = max(0.0, 1.0 - total)
    keys = list(weights)
    probs = np.array([weights[k] for k in keys])
    probs = probs / probs.sum()
    return str(rng.choice(keys, p=probs))


def _apply_name_transformation(name: str, department: str, rng: np.random.Generator) -> str:
    mode = rng.choice(["abbreviate", "suffix_removal", "punctuation_variation",
                        "service_added", "geo_qualifier_added", "token_reorder"])
    if mode == "abbreviate":
        for full, abbr in _ABBREVIATIONS.items():
            if name.startswith(full):
                return name.replace(full, abbr, 1)
        return name
    if mode == "suffix_removal":
        tokens = name.split(" ")
        return " ".join(tokens[:-1]) if len(tokens) > 2 else name
    if mode == "punctuation_variation":
        return name.replace("é", "e").replace("è", "e").replace("'", " ").upper()
    if mode == "service_added":
        return f"{name} - Service des marchés publics"
    if mode == "geo_qualifier_added":
        return f"{name} ({department})"
    if mode == "token_reorder":
        tokens = name.split(" ")
        if len(tokens) > 2:
            rng.shuffle(tokens)
            return " ".join(tokens)
        return name
    return name


def _corrupt_identifier(row, siblings_by_siren: dict[str, list[str]], mult: float,
                          scen_ids, rng: np.random.Generator, logger) -> tuple[str | None, str | None]:
    rates = dict(SIREN_ONLY=scen_ids.siren_only_rate, BOTH_MISSING=scen_ids.both_missing_rate,
                 INVALID=scen_ids.invalid_identifier_rate,
                 WRONG_ESTABLISHMENT=scen_ids.wrong_establishment_siret_rate)
    outcome = _weighted_outcome(rates, mult, rng)
    siret_true, siren_true = row["siret_true"], row["siren_true"]  # noqa

    if outcome == "OK":
        return siret_true, siren_true
    if outcome == "SIREN_ONLY":
        logger.log(row["notice_id_synthetic"], "buyer_siret_raw", siret_true, None, "SIREN_ONLY_OBSERVED", severity=mult)
        return None, siren_true
    if outcome == "BOTH_MISSING":
        logger.log(row["notice_id_synthetic"], "buyer_siret_raw", siret_true, None, "BOTH_MISSING", severity=mult)
        logger.log(row["notice_id_synthetic"], "buyer_siren_raw", siren_true, None, "BOTH_MISSING", severity=mult)
        return None, None
    if outcome == "INVALID":
        bad = (siret_true[:-1] + str((int(siret_true[-1]) + 1) % 10)) if siret_true else None
        logger.log(row["notice_id_synthetic"], "buyer_siret_raw", siret_true, bad, "INVALID_CHECKSUM", severity=mult)
        return bad, None
    if outcome == "WRONG_ESTABLISHMENT":
        siblings = [s for s in siblings_by_siren.get(siren_true, []) if s != siret_true]
        if siblings:
            wrong = str(rng.choice(siblings))
            logger.log(row["notice_id_synthetic"], "buyer_siret_raw", siret_true, wrong, "WRONG_ESTABLISHMENT_SAME_SIREN", severity=mult)
            return wrong, siren_true
        return siret_true, siren_true
    return siret_true, siren_true


def _corrupt_cpv(row, mult: float, scen_cpv, rng: np.random.Generator, logger) -> str | None:
    rates = dict(MISSING=scen_cpv.missing_rate, PARENT=scen_cpv.parent_replace_rate,
                 DIVISION_ONLY=scen_cpv.division_only_rate, GENERIC=scen_cpv.generic_rate,
                 WRONG_RELATED=scen_cpv.wrong_related_rate)
    outcome = _weighted_outcome(rates, mult, rng)
    cpv_true = row["cpv_true"]
    if outcome == "OK":
        return cpv_true
    corrupted = {
        "MISSING": None,
        "PARENT": cpv_true[:5] + "000",
        "DIVISION_ONLY": cpv_true[:2] + "000000",
        "GENERIC": cpv_true[:2] + "000000",
        "WRONG_RELATED": cpv_true[:2] + "".join(str(int(d)) for d in rng.integers(0, 10, size=6)),
    }[outcome]
    logger.log(row["notice_id_synthetic"], "cpv_clean", cpv_true, corrupted, outcome, severity=mult)
    return corrupted


def _corrupt_duration(row, mult: float, scen_dur, rng: np.random.Generator, logger) -> float | None:
    true_val = row["duration_true_months"]
    if rng.random() < min(0.98, scen_dur.missing_rate * mult):
        logger.log(row["notice_id_synthetic"], "declared_duration_months", true_val, None, "MISSING", severity=mult)
        return None
    val = true_val
    if rng.random() < min(0.98, scen_dur.rounding_severity * mult):
        step = 6 if val <= 24 else 12
        val = max(1.0, round(val / step) * step)
    if rng.random() < min(0.98, scen_dur.common_admin_value_rate * mult):
        val = min([1, 3, 6, 12, 24, 36, 48], key=lambda c: abs(c - val))
    if rng.random() < min(0.98, scen_dur.unit_conversion_failure_rate * mult):
        val = round(val * 30.0, 1)  # months mistakenly re-expressed as days, unit label unchanged
    if val != true_val:
        logger.log(row["notice_id_synthetic"], "declared_duration_months", true_val, val, "ROUNDED_OR_CONVERTED", severity=mult)
    return val


def _corrupt_text(row, mult: float, scen_text, need_vocab: list[str], rng: np.random.Generator, logger) -> str:
    text = row["objet_true"]
    if row["role"] == "AWARD" and text and rng.random() < min(0.98, scen_text.next_cycle_drift_severity * mult * 0.3):
        # Even within a cycle, a poorly-recorded award can drift lexically
        # from its own call (distinct from the deliberate next_cycle_drift
        # applied between cycles at the need level — this is a *within*
        # this-notice corruption, hence the extra 0.3 damping factor).
        drifted = apply_next_cycle_drift(text, need_vocab, rng, severity=min(1.0, scen_text.next_cycle_drift_severity * 0.5))
        logger.log(row["notice_id_synthetic"], "objet_clean", text, drifted, "LEXICAL_DRIFT", severity=mult)
        text = drifted
    if rng.random() < min(0.98, scen_text.boilerplate_rate * mult):
        boilerplate = "Marché public - voir cahier des charges pour le détail des prestations."
        logger.log(row["notice_id_synthetic"], "objet_clean", text, boilerplate, "GENERIC_BOILERPLATE", severity=mult)
        text = boilerplate
    return text


def corrupt_notices(clean_notices: pd.DataFrame, buyers: pd.DataFrame, establishments: pd.DataFrame,
                     scenario, rng: np.random.Generator, logger) -> pd.DataFrame:
    quality_class = assign_quality_class(clean_notices, buyers, scenario, rng)
    mult = severity_multiplier(quality_class)

    siblings_by_siren: dict[str, list[str]] = {
        siren: grp["siret_true"].tolist() for siren, grp in establishments.groupby("siren_true")
    }
    buyers_idx = buyers.set_index("buyer_id_true")
    need_vocab_lookup = clean_notices.drop_duplicates("need_id_true").set_index("need_id_true")

    rows = []
    for i, row in clean_notices.reset_index(drop=True).iterrows():
        m = float(mult.iloc[i])
        buyer = buyers_idx.loc[row["buyer_id_true"]]

        siret_obs, siren_obs = _corrupt_identifier(row, siblings_by_siren, m, scenario.identifiers, rng, logger)

        name_true = row["buyer_name_true"]
        name_obs = name_true
        if rng.random() < min(0.98, scenario.buyer_names.generic_collision_rate * m * float(buyer["alias_propensity"] + 0.3)):
            pool = GENERIC_NAME_POOL.get(buyer["buyer_type_true"], GENERIC_NAME_POOL["AUTRE"])
            name_obs = str(rng.choice(pool))
            logger.log(row["notice_id_synthetic"], "buyer_name_raw", name_true, name_obs, "GENERIC_NAME_COLLISION", severity=m)
        elif rng.random() < min(0.98, scenario.buyer_names.false_split_rate * m * float(buyer["alias_propensity"] + 0.3)):
            name_obs = _apply_name_transformation(name_true, row["department_true"], rng)
            logger.log(row["notice_id_synthetic"], "buyer_name_raw", name_true, name_obs, "NAME_VARIANT", severity=m)

        cpv_obs = _corrupt_cpv(row, m, scenario.cpv, rng, logger)
        duration_obs = _corrupt_duration(row, m, scenario.duration, rng, logger)

        need_vocab = need_vocab_lookup.loc[row["need_id_true"], "objet_true"] if row["need_id_true"] in need_vocab_lookup.index else []
        text_obs = _corrupt_text(row, m, scenario.text, need_vocab if isinstance(need_vocab, list) else [], rng, logger)

        linked_obs = row["linked_call_notice_id_true"]
        if row["role"] == "AWARD" and linked_obs is not None:
            if rng.random() < min(0.98, scenario.linked_notice_visibility.missing_rate * m):
                logger.log(row["notice_id_synthetic"], "linked_call_notice_id", linked_obs, None, "LINK_NOT_RECORDED", severity=m)
                linked_obs = None

        rows.append(dict(
            notice_id_synthetic=row["notice_id_synthetic"],
            publication_date=row["publication_date_true"],
            notice_type_normalized=row["notice_type_true"],
            schema_family=row["schema_family_true"],
            buyer_siret_raw=siret_obs,
            buyer_siren_raw=siren_obs,
            buyer_name_raw=name_obs,
            code_departement=row["department_true"],
            cpv_clean=cpv_obs,
            declared_duration_months=duration_obs,
            objet_clean=text_obs,
            linked_call_notice_id=linked_obs,
        ))

    return pd.DataFrame(rows)
