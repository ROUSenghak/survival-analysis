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
from utils.identifiers import normalize_buyer_name, validate_siren, validate_siret

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
    "Conseil régional": "CR", "Office public de l'habitat": "OPH",
    "Syndicat mixte": "SM", "Établissement public": "EP",
    "Commune": "CNE", "Mairie": "MAIRIE", "Département": "DEPT",
    "Université": "UNIV", "Lycée": "LYC",
}

# v0.4 buyer-name alias families. The v0.3 mechanism drew one of six edits
# uniformly, two of which could not produce an observable variant at all:
# `punctuation_variation` (accent strip + uppercase) is erased by
# `normalize_buyer_name`, and `token_reorder` leaves the token set untouched so
# its token Jaccard is exactly 1.0 -- 18.6% of synthetic same-SIREN pairs sat at
# Jaccard 1.0 against 0.2% in the real corpus. Meanwhile 25.4% of *real*
# same-SIREN name pairs share NO token at all, because French public buyers
# publish under acronyms, directorate names and service names as well as their
# legal name; synthetic produced 0.5%.
#
# The families below are grouped by how much token overlap they destroy, so the
# scenario can set the share of each band directly against the observable real
# similarity distribution rather than hoping a uniform edit mix lands there.
_ALIAS_DIRECTORATES: list[str] = [
    "Direction des achats", "Direction de la commande publique",
    "Service des marchés publics", "Direction des services techniques",
    "Pôle achats et marchés", "Direction générale des services",
]
_ALIAS_INSTITUTIONAL_SYNONYMS: dict[str, str] = {
    "Commune": "Ville", "Mairie": "Ville", "Communauté de communes": "Intercommunalité",
    "Communauté d'agglomération": "Agglomération", "Conseil départemental": "Département",
    "Centre hospitalier": "Hôpital", "Office public de l'habitat": "Bailleur social",
    "Syndicat mixte": "Syndicat",
}
_ALIAS_GEO_PREFIXES: list[str] = ["Grand", "Pays de", "Val de", "Terres de"]

ALIAS_FAMILIES_ZERO_OVERLAP: tuple[str, ...] = (
    "acronym_only",
    "directorate_only",
)
ALIAS_FAMILIES_PARTIAL_OVERLAP: tuple[str, ...] = (
    "legal_form_swap",
    "institutional_type_deletion",
    "geographic_qualifier_insertion",
    "token_deletion",
    "multi_token_abbreviation",
    "administrative_synonym",
    "service_suffix",
)
ALIAS_FAMILIES_FULL_OVERLAP: tuple[str, ...] = ("token_reorder",)


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


def _leading_type_phrase(name: str) -> str | None:
    """The institutional-type phrase a synthetic buyer name starts with, if any."""
    for phrase in sorted(_ALIAS_ABBREVIABLE_PHRASES, key=len, reverse=True):
        if name.startswith(phrase):
            return phrase
    return None


_ALIAS_ABBREVIABLE_PHRASES = tuple(_ABBREVIATIONS)


def _place_tokens(name: str) -> list[str]:
    """Tokens of the name after its institutional-type phrase and any 'de/du/d''."""
    phrase = _leading_type_phrase(name)
    rest = name[len(phrase):].strip() if phrase else name
    tokens = [t for t in rest.split(" ") if t]
    while tokens and tokens[0].lower().rstrip("'") in {"de", "du", "des", "d", "la", "le", "les"}:
        tokens = tokens[1:]
    return tokens


def _alias_variant(name: str, family: str, department: str, rng: np.random.Generator) -> str:
    """One alias of `name` in the requested family.

    Families are allowed to fall through to a milder edit when the base name has
    no structure to work on (a two-token name cannot lose a token and stay a
    name); the caller re-checks that the produced alias is actually distinct, so
    a fall-through costs an alias slot rather than silently inflating the
    zero-overlap share.
    """
    tokens = name.split(" ")
    place = " ".join(_place_tokens(name)) or (tokens[-1] if tokens else name)
    phrase = _leading_type_phrase(name)

    if family == "acronym_only":
        # "Communauté de communes Verbourg" -> "CC Verbourg" is still a partial
        # overlap; a pure acronym drops the place word too, which is what the
        # real zero-overlap pairs look like.
        abbr = _ABBREVIATIONS.get(phrase) if phrase else None
        initials = "".join(word[0] for word in place.split(" ") if word).upper()
        if abbr and initials:
            return f"{abbr}{initials}"
        if initials and len(initials) >= 2:
            return initials
        return "".join(word[0] for word in tokens if word).upper() or name

    if family == "directorate_only":
        return str(rng.choice(_ALIAS_DIRECTORATES))

    if family == "legal_form_swap":
        if phrase and phrase in _ALIAS_INSTITUTIONAL_SYNONYMS:
            return f"{_ALIAS_INSTITUTIONAL_SYNONYMS[phrase]} de {place}"
        return f"Etablissement {place}"

    if family == "institutional_type_deletion":
        return place or name

    if family == "geographic_qualifier_insertion":
        if rng.random() < 0.5:
            return f"{str(rng.choice(_ALIAS_GEO_PREFIXES))} {place}"
        return f"{name} ({department})"

    if family == "token_deletion":
        if len(tokens) > 2:
            drop = int(rng.integers(0, len(tokens)))
            return " ".join(tokens[:drop] + tokens[drop + 1:])
        return place or name

    if family == "multi_token_abbreviation":
        if phrase:
            abbr = _ABBREVIATIONS.get(phrase, "".join(w[0] for w in phrase.split(" ")).upper())
            return f"{abbr} {place}".strip()
        return " ".join([tokens[0][:3].upper(), *tokens[1:]]) if tokens else name

    if family == "administrative_synonym":
        if phrase and phrase in _ALIAS_INSTITUTIONAL_SYNONYMS:
            return name.replace(phrase, _ALIAS_INSTITUTIONAL_SYNONYMS[phrase], 1)
        return f"{name} - {str(rng.choice(_ALIAS_DIRECTORATES))}"

    if family == "service_suffix":
        return f"{name} - {str(rng.choice(_ALIAS_DIRECTORATES))}"

    if family == "token_reorder":
        if len(tokens) > 2:
            shuffled = list(tokens)
            rng.shuffle(shuffled)
            return " ".join(shuffled)
        return name

    return name


def build_buyer_alias_sets(
    buyers: pd.DataFrame, scen_names, rng: np.random.Generator
) -> dict[str, list[str]]:
    """Persistent alias set per buyer, drawn once for the whole world.

    v0.3 re-drew an independent edit per notice family, so a buyer's observed
    names were a cloud of one-off mutations of the true name rather than a small
    stable set of administrative forms. Real buyers reuse a handful of forms:
    69.7% of real SIRENs publish under exactly one normalized name, 18.5% under
    two, 6.4% under three. Drawing the set once reproduces that, and makes alias
    persistence over time a property of the generator rather than an accident.

    Returns buyer_id -> [primary_name, alias, ...]; the primary is always first.
    """
    cfg = getattr(scen_names, "persistent_aliases", None)
    if not getattr(cfg, "enabled", False):
        return {}

    size_weights = getattr(cfg, "alias_set_size_weights", None)
    raw_sizes = (
        {int(k): float(v) for k, v in vars(size_weights).items()}
        if size_weights is not None and not isinstance(size_weights, dict)
        else {int(k): float(v) for k, v in (size_weights or {1: 1.0}).items()}
    )
    sizes = np.array(sorted(raw_sizes), dtype=int)
    size_probs = np.array([raw_sizes[int(s)] for s in sizes], dtype=float)
    size_probs = size_probs / size_probs.sum()

    zero_share = float(getattr(cfg, "zero_overlap_family_share", 0.30))
    full_share = float(getattr(cfg, "full_overlap_family_share", 0.01))
    partial_share = max(0.0, 1.0 - zero_share - full_share)
    band_probs = np.array([zero_share, partial_share, full_share], dtype=float)
    band_probs = band_probs / band_probs.sum()
    bands = (
        ALIAS_FAMILIES_ZERO_OVERLAP,
        ALIAS_FAMILIES_PARTIAL_OVERLAP,
        ALIAS_FAMILIES_FULL_OVERLAP,
    )
    max_attempts = int(getattr(cfg, "max_alias_attempts", 6))

    # Alias-set sizes are assigned by quota against the calibrated weights rather
    # than drawn independently, so the marginal size distribution matches the
    # observable real one exactly at any buyer count. Buyers are ordered by their
    # own `alias_propensity`, which keeps the buyer-level gradient (some
    # organisations really do publish under many forms) without letting an
    # independent draw distort the calibrated marginal.
    n_buyers = len(buyers)
    counts = np.floor(size_probs * n_buyers).astype(int)
    # Flooring loses up to one buyer per distinct size. Give the remainder to the
    # *most common* size rather than to the last one: the size list runs up to 14
    # aliases, and dumping the rounding remainder there would hand a dozen buyers
    # the largest alias set in the calibrated distribution.
    counts[int(np.argmax(size_probs))] += n_buyers - counts.sum()
    targets_sorted = np.repeat(sizes, counts)
    order = np.argsort(buyers["alias_propensity"].to_numpy(dtype=float), kind="stable")
    targets = np.empty(n_buyers, dtype=int)
    targets[order] = targets_sorted

    alias_sets: dict[str, list[str]] = {}
    for position, (_, buyer) in enumerate(buyers.iterrows()):
        base = str(buyer["buyer_name_true"])
        names = [base]
        seen = {normalize_buyer_name(base)}
        for _ in range(int(targets[position]) - 1):
            for _attempt in range(max_attempts):
                band = bands[int(rng.choice(len(bands), p=band_probs))]
                family = str(rng.choice(band))
                candidate = _alias_variant(base, family, str(buyer["department_true"]), rng)
                normalized = normalize_buyer_name(candidate)
                if normalized and normalized not in seen:
                    names.append(candidate)
                    seen.add(normalized)
                    break
        alias_sets[str(buyer["buyer_id_true"])] = names
    return alias_sets


def _observed_buyer_key(siret: str | None, siren: str | None, name: str | None) -> str | None:
    if pd.notna(siret) and all(validate_siret(str(siret))):
        return f"SIRET:{siret}"
    if pd.notna(siren) and all(validate_siren(str(siren))):
        return f"SIREN:{siren}"
    normalized = normalize_buyer_name(name)
    if pd.notna(normalized):
        return f"NAME:{normalized}"
    return None


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


def _logit(p: float) -> float:
    p = min(1.0 - 1e-9, max(1e-9, p))
    return float(np.log(p / (1.0 - p)))


def _expit(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))


_GAUSS_HERMITE_NODES, _GAUSS_HERMITE_WEIGHTS = np.polynomial.hermite_e.hermegauss(41)
_GAUSS_HERMITE_WEIGHTS = _GAUSS_HERMITE_WEIGHTS / _GAUSS_HERMITE_WEIGHTS.sum()


class MarginalPreservingLogitIntercept:
    """Cell intercepts that keep a random-effect model's marginal rate on target.

    Adding a symmetric logit-scale buyer effect to a cell rate does **not** leave
    that rate alone: `E_Z[expit(logit(p) + sigma Z)]` is pulled toward 0.5, so a
    corpus whose cells mostly sit near 0.1-0.5 gains several percentage points of
    SIRET presence purely from Jensen's inequality. Measured on a v0.4 pilot, an
    uncorrected sigma = 2.1 pushed the marginal from 0.272 to 0.390.

    Rather than absorb that into a fudge factor, each distinct cell rate `p` gets
    an intercept `eta*` solved so that `E_Z[expit(eta* + sigma Z)] = p` exactly
    (Gauss-Hermite quadrature plus Brent root-finding, both cheap because the
    generator only ever sees a few hundred distinct cell rates). The result is a
    mechanism that adds between-buyer dispersion while leaving every calibrated
    schema x year x notice-type rate where the real corpus put it -- the
    population-averaged versus subject-specific distinction of Zeger, Liang and
    Albert (1988), solved numerically instead of approximated.
    """

    def __init__(self, sigma: float) -> None:
        self.sigma = float(sigma)
        self._cache: dict[float, float] = {}

    def _marginal(self, eta: float) -> float:
        return float(
            (_expit_array(eta + self.sigma * _GAUSS_HERMITE_NODES) * _GAUSS_HERMITE_WEIGHTS).sum()
        )

    def __call__(self, target_rate: float) -> float:
        p = min(1.0 - 1e-6, max(1e-6, float(target_rate)))
        key = round(p, 9)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        from scipy.optimize import brentq

        lo, hi = -40.0, 40.0
        try:
            eta = float(brentq(lambda e: self._marginal(e) - p, lo, hi, xtol=1e-10, maxiter=200))
        except ValueError:  # pragma: no cover - only if p is outside the reachable range
            eta = _logit(p)
        self._cache[key] = eta
        return eta


def _expit_array(x: np.ndarray) -> np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -700.0, 700.0)))


def buyer_identifier_offsets(buyer_effect_sd: float, propensity: np.ndarray) -> np.ndarray:
    """Logit-scale buyer random effects from the buyers' identifier propensities.

    v0.2 moved SIRET visibility onto an observable schema x year x notice-type
    rate table and, in doing so, made it independent across notices of the same
    buyer: `identifier_quality_propensity` (drawn per buyer in buyers.py) stopped
    being read on this path entirely. Real BOAMP is strongly buyer-persistent --
    among real name groups with at least five notices, 27% never show a
    checksum-valid SIRET and 5% always do, while the synthetic corpus squeezed
    74% of buyers into a 0.1-0.5 presence rate.

    The offset is applied on the logit scale so the cell-conditional ordering and
    the calibrated schema/year/type shape are preserved by construction: it moves
    every cell of a buyer by the same amount, it cannot push a rate outside
    (0, 1), and averaged over buyers it leaves the conditional rate close to its
    calibrated value (exactly so only in the limit; the residual is measured in
    the conditional WMAE gate, not assumed away).

    `propensity` is the Beta(5, 2) draw already stored on the buyer; the probit
    transform below turns it into an approximately standard normal so
    `buyer_effect_sd` reads directly as a logit-scale standard deviation. Reusing
    that existing column rather than drawing a fresh normal keeps the buyer's
    identifier behaviour tied to the same latent quality signal that
    missingness.py already uses, instead of introducing a second, unrelated one.
    """
    from scipy.stats import beta as _beta, norm as _norm

    values = np.clip(np.asarray(propensity, dtype=float), 1e-9, 1.0 - 1e-9)
    quantiles = np.clip(_beta.cdf(values, 5.0, 2.0), 1e-9, 1.0 - 1e-9)
    return buyer_effect_sd * _norm.ppf(quantiles)


def _conditional_identifier_outcome(row, siblings_by_siren: dict[str, list[str]], scen_ids,
                                    rng: np.random.Generator, logger, observation_model,
                                    buyer_logit_offset: float = 0.0,
                                    intercept: MarginalPreservingLogitIntercept | None = None,
                                    ) -> tuple[str | None, str | None]:
    """Draw identifier visibility from observable conditional SIRET targets.

    The target is checksum-valid SIRET presence. When SIRET is not observed,
    the old corruption vocabulary is preserved by splitting the absent mass
    into SIREN-only, invalid-SIRET, and fully missing official identifiers.
    """
    cfg = getattr(scen_ids, "conditional_siret_presence", None)
    presence_scale = float(getattr(cfg, "presence_scale", 1.0))
    cell_rate = observation_model.siret_present_rate(row) * presence_scale
    if intercept is not None:
        present_rate = _expit(intercept(cell_rate) + buyer_logit_offset)
    else:
        present_rate = min(1.0, max(0.0, cell_rate))
    siret_true, siren_true = row["siret_true"], row["siren_true"]
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
                          observation_model=None,
                          buyer_logit_offset: float = 0.0,
                          intercept: MarginalPreservingLogitIntercept | None = None,
                          ) -> tuple[str | None, str | None]:
    conditional_cfg = getattr(scen_ids, "conditional_siret_presence", None)
    if observation_model is not None and getattr(conditional_cfg, "enabled", False):
        return _conditional_identifier_outcome(
            row, siblings_by_siren, scen_ids, rng, logger, observation_model,
            buyer_logit_offset=buyer_logit_offset, intercept=intercept,
        )

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
        val = observation_model.declared_duration_value(row["notice_id_synthetic"])
        if val != true_val:
            logger.log(row["notice_id_synthetic"], "declared_duration_months", true_val, val,
                       "EMPIRICAL_RAW_DECLARED_DURATION", severity=1.0)
        return val
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
                  logger, observation_model=None, buyer_activity_tier: str | None = None,
                  same_family_key_mismatch: bool = False,
                  observed_buyer_key: str | None = None) -> str:
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
        same_buyer_template_rate = getattr(conditional_cfg, "same_buyer_admin_template_rate", 0.0)
        if (
            buyer_activity_tier in {"6-20", "21+"}
            and rng.random() < same_buyer_template_rate
        ):
            key = observed_buyer_key or "MISSING"
            admin = f"Marché public - acheteur {key}."
            logger.log(row["notice_id_synthetic"], "objet_clean", text, admin,
                       "SAME_BUYER_ADMIN_TEMPLATE", severity=1.0)
            return admin
        same_family_near_rate = getattr(conditional_cfg, "same_family_near_duplicate_rate", 0.0)
        if (
            row["role"] == "AWARD"
            and text == row["objet_true"]
            and (same_family_key_mismatch or rng.random() < same_family_near_rate)
        ):
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
    scoped_identity_by_need = bool(
        getattr(scoped_candidate_cfg, "enabled", False)
        and getattr(scoped_candidate_cfg, "stabilize_scoped_identity_by_need", False)
    )
    scoped_divisions = {str(v) for v in getattr(scoped_candidate_cfg, "cpv_divisions", [])}
    stable_scoped_name_by_buyer: dict[str, str] = {}
    family_identity_cache: dict[str, tuple[str | None, str | None, str]] = {}
    scoped_call_identifier_cache: dict[str, tuple[str | None, str | None]] = {}
    family_buyer_key_cache: dict[str, str | None] = {}
    conditional_identifier_presence = bool(
        observation_model is not None
        and getattr(getattr(scenario.identifiers, "conditional_siret_presence", None), "enabled", False)
    )
    # v0.4: buyer-persistent identifier visibility and persistent alias sets.
    # Both are precomputed once per world so they are properties of the buyer,
    # not of the notice that happens to be processed first.
    buyer_effect_sd = float(
        getattr(
            getattr(scenario.identifiers, "conditional_siret_presence", None),
            "buyer_effect_logit_sd",
            0.0,
        )
    )
    buyer_offsets: dict[str, float] = (
        dict(
            zip(
                buyers["buyer_id_true"].astype(str),
                buyer_identifier_offsets(
                    buyer_effect_sd, buyers["identifier_quality_propensity"].to_numpy(dtype=float)
                ),
                strict=False,
            )
        )
        if buyer_effect_sd > 0
        else {}
    )
    identifier_intercept = (
        MarginalPreservingLogitIntercept(buyer_effect_sd) if buyer_effect_sd > 0 else None
    )
    alias_sets = build_buyer_alias_sets(buyers, scenario.buyer_names, rng)
    alias_dominant_share = float(
        getattr(getattr(scenario.buyer_names, "persistent_aliases", None), "dominant_alias_share", 0.7)
    )
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
        buyer_offset = buyer_offsets.get(str(row["buyer_id_true"]), 0.0)

        is_scoped_notice = str(row["cpv_true"])[:2] in scoped_divisions
        identity_cache_key = (
            f"NEED::{row['need_id_true']}"
            if scoped_identity_by_need and is_scoped_notice
            else str(row["cycle_id_true"])
        )
        if identity_cache_key in family_identity_cache:
            siret_obs, siren_obs, name_obs = family_identity_cache[identity_cache_key]
        else:
            # The observed buyer name is a family-level observation, not an
            # independent latent buyer per CALL/AWARD sibling. Legacy
            # identifier corruption shares that family-level draw too, but
            # empirical conditional SIRET calibration is notice-level because
            # it is keyed by schema family and notice type.
            if conditional_identifier_presence:
                siret_obs, siren_obs = None, None
            else:
                siret_obs, siren_obs = _corrupt_identifier(
                    row, siblings_by_siren, m, scenario.identifiers, rng, logger,
                    observation_model=observation_model,
                    buyer_logit_offset=buyer_offset, intercept=identifier_intercept,
                )

            name_true = row["buyer_name_true"]
            use_stable_scoped_name = (
                scoped_name_stability
                and is_scoped_notice
            )
            if use_stable_scoped_name and row["buyer_id_true"] in stable_scoped_name_by_buyer:
                name_obs = stable_scoped_name_by_buyer[row["buyer_id_true"]]
            else:
                name_obs = name_true
                buyer_aliases = alias_sets.get(str(row["buyer_id_true"]))
                if rng.random() < min(0.98, scenario.buyer_names.generic_collision_rate * m * float(buyer["alias_propensity"] + 0.3)):
                    # False merge: two different buyers publish under the same
                    # generic name. Kept ahead of the alias branch so the two
                    # mechanisms stay separable in the corruption log.
                    pool = GENERIC_NAME_POOL.get(buyer["buyer_type_true"], GENERIC_NAME_POOL["AUTRE"])
                    name_obs = str(rng.choice(pool))
                    logger.log(row["notice_id_synthetic"], "buyer_name_raw", name_true, name_obs, "GENERIC_NAME_COLLISION", severity=m)
                elif buyer_aliases is not None and len(buyer_aliases) > 1:
                    # False split: the buyer publishes under one of its own
                    # persistent administrative forms. Which form is drawn per
                    # notice family; the *set* is fixed for the whole world.
                    if rng.random() >= alias_dominant_share:
                        name_obs = str(rng.choice(buyer_aliases[1:]))
                        logger.log(row["notice_id_synthetic"], "buyer_name_raw", name_true, name_obs,
                                   "PERSISTENT_BUYER_ALIAS", severity=m)
                elif buyer_aliases is None and rng.random() < min(0.98, scenario.buyer_names.false_split_rate * m * float(buyer["alias_propensity"] + 0.3)):
                    name_obs = _apply_name_transformation(name_true, row["department_true"], rng)
                    logger.log(row["notice_id_synthetic"], "buyer_name_raw", name_true, name_obs, "NAME_VARIANT", severity=m)
                if use_stable_scoped_name:
                    stable_scoped_name_by_buyer[row["buyer_id_true"]] = name_obs
            family_identity_cache[identity_cache_key] = (siret_obs, siren_obs, name_obs)

        if conditional_identifier_presence:
            # Conditional SIRET calibration is defined at the observable
            # schema/type cell level. Draw identifiers per notice so an AWARD
            # does not inherit a CALL-level visibility probability.
            if scoped_identity_by_need and is_scoped_notice and row["role"] == "CALL":
                cached = scoped_call_identifier_cache.get(identity_cache_key)
                if cached is None:
                    cached = _corrupt_identifier(
                        row, siblings_by_siren, m, scenario.identifiers, rng, logger,
                        observation_model=observation_model,
                        buyer_logit_offset=buyer_offset, intercept=identifier_intercept,
                    )
                    scoped_call_identifier_cache[identity_cache_key] = cached
                siret_obs, siren_obs = cached
            else:
                siret_obs, siren_obs = _corrupt_identifier(
                    row, siblings_by_siren, m, scenario.identifiers, rng, logger,
                    observation_model=observation_model,
                    buyer_logit_offset=buyer_offset, intercept=identifier_intercept,
                )
        observed_buyer_key = _observed_buyer_key(siret_obs, siren_obs, name_obs)
        family_key = str(row["cycle_id_true"])
        first_observed_buyer_key = family_buyer_key_cache.setdefault(family_key, observed_buyer_key)
        same_family_key_mismatch = (
            row["role"] == "AWARD"
            and first_observed_buyer_key is not None
            and observed_buyer_key != first_observed_buyer_key
        )

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
            same_family_key_mismatch=same_family_key_mismatch,
            observed_buyer_key=observed_buyer_key,
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
