"""Analyze manual-audit failure modes for real BOAMP linkage.

This is a diagnostic analysis of the completed 100-case audit. The sample was
stratified and purposive, so the outputs below should be used to repair the
linkage rule and design the next statistically interpretable audit, not as final
population precision or recall estimates.
"""

from __future__ import annotations

import json
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.config import load_config  # noqa: E402

warnings.filterwarnings("ignore", category=RuntimeWarning, message="Mean of empty slice")


TEXT_COLS = ["reviewer_notes", "source_text", "candidate_text"]
FEATURES = [
    "s_text",
    "s_cpv",
    "s_time",
    "s_buyer",
    "composite_score",
    "gbm_score",
    "top1_top2_margin",
    "n_candidates_for_source",
    "gap_months",
    "buyer_n_sources",
]
FAILURE_MODE_DEFINITIONS = {
    "MATERIAL_SCOPE_MISMATCH": (
        "Source and candidate describe different concrete functions, software, equipment, lot, "
        "beneficiary, or procurement purpose."
    ),
    "ADMINISTRATIVE_VERSION_OR_RECTIFICATIF": (
        "The candidate is a rectificatif, notice version/update, cancellation/correction, or same "
        "procedure update rather than a distinct successor contract."
    ),
    "SAME_BUYER_BROAD_DIGITAL_SIGNAL": (
        "The apparent match is mainly driven by same buyer plus generic digital/procurement language."
    ),
    "HIGH_BUYER_ACTIVITY_AMBIGUITY": (
        "The buyer has many in-scope notices or the source has many candidates, creating many plausible "
        "same-buyer distractors."
    ),
    "NAME_FALLBACK_IDENTITY_RISK": (
        "The pair is blocked by buyer-name fallback rather than a stronger SIRET/SIREN identity."
    ),
    "HIGH_CPV_FALSE_SECURITY": (
        "The CPV score is high even though the manual label says the procurement objects differ."
    ),
    "LOW_TEXT_EVIDENCE": (
        "TF-IDF text similarity is low, so the accepted link lacks strong text evidence."
    ),
    "SMALL_MARGIN_AMBIGUITY": (
        "The top candidate is close to the runner-up; acceptance depends on an ambiguous ranking."
    ),
    "METHOD_DISAGREEMENT_FALSE_POSITIVE": (
        "Only one maintained method linked the source, and the reviewed proposed link was wrong."
    ),
}


def _as_number(frame: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _text_blob(frame: pd.DataFrame) -> pd.Series:
    parts = []
    for col in TEXT_COLS:
        if col in frame.columns:
            parts.append(frame[col].fillna("").astype(str))
    return pd.concat(parts, axis=1).agg(" ".join, axis=1).str.lower()


def add_failure_flags(df: pd.DataFrame) -> pd.DataFrame:
    out = _as_number(df, FEATURES)
    text = _text_blob(out)
    wrong = out["reviewer_label"].eq("WRONG_LINK")
    gbm_linked = out["gbm_decision"].eq("LINKED")
    composite_linked = out["composite_decision"].eq("LINKED")

    out["failure_material_scope_mismatch"] = wrong & (
        text.str.contains("materially different|concrete functions|procurement purpose|different", regex=True)
    )
    out["failure_administrative_version_or_rectificatif"] = wrong & (
        text.str.contains(
            "rectificatif|changed notice|version 0|version|notice update|corrected version|same procedure",
            regex=True,
        )
    )
    out["failure_same_buyer_broad_digital_signal"] = wrong & (
        text.str.contains("same buyer|broad digital|broad digital/cpv|generic wording|cpv similarity", regex=True)
    )
    out["failure_high_buyer_activity_ambiguity"] = wrong & (
        out["buyer_n_sources"].ge(20) | out["n_candidates_for_source"].ge(10)
    )
    out["failure_name_fallback_identity_risk"] = wrong & out["buyer_key_type"].eq("NAME_FALLBACK")
    out["failure_high_cpv_false_security"] = wrong & out["s_cpv"].ge(0.8)
    out["failure_low_text_evidence"] = wrong & out["s_text"].lt(0.20)
    out["failure_small_margin_ambiguity"] = wrong & out["top1_top2_margin"].lt(0.05)
    out["failure_method_disagreement_false_positive"] = wrong & (gbm_linked ^ composite_linked)

    flag_cols = [c for c in out.columns if c.startswith("failure_") and out[c].dtype == bool]
    out["n_failure_modes"] = out[flag_cols].sum(axis=1).astype(int)
    out["failure_modes"] = out.apply(
        lambda row: ";".join(
            col.removeprefix("failure_").upper()
            for col in flag_cols
            if bool(row[col])
        ),
        axis=1,
    )
    return out


def _failure_mode_summary(flagged: pd.DataFrame) -> pd.DataFrame:
    wrong = flagged[flagged["reviewer_label"].eq("WRONG_LINK")].copy()
    rows = []
    for col in _failure_flag_columns(flagged):
        mode = col.removeprefix("failure_").upper()
        sub = wrong[wrong[col]]
        rows.append(
            {
                "failure_mode": mode,
                "description": FAILURE_MODE_DEFINITIONS.get(mode, ""),
                "n_wrong_links": int(len(sub)),
                "share_wrong_links": len(sub) / len(wrong) if len(wrong) else np.nan,
                "median_s_text": sub["s_text"].median(),
                "median_s_cpv": sub["s_cpv"].median(),
                "median_composite_score": sub["composite_score"].median(),
                "median_gbm_score": sub["gbm_score"].median(),
                "median_margin": sub["top1_top2_margin"].median(),
                "median_n_candidates": sub["n_candidates_for_source"].median(),
                "median_buyer_n_sources": sub["buyer_n_sources"].median(),
            }
        )
    return pd.DataFrame(rows).sort_values(["n_wrong_links", "failure_mode"], ascending=[False, True])


def _feature_summary_by_label(flagged: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for label, sub in flagged.groupby("reviewer_label", dropna=False):
        row = {"reviewer_label": label, "n_cases": int(len(sub))}
        for col in FEATURES:
            if col in sub.columns:
                row[f"{col}_median"] = sub[col].median()
                row[f"{col}_q25"] = sub[col].quantile(0.25)
                row[f"{col}_q75"] = sub[col].quantile(0.75)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("reviewer_label")


def _method_failure_summary(flagged: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for method, decision_col in [("primary_gbm", "gbm_decision"), ("composite_balanced", "composite_decision")]:
        linked = flagged[flagged[decision_col].eq("LINKED")]
        determinate = linked[linked["reviewer_label"].isin(["CORRECT_LINK", "WRONG_LINK"])]
        correct = int(determinate["reviewer_label"].eq("CORRECT_LINK").sum())
        wrong = int(determinate["reviewer_label"].eq("WRONG_LINK").sum())
        rows.append(
            {
                "method": method,
                "linked_reviewed": int(len(linked)),
                "determinate_link_reviews": int(len(determinate)),
                "correct_links": correct,
                "wrong_links": wrong,
                "diagnostic_precision": correct / (correct + wrong) if (correct + wrong) else np.nan,
                "insufficient_link_reviews": int(linked["reviewer_label"].eq("INSUFFICIENT_INFORMATION").sum()),
            }
        )
    return pd.DataFrame(rows)


def _stratum_failure_summary(flagged: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for stratum, sub in flagged.groupby("audit_stratum", dropna=False):
        wrong = sub[sub["reviewer_label"].eq("WRONG_LINK")]
        row = {
            "audit_stratum": stratum,
            "n_cases": int(len(sub)),
            "n_wrong_links": int(len(wrong)),
            "wrong_share": len(wrong) / len(sub) if len(sub) else np.nan,
        }
        for col in _failure_flag_columns(flagged):
            row[col.removeprefix("failure_")] = int(wrong[col].sum())
        rows.append(row)
    return pd.DataFrame(rows).sort_values(["n_wrong_links", "audit_stratum"], ascending=[False, True])


def _repair_signal_summary(flagged: pd.DataFrame) -> pd.DataFrame:
    linked = flagged[
        flagged["reviewer_label"].isin(["CORRECT_LINK", "WRONG_LINK"])
        & (flagged["gbm_decision"].eq("LINKED") | flagged["composite_decision"].eq("LINKED"))
    ].copy()
    rules = [
        ("s_text >= 0.20", linked["s_text"].ge(0.20)),
        ("s_text >= 0.30", linked["s_text"].ge(0.30)),
        ("s_text >= 0.40", linked["s_text"].ge(0.40)),
        ("s_cpv >= 0.80", linked["s_cpv"].ge(0.80)),
        ("top1_top2_margin >= 0.05", linked["top1_top2_margin"].ge(0.05)),
        ("buyer_key_type != NAME_FALLBACK", linked["buyer_key_type"].ne("NAME_FALLBACK")),
        ("n_candidates_for_source < 10", linked["n_candidates_for_source"].lt(10)),
        ("buyer_n_sources < 20", linked["buyer_n_sources"].lt(20)),
        ("not administrative version/rectificatif", ~linked["failure_administrative_version_or_rectificatif"]),
    ]
    rows = []
    for rule_name, mask in rules:
        kept = linked[mask.fillna(False)]
        correct = int(kept["reviewer_label"].eq("CORRECT_LINK").sum())
        wrong = int(kept["reviewer_label"].eq("WRONG_LINK").sum())
        rows.append(
            {
                "candidate_repair_filter": rule_name,
                "reviewed_links_kept": int(len(kept)),
                "correct_links_kept": correct,
                "wrong_links_kept": wrong,
                "diagnostic_precision_if_filter_used_alone": correct / (correct + wrong) if (correct + wrong) else np.nan,
                "wrong_links_removed": int(linked["reviewer_label"].eq("WRONG_LINK").sum() - wrong),
                "correct_links_removed": int(linked["reviewer_label"].eq("CORRECT_LINK").sum() - correct),
            }
        )
    return pd.DataFrame(rows)


def _failure_flag_columns(frame: pd.DataFrame) -> list[str]:
    return [c for c in frame.columns if c.startswith("failure_") and frame[c].dtype == bool]


def _markdown_table(df: pd.DataFrame, max_rows: int | None = None) -> str:
    if max_rows is not None:
        df = df.head(max_rows)
    if df.empty:
        return "_No rows._"
    cols = list(df.columns)
    rows = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for record in df.fillna("").astype(str).to_dict(orient="records"):
        rows.append("| " + " | ".join(record[c].replace("|", "\\|") for c in cols) + " |")
    return "\n".join(rows)


def _write_report(
    flagged: pd.DataFrame,
    failure_modes: pd.DataFrame,
    methods: pd.DataFrame,
    repair_signals: pd.DataFrame,
    stratum_summary: pd.DataFrame,
    path: Path,
) -> None:
    wrong = flagged[flagged["reviewer_label"].eq("WRONG_LINK")]
    correct = flagged[flagged["reviewer_label"].eq("CORRECT_LINK")]
    high_conf_wrong = wrong[wrong["reviewer_confidence"].eq("HIGH")]
    admin_wrong = wrong[wrong["failure_administrative_version_or_rectificatif"]]
    scope_wrong = wrong[wrong["failure_material_scope_mismatch"]]

    text = f"""# Manual Audit Failure Analysis

Generated at UTC: `{datetime.now(timezone.utc).isoformat()}`

Input: `reports/tables/manual_audit/real_audit_validated_labels.csv`

## Verdict

The completed 100-case audit identifies a serious synthetic-to-real transfer
problem for accepted links. Among the reviewed determinate accepted-link cases,
the dominant failure is not weak chronology; it is substantive mismatch: the
same buyer issues several digital procurements, and the linker often treats a
different software, equipment, lot, beneficiary, or administrative notice update
as a renewal.

This is a diagnostic, stratified audit. It should drive rule repair and the next
weighted validation sample, not a final population precision/recall claim.

## Headline Counts

- Wrong links: `{len(wrong)}`
- Correct links: `{len(correct)}`
- High-confidence wrong links: `{len(high_conf_wrong)}`
- Wrong links flagged as material scope mismatch: `{len(scope_wrong)}`
- Wrong links flagged as administrative version/rectificatif: `{len(admin_wrong)}`

## Method-Level Diagnostic Precision

{_markdown_table(methods)}

## Failure Modes Among Wrong Links

{_markdown_table(failure_modes[["failure_mode", "n_wrong_links", "share_wrong_links", "median_s_text", "median_s_cpv", "median_margin", "median_n_candidates", "median_buyer_n_sources"]])}

## Stratum-Level Pattern

{_markdown_table(stratum_summary)}

## Single-Filter Repair Signals

These are univariate diagnostics only. Do not freeze a new rule from these
alone; use them to define a repair candidate and then validate it on a new
probability-designed audit sample.

{_markdown_table(repair_signals)}

## Immediate Scientific Interpretation

1. Same-buyer blocking is necessary but insufficient. High-activity buyers
   generate many false same-buyer candidates.
2. CPV agreement is not specific enough for real renewal evidence. Several
   wrong links have high CPV similarity.
3. The models over-trust broad digital language and administrative continuity.
4. `NAME_FALLBACK` identity is a major risk surface in the reviewed failures.
5. eForms versions and rectificatifs need explicit exclusion or down-weighting
   before treating a link as a survival event.

## Recommended Repair Direction

- Add an administrative-update exclusion feature/rule for rectificatifs,
  same-procedure versions, changed-notice references, and cancellation/update
  notices.
- Make text evidence stricter for accepted events, especially when buyer
  identity is `NAME_FALLBACK` or buyer activity is high.
- Penalize high candidate-count/high buyer-activity cases unless the text/CPV
  evidence is very specific.
- Treat CPV as supporting evidence only; do not let high CPV compensate for
  low text similarity and generic same-buyer context.
- After repair, draw a new validation sample with saved stratum populations and
  inclusion probabilities.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    cfg = load_config(ROOT)
    source = cfg.paths.manual_audit_validated_labels
    out_dir = cfg.paths.manual_audit_failure_analysis_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(source, low_memory=False)
    flagged = add_failure_flags(df)
    failure_modes = _failure_mode_summary(flagged)
    feature_summary = _feature_summary_by_label(flagged)
    methods = _method_failure_summary(flagged)
    stratum_summary = _stratum_failure_summary(flagged)
    repair_signals = _repair_signal_summary(flagged)

    flagged.to_csv(out_dir / "manual_audit_cases_with_failure_flags.csv", index=False)
    failure_modes.to_csv(out_dir / "wrong_link_failure_mode_summary.csv", index=False)
    feature_summary.to_csv(out_dir / "feature_summary_by_manual_label.csv", index=False)
    methods.to_csv(out_dir / "method_diagnostic_precision.csv", index=False)
    stratum_summary.to_csv(out_dir / "stratum_failure_summary.csv", index=False)
    repair_signals.to_csv(out_dir / "single_filter_repair_signals.csv", index=False)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input": str(source.relative_to(ROOT)),
        "n_cases": int(len(flagged)),
        "n_wrong_links": int(flagged["reviewer_label"].eq("WRONG_LINK").sum()),
        "n_correct_links": int(flagged["reviewer_label"].eq("CORRECT_LINK").sum()),
        "failure_mode_definitions": FAILURE_MODE_DEFINITIONS,
        "scientific_caveat": (
            "Stratified/purposive audit; outputs are diagnostic and repair-oriented, "
            "not final population precision/recall estimates."
        ),
    }
    (out_dir / "failure_analysis_manifest.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    _write_report(flagged, failure_modes, methods, repair_signals, stratum_summary, cfg.paths.manual_audit_failure_analysis_report)

    print(f"WROTE {out_dir.relative_to(ROOT)}")
    print(f"WROTE {cfg.paths.manual_audit_failure_analysis_report.relative_to(ROOT)}")
    print(failure_modes[['failure_mode', 'n_wrong_links', 'share_wrong_links']].to_string(index=False))


if __name__ == "__main__":
    main()
