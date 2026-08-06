"""Build curve diagnostics for the frozen synthetic linkage benchmark.

This script reads the sealed v0.4 synthetic benchmark artifacts, reconstructs
the scored production candidate pairs with the same train/calibration/evaluate
split used by notebook 14, and writes curve-level diagnostics that are not
stored by the original benchmark notebook:

- candidate-pair ROC curves
- candidate-pair precision-recall curves
- rank-1 threshold precision/recall/F1 curves
- gradient boosting staged train/calibration log-loss

It does not regenerate synthetic data. It only reloads existing frozen worlds.
"""

from __future__ import annotations

import sys
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    auc,
    log_loss,
    precision_recall_curve,
    roc_curve,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.config import load_config
from boamp.synthetic.validation_framework.difficulty import (
    FS_AGREEMENT_THRESHOLDS,
    FS_M_PROBABILITIES,
    FS_U_PROBABILITIES,
    _generate_candidates,
    _pair_key_set,
    _pair_scores,
    _unordered,
    scoped_sources,
    true_match_pairs,
)
from boamp.synthetic.validation_framework.loaders import load_benchmark_data


warnings.filterwarnings("ignore", category=FutureWarning)

BENCHMARK_VERSION = "v0_4_population_alias_revision"
FIT_SCENARIO = "central_provisional"
FIT_WORLDS = ["001", "002", "003", "004"]
CALIBRATION_WORLDS = ["005", "006"]
EVALUATION_SCENARIOS = [
    "central_provisional",
    "easier",
    "moderate",
    "difficult",
    "stress",
]
EVALUATION_WORLDS = ["007", "008", "009", "010"]
CORRUPTION_FOR_WORLD = {world: world for world in [f"{i:03d}" for i in range(1, 11)]}

TABLE_DIR = (
    ROOT
    / "reports"
    / "tables"
    / "synthetic_benchmark"
    / BENCHMARK_VERSION
    / "linkage_algorithm_benchmark"
)
FIGURE_DIR = (
    ROOT
    / "reports"
    / "figures"
    / "synthetic_benchmark"
    / BENCHMARK_VERSION
    / "linkage_algorithm_benchmark"
)

NUMERIC_FEATURES = [
    "s_text",
    "s_cpv",
    "s_time",
    "s_buyer",
    "gap_months",
    "abs_gap_to_expected_end",
    "n_candidates_for_source",
    "source_publication_year",
]
BINARY_FEATURES = [
    "cpv_missing",
    "cpv_generic_flag",
    "source_cpv_missing",
    "source_duration_missing",
]
CATEGORICAL_FEATURES = [
    "buyer_key_type",
    "source_schema_family",
    "source_cpv_division",
]
FEATURE_COLUMNS = NUMERIC_FEATURES + BINARY_FEATURES + CATEGORICAL_FEATURES

ALGORITHM_LABELS = {
    "current_weighted_composite": "Composite",
    "fellegi_sunter_style": "Fellegi-Sunter",
    "logistic_regression": "Logistic regression",
    "gradient_boosting": "Gradient boosting",
}
PALETTE = {
    "current_weighted_composite": "#2f6f9f",
    "fellegi_sunter_style": "#b8870b",
    "logistic_regression": "#8a5a99",
    "gradient_boosting": "#4b8b3b",
}
MAX_STORED_CURVE_POINTS_PER_ALGORITHM = 5000


def one_hot_encoder() -> OneHotEncoder:
    try:
        return OneHotEncoder(handle_unknown="ignore", sparse_output=False)
    except TypeError:
        return OneHotEncoder(handle_unknown="ignore", sparse=False)


def fellegi_sunter_log_odds(frame: pd.DataFrame) -> pd.Series:
    score = np.zeros(len(frame), dtype=float)
    for field, threshold in FS_AGREEMENT_THRESHOLDS.items():
        values = pd.to_numeric(frame[field], errors="coerce")
        agree = values.ge(threshold).fillna(False).to_numpy()
        m = FS_M_PROBABILITIES[field]
        u = FS_U_PROBABILITIES[field]
        score += np.where(agree, np.log(m / u), np.log((1 - m) / (1 - u)))
    return pd.Series(score, index=frame.index)


def add_source_candidate_context(scored: pd.DataFrame, scoped: pd.DataFrame) -> pd.DataFrame:
    attrs = scoped.copy()
    attrs["notice_id"] = attrs["notice_id"].astype(str)
    attrs["publication_year"] = pd.to_datetime(attrs["publication_date"]).dt.year
    context_cols = [
        "notice_id",
        "schema_family",
        "notice_type_normalized",
        "publication_year",
        "buyer_key_type",
        "code_departement",
        "cpv_clean",
        "cpv_division",
        "declared_duration_months",
        "dur_was_imputed",
    ]
    available = [c for c in context_cols if c in attrs.columns]
    source_context = attrs[available].rename(
        columns={c: f"source_{c}" for c in available if c != "notice_id"}
    )
    candidate_context = attrs[available].rename(
        columns={c: f"candidate_{c}" for c in available if c != "notice_id"}
    )
    out = scored.merge(
        source_context,
        left_on="source_notice_id",
        right_on="notice_id",
        how="left",
    ).drop(columns=["notice_id"], errors="ignore")
    out = out.merge(
        candidate_context,
        left_on="candidate_notice_id",
        right_on="notice_id",
        how="left",
    ).drop(columns=["notice_id"], errors="ignore")
    out["source_cpv_missing"] = out["source_cpv_clean"].isna()
    out["source_duration_missing"] = out["source_declared_duration_months"].isna()
    return out


def load_world_frame(
    scenario: str,
    world: str,
    cfg,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    corruption = CORRUPTION_FOR_WORLD[world]
    data = load_benchmark_data(ROOT, BENCHMARK_VERSION, scenario, world, corruption)
    scoped = scoped_sources(data)
    scoped_ids = set(scoped["notice_id"].astype(str))
    truth = true_match_pairs(data)
    truth_in_scope = truth.loc[
        truth["notice_a"].astype(str).isin(scoped_ids)
        & truth["notice_b"].astype(str).isin(scoped_ids)
    ].copy()
    truth_set = _pair_key_set(truth_in_scope, "notice_a", "notice_b")

    pairs = _generate_candidates(scoped, cfg, window=None)
    scored = _pair_scores(pairs, truth_set)
    scored = add_source_candidate_context(scored, scoped)
    scored["scenario"] = scenario
    scored["world"] = world
    scored["corruption"] = corruption
    scored["pair_key"] = [
        _unordered(a, b)
        for a, b in zip(scored["source_notice_id"], scored["candidate_notice_id"])
    ]
    scored["global_pair_key"] = [
        f"{scenario}|{world}|{a}|{b}" for a, b in scored["pair_key"]
    ]
    scored["fs_log_odds"] = fellegi_sunter_log_odds(scored)

    truth_context = truth_in_scope.copy()
    truth_context["scenario"] = scenario
    truth_context["world"] = world
    truth_context["pair_key"] = [
        _unordered(a, b)
        for a, b in zip(truth_context["notice_a"], truth_context["notice_b"])
    ]
    truth_context["global_pair_key"] = [
        f"{scenario}|{world}|{a}|{b}" for a, b in truth_context["pair_key"]
    ]
    candidate_truth = set(scored.loc[scored["is_true_match"], "global_pair_key"])
    truth_context["reachable_by_production_candidates"] = truth_context[
        "global_pair_key"
    ].isin(candidate_truth)

    metadata = {
        "scenario": scenario,
        "world": world,
        "corruption": corruption,
        "n_scoped_sources": int(len(scoped)),
        "n_candidate_pairs": int(len(scored)),
        "n_truth_in_scope": int(truth_context["global_pair_key"].nunique()),
        "n_reachable_truth": int(len(candidate_truth)),
    }
    metadata["blocking_recall"] = (
        metadata["n_reachable_truth"] / metadata["n_truth_in_scope"]
        if metadata["n_truth_in_scope"]
        else np.nan
    )
    return scored, truth_context, metadata


def collect_frames(
    scenarios: list[str],
    worlds: list[str],
    cfg,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    pair_frames = []
    truth_frames = []
    metadata_rows = []
    for scenario in scenarios:
        for world in worlds:
            scored, truth_context, metadata = load_world_frame(scenario, world, cfg)
            pair_frames.append(scored)
            truth_frames.append(truth_context)
            metadata_rows.append(metadata)
            print(
                f"{scenario} world {world}: "
                f"{metadata['n_candidate_pairs']:,} pairs; "
                f"{metadata['n_truth_in_scope']:,} truth; "
                f"blocking recall {metadata['blocking_recall']:.3f}",
                flush=True,
            )
    return (
        pd.concat(pair_frames, ignore_index=True),
        pd.concat(truth_frames, ignore_index=True),
        pd.DataFrame(metadata_rows),
    )


def make_feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    features = frame.reindex(columns=FEATURE_COLUMNS).copy()
    for col in BINARY_FEATURES:
        features[col] = pd.to_numeric(features[col], errors="coerce").astype(float)
    for col in CATEGORICAL_FEATURES:
        features[col] = features[col].astype(str)
    return features


def build_models(random_seed: int) -> dict[str, Pipeline]:
    pre_lr = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                        ("scaler", StandardScaler()),
                    ]
                ),
                NUMERIC_FEATURES + BINARY_FEATURES,
            ),
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", one_hot_encoder()),
                    ]
                ),
                CATEGORICAL_FEATURES,
            ),
        ]
    )
    pre_gb = ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))]),
                NUMERIC_FEATURES + BINARY_FEATURES,
            ),
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("onehot", one_hot_encoder()),
                    ]
                ),
                CATEGORICAL_FEATURES,
            ),
        ]
    )
    return {
        "logistic_regression": Pipeline(
            steps=[
                ("preprocess", pre_lr),
                (
                    "model",
                    LogisticRegression(
                        max_iter=1000,
                        class_weight="balanced",
                        random_state=random_seed,
                    ),
                ),
            ]
        ),
        "gradient_boosting": Pipeline(
            steps=[
                ("preprocess", pre_gb),
                (
                    "model",
                    GradientBoostingClassifier(
                        n_estimators=160,
                        learning_rate=0.045,
                        max_depth=3,
                        subsample=0.8,
                        random_state=random_seed,
                    ),
                ),
            ]
        ),
    }


def add_model_scores(
    frame: pd.DataFrame,
    models: dict[str, Pipeline],
) -> pd.DataFrame:
    out = frame.copy()
    features = make_feature_frame(out)
    out["logistic_score"] = models["logistic_regression"].predict_proba(features)[:, 1]
    out["gradient_boosting_score"] = models["gradient_boosting"].predict_proba(features)[:, 1]
    return out


def algorithm_specs() -> dict[str, dict[str, object]]:
    thresholds = pd.read_csv(TABLE_DIR / "algorithm_thresholds.csv").set_index("algorithm")
    return {
        row.Index: {
            "score_col": row.score_col,
            "threshold": float(row.threshold),
            "threshold_source": row.threshold_source,
        }
        for row in thresholds.itertuples()
    }


def rank1_threshold_metrics(
    pairs: pd.DataFrame,
    truth: pd.DataFrame,
    algorithm: str,
    score_col: str,
    threshold_values: np.ndarray,
    frozen_threshold: float,
) -> pd.DataFrame:
    ordered = pairs.sort_values(
        ["scenario", "world", "source_notice_id", score_col, "candidate_date"],
        ascending=[True, True, True, False, True],
    )
    top = ordered.groupby(["scenario", "world", "source_notice_id"], as_index=False).head(1)
    top = top[[score_col, "global_pair_key", "is_true_match"]].copy()
    truth_set = set(truth["global_pair_key"])
    reachable_set = set(
        truth.loc[truth["reachable_by_production_candidates"], "global_pair_key"]
    )
    rows = []
    for threshold in threshold_values:
        predicted = top.loc[top[score_col].ge(threshold)]
        pred_set = set(predicted["global_pair_key"])
        true_positive = len(pred_set & truth_set)
        n_predicted = len(pred_set)
        precision = true_positive / n_predicted if n_predicted else np.nan
        recall_fixed = true_positive / len(reachable_set) if reachable_set else np.nan
        recall_end_to_end = true_positive / len(truth_set) if truth_set else np.nan
        f1_fixed = (
            2 * precision * recall_fixed / (precision + recall_fixed)
            if precision and recall_fixed
            else 0.0
        )
        f1_end_to_end = (
            2 * precision * recall_end_to_end / (precision + recall_end_to_end)
            if precision and recall_end_to_end
            else 0.0
        )
        rows.append(
            {
                "algorithm": algorithm,
                "score_col": score_col,
                "threshold": float(threshold),
                "is_frozen_threshold": bool(np.isclose(threshold, frozen_threshold)),
                "n_predicted_pairs": int(n_predicted),
                "true_positive_pairs": int(true_positive),
                "pair_precision": precision,
                "pair_recall_fixed_candidate": recall_fixed,
                "pair_recall_end_to_end": recall_end_to_end,
                "pair_f1_fixed_candidate": f1_fixed,
                "pair_f1_end_to_end": f1_end_to_end,
            }
        )
    return pd.DataFrame(rows)


def thresholds_for_curve(scores: pd.Series, frozen_threshold: float) -> np.ndarray:
    finite = pd.to_numeric(scores, errors="coerce").dropna()
    quantile_thresholds = np.unique(
        np.quantile(finite, np.linspace(0.0, 1.0, 201))
    )
    values = np.unique(np.r_[quantile_thresholds, frozen_threshold])
    return values.astype(float)


def thin_curve_points(frame: pd.DataFrame) -> pd.DataFrame:
    """Store plot-ready curve points without retaining every unique threshold."""
    thinned = []
    for algorithm, sub in frame.groupby("algorithm", sort=False):
        if len(sub) <= MAX_STORED_CURVE_POINTS_PER_ALGORITHM:
            kept = sub.copy()
        else:
            positions = np.unique(
                np.linspace(
                    0,
                    len(sub) - 1,
                    MAX_STORED_CURVE_POINTS_PER_ALGORITHM,
                    dtype=int,
                )
            )
            kept = sub.iloc[positions].copy()
        kept["stored_point_count"] = len(kept)
        kept["full_point_count"] = len(sub)
        kept["point_storage"] = "even_index_thin_preserving_endpoints"
        thinned.append(kept)
    return pd.concat(thinned, ignore_index=True)


def save_curve_figures(
    roc_points: pd.DataFrame,
    pr_points: pd.DataFrame,
    f1_points: pd.DataFrame,
    gbm_loss: pd.DataFrame,
) -> None:
    sns.set_theme(style="whitegrid", context="notebook")
    plt.rcParams.update(
        {
            "figure.dpi": 120,
            "savefig.dpi": 180,
            "axes.labelcolor": "#2f3437",
            "axes.titlecolor": "#2f3437",
            "text.color": "#2f3437",
        }
    )

    fig, ax = plt.subplots(figsize=(7, 5.2))
    for algorithm, sub in roc_points.groupby("algorithm", sort=False):
        ax.plot(
            sub["false_positive_rate"],
            sub["true_positive_rate"],
            color=PALETTE[algorithm],
            linewidth=2,
            label=f"{ALGORITHM_LABELS[algorithm]} (AUC={sub['roc_auc'].iloc[0]:.3f})",
        )
    ax.plot([0, 1], [0, 1], color="#8c8c8c", linewidth=1, linestyle="--")
    ax.set_title("Candidate-pair ROC curves")
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(title="", loc="lower right")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "roc_curves.png", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 5.2))
    for algorithm, sub in pr_points.groupby("algorithm", sort=False):
        ax.plot(
            sub["recall"],
            sub["precision"],
            color=PALETTE[algorithm],
            linewidth=2,
            label=(
                f"{ALGORITHM_LABELS[algorithm]} "
                f"(AP={sub['average_precision'].iloc[0]:.3f})"
            ),
        )
    ax.set_title("Candidate-pair precision-recall curves")
    ax.set_xlabel("Recall over candidate pairs")
    ax.set_ylabel("Precision")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(title="", loc="upper right")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "precision_recall_curves.png", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5.2))
    for algorithm, sub in f1_points.groupby("algorithm", sort=False):
        ax.plot(
            sub["threshold"],
            sub["pair_f1_end_to_end"],
            color=PALETTE[algorithm],
            linewidth=2,
            label=ALGORITHM_LABELS[algorithm],
        )
        frozen = sub.loc[sub["is_frozen_threshold"]]
        if len(frozen):
            ax.scatter(
                frozen["threshold"],
                frozen["pair_f1_end_to_end"],
                color=PALETTE[algorithm],
                edgecolor="white",
                linewidth=0.8,
                s=55,
                zorder=3,
            )
    ax.set_title("Rank-1 threshold curves")
    ax.set_xlabel("Acceptance threshold")
    ax.set_ylabel("End-to-end pair-F1")
    ax.legend(title="", loc="best")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "rank1_f1_threshold_curves.png", bbox_inches="tight")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 5.2))
    ax.plot(
        gbm_loss["stage"],
        gbm_loss["train_log_loss"],
        color="#4b8b3b",
        linewidth=2,
        label="Train",
    )
    ax.plot(
        gbm_loss["stage"],
        gbm_loss["calibration_log_loss"],
        color="#2f6f9f",
        linewidth=2,
        label="Calibration",
    )
    ax.set_title("Gradient boosting staged log-loss")
    ax.set_xlabel("Boosting stage")
    ax.set_ylabel("Log loss")
    ax.legend(title="", loc="best")
    fig.tight_layout()
    fig.savefig(FIGURE_DIR / "gbm_loss_curve.png", bbox_inches="tight")
    plt.close(fig)


def build_gbm_loss_curve(
    model: Pipeline,
    fit_pairs: pd.DataFrame,
    calibration_pairs: pd.DataFrame,
) -> pd.DataFrame:
    preprocess = model.named_steps["preprocess"]
    gbm = model.named_steps["model"]
    x_fit = preprocess.transform(make_feature_frame(fit_pairs))
    x_cal = preprocess.transform(make_feature_frame(calibration_pairs))
    y_fit = fit_pairs["is_true_match"].astype(int).to_numpy()
    y_cal = calibration_pairs["is_true_match"].astype(int).to_numpy()

    rows = []
    for stage, (p_fit, p_cal) in enumerate(
        zip(gbm.staged_predict_proba(x_fit), gbm.staged_predict_proba(x_cal)),
        start=1,
    ):
        rows.append(
            {
                "stage": stage,
                "train_log_loss": log_loss(y_fit, p_fit[:, 1], labels=[0, 1]),
                "calibration_log_loss": log_loss(y_cal, p_cal[:, 1], labels=[0, 1]),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    TABLE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURE_DIR.mkdir(parents=True, exist_ok=True)

    cfg = load_config(ROOT)
    random_seed = int(cfg.pipeline.run.random_seed)
    specs = algorithm_specs()

    print("Loading frozen benchmark candidate pairs...", flush=True)
    fit_pairs, _, _ = collect_frames([FIT_SCENARIO], FIT_WORLDS, cfg)
    calibration_pairs, calibration_truth, _ = collect_frames(
        [FIT_SCENARIO], CALIBRATION_WORLDS, cfg
    )
    evaluation_pairs, evaluation_truth, _ = collect_frames(
        EVALUATION_SCENARIOS, EVALUATION_WORLDS, cfg
    )

    print("Training supervised benchmark models...", flush=True)
    models = build_models(random_seed)
    x_fit = make_feature_frame(fit_pairs)
    y_fit = fit_pairs["is_true_match"].astype(int)
    for model in models.values():
        model.fit(x_fit, y_fit)

    fit_pairs = add_model_scores(fit_pairs, models)
    calibration_pairs = add_model_scores(calibration_pairs, models)
    evaluation_pairs = add_model_scores(evaluation_pairs, models)

    score_cols = {algorithm: spec["score_col"] for algorithm, spec in specs.items()}
    print("Writing ROC and precision-recall curve points...", flush=True)
    roc_rows = []
    pr_rows = []
    for algorithm, score_col in score_cols.items():
        y = evaluation_pairs["is_true_match"].astype(int).to_numpy()
        scores = pd.to_numeric(evaluation_pairs[score_col], errors="coerce").to_numpy()

        fpr, tpr, roc_thresholds = roc_curve(y, scores)
        roc_auc = auc(fpr, tpr)
        for idx, (fpr_i, tpr_i, threshold_i) in enumerate(
            zip(fpr, tpr, roc_thresholds)
        ):
            roc_rows.append(
                {
                    "algorithm": algorithm,
                    "score_col": score_col,
                    "point_index": idx,
                    "false_positive_rate": fpr_i,
                    "true_positive_rate": tpr_i,
                    "threshold": threshold_i,
                    "roc_auc": roc_auc,
                }
            )

        precision, recall, pr_thresholds = precision_recall_curve(y, scores)
        avg_precision = average_precision_score(y, scores)
        padded_thresholds = np.r_[pr_thresholds, np.nan]
        for idx, (precision_i, recall_i, threshold_i) in enumerate(
            zip(precision, recall, padded_thresholds)
        ):
            pr_rows.append(
                {
                    "algorithm": algorithm,
                    "score_col": score_col,
                    "point_index": idx,
                    "precision": precision_i,
                    "recall": recall_i,
                    "threshold": threshold_i,
                    "average_precision": avg_precision,
                }
            )

    roc_points_full = pd.DataFrame(roc_rows)
    pr_points_full = pd.DataFrame(pr_rows)
    roc_points = thin_curve_points(roc_points_full)
    pr_points = thin_curve_points(pr_points_full)
    roc_points.to_csv(TABLE_DIR / "roc_curve_points.csv", index=False)
    pr_points.to_csv(TABLE_DIR / "precision_recall_curve_points.csv", index=False)

    print("Writing rank-1 F1 threshold curves...", flush=True)
    f1_points = pd.concat(
        [
            rank1_threshold_metrics(
                evaluation_pairs,
                evaluation_truth,
                algorithm,
                spec["score_col"],
                thresholds_for_curve(
                    evaluation_pairs[spec["score_col"]],
                    float(spec["threshold"]),
                ),
                float(spec["threshold"]),
            )
            for algorithm, spec in specs.items()
        ],
        ignore_index=True,
    )
    f1_points.to_csv(TABLE_DIR / "rank1_f1_threshold_curve.csv", index=False)

    print("Writing GBM loss curve...", flush=True)
    gbm_loss = build_gbm_loss_curve(
        models["gradient_boosting"],
        fit_pairs,
        calibration_pairs,
    )
    gbm_loss.to_csv(TABLE_DIR / "gbm_loss_curve.csv", index=False)

    best_f1 = (
        f1_points.sort_values(["algorithm", "pair_f1_end_to_end"], ascending=[True, False])
        .groupby("algorithm", as_index=False)
        .head(1)
        .rename(
            columns={
                "threshold": "best_rank1_threshold_in_grid",
                "pair_f1_end_to_end": "best_rank1_pair_f1_end_to_end_in_grid",
            }
        )
    )
    curve_summary = []
    for algorithm, spec in specs.items():
        roc_sub = roc_points.loc[roc_points["algorithm"].eq(algorithm)]
        pr_sub = pr_points.loc[pr_points["algorithm"].eq(algorithm)]
        roc = roc_sub["roc_auc"].iloc[0]
        ap = pr_points.loc[
            pr_points["algorithm"].eq(algorithm), "average_precision"
        ].iloc[0]
        frozen = f1_points.loc[
            f1_points["algorithm"].eq(algorithm)
            & f1_points["is_frozen_threshold"]
        ].iloc[0]
        best = best_f1.loc[best_f1["algorithm"].eq(algorithm)].iloc[0]
        curve_summary.append(
            {
                "algorithm": algorithm,
                "score_col": spec["score_col"],
                "frozen_threshold": float(spec["threshold"]),
                "roc_auc_candidate_pairs": float(roc),
                "average_precision_candidate_pairs": float(ap),
                "stored_roc_curve_points": int(roc_sub["stored_point_count"].iloc[0]),
                "full_roc_curve_points": int(roc_sub["full_point_count"].iloc[0]),
                "stored_precision_recall_curve_points": int(
                    pr_sub["stored_point_count"].iloc[0]
                ),
                "full_precision_recall_curve_points": int(
                    pr_sub["full_point_count"].iloc[0]
                ),
                "curve_point_storage": str(roc_sub["point_storage"].iloc[0]),
                "frozen_rank1_pair_precision": float(frozen["pair_precision"]),
                "frozen_rank1_pair_recall_end_to_end": float(
                    frozen["pair_recall_end_to_end"]
                ),
                "frozen_rank1_pair_f1_end_to_end": float(
                    frozen["pair_f1_end_to_end"]
                ),
                "best_rank1_threshold_in_grid": float(
                    best["best_rank1_threshold_in_grid"]
                ),
                "best_rank1_pair_f1_end_to_end_in_grid": float(
                    best["best_rank1_pair_f1_end_to_end_in_grid"]
                ),
            }
        )
    pd.DataFrame(curve_summary).to_csv(
        TABLE_DIR / "diagnostic_curve_summary.csv",
        index=False,
    )

    print("Writing diagnostic figures...", flush=True)
    save_curve_figures(roc_points, pr_points, f1_points, gbm_loss)
    print(f"Wrote diagnostics to {TABLE_DIR} and {FIGURE_DIR}", flush=True)


if __name__ == "__main__":
    main()
