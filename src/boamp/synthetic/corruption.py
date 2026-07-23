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

from boamp.synthetic.missingness import assign_quality_class, duration_severity_multiplier, severity_multiplier
from boamp.synthetic.text_generation import apply_next_cycle_drift, generate_hard_negative_text

# Small shared cross-buyer boilerplate pool (v0.1 fidelity follow-up,
# exact_duplicate_template_rate) -- real BOAMP's high literal-duplication
# rate (51.4%) is driven by shared official boilerplate reused across many
# UNRELATED buyers, not only same-cycle CALL/AWARD reuse. A single fixed
# string would work numerically but concentrate all boilerplate-corrupted
# notices into one unrealistic monoculture; several fixed phrases spread the
# duplication across a few distinct clusters (more realistic) at the cost of
# needing a higher boilerplate_rate to hit the same aggregate rate (each
# additional phrase dilutes the per-corruption uniqueness reduction).
GENERIC_BOILERPLATE_POOL: list[str] = [
    "Marché public - voir cahier des charges pour le détail des prestations.",
    "Consultation lancée dans le cadre d'un marché public de fournitures et services courants.",
    "Prestations diverses dans le cadre d'un marché public, se reporter au dossier de consultation.",
]

EXACT_TEMPLATE_POOL: list[str] = [
    "Avis de marché public - prestations courantes.",
    "Consultation pour des fournitures et services.",
    "Marché public de services administratifs.",
    "Procédure adaptée pour prestations diverses.",
    "Accord-cadre relatif à des prestations courantes.",
    "Prestations de maintenance et services associés.",
    "Fourniture et livraison de matériels.",
    "Services d'assistance et de support.",
    "Travaux et prestations connexes.",
    "Renouvellement de marché public.",
    "Mission de service auprès de la collectivité.",
    "Prestation technique pour besoins courants.",
]

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


def _identifier_year_regime_scale(year: int, scen_ids) -> float:
    """v0.2 conditional-fidelity follow-up: real SIRET presence shows a
    regime shift centered on 2022 that is INDEPENDENT of the EFORMS schema
    cutover -- 2022 and 2023 are both 100% LEGACY in this corpus, yet SIRET
    presence jumps from ~9-17% (2015-2021) to ~53-56% (2022-2023) then
    partially recedes to ~39-49% (2024-2026). Not explainable by
    schema_family; modeled here as a year-regime scale factor applied on top
    of the base identifier corruption rates (see
    v0_1_fidelity_report.md's conditional-fidelity section)."""
    regimes = getattr(scen_ids, "year_regime_scale", None)
    if regimes is None:
        return 1.0
    if year <= regimes.early.end_year:
        return regimes.early.scale
    if year <= regimes.mid.end_year:
        return regimes.mid.scale
    return regimes.late.scale


def _conditional_identifier_outcome(row, siblings_by_siren: dict[str, list[str]], scen_ids,
                                    rng: np.random.Generator, logger, observation_model) -> tuple[str | None, str | None]:
    """Draw identifier visibility from observable conditional SIRET targets.

    The target is checksum-valid SIRET presence. When SIRET is not observed,
    the old corruption vocabulary is preserved by splitting the absent mass
    into SIREN-only, invalid-SIRET, and fully missing official identifiers.
    """
    present_rate = observation_model.siret_present_rate(row)
    siret_true, siren_true = row["siret_true"], row["siren_true"]
    cfg = getattr(scen_ids, "conditional_siret_presence", None)
    wrong_rate = getattr(scen_ids, "wrong_establishment_siret_rate", 0.0)
    siren_only_rate = getattr(cfg, "siren_only_among_absent_rate", 0.03)
    invalid_rate = getattr(cfg, "invalid_among_absent_rate", 0.01)

    if rng.random() < present_rate:
        if rng.random() < wrong_rate:
            siblings = [s for s in siblings_by_siren.get(siren_true, []) if s != siret_true]
            if siblings:
                wrong = str(rng.choice(siblings))
                logger.log(row["notice_id_synthetic"], "buyer_siret_raw", siret_true, wrong,
                           "WRONG_ESTABLISHMENT_SAME_SIREN", severity=1.0)
                return wrong, siren_true
        return siret_true, siren_true

    draw = rng.random()
    if draw < siren_only_rate:
        logger.log(row["notice_id_synthetic"], "buyer_siret_raw", siret_true, None,
                   "SIREN_ONLY_OBSERVED", severity=1.0)
        return None, siren_true
    if draw < siren_only_rate + invalid_rate:
        bad = (siret_true[:-1] + str((int(siret_true[-1]) + 1) % 10)) if siret_true else None
        logger.log(row["notice_id_synthetic"], "buyer_siret_raw", siret_true, bad,
                   "INVALID_CHECKSUM", severity=1.0)
        return bad, None

    logger.log(row["notice_id_synthetic"], "buyer_siret_raw", siret_true, None, "BOTH_MISSING", severity=1.0)
    logger.log(row["notice_id_synthetic"], "buyer_siren_raw", siren_true, None, "BOTH_MISSING", severity=1.0)
    return None, None


def _corrupt_identifier(row, siblings_by_siren: dict[str, list[str]], mult: float,
                          scen_ids, rng: np.random.Generator, logger,
                          observation_model=None) -> tuple[str | None, str | None]:
    conditional_cfg = getattr(scen_ids, "conditional_siret_presence", None)
    if observation_model is not None and getattr(conditional_cfg, "enabled", False):
        return _conditional_identifier_outcome(row, siblings_by_siren, scen_ids, rng, logger, observation_model)

    regime_scale = _identifier_year_regime_scale(row["publication_date_true"].year, scen_ids)
    rates = dict(SIREN_ONLY=scen_ids.siren_only_rate, BOTH_MISSING=scen_ids.both_missing_rate,
                 INVALID=scen_ids.invalid_identifier_rate,
                 WRONG_ESTABLISHMENT=scen_ids.wrong_establishment_siret_rate)
    outcome = _weighted_outcome(rates, mult * regime_scale, rng)
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


def _cpv_missing_rate(row, scen_cpv) -> float:
    """v0.2 conditional-fidelity follow-up: real CPV missingness is strongly
    schema- and notice-type-conditional (EFORMS: 0.0% missing; LEGACY:
    19.5%; APPEL_OFFRE: 21.4%, ATTRIBUTION: 7.1%) rather than a single flat
    rate (see v0_1_fidelity_report.md's conditional-fidelity section). Falls
    back to the flat `missing_rate` for scenarios that don't configure
    `missing_rate_by_condition`."""
    by_condition = getattr(scen_cpv, "missing_rate_by_condition", None)
    if by_condition is None:
        return scen_cpv.missing_rate
    if row["schema_family_true"] == "EFORMS":
        return by_condition.eforms
    return getattr(by_condition.legacy, row["notice_type_true"], scen_cpv.missing_rate)


def _corrupt_cpv(row, mult: float, scen_cpv, rng: np.random.Generator, logger) -> str | None:
    rates = dict(MISSING=_cpv_missing_rate(row, scen_cpv), PARENT=scen_cpv.parent_replace_rate,
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


def _corrupt_duration(row, mult: float, scen_dur, rng: np.random.Generator, logger,
                      observation_model=None) -> float | None:
    """v0.2 conditional-fidelity follow-up: real duration presence is a
    near-deterministic function of schema_family (0.0% every year 2015-2023,
    then 52-68% once EFORMS is mandated), not a smooth quality-driven rate --
    the previous flat `missing_rate` matched the marginal average only by
    coincidence of the observation window's year mix (see
    v0_1_fidelity_report.md's conditional-fidelity section). When
    `scen_dur.missing_rate_by_schema` is configured, it takes precedence
    over the flat `missing_rate` (kept as a fallback for scenarios, e.g.
    clean_sanity/adverse_identity, that don't set it)."""
    true_val = row["duration_true_months"]
    conditional_cfg = getattr(scen_dur, "conditional_presence", None)
    if observation_model is not None and getattr(conditional_cfg, "enabled", False):
        if rng.random() >= observation_model.duration_present_rate(row):
            logger.log(row["notice_id_synthetic"], "declared_duration_months", true_val, None,
                       "MISSING", severity=1.0)
            return None
        base_rate = 0.0
    else:
        by_schema = getattr(scen_dur, "missing_rate_by_schema", None)
        base_rate = (getattr(by_schema, row["schema_family_true"], scen_dur.missing_rate)
                     if by_schema is not None else scen_dur.missing_rate)
        if rng.random() < min(0.98, base_rate * mult):
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


def _near_boilerplate_text(row, text: str, rng: np.random.Generator) -> str:
    phrase = str(rng.choice(GENERIC_BOILERPLATE_POOL))
    suffixes = [
        f" Acheteur: {row['buyer_name_true']}.",
        f" Secteur CPV {str(row['cpv_true'])[:2]}.",
        f" Publication {pd.Timestamp(row['publication_date_true']).year}.",
        f" Département {row['department_true']}.",
    ]
    return f"{phrase} {text[:70]}{str(rng.choice(suffixes))}"


def _generic_weak_text(row, rng: np.random.Generator) -> str:
    verbs = ["Fourniture", "Maintenance", "Prestations", "Services", "Travaux"]
    scopes = ["courants", "techniques", "administratifs", "associés", "spécifiques"]
    return (
        f"{str(rng.choice(verbs))} {str(rng.choice(scopes))} - "
        f"{row['buyer_name_true']} - CPV {str(row['cpv_true'])[:2]}."
    )


def _corrupt_text(row, mult: float, scen_text, need_vocab: list[str], rng: np.random.Generator,
                  logger, observation_model=None, buyer_activity_tier: str | None = None) -> str:
    text = row["objet_true"]
    if row["role"] == "AWARD" and text and rng.random() < min(0.98, scen_text.next_cycle_drift_severity * mult * 0.3):
        # Even within a cycle, a poorly-recorded award can drift lexically
        # from its own call (distinct from the deliberate next_cycle_drift
        # applied between cycles at the need level — this is a *within*
        # this-notice corruption, hence the extra 0.3 damping factor).
        drifted = apply_next_cycle_drift(text, need_vocab, rng, severity=min(1.0, scen_text.next_cycle_drift_severity * 0.5))
        logger.log(row["notice_id_synthetic"], "objet_clean", text, drifted, "LEXICAL_DRIFT", severity=mult)
        text = drifted

    conditional_cfg = getattr(scen_text, "conditional_reuse", None)
    if observation_model is not None and getattr(conditional_cfg, "enabled", False):
        target = observation_model.generic_text_rate(row["notice_type_true"], buyer_activity_tier or "21+")
        exact_share = getattr(conditional_cfg, "exact_template_share", 0.82)
        near_extra = getattr(conditional_cfg, "near_boilerplate_extra_rate", 0.08)
        weak_extra = getattr(conditional_cfg, "generic_weak_extra_rate", 0.04)
        if rng.random() < min(0.95, target * exact_share):
            template = str(rng.choice(EXACT_TEMPLATE_POOL))
            logger.log(row["notice_id_synthetic"], "objet_clean", text, template,
                       "EXACT_CROSS_BUYER_TEMPLATE", severity=1.0)
            return template
        if rng.random() < min(0.95, target * near_extra):
            near = _near_boilerplate_text(row, text, rng)
            logger.log(row["notice_id_synthetic"], "objet_clean", text, near,
                       "NEAR_BOILERPLATE_WITH_SPECIFIC_TOKENS", severity=1.0)
            return near
        if rng.random() < min(0.95, target * weak_extra):
            weak = _generic_weak_text(row, rng)
            logger.log(row["notice_id_synthetic"], "objet_clean", text, weak,
                       "GENERIC_WEAK_PROCUREMENT_TEXT", severity=1.0)
            return weak
        same_family_near_rate = getattr(conditional_cfg, "same_family_near_duplicate_rate", 0.0)
        if row["role"] == "AWARD" and rng.random() < same_family_near_rate:
            near_family = f"{text.rstrip('.')} - attribution du marché."
            logger.log(row["notice_id_synthetic"], "objet_clean", text, near_family,
                       "SAME_FAMILY_NEAR_DUPLICATE", severity=1.0)
            return near_family
        return text

    if rng.random() < min(0.98, scen_text.boilerplate_rate * mult):
        boilerplate = str(rng.choice(GENERIC_BOILERPLATE_POOL))
        logger.log(row["notice_id_synthetic"], "objet_clean", text, boilerplate, "GENERIC_BOILERPLATE", severity=mult)
        text = boilerplate
    return text


def corrupt_notices(clean_notices: pd.DataFrame, buyers: pd.DataFrame, establishments: pd.DataFrame,
                     scenario, rng: np.random.Generator, logger, observation_model=None) -> pd.DataFrame:
    quality_class = assign_quality_class(clean_notices, buyers, scenario, rng)
    mult = severity_multiplier(quality_class)
    duration_mult = duration_severity_multiplier(quality_class)

    siblings_by_siren: dict[str, list[str]] = {
        siren: grp["siret_true"].tolist() for siren, grp in establishments.groupby("siren_true")
    }
    buyers_idx = buyers.set_index("buyer_id_true")
    need_vocab_lookup = clean_notices.drop_duplicates("need_id_true").set_index("need_id_true")
    scoped_candidate_cfg = getattr(getattr(scenario, "recurrence", None), "scoped_candidate_environment", None)
    scoped_name_stability = bool(
        getattr(scoped_candidate_cfg, "enabled", False)
        and getattr(scoped_candidate_cfg, "stabilize_scoped_name_fallback", False)
    )
    scoped_divisions = {str(v) for v in getattr(scoped_candidate_cfg, "cpv_divisions", [])}
    stable_scoped_name_by_buyer: dict[str, str] = {}
    buyer_notice_tier = pd.cut(
        clean_notices.groupby("buyer_id_true")["notice_id_synthetic"].transform("size"),
        bins=[0, 1, 5, 20, np.inf],
        labels=["1 (single)", "2-5", "6-20", "21+"],
        right=True,
    ).astype(str)

    rows = []
    for i, row in clean_notices.reset_index(drop=True).iterrows():
        m = float(mult.iloc[i])
        buyer = buyers_idx.loc[row["buyer_id_true"]]

        siret_obs, siren_obs = _corrupt_identifier(
            row, siblings_by_siren, m, scenario.identifiers, rng, logger,
            observation_model=observation_model,
        )

        name_true = row["buyer_name_true"]
        use_stable_scoped_name = (
            scoped_name_stability
            and str(row["cpv_true"])[:2] in scoped_divisions
        )
        if use_stable_scoped_name and row["buyer_id_true"] in stable_scoped_name_by_buyer:
            name_obs = stable_scoped_name_by_buyer[row["buyer_id_true"]]
        else:
            name_obs = name_true
            if rng.random() < min(0.98, scenario.buyer_names.generic_collision_rate * m * float(buyer["alias_propensity"] + 0.3)):
                pool = GENERIC_NAME_POOL.get(buyer["buyer_type_true"], GENERIC_NAME_POOL["AUTRE"])
                name_obs = str(rng.choice(pool))
                logger.log(row["notice_id_synthetic"], "buyer_name_raw", name_true, name_obs, "GENERIC_NAME_COLLISION", severity=m)
            elif rng.random() < min(0.98, scenario.buyer_names.false_split_rate * m * float(buyer["alias_propensity"] + 0.3)):
                name_obs = _apply_name_transformation(name_true, row["department_true"], rng)
                logger.log(row["notice_id_synthetic"], "buyer_name_raw", name_true, name_obs, "NAME_VARIANT", severity=m)
            if use_stable_scoped_name:
                stable_scoped_name_by_buyer[row["buyer_id_true"]] = name_obs

        cpv_obs = _corrupt_cpv(row, m, scenario.cpv, rng, logger)
        duration_obs = _corrupt_duration(
            row, float(duration_mult.iloc[i]), scenario.duration, rng, logger,
            observation_model=observation_model,
        )

        need_vocab = need_vocab_lookup.loc[row["need_id_true"], "objet_true"] if row["need_id_true"] in need_vocab_lookup.index else []
        text_obs = _corrupt_text(
            row, m, scenario.text, need_vocab if isinstance(need_vocab, list) else [], rng, logger,
            observation_model=observation_model,
            buyer_activity_tier=str(buyer_notice_tier.iloc[i]),
        )

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
