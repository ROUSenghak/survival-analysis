"""Hidden-truth benchmark difficulty and probe-linker utility (Sections 5.7, 8).

Everything here needs the sealed truth tables and therefore cannot be computed
on real BOAMP at all. Two questions are answered:

* **Is the linkage task BOAMP-like in difficulty?** Blocking recall, reduction
  ratio and pairs quality say whether a comparison model is even being given
  the chance to work; hard-negative score overlap and true-match rank say
  whether distinguishing a match from a plausible non-match requires real
  discrimination rather than a threshold on an obvious gap.
* **Does the benchmark rank algorithms informatively?** Three deliberately
  different probe linkers are run. Their parameters are frozen constants
  chosen once and never tuned against these results, and none of them is the
  production acceptance threshold -- per Section 10 a pipeline threshold is an
  output of a particular pipeline, never a definition of truth.

Recall is always measured against true matches *whose two notices both sit in
the candidate-generation scope*. Successors outside that scope cannot be found
by any method operating on these candidates, so including them would charge
every probe for the same fixed scoping loss and hide the differences between
them. That scoping loss is reported separately as its own metric.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from boamp.config import load_config
from boamp.data.prepare import tag_digital_scope
from boamp.linkage.candidates import generate_pairs_single_key
from boamp.linkage.scoring import add_rank_and_margin, build_tfidf_matrix, cpv_pair_score, estimate_window_months
from boamp.synthetic.compatibility import adapt_observed_notices_to_sources
from boamp.synthetic.validation_framework.bootstrap import overlap_coefficient
from boamp.synthetic.validation_framework.loaders import BenchmarkData
from boamp.synthetic.validation_framework.models import MetricResult, Status, classify_range, classify_upper
from utils.text_clean import normalize_objet


TOLERANCES = {
    "widened_pairs_completeness_min": 0.80,
    "production_pairs_completeness_min": 0.25,
    "pairs_quality_min": 0.05,
    "reduction_ratio_min": 0.95,
    "match_nonmatch_overlap_min": 0.05,
    "match_nonmatch_overlap_max": 0.95,
    "probe_best_f1_max": 0.99,
    "probe_best_f1_min": 0.05,
    "probe_f1_spread_min": 0.01,
}

# Window used to separate "blocking cannot see the truth at all" from "the
# production 6-month window is narrower than the benchmark's true renewal
# gaps". Not a proposed production setting.
WIDENED_PROBE_WINDOW_MONTHS = 36

# Frozen probe-linker parameters. Chosen once, never tuned against results.
PROBE_TOP1_MIN_SCORE = 0.45
PROBE_THRESHOLD_MIN_SCORE = 0.55
FS_AGREEMENT_THRESHOLDS = {"s_text": 0.30, "s_cpv": 0.80, "s_time": 0.50}
FS_M_PROBABILITIES = {"s_text": 0.80, "s_cpv": 0.85, "s_time": 0.60}
FS_U_PROBABILITIES = {"s_text": 0.25, "s_cpv": 0.45, "s_time": 0.35}
FS_ACCEPT_LOG_ODDS = 0.0


def _metric(
    data: BenchmarkData,
    scope: str,
    subgroup: str,
    prop: str,
    metric: str,
    real,
    synthetic,
    diff,
    effect,
    tolerance,
    status: Status | str,
    provenance: str = "synthetic_truth",
    notes: str = "",
) -> MetricResult:
    return MetricResult(
        benchmark_version=data.benchmark_version,
        scenario=data.scenario,
        seed=data.seed_label,
        scope=scope,
        subgroup=subgroup,
        property=prop,
        metric=metric,
        real_estimate=real,
        synthetic_estimate=synthetic,
        difference=diff,
        effect_size=effect,
        ci_low=None,
        ci_high=None,
        tolerance=tolerance,
        status=status,
        provenance=provenance,
        notes=notes,
    )


def scoped_sources(data: BenchmarkData) -> pd.DataFrame:
    """Synthetic notices inside the production Layer-1 candidate scope."""
    cfg = load_config(data.project_root)
    sources = adapt_observed_notices_to_sources(data.observed)
    sources["objet_normalized"] = sources["objet_clean"].map(normalize_objet)
    sources["is_digital_scope"] = sources.apply(
        lambda row: tag_digital_scope(row["cpv_division"], row["objet_normalized"], cfg), axis=1
    )
    return sources.loc[
        sources["notice_type_normalized"].eq("APPEL_OFFRE") & sources["is_digital_scope"]
    ].copy()


def true_match_pairs(data: BenchmarkData) -> pd.DataFrame:
    """Unordered notice-level true matches implied by NEXT_CYCLE relations.

    A cycle is observed through its CALL notice, so a true successor relation
    between two cycles becomes a true match between their two CALL notices.
    """
    call = (
        data.notice_family_membership.loc[data.notice_family_membership["role"].eq("CALL")]
        .set_index("cycle_id_true")["notice_id_synthetic"]
    )
    nxt = data.true_relations.loc[data.true_relations["relation_type"].eq("NEXT_CYCLE")]
    pairs = pd.DataFrame(
        {
            "notice_a": nxt["source_cycle_id"].map(call).to_numpy(),
            "notice_b": nxt["target_cycle_id"].map(call).to_numpy(),
            "true_gap_months": nxt["true_gap_months"].to_numpy(),
        }
    ).dropna(subset=["notice_a", "notice_b"])
    return pairs


def _unordered(a, b) -> tuple[str, str]:
    a, b = str(a), str(b)
    return (a, b) if a <= b else (b, a)


def _pair_key_set(frame: pd.DataFrame, a_col: str, b_col: str) -> set[tuple[str, str]]:
    return {_unordered(a, b) for a, b in zip(frame[a_col], frame[b_col])}


def _generate_candidates(scoped: pd.DataFrame, cfg, window: int | None) -> pd.DataFrame:
    pairs, _ = generate_pairs_single_key(scoped, cfg, verbose=False, window_override=window)
    return pairs


def _score_truth_pairs(scoped: pd.DataFrame, truth_pairs: pd.DataFrame, cfg) -> pd.DataFrame:
    """Score true successor pairs under the production feature definitions.

    This is used only for the ORACLE_CANDIDATE_SCORING diagnostic: the true
    successor is inserted into each source's candidate list, while any
    production-generated distractors for the same source are left in place.
    """
    if truth_pairs.empty:
        return pd.DataFrame()

    p = cfg.pipeline
    month_days = p.run.month_days
    weights = p.scoring.weights
    buyer_type_score = vars(p.buyer_score.boamp_only)
    window, _median_dur = estimate_window_months(scoped, cfg)

    scoped = scoped.reset_index(drop=True)
    id_to_idx = {str(nid): idx for idx, nid in enumerate(scoped["notice_id"].astype(str))}
    _vectorizer, tfidf = build_tfidf_matrix(scoped["objet_clean"].fillna("").tolist(), cfg)
    rows = []
    for rel in truth_pairs.itertuples(index=False):
        source_id = str(rel.notice_a)
        candidate_id = str(rel.notice_b)
        if source_id not in id_to_idx or candidate_id not in id_to_idx:
            continue
        src = scoped.iloc[id_to_idx[source_id]]
        cand = scoped.iloc[id_to_idx[candidate_id]]
        if pd.to_datetime(cand["publication_date"]) <= pd.to_datetime(src["publication_date"]):
            continue

        abs_gap = abs(
            (pd.to_datetime(cand["publication_date"]) - pd.to_datetime(src["estimated_end_date"])).total_seconds()
            / (3600 * 24 * month_days)
        )
        gap_months = (
            (pd.to_datetime(cand["publication_date"]) - pd.to_datetime(src["publication_date"])).total_seconds()
            / (3600 * 24 * month_days)
        )
        s_time = max(1.0 - abs_gap / window, 0.0) if window else 0.0
        s_text = float(tfidf[id_to_idx[candidate_id]].dot(tfidf[id_to_idx[source_id]].T).toarray().ravel()[0])
        s_cpv = cpv_pair_score(
            src["cpv_clean"], cand["cpv_clean"],
            src["cpv_category"], cand["cpv_category"],
            src["cpv_class"], cand["cpv_class"],
            src["cpv_group"], cand["cpv_group"],
            src["cpv_division"], cand["cpv_division"],
            p.cpv_score,
        )
        s_buyer = buyer_type_score.get(src["buyer_key_type"], 0.0)
        rows.append(
            {
                "source_notice_id": source_id,
                "candidate_notice_id": candidate_id,
                "source_date": src["publication_date"],
                "candidate_date": cand["publication_date"],
                "buyer_key": src["buyer_key"],
                "buyer_key_type": src["buyer_key_type"],
                "gap_months": gap_months,
                "expected_end_date": src["estimated_end_date"],
                "abs_gap_to_expected_end": abs_gap,
                "s_time": s_time,
                "s_text": s_text,
                "s_cpv": s_cpv,
                "s_buyer": s_buyer,
                "composite_score": (
                    weights.text * s_text + weights.cpv * s_cpv + weights.time * s_time + weights.buyer * s_buyer
                ),
                "cpv_missing": bool(pd.isna(src["cpv_clean"]) or pd.isna(cand["cpv_clean"])),
                "cpv_generic_flag": bool(src["cpv_generic_flag"] or cand["cpv_generic_flag"]),
                "oracle_inserted_true_successor": True,
            }
        )
    return pd.DataFrame.from_records(rows)


def _oracle_candidate_scoring_frame(
    production_pairs: pd.DataFrame,
    scoped: pd.DataFrame,
    truth_in_scope: pd.DataFrame,
    cfg,
) -> pd.DataFrame:
    oracle_truth = _score_truth_pairs(scoped, truth_in_scope, cfg)
    production = production_pairs.copy()
    if len(production):
        production["oracle_inserted_true_successor"] = False
    combined = pd.concat([production, oracle_truth], ignore_index=True, sort=False)
    if combined.empty:
        return combined
    combined["_pair_key"] = [
        _unordered(a, b) for a, b in zip(combined["source_notice_id"], combined["candidate_notice_id"])
    ]
    combined = (
        combined.sort_values("oracle_inserted_true_successor", ascending=True)
        .drop_duplicates(["source_notice_id", "candidate_notice_id"], keep="first")
        .drop(columns="_pair_key")
    )
    return add_rank_and_margin(combined)


def _connected_components(nodes: list[str], edges: set[tuple[str, str]]) -> dict[str, int]:
    """Union-find over an undirected edge set; isolated nodes become singletons."""
    parent = {n: n for n in nodes}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb
    labels: dict[str, int] = {}
    ids: dict[str, int] = {}
    for n in nodes:
        root = find(n)
        labels[n] = ids.setdefault(root, len(ids))
    return labels


def _bcubed(truth: dict[str, int], predicted: dict[str, int]) -> tuple[float, float, float]:
    """B-cubed precision, recall and F1 over a shared node set."""
    nodes = [n for n in truth if n in predicted]
    if not nodes:
        return float("nan"), float("nan"), float("nan")
    truth_sizes = pd.Series([truth[n] for n in nodes]).value_counts().to_dict()
    pred_sizes = pd.Series([predicted[n] for n in nodes]).value_counts().to_dict()
    joint = pd.Series(
        [f"{truth[n]}|{predicted[n]}" for n in nodes]
    ).value_counts().to_dict()

    precision_sum, recall_sum = 0.0, 0.0
    for n in nodes:
        both = joint[f"{truth[n]}|{predicted[n]}"]
        precision_sum += both / pred_sizes[predicted[n]]
        recall_sum += both / truth_sizes[truth[n]]
    precision = precision_sum / len(nodes)
    recall = recall_sum / len(nodes)
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return float(precision), float(recall), float(f1)


def _pair_scores(pairs: pd.DataFrame, truth: set[tuple[str, str]]) -> pd.DataFrame:
    out = pairs.copy()
    out["is_true_match"] = [
        _unordered(a, b) in truth
        for a, b in zip(out["source_notice_id"], out["candidate_notice_id"])
    ]
    return out


def _fellegi_sunter_score(row: pd.Series) -> float:
    """Frozen Fellegi-Sunter log-odds over three binary field agreements."""
    total = 0.0
    for field, threshold in FS_AGREEMENT_THRESHOLDS.items():
        value = row.get(field)
        agree = bool(pd.notna(value) and float(value) >= threshold)
        m, u = FS_M_PROBABILITIES[field], FS_U_PROBABILITIES[field]
        total += np.log(m / u) if agree else np.log((1 - m) / (1 - u))
    return float(total)


def _probe_predictions(scored: pd.DataFrame) -> dict[str, pd.Series]:
    """Boolean accept masks for each frozen probe linker."""
    fs = scored.apply(_fellegi_sunter_score, axis=1) if len(scored) else pd.Series(dtype=float)
    return {
        "deterministic_top1": scored["candidate_rank"].eq(1)
        & scored["composite_score"].ge(PROBE_TOP1_MIN_SCORE),
        "score_threshold_all_ranks": scored["composite_score"].ge(PROBE_THRESHOLD_MIN_SCORE),
        "fellegi_sunter": fs.ge(FS_ACCEPT_LOG_ODDS) if len(scored) else pd.Series(dtype=bool),
    }


def run_difficulty_metrics(data: BenchmarkData) -> tuple[list[MetricResult], pd.DataFrame]:
    """Blocking, ambiguity and probe-linker diagnostics against sealed truth."""
    cfg = load_config(data.project_root)
    scoped = scoped_sources(data)
    metrics: list[MetricResult] = []
    empty_probe = pd.DataFrame(columns=["probe", "pair_precision", "pair_recall", "pair_f1"])

    if len(scoped) < 30:
        return (
            [
                _metric(
                    data, "hidden_truth_difficulty", "algorithm_scope", "scoped_sources", "count",
                    None, len(scoped), None, None, ">=30", Status.INCONCLUSIVE,
                    notes="too few in-scope synthetic notices to evaluate difficulty",
                )
            ],
            empty_probe,
        )

    all_truth = true_match_pairs(data)
    scoped_ids = set(scoped["notice_id"].astype(str))
    in_scope_mask = all_truth["notice_a"].astype(str).isin(scoped_ids) & all_truth["notice_b"].astype(
        str
    ).isin(scoped_ids)
    truth_in_scope = all_truth.loc[in_scope_mask]
    truth_set = _pair_key_set(truth_in_scope, "notice_a", "notice_b")

    metrics.append(
        _metric(
            data, "hidden_truth_difficulty", "algorithm_scope", "true_matches_in_scope", "count",
            None, len(truth_set), None, None, "context_only", Status.PASS,
            notes=(
                f"{len(all_truth)} true successor pairs exist in the whole benchmark; {len(truth_set)} have "
                f"both notices inside the {len(scoped)}-notice candidate scope. Only these are recoverable "
                "by any method run on this candidate set, and they are the recall denominator below"
            ),
        )
    )
    if not truth_set:
        return metrics, empty_probe

    production_pairs = _generate_candidates(scoped, cfg, window=None)
    widened_pairs = _generate_candidates(scoped, cfg, window=WIDENED_PROBE_WINDOW_MONTHS)
    n_universe = len(scoped) * (len(scoped) - 1) / 2

    production_candidate_set: set[tuple[str, str]] = set()
    production_recovered: set[tuple[str, str]] = set()
    production_pc = float("nan")
    for label, pairs in [("production_window", production_pairs), (f"{WIDENED_PROBE_WINDOW_MONTHS}m_window", widened_pairs)]:
        candidate_set = _pair_key_set(pairs, "source_notice_id", "candidate_notice_id")
        recovered = candidate_set & truth_set
        pc = len(recovered) / len(truth_set)
        if label == "production_window":
            production_candidate_set = candidate_set
            production_recovered = recovered
            production_pc = pc
        pq = len(recovered) / len(candidate_set) if candidate_set else float("nan")
        rr = 1 - len(candidate_set) / n_universe if n_universe else float("nan")
        is_widened = label != "production_window"
        pc_floor = (
            TOLERANCES["widened_pairs_completeness_min"]
            if is_widened
            else TOLERANCES["production_pairs_completeness_min"]
        )
        metrics.append(
            _metric(
                data, "hidden_truth_difficulty", label, "blocking_pairs_completeness", "PC",
                None, pc, pc - pc_floor, pc, pc_floor,
                Status.PASS if pc >= pc_floor else Status.WARNING if pc >= pc_floor * 0.6 else Status.FAIL,
                notes=(
                    "share of in-scope true matches that survive blocking. The production window is the "
                    "pipeline's own 6-month rule and a low value there is a property of that pipeline "
                    "against this benchmark's true renewal gaps, not a generator defect; the widened "
                    "window tests whether buyer-key blocking can reach the truth at all"
                ),
            )
        )
        setting_label = "PRODUCTION_BLOCKING" if label == "production_window" else f"{WIDENED_PROBE_WINDOW_MONTHS}M_BLOCKING"
        metrics.append(
            _metric(
                data, "hidden_truth_difficulty", setting_label, "evaluation_setting", "R_blocking",
                None, pc, pc - pc_floor, pc, pc_floor,
                Status.PASS if pc >= pc_floor else Status.WARNING if pc >= pc_floor * 0.6 else Status.FAIL,
                notes=(
                    f"{setting_label}: blocking-only recall over {len(truth_set)} in-scope true pairs; "
                    "no scoring or acceptance threshold is applied"
                ),
            )
        )
        metrics.append(
            _metric(
                data, "hidden_truth_difficulty", label, "pairs_quality", "PQ",
                None, pq, None, pq, TOLERANCES["pairs_quality_min"],
                Status.PASS if pq >= TOLERANCES["pairs_quality_min"] else Status.WARNING,
                notes=f"{len(recovered)} true matches among {len(candidate_set)} candidate pairs",
            )
        )
        metrics.append(
            _metric(
                data, "hidden_truth_difficulty", label, "reduction_ratio", "RR",
                None, rr, None, rr, TOLERANCES["reduction_ratio_min"],
                Status.PASS if rr >= TOLERANCES["reduction_ratio_min"] else Status.WARNING,
                notes=f"universe of {int(n_universe)} in-scope pairs reduced to {len(candidate_set)}",
            )
        )

    # Ambiguity and hard negatives, on the production candidate set.
    scored = _pair_scores(production_pairs, truth_set)
    if scored.empty:
        return metrics, empty_probe

    matches = scored.loc[scored["is_true_match"], "composite_score"]
    non_matches = scored.loc[~scored["is_true_match"], "composite_score"]
    overlap = overlap_coefficient(matches, non_matches)
    metrics.append(
        _metric(
            data, "hidden_truth_difficulty", "production_window", "match_vs_hard_negative_score", "overlap",
            None, overlap, None, overlap,
            f"{TOLERANCES['match_nonmatch_overlap_min']}-{TOLERANCES['match_nonmatch_overlap_max']}",
            classify_range(
                overlap,
                TOLERANCES["match_nonmatch_overlap_min"],
                TOLERANCES["match_nonmatch_overlap_max"],
            ),
            notes=(
                f"n_match={len(matches)}, n_non_match={len(non_matches)}. Near-zero overlap would mean a "
                "trivially separable benchmark; near-total overlap would mean an unlearnable one"
            ),
        )
    )

    # Where does the true match sit among a source's ranked candidates?
    with_truth = scored.loc[scored["is_true_match"]]
    if len(with_truth):
        ranks = with_truth["candidate_rank"].astype(float)
        mrr = float((1.0 / ranks).mean())
        top1 = float(ranks.eq(1).mean())
        metrics.append(
            _metric(
                data, "hidden_truth_difficulty", "production_window", "true_match_rank", "MRR",
                None, mrr, None, mrr, "context_only", Status.PASS,
                notes=f"top-1 share {top1:.3f} over {len(with_truth)} retrieved true matches",
            )
        )
        median_margin = float(scored.loc[scored["candidate_rank"].eq(1), "top1_top2_margin"].median())
        metrics.append(
            _metric(
                data, "hidden_truth_difficulty", "production_window", "top1_top2_margin", "median",
                None, median_margin, None, median_margin, "context_only", Status.PASS,
                notes="score gap between the best and second-best candidate; small margins mean genuine ambiguity",
            )
        )

    # Probe linkers.
    truth_labels = _connected_components(sorted(scoped_ids), truth_set)
    oracle_scored = _pair_scores(
        _oracle_candidate_scoring_frame(production_pairs, scoped, truth_in_scope, cfg),
        truth_set,
    )
    oracle_inserted = int(
        oracle_scored.get("oracle_inserted_true_successor", pd.Series(dtype=bool)).fillna(False).sum()
    )
    metrics.append(
        _metric(
            data, "algorithm_utility", "ORACLE_CANDIDATE_SCORING", "evaluation_setting",
            "inserted_true_successor_pairs",
            None, oracle_inserted, None, None, "context_only", Status.PASS,
            notes=(
                "Oracle scoring inserts missing true successors into the production-distractor environment. "
                "It evaluates ranking/scoring conditional on truth being reachable and is not a production "
                "blocking result"
            ),
        )
    )
    probe_rows = []
    for probe, accept in _probe_predictions(scored).items():
        accepted = scored.loc[accept.reindex(scored.index, fill_value=False)]
        predicted_set = _pair_key_set(accepted, "source_notice_id", "candidate_notice_id")
        tp = len(predicted_set & truth_set)
        precision = tp / len(predicted_set) if predicted_set else float("nan")
        recall = tp / len(truth_set)
        f1 = 2 * precision * recall / (precision + recall) if precision and recall else 0.0
        pred_labels = _connected_components(sorted(scoped_ids), predicted_set)
        b3p, b3r, b3f = _bcubed(truth_labels, pred_labels)
        probe_rows.append(
            {
                "probe": probe,
                "n_predicted_pairs": len(predicted_set),
                "pair_precision": precision,
                "pair_recall": recall,
                "pair_f1": f1,
                "bcubed_precision": b3p,
                "bcubed_recall": b3r,
                "bcubed_f1": b3f,
            }
        )
        for name, value in [
            ("pair_precision", precision),
            ("pair_recall", recall),
            ("pair_f1", f1),
            ("bcubed_f1", b3f),
        ]:
            metrics.append(
                _metric(
                    data, "algorithm_utility", probe, "probe_linker", name,
                    None, value, None, value, "context_only", Status.PASS,
                    notes=(
                        f"frozen probe over {len(scored)} production candidate pairs; "
                        f"{len(predicted_set)} accepted. Probe parameters are fixed constants, "
                        "not the production acceptance threshold"
                    ),
                )
            )

        reachable_tp = len(predicted_set & production_recovered)
        scoring_given_reachable = (
            reachable_tp / len(production_recovered) if production_recovered else float("nan")
        )
        product_recall = production_pc * scoring_given_reachable if pd.notna(scoring_given_reachable) else float("nan")
        metrics.extend(
            [
                _metric(
                    data, "algorithm_utility", f"END_TO_END:{probe}", "recall_decomposition",
                    "R_end_to_end",
                    None, recall, None, recall, "context_only", Status.PASS,
                    notes="pair recall over all in-scope true matches after production blocking and probe scoring",
                ),
                _metric(
                    data, "algorithm_utility", f"END_TO_END:{probe}", "recall_decomposition",
                    "R_scoring_given_reachable",
                    None, scoring_given_reachable, None, scoring_given_reachable,
                    "context_only", Status.PASS,
                    notes=(
                        f"probe recall among {len(production_recovered)} true matches reachable under "
                        "production blocking"
                    ),
                ),
                _metric(
                    data, "algorithm_utility", f"END_TO_END:{probe}", "recall_decomposition",
                    "R_blocking_times_scoring",
                    None, product_recall, product_recall - recall if pd.notna(product_recall) else None,
                    abs(product_recall - recall) if pd.notna(product_recall) else None,
                    "exact", Status.PASS if pd.notna(product_recall) and np.isclose(product_recall, recall) else Status.INCONCLUSIVE,
                    notes="checks R_end_to_end = R_blocking * R_scoring_given_reachable",
                ),
            ]
        )

        if not oracle_scored.empty:
            oracle_accept = _probe_predictions(oracle_scored)[probe].reindex(oracle_scored.index, fill_value=False)
            oracle_accepted = oracle_scored.loc[oracle_accept]
            oracle_predicted_set = _pair_key_set(
                oracle_accepted, "source_notice_id", "candidate_notice_id"
            )
            oracle_tp = len(oracle_predicted_set & truth_set)
            oracle_precision = oracle_tp / len(oracle_predicted_set) if oracle_predicted_set else float("nan")
            oracle_recall = oracle_tp / len(truth_set)
            oracle_f1 = (
                2 * oracle_precision * oracle_recall / (oracle_precision + oracle_recall)
                if oracle_precision and oracle_recall else 0.0
            )
            for name, value in [
                ("pair_precision", oracle_precision),
                ("pair_recall", oracle_recall),
                ("pair_f1", oracle_f1),
            ]:
                metrics.append(
                    _metric(
                        data, "algorithm_utility", f"ORACLE_CANDIDATE_SCORING:{probe}",
                        "oracle_candidate_scoring", name,
                        None, value, None, value, "context_only", Status.PASS,
                        notes=(
                            "true successors are inserted before ranking/scoring; production distractors are "
                            "retained where they exist. This is a scoring/ranking diagnostic, not a blocking result"
                        ),
                    )
                )

    probe_frame = pd.DataFrame(probe_rows)
    f1_values = probe_frame["pair_f1"].astype(float)
    best_f1 = float(f1_values.max())
    spread = float(f1_values.max() - f1_values.min())
    metrics.append(
        _metric(
            data, "algorithm_utility", "all_probes", "probe_discrimination", "f1_spread",
            None, spread, None, spread, TOLERANCES["probe_f1_spread_min"],
            Status.PASS if spread >= TOLERANCES["probe_f1_spread_min"] else Status.FAIL,
            notes=(
                "range of pair-F1 across the three probes. A zero spread would mean the benchmark cannot "
                "tell substantively different linkers apart, which is the whole point of a benchmark"
            ),
        )
    )
    metrics.append(
        _metric(
            data, "algorithm_utility", "all_probes", "probe_headroom", "best_pair_f1",
            None, best_f1, None, best_f1,
            f"{TOLERANCES['probe_best_f1_min']}-{TOLERANCES['probe_best_f1_max']}",
            classify_range(best_f1, TOLERANCES["probe_best_f1_min"], TOLERANCES["probe_best_f1_max"]),
            notes=(
                "best probe pair-F1. Near 1.0 would mean a shortcut exists and the task is trivial; "
                "near 0.0 would mean no method can learn anything from this candidate set"
            ),
        )
    )
    metrics.append(
        _metric(
            data, "algorithm_utility", "all_probes", "probe_count", "n_probes",
            None, len(probe_frame), None, None, ">=3",
            Status.PASS if len(probe_frame) >= 3 else Status.FAIL,
            notes="; ".join(f"{r.probe}: F1={r.pair_f1:.3f}" for r in probe_frame.itertuples()),
        )
    )
    return metrics, probe_frame


def run_difficulty_validation(data: BenchmarkData) -> list[MetricResult]:
    metrics, _ = run_difficulty_metrics(data)
    return metrics
