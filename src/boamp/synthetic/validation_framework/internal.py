"""Internal validity checks for synthetic benchmark outputs."""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd

from boamp.synthetic import schemas
from boamp.synthetic.validation_framework.loaders import BenchmarkData
from boamp.synthetic.validation_framework.models import MetricResult, Status, classify_invariant


SCHEMAS = {
    "observed_notices": schemas.OBSERVED_NOTICES,
    "clean_notices": schemas.CLEAN_NOTICES,
    "true_relations": schemas.TRUE_RELATIONS,
    "notice_family_membership": schemas.NOTICE_FAMILY_MEMBERSHIP,
    "corruption_log": schemas.CORRUPTION_LOG,
    "latent_cycles": schemas.LATENT_CYCLES,
    "latent_needs": schemas.LATENT_NEEDS,
    "latent_buyers": schemas.LATENT_BUYERS,
    "latent_establishments": schemas.LATENT_ESTABLISHMENTS,
}

FRAME_ATTRS = {
    "observed_notices": "observed",
    "clean_notices": "clean",
    "true_relations": "true_relations",
    "notice_family_membership": "notice_family_membership",
    "corruption_log": "corruption_log",
    "latent_cycles": "latent_cycles",
    "latent_needs": "latent_needs",
    "latent_buyers": "latent_buyers",
    "latent_establishments": "latent_establishments",
}

CLEAN_FIELD_MAP = {
    "buyer_siret_raw": "siret_true",
    "buyer_siren_raw": "siren_true",
    "buyer_name_raw": "buyer_name_true",
    "code_departement": "department_true",
    "cpv_clean": "cpv_true",
    "declared_duration_months": "duration_true_months",
    "objet_clean": "objet_true",
    "linked_call_notice_id": "linked_call_notice_id_true",
}

# Parameter-recovery findings are reported under their own gate: a benchmark
# whose saved parameters do not reproduce its own data is a specification
# defect, which is a different failure from a broken invariant or a truth leak
# and deserves its own blocking reason.
SPEC_SCOPE = "specification_recovery"

INTERNAL_ID_COLUMNS = [
    "cycle_id_true",
    "need_id_true",
    "buyer_id_true",
    "establishment_id_true",
]

# Column names that would expose hidden entities or labels even if a developer
# dropped the "_true" suffix before writing the observed layer.
HIDDEN_OBSERVED_COLUMN_NAMES = {
    "cycle_id",
    "need_id",
    "buyer_id",
    "establishment_id",
    "contract_family_id",
    "family_id",
    "source_cycle_id",
    "target_cycle_id",
    "successor_cycle_id",
    "predecessor_cycle_id",
    "relation_type",
    "strict_label",
    "broad_label",
    "true_gap_months",
    "source_expected_end",
    "target_start",
    "corruption_type",
    "corruption_history",
    "quality_class",
    "scenario_label",
}
HIDDEN_OBSERVED_COLUMN_SIGNATURES = {
    re.sub(r"[^a-z0-9]+", "", name.lower()) for name in HIDDEN_OBSERVED_COLUMN_NAMES
}

HASH_ALGORITHMS = ("md5", "sha1", "sha256")


def checksum_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _base(
    data: BenchmarkData,
    prop: str,
    metric: str,
    ok: bool,
    notes: str = "",
    synthetic_estimate=None,
    scope: str = "internal",
) -> MetricResult:
    return MetricResult(
        benchmark_version=data.benchmark_version,
        scenario=data.scenario,
        seed=data.seed_label,
        scope=scope,
        subgroup="overall",
        property=prop,
        metric=metric,
        real_estimate=None,
        synthetic_estimate=bool(ok) if synthetic_estimate is None else synthetic_estimate,
        difference=0.0 if ok else 1.0,
        effect_size=None,
        ci_low=None,
        ci_high=None,
        tolerance="exact",
        status=classify_invariant(ok),
        provenance="synthetic_truth",
        notes=notes,
    )


def _is_missing(value) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _values_equal(a, b) -> bool:
    if _is_missing(a) and _is_missing(b):
        return True
    try:
        af = float(a)
        bf = float(b)
        if math.isfinite(af) and math.isfinite(bf):
            return bool(np.isclose(af, bf, rtol=1e-9, atol=1e-9))
    except (TypeError, ValueError):
        pass
    return str(a) == str(b)


def _detect_cycle(edges: dict[str, str]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visited:
            return False
        if node in visiting:
            return True
        visiting.add(node)
        nxt = edges.get(node)
        if nxt is not None and visit(nxt):
            return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in edges)


def _normalised_truth_token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _truth_id_value_signatures(values: set[str]) -> set[str]:
    """Return exact, normalised and hashed signatures of hidden truth IDs."""
    signatures: set[str] = set()
    for value in values:
        text = str(value)
        if not text:
            continue
        signatures.add(text)
        norm = _normalised_truth_token(text)
        if norm:
            signatures.add(norm)
        payload = text.encode("utf-8")
        for algorithm in HASH_ALGORITHMS:
            signatures.add(hashlib.new(algorithm, payload).hexdigest())
    return signatures


def _observed_text_signatures(series: pd.Series) -> pd.Series:
    values = series.dropna().astype(str)
    exact = values
    normalised = values.map(_normalised_truth_token)
    return pd.concat([exact, normalised], ignore_index=True)


def validate_schema_support(data: BenchmarkData) -> list[MetricResult]:
    metrics = []
    for table, required in SCHEMAS.items():
        frame = getattr(data, FRAME_ATTRS[table])
        missing = [c for c in required if c not in frame.columns]
        metrics.append(_base(data, f"{table}_schema", "required_columns_present", not missing, f"missing={missing}"))
    return metrics


def validate_truth_graph(data: BenchmarkData) -> list[MetricResult]:
    cycles = data.latent_cycles.copy()
    rel = data.true_relations.copy()
    cycle_ids = set(cycles["cycle_id_true"])
    next_rel = rel.loc[rel["relation_type"].eq("NEXT_CYCLE")].copy()
    no_successor = rel.loc[rel["relation_type"].eq("NO_SUCCESSOR")].copy()
    outgoing = rel.groupby("source_cycle_id").size()

    source_known = rel["source_cycle_id"].isin(cycle_ids).all()
    target_known = next_rel["target_cycle_id"].isin(cycle_ids).all()
    exactly_one = len(outgoing) == len(cycles) and bool((outgoing == 1).all())
    target_unique = not next_rel["target_cycle_id"].duplicated().any()
    no_target = no_successor["target_cycle_id"].isna().all()

    merged = next_rel.merge(
        cycles[["cycle_id_true", "start_date_true"]].rename(
            columns={"cycle_id_true": "source_cycle_id", "start_date_true": "source_start"}
        ),
        on="source_cycle_id",
        how="left",
    ).merge(
        cycles[["cycle_id_true", "start_date_true"]].rename(
            columns={"cycle_id_true": "target_cycle_id", "start_date_true": "target_start_check"}
        ),
        on="target_cycle_id",
        how="left",
    )
    temporal_ok = bool((pd.to_datetime(merged["target_start_check"]) > pd.to_datetime(merged["source_start"])).all())
    edges = {
        str(r.source_cycle_id): str(r.target_cycle_id)
        for r in next_rel.itertuples()
        if pd.notna(r.target_cycle_id)
    }
    acyclic = not _detect_cycle(edges)

    return [
        _base(data, "truth_graph", "source_cycles_exist", source_known),
        _base(data, "truth_graph", "target_cycles_exist", target_known),
        _base(data, "truth_graph", "exactly_one_outgoing_relation", exactly_one),
        _base(data, "truth_graph", "next_cycle_target_unique", target_unique),
        _base(data, "truth_graph", "no_successor_target_null", no_target),
        _base(data, "truth_graph", "successor_after_source", temporal_ok),
        _base(data, "truth_graph", "acyclic_next_cycle_graph", acyclic),
    ]


def validate_count_reconciliation(data: BenchmarkData) -> list[MetricResult]:
    observed_ids = set(data.observed["notice_id_synthetic"])
    clean_ids = set(data.clean["notice_id_synthetic"])
    membership_ids = set(data.notice_family_membership["notice_id_synthetic"])
    cycle_ids = set(data.latent_cycles["cycle_id_true"])
    clean_role = data.clean.set_index("notice_id_synthetic")["role"]
    mem_role = data.notice_family_membership.set_index("notice_id_synthetic")["role"]

    same_notice_ids = observed_ids == clean_ids == membership_ids
    membership_cycles_known = data.notice_family_membership["cycle_id_true"].isin(cycle_ids).all()
    role_ok = clean_role.sort_index().equals(mem_role.sort_index())
    relation_count_ok = len(data.true_relations) == len(data.latent_cycles)

    return [
        _base(data, "count_reconciliation", "observed_clean_membership_notice_ids_match", same_notice_ids),
        _base(data, "count_reconciliation", "membership_cycles_exist", membership_cycles_known),
        _base(data, "count_reconciliation", "membership_roles_match_clean_notices", role_ok),
        _base(data, "count_reconciliation", "one_relation_row_per_cycle", relation_count_ok),
    ]


def validate_leakage(data: BenchmarkData) -> list[MetricResult]:
    observed = data.observed
    leaked_columns = [c for c in observed.columns if c.endswith("_true") or c in INTERNAL_ID_COLUMNS]
    hidden_alias_columns = [
        c for c in observed.columns if _normalised_truth_token(c) in HIDDEN_OBSERVED_COLUMN_SIGNATURES
    ]
    truth_values: set[str] = set()
    for col in INTERNAL_ID_COLUMNS:
        if col in data.clean.columns:
            truth_values.update(data.clean[col].dropna().astype(str))
        truth_table = col.replace("_id_true", "_id")
        if truth_table in data.true_relations.columns:
            truth_values.update(data.true_relations[truth_table].dropna().astype(str))
    truth_signatures = _truth_id_value_signatures(truth_values)
    value_hits = 0
    for col in observed.select_dtypes(include=["object", "string"]).columns:
        value_hits += int(_observed_text_signatures(observed[col]).isin(truth_signatures).sum())
    index_leaks = any((name or "").endswith("_true") for name in observed.index.names)
    return [
        _base(data, "leakage", "no_truth_columns_in_observed", not leaked_columns, f"leaked_columns={leaked_columns}"),
        _base(
            data,
            "leakage",
            "no_hidden_truth_alias_columns_in_observed",
            not hidden_alias_columns,
            f"hidden_alias_columns={hidden_alias_columns}",
        ),
        _base(data, "leakage", "no_internal_truth_id_values_in_observed", value_hits == 0, f"value_hits={value_hits}", value_hits),
        _base(data, "leakage", "observed_index_has_no_truth_name", not index_leaks),
    ]


def validate_corruption_replay(data: BenchmarkData) -> list[MetricResult]:
    if data.corruption_log.empty:
        return [_base(data, "corruption_replay", "logged_changes_match_tables", True, "empty corruption log")]

    clean = data.clean.set_index("notice_id_synthetic")
    observed = data.observed.set_index("notice_id_synthetic")
    failures = []
    for (notice_id, field), group in data.corruption_log.groupby(["notice_id_synthetic", "field"], sort=False):
        clean_field = CLEAN_FIELD_MAP.get(field)
        if clean_field is None or field not in observed.columns or notice_id not in clean.index or notice_id not in observed.index:
            failures.append((notice_id, field, "unmapped_or_missing"))
            continue
        rows = list(group.itertuples(index=False))
        if not _values_equal(rows[0].clean_value, clean.loc[notice_id, clean_field]):
            failures.append((notice_id, field, "clean_value"))
            continue
        chain_ok = True
        for previous, current in zip(rows, rows[1:]):
            if not _values_equal(previous.observed_value, current.clean_value):
                chain_ok = False
                break
        if not chain_ok:
            failures.append((notice_id, field, "corruption_chain"))
            continue
        if not _values_equal(rows[-1].observed_value, observed.loc[notice_id, field]):
            failures.append((notice_id, field, "observed_value"))
    notes = "; ".join(f"{nid}:{field}:{kind}" for nid, field, kind in failures[:5])
    return [
        _base(
            data,
            "corruption_replay",
            "logged_changes_match_tables",
            len(failures) == 0,
            f"failures={len(failures)} {notes}".strip(),
            len(failures),
        )
    ]


def _observation_window_end(data: BenchmarkData) -> pd.Timestamp:
    """End of the generator's observation window, from config where available."""
    try:
        from boamp.synthetic.scenarios import load_benchmark_defaults

        defaults = load_benchmark_defaults(data.project_root)
        return pd.to_datetime(defaults.observation_window.end_date)
    except (FileNotFoundError, AttributeError, ValueError):
        return pd.to_datetime(data.latent_cycles["start_date_true"]).max()


def validate_parameter_recovery(data: BenchmarkData) -> list[MetricResult]:
    """Do realized outputs match the distributions the scenario declared?

    Only parameters whose realized counterpart is unambiguously derivable from
    the saved tables are checked. Each is compared against a Monte Carlo
    interval simulated from the declared mechanism itself, so the test asks
    "is this a plausible draw from what was declared?" rather than "is the
    point estimate close?", which would either pass everything or fail
    everything depending on sample size.
    """
    from types import SimpleNamespace

    from boamp.synthetic.scenarios import load_scenario

    def _to_namespace(value):
        return SimpleNamespace(**value) if isinstance(value, dict) else None

    def _plain(value):
        if hasattr(value, "__dict__"):
            return {k: _plain(v) for k, v in vars(value).items()}
        if isinstance(value, dict):
            return {k: _plain(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_plain(v) for v in value]
        return value

    def _same_value(left, right) -> bool:
        if isinstance(left, float) or isinstance(right, float):
            try:
                return bool(np.isclose(float(left), float(right), rtol=1e-12, atol=1e-12))
            except (TypeError, ValueError):
                return False
        return _plain(left) == _plain(right)

    metrics: list[MetricResult] = []
    try:
        # Read the scenario from the configuration family the artifact was
        # generated under. Loading the flat file for a family-versioned artifact
        # compares the realized world against a *different* scenario, which
        # reports a specification defect that does not exist.
        scenario = load_scenario(
            data.project_root, data.scenario, family=data.metadata.get("config_family")
        )
    except (FileNotFoundError, KeyError, AttributeError) as exc:
        return [_base(data, "parameter_recovery", "scenario_loadable", False, f"error={exc}", scope=SPEC_SCOPE)]

    recurrence = getattr(scenario, "recurrence", None)
    if recurrence is None:
        return [_base(data, "parameter_recovery", "scenario_declares_recurrence", False, scope=SPEC_SCOPE)]

    # Hard invariant: no need may exceed its declared cycle cap.
    max_declared = int(getattr(recurrence, "max_cycles_per_need", 0) or 0)
    if max_declared:
        observed_max = int(data.latent_cycles["cycle_number"].max())
        metrics.append(
            _base(
                data, "parameter_recovery", "max_cycles_per_need_respected",
                observed_max <= max_declared,
                f"declared={max_declared}; observed_max={observed_max}",
                observed_max, scope=SPEC_SCOPE,
            )
        )

    # Cycle chains must be contiguous 1..k within a need.
    chains = data.latent_cycles.groupby("need_id_true")["cycle_number"]
    contiguous = bool(
        (chains.min() == 1).all()
        and (chains.max() == chains.size()).all()
        and (chains.nunique() == chains.size()).all()
    )
    metrics.append(_base(data, "parameter_recovery", "cycle_numbers_contiguous_per_need", contiguous, scope=SPEC_SCOPE))

    # Older v0.3 artifacts carried the selected scoped-candidate parameters as
    # an in-memory metadata override. Current released scenarios are expected to
    # carry the same values directly in YAML; metadata may retain them as
    # provenance, but a mismatch is a reproducibility defect.
    scoped = getattr(recurrence, "scoped_candidate_environment", None)
    override = (data.metadata.get("candidate_revision") or {}).get("parameters") or {}
    scoped_enabled = bool(getattr(scoped, "enabled", False))
    near_share = float(getattr(scoped, "near_window_share", 0.0)) if scoped_enabled else 0.0
    near_dist = getattr(scoped, "near_window_distribution", None) if scoped_enabled else None
    override_mismatches = []
    if override:
        for key, value in override.items():
            scenario_value = getattr(scoped, key, None) if scoped is not None else None
            if not _same_value(scenario_value, value):
                override_mismatches.append(key)
        near_share = float(override.get("near_window_share", near_share))
        near_dist = _to_namespace(override.get("near_window_distribution")) or near_dist
        scoped_enabled = True
    scenario_describes_data = not override_mismatches
    metrics.append(
        _base(
            data, "parameter_recovery", "scenario_file_describes_generated_data", scenario_describes_data,
            scope=SPEC_SCOPE,
            notes=(
                "candidate_revision metadata disagrees with the scenario YAML for "
                f"{sorted(override_mismatches)}; recovery below uses metadata as the effective "
                "parameters, but the release scenario is not replayable from YAML alone"
            )
            if override_mismatches
            else (
                "candidate_revision metadata matches the scenario YAML and is retained only as "
                "selection provenance"
                if override
                else "no in-memory parameter override recorded for this run"
            ),
        )
    )

    gap_dist = getattr(recurrence, "cycle_gap_distribution", None)
    gaps = pd.to_numeric(
        data.true_relations.loc[data.true_relations["relation_type"].eq("NEXT_CYCLE"), "true_gap_months"],
        errors="coerce",
    ).dropna()
    if gap_dist is not None and len(gaps) >= 30:
        # With the scoped block active, gaps are a mixture and the attainable
        # minimum is the smaller of the two components' minima.
        min_months = float(getattr(gap_dist, "min_months", 0.0))
        if near_share > 0 and near_dist is not None:
            min_months = min(min_months, float(getattr(near_dist, "min_months", min_months)))
        # Gaps are stored as a difference between two calendar dates, so the
        # drawn float is re-derived at day resolution; allow one day of slack
        # rather than flagging sub-day rounding as a violated bound.
        day_in_months = 1.0 / 30.44
        metrics.append(
            _base(
                data, "parameter_recovery", "true_gaps_respect_declared_minimum",
                bool((gaps >= min_months - day_in_months).all()),
                f"effective_min_months={min_months}; observed_min={float(gaps.min()):.3f} "
                "(one day of date-rounding slack allowed)",
                float(gaps.min()),
                scope=SPEC_SCOPE,
            )
        )

        # The near-window component applies only to needs whose CPV falls in
        # the scoped divisions, so the mixture weight is per-relation rather
        # than global. Simulating it any other way would compare the data
        # against a mechanism that was never used.
        scoped_divisions = {
            str(d) for d in (override.get("cpv_divisions") or getattr(scoped, "cpv_divisions", []) or [])
        }
        need_cpv = data.latent_needs.set_index("need_id_true")["cpv_true"].astype(str)
        relation_needs = (
            data.true_relations.loc[data.true_relations["relation_type"].eq("NEXT_CYCLE"), "source_cycle_id"]
            .map(data.latent_cycles.set_index("cycle_id_true")["need_id_true"])
        )
        # `gaps` dropped any relation with a non-numeric gap, so every
        # per-relation covariate below is realigned on `gaps.index` rather than
        # by position. Tiling or truncating to length would pair a gap with
        # another relation's scope flag and window, which corrupts the null
        # silently instead of raising.
        is_scoped_series = (
            relation_needs.map(need_cpv).fillna("").str[:2].isin(scoped_divisions)
            if scoped_divisions
            else pd.Series(False, index=relation_needs.index)
        )
        is_scoped = is_scoped_series.reindex(gaps.index).fillna(False).to_numpy(dtype=bool)

        # A successor cycle only exists if its start still falls inside the
        # observation window, so the gaps that survive into the truth table are
        # right-censored by the time each source cycle has left. Simulating the
        # unconditional draw would compare the data against a mechanism whose
        # long tail was never observable, and would fail every time.
        #
        # The generator measures that remaining time from the source cycle's
        # *expected end*, not its start: cycles.py stops a chain when
        # `expected_end + gap > observation_end`. Anchoring the null on
        # `start_date_true` instead would overstate the headroom by one cycle
        # duration (~13 months here), under-truncate the simulated draws, and
        # bias the interval upward against correctly generated data.
        window_end = _observation_window_end(data)
        source_expected_end = pd.to_datetime(
            data.true_relations.loc[
                data.true_relations["relation_type"].eq("NEXT_CYCLE"), "source_expected_end"
            ],
            errors="coerce",
        ).reindex(gaps.index)
        headroom = ((window_end - source_expected_end).dt.days / 30.44).to_numpy(dtype=float)
        headroom = np.where(np.isfinite(headroom), headroom, np.inf)

        rng = np.random.default_rng(20260723)
        n = len(gaps)
        base_min = float(getattr(gap_dist, "min_months", 0.0))
        sim_means = np.empty(400, dtype=float)
        for i in range(400):
            draws = np.full(n, np.nan)
            pending = np.ones(n, dtype=bool)
            for _attempt in range(40):  # rejection sampling against the window
                k = int(pending.sum())
                if not k:
                    break
                proposal = np.maximum(
                    rng.normal(float(gap_dist.mean_months), float(gap_dist.sd_months), size=k), base_min
                )
                if near_dist is not None and near_share > 0 and is_scoped.any():
                    near = np.clip(
                        rng.normal(float(near_dist.mean_months), float(near_dist.sd_months), size=k),
                        float(getattr(near_dist, "min_months", 0.0)),
                        float(getattr(near_dist, "max_months", np.inf)),
                    )
                    use_near = is_scoped[pending] & (rng.random(k) < near_share)
                    proposal = np.where(use_near, near, proposal)
                accepted = proposal <= headroom[pending]
                idx = np.flatnonzero(pending)[accepted]
                draws[idx] = proposal[accepted]
                pending[idx] = False
            # Sources with almost no headroom left may never accept; clip them.
            if pending.any():
                draws[pending] = np.minimum(headroom[pending], float(gap_dist.mean_months))
            sim_means[i] = np.nanmean(draws)
        lo, hi = np.percentile(sim_means, [0.5, 99.5])
        observed_mean = float(gaps.mean())
        inside = bool(lo <= observed_mean <= hi)
        metrics.append(
            MetricResult(
                benchmark_version=data.benchmark_version,
                scenario=data.scenario,
                seed=data.seed_label,
                scope=SPEC_SCOPE,
                subgroup="overall",
                property="parameter_recovery",
                metric="mean_true_gap_months_in_monte_carlo_interval",
                real_estimate=None,
                synthetic_estimate=observed_mean,
                difference=observed_mean - float(np.mean(sim_means)),
                effect_size=None,
                ci_low=float(lo),
                ci_high=float(hi),
                tolerance="99% Monte Carlo interval under the declared mechanism",
                status=classify_invariant(inside),
                provenance="synthetic_truth",
                notes=(
                    f"n_gaps={n}; effective mechanism = normal(mean={gap_dist.mean_months}, "
                    f"sd={gap_dist.sd_months}) truncated at {getattr(gap_dist, 'min_months', 0.0)}"
                    + (
                        f", mixed at share {near_share} with the near-window component"
                        if near_share
                        else ""
                    )
                    + ", right-censored at each source cycle's remaining window "
                    "(observation_end - source_expected_end), which is the same rule cycles.py "
                    "applies when it stops a chain. Same-buyer hard-negative chain alignment shifts "
                    "whole chains by a constant offset and so leaves within-need gaps unchanged; it "
                    "is deliberately not a reason to soften this metric. A miss means the recorded "
                    "parameters do not fully describe how the gaps were actually drawn -- a "
                    "specification defect rather than a bad draw"
                ),
            )
        )

    # Parameters that cannot be recovered from saved outputs alone are recorded
    # rather than silently skipped.
    metrics.append(
        _base(
            data, "parameter_recovery", "unrecoverable_parameters_declared", True,
            scope=SPEC_SCOPE,
            notes=(
                "base_recurrence_propensity and quality_class_mix are not identifiable from the saved "
                "tables alone: both are filtered by the observation-window truncation applied during "
                "generation, so recovering them requires instrumenting a generator run, not reading "
                "its output"
            ),
        )
    )
    return metrics


def _scenario_snapshot_mismatches(data: BenchmarkData) -> tuple[list[str], str]:
    """Compare the recorded scenario snapshot against the live scenario file.

    Recording the resolved scenario in run metadata only helps if something
    checks it: without this, a later edit to the YAML leaves the released
    artifacts describing a configuration that no longer exists, and the only
    symptom is an unexplained replay hash mismatch.
    """
    from boamp.synthetic.scenarios import load_scenario, to_plain_dict

    snapshot = data.metadata.get("resolved_scenario")
    if not snapshot:
        return [], "run metadata carries no resolved_scenario snapshot to compare"
    try:
        live = to_plain_dict(
            load_scenario(
                data.project_root, data.scenario, family=data.metadata.get("config_family")
            )
        )
    except (FileNotFoundError, ValueError) as exc:
        return ["<scenario file unreadable>"], f"{type(exc).__name__}: {exc}"

    mismatches: list[str] = []

    def walk(recorded, current, path: str) -> None:
        if isinstance(recorded, dict) and isinstance(current, dict):
            # Compare on string keys. The snapshot is round-tripped through JSON,
            # which turns integer mapping keys into strings, while the live
            # scenario keeps them as integers -- v0.4's by-year entry weights and
            # alias-set-size weights are both keyed that way. Without this the
            # union of the two key sets is a mix of str and int and cannot be
            # sorted, and every such table would otherwise report as a mismatch.
            recorded_by_key = {str(k): v for k, v in recorded.items()}
            current_by_key = {str(k): v for k, v in current.items()}
            for key in sorted(set(recorded_by_key) | set(current_by_key)):
                walk(
                    recorded_by_key.get(key),
                    current_by_key.get(key),
                    f"{path}.{key}" if path else key,
                )
            return
        if isinstance(recorded, float) or isinstance(current, float):
            try:
                if np.isclose(float(recorded), float(current), rtol=1e-12, atol=1e-12):
                    return
            except (TypeError, ValueError):
                pass
        if recorded != current:
            mismatches.append(path)

    walk(snapshot, live, "")
    return mismatches, (
        f"scenario file differs from the recorded snapshot at {mismatches[:8]}"
        if mismatches
        else "recorded scenario snapshot matches the live scenario file"
    )


def validate_reproducibility_manifest(data: BenchmarkData, replay: bool = False) -> list[MetricResult]:
    """Is enough recorded to regenerate this benchmark exactly?"""
    metadata = data.metadata
    required = ["generator_version", "world_seed", "corruption_seed", "config_hashes", "git_commit"]
    missing = [k for k in required if metadata.get(k) in (None, "", {})]
    metrics = [
        _base(
            data, "reproducibility", "manifest_records_seeds_and_code_version", not missing,
            f"missing={missing}",
        )
    ]

    snapshot_mismatches, snapshot_note = _scenario_snapshot_mismatches(data)
    metrics.append(
        _base(
            data, "reproducibility", "scenario_snapshot_matches_scenario_file",
            not snapshot_mismatches, snapshot_note,
        )
    )

    logged_seeds = set()
    if "seed" in data.corruption_log.columns and not data.corruption_log.empty:
        logged_seeds = set(pd.to_numeric(data.corruption_log["seed"], errors="coerce").dropna().astype(int))
    declared_seed = metadata.get("corruption_seed")
    seed_ok = (not logged_seeds) or (declared_seed is not None and logged_seeds == {int(declared_seed)})
    metrics.append(
        _base(
            data, "reproducibility", "corruption_log_seed_matches_manifest", seed_ok,
            f"declared={declared_seed}; logged={sorted(logged_seeds)[:5]}",
        )
    )

    # Regeneration is the only check that can prove the released tables still
    # follow from the released configuration and seeds. It is compared on
    # canonical table content rather than Parquet bytes, because writer and
    # library versions change file bytes without changing the data.
    replayed, replay_note = _canonical_replay_result(data) if replay else (None, "")
    if replayed is None:
        metrics.append(
            MetricResult(
                benchmark_version=data.benchmark_version,
                scenario=data.scenario,
                seed=data.seed_label,
                scope="internal",
                subgroup="overall",
                property="reproducibility",
                metric="canonical_replay_matches_released_tables",
                real_estimate=None,
                synthetic_estimate=None,
                difference=None,
                effect_size=None,
                ci_low=None,
                ci_high=None,
                tolerance="exact canonical table content",
                status=Status.INCONCLUSIVE,
                provenance="synthetic_truth",
                notes=(
                    replay_note
                    or "replay disabled for this pass; re-run with replay enabled to verify that the "
                    "recorded seeds and configuration still regenerate the released tables"
                ),
            )
        )
        return metrics

    metrics.append(
        _base(
            data, "reproducibility", "canonical_replay_matches_released_tables",
            replayed, replay_note, scope="internal",
        )
    )
    return metrics


def _canonical_replay_result(data: BenchmarkData) -> tuple[bool | None, str]:
    """Regenerate from recorded seeds and compare canonical table content."""
    from boamp.synthetic.reproducibility import (
        compare_table_sets,
        regenerate_tables_from_metadata,
    )

    released = {
        "latent_buyers": data.latent_buyers,
        "latent_establishments": data.latent_establishments,
        "latent_needs": data.latent_needs,
        "latent_cycles": data.latent_cycles,
        "true_relations": data.true_relations,
        "notice_family_membership": data.notice_family_membership,
        "clean_notices": data.clean,
        "observed_notices": data.observed,
        "corruption_log": data.corruption_log,
    }
    try:
        regenerated = regenerate_tables_from_metadata(data.project_root, data.metadata, data.scenario)
    except Exception as exc:  # noqa: BLE001 - a failed replay is a reportable outcome, not a crash
        return False, f"regeneration failed: {type(exc).__name__}: {exc}"
    comparisons = compare_table_sets(released, regenerated)
    failed = [c.table for c in comparisons if not c.passed]
    return (
        not failed,
        f"{len(comparisons) - len(failed)}/{len(comparisons)} tables reproduced from the recorded "
        f"seeds and the live scenario file" + (f"; differing: {failed}" if failed else ""),
    )


def run_negative_controls(data: BenchmarkData) -> list[MetricResult]:
    """Deliberately break the data and confirm the suite notices (Section 6.9).

    Without this, a suite that silently stopped checking anything would report
    a clean pass forever. Each control mutates a copy of the loaded tables and
    asserts that the corresponding check flips to FAIL.
    """
    from dataclasses import replace

    def leak_truth_column():
        observed = data.observed.copy()
        observed["cycle_id_true"] = data.clean["cycle_id_true"].to_numpy()
        return validate_leakage(replace(data, observed=observed))

    def self_referential_relation():
        rel = data.true_relations.copy()
        idx = rel.index[rel["relation_type"].eq("NEXT_CYCLE")]
        if not len(idx):
            return []
        rel.loc[idx[0], "target_cycle_id"] = rel.loc[idx[0], "source_cycle_id"]
        return validate_truth_graph(replace(data, true_relations=rel))

    def broken_replay():
        if data.corruption_log.empty:
            return []
        first = data.corruption_log.iloc[0]
        observed = data.observed.copy()
        observed.loc[
            observed["notice_id_synthetic"].eq(first["notice_id_synthetic"]), first["field"]
        ] = "__NEGATIVE_CONTROL__"
        return validate_corruption_replay(replace(data, observed=observed))

    def dropped_column():
        observed = data.observed.drop(columns=["cpv_clean"])
        return validate_schema_support(replace(data, observed=observed))

    def scrambled_membership():
        membership = data.notice_family_membership.copy()
        membership["role"] = membership["role"].to_numpy()[::-1]
        return validate_count_reconciliation(replace(data, notice_family_membership=membership))

    def shifted_true_gaps():
        """Gaps that no longer match the declared distribution must still FAIL.

        This control exists because the gap recovery metric was once softened to
        a warning whenever hard-negative chain alignment was enabled, which made
        it unfalsifiable for every scenario that uses the scoped block. Chain
        alignment translates whole chains by a constant offset and therefore
        cannot move a within-need gap, so it is not an excuse for a miss: with
        the scoped block active, an injected shift must still be detected.
        """
        rel = data.true_relations.copy()
        mask = rel["relation_type"].eq("NEXT_CYCLE")
        if int(mask.sum()) < 30:
            return []
        rel.loc[mask, "true_gap_months"] = (
            pd.to_numeric(rel.loc[mask, "true_gap_months"], errors="coerce") + 6.0
        )
        return validate_parameter_recovery(replace(data, true_relations=rel))

    controls = [
        ("leaked_truth_column", leak_truth_column),
        ("self_referential_relation", self_referential_relation),
        ("broken_corruption_replay", broken_replay),
        ("dropped_required_column", dropped_column),
        ("scrambled_membership_roles", scrambled_membership),
        ("shifted_true_gaps", shifted_true_gaps),
    ]

    metrics = []
    for name, control in controls:
        try:
            produced = control()
            detected = any(str(m.status) == str(Status.FAIL) for m in produced)
            note = "" if produced else "control not applicable to this dataset"
        except Exception as exc:  # noqa: BLE001 - a raising check still counts as detection
            detected, note = True, f"check raised {type(exc).__name__}: {exc}"
        metrics.append(
            _base(
                data, "negative_control", name, detected,
                note or "injected defect was detected by the corresponding check",
            )
        )
    return metrics


def run_internal_validation(data: BenchmarkData, replay: bool = False) -> list[MetricResult]:
    metrics: list[MetricResult] = []
    metrics.extend(validate_schema_support(data))
    metrics.extend(validate_truth_graph(data))
    metrics.extend(validate_count_reconciliation(data))
    metrics.extend(validate_leakage(data))
    metrics.extend(validate_corruption_replay(data))
    metrics.extend(validate_parameter_recovery(data))
    metrics.extend(validate_reproducibility_manifest(data, replay=replay))
    metrics.extend(run_negative_controls(data))
    return metrics
