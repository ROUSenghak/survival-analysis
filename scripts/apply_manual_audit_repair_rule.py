"""Apply manual-audit-informed linkage repair rule v1 to real BOAMP.

This script does not finalize the real linkage method. It creates provisional
repair candidates after the first manual audit showed that accepted links were
dominated by material scope mismatches and administrative update/version cases.

Rule v1 keeps a link only when it already passes a maintained linker and:

* source and candidate notices are both BOAMP `INITIAL`;
* neither notice explicitly references the other through `annonce_lie`;
* both source and candidate object texts have at least four tokens;
* TF-IDF cosine text similarity `s_text` is at least 0.30.

The thresholds are motivated by the completed stratified audit and must be
validated on a fresh probability-designed audit sample before any final
precision/recall or survival claims.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.config import load_config  # noqa: E402
from boamp.linkage.links import assign_confidence_tier, build_links  # noqa: E402
from boamp.survival.datasets import build_survival_dataset  # noqa: E402


GBM_THRESHOLD = 0.2309637726207583
TEXT_MIN = 0.30
MIN_TOKEN_COUNT = 4
RULE_VERSION = "manual_audit_repair_v1_text030_initial_no_linked_ref_min4tokens"


def _read_csv_drop_header_rows(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    for col in ["source_notice_id", "notice_id"]:
        if col in df.columns:
            df = df[df[col].astype(str).ne(col)].copy()
    return df


def _numeric(frame: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = frame.copy()
    for col in cols:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _attrs() -> pd.DataFrame:
    cols = [
        "notice_id",
        "etat",
        "schema_family",
        "annonce_lie",
        "token_count",
        "text_length",
        "notice_type_normalized",
        "objet_clean",
    ]
    return pd.read_csv(ROOT / "data/interim/boamp_common_prepared.csv", usecols=cols, low_memory=False)


def add_repair_features(links: pd.DataFrame, attrs: pd.DataFrame) -> pd.DataFrame:
    out = links.copy()
    out = out.merge(attrs.add_prefix("source_"), left_on="source_notice_id", right_on="source_notice_id", how="left")
    out = out.merge(
        attrs.add_prefix("candidate_"),
        left_on="candidate_notice_id",
        right_on="candidate_notice_id",
        how="left",
    )
    out = _numeric(
        out,
        [
            "s_text",
            "s_cpv",
            "s_time",
            "s_buyer",
            "composite_score",
            "gradient_boosting_score",
            "transfer_score",
            "top1_top2_margin",
            "n_candidates_for_source",
            "source_token_count",
            "candidate_token_count",
        ],
    )
    linked_ref = (
        out["candidate_annonce_lie"].astype(str).eq(out["source_notice_id"].astype(str))
        | out["source_annonce_lie"].astype(str).eq(out["candidate_notice_id"].astype(str))
    )
    out["repair_pass_text_min"] = out["s_text"].ge(TEXT_MIN)
    out["repair_pass_initial_source"] = out["source_etat"].eq("INITIAL")
    out["repair_pass_initial_candidate"] = out["candidate_etat"].eq("INITIAL")
    out["repair_pass_no_explicit_linked_notice_ref"] = ~linked_ref
    out["repair_pass_min_token_count"] = out["source_token_count"].ge(MIN_TOKEN_COUNT) & out[
        "candidate_token_count"
    ].ge(MIN_TOKEN_COUNT)
    pass_cols = [c for c in out.columns if c.startswith("repair_pass_")]
    out["repair_rule_pass"] = out[pass_cols].all(axis=1)
    out["repair_failure_reasons"] = out.apply(
        lambda row: ";".join(c.removeprefix("repair_pass_").upper() for c in pass_cols if not bool(row[c])),
        axis=1,
    )
    out["repair_rule_version"] = RULE_VERSION
    return out


def _base_composite_links(cfg) -> pd.DataFrame:
    pairs = _read_csv_drop_header_rows(ROOT / "reports/tables/real_linkage_freeze/real_candidate_pairs_reproduced.csv")
    pairs = _numeric(
        pairs,
        ["candidate_rank", "composite_score", "s_text", "s_cpv", "s_time", "s_buyer", "top1_top2_margin"],
    )
    return build_links(pairs, cfg.pipeline.thresholds.balanced, "baseline_composite_balanced", cfg)


def _base_gbm_links() -> pd.DataFrame:
    return _read_csv_drop_header_rows(ROOT / "reports/tables/real_linkage_freeze/real_primary_gbm_links.csv")


def _apply_repair(base: pd.DataFrame, method: str, attrs: pd.DataFrame, cfg) -> pd.DataFrame:
    enriched = add_repair_features(base, attrs)
    repaired = enriched[enriched["repair_rule_pass"]].copy()
    repaired["variant"] = f"{method}_{RULE_VERSION}"
    repaired["rule_role"] = (
        "preferred_repair_candidate_for_fresh_validation"
        if method == "composite_balanced"
        else "gbm_repair_comparator_for_fresh_validation"
    )
    if "transfer_score" not in repaired.columns and "gradient_boosting_score" in repaired.columns:
        repaired["transfer_score"] = repaired["gradient_boosting_score"]
    if "confidence_tier" not in repaired.columns:
        tier_frame = repaired.copy()
        repaired["confidence_tier"] = assign_confidence_tier(tier_frame, cfg)
    return repaired


def _audit_diagnostic_for_rule(method: str) -> dict:
    audit = pd.read_csv(ROOT / "reports/tables/manual_audit/real_audit_validated_labels.csv", low_memory=False)
    attrs = _attrs()
    audit = audit.merge(attrs.add_prefix("source_"), left_on="source_notice_id", right_on="source_notice_id", how="left")
    audit = audit.merge(
        attrs.add_prefix("candidate_"), left_on="candidate_notice_id", right_on="candidate_notice_id", how="left"
    )
    audit = _numeric(
        audit,
        ["s_text", "source_token_count", "candidate_token_count", "top1_top2_margin", "composite_score", "gbm_score"],
    )
    linked_col = "composite_decision" if method == "composite_balanced" else "gbm_decision"
    linked_ref = (
        audit["candidate_annonce_lie"].astype(str).eq(audit["source_notice_id"].astype(str))
        | audit["source_annonce_lie"].astype(str).eq(audit["candidate_notice_id"].astype(str))
    )
    determinate = audit["reviewer_label"].isin(["CORRECT_LINK", "WRONG_LINK"])
    rule = (
        audit[linked_col].eq("LINKED")
        & audit["s_text"].ge(TEXT_MIN)
        & audit["source_etat"].eq("INITIAL")
        & audit["candidate_etat"].eq("INITIAL")
        & (~linked_ref)
        & audit["source_token_count"].ge(MIN_TOKEN_COUNT)
        & audit["candidate_token_count"].ge(MIN_TOKEN_COUNT)
        & determinate
    )
    kept = audit[rule]
    correct = int(kept["reviewer_label"].eq("CORRECT_LINK").sum())
    wrong = int(kept["reviewer_label"].eq("WRONG_LINK").sum())
    base = audit[audit[linked_col].eq("LINKED") & determinate]
    return {
        "method": method,
        "reviewed_determinate_linked_before_repair": int(len(base)),
        "reviewed_correct_before_repair": int(base["reviewer_label"].eq("CORRECT_LINK").sum()),
        "reviewed_wrong_before_repair": int(base["reviewer_label"].eq("WRONG_LINK").sum()),
        "reviewed_determinate_linked_after_repair": int(len(kept)),
        "reviewed_correct_after_repair": correct,
        "reviewed_wrong_after_repair": wrong,
        "diagnostic_precision_after_repair_same_audit": correct / (correct + wrong) if (correct + wrong) else np.nan,
        "wrong_reviewed_links_removed": int(base["reviewer_label"].eq("WRONG_LINK").sum() - wrong),
        "correct_reviewed_links_removed": int(base["reviewer_label"].eq("CORRECT_LINK").sum() - correct),
    }


def _summary_row(method: str, base: pd.DataFrame, repaired: pd.DataFrame, sources: pd.DataFrame) -> dict:
    eligible_n = int(sources[sources["buyer_key_type"].ne("MISSING")].shape[0])
    return {
        "method": method,
        "base_links": int(len(base)),
        "repaired_links": int(len(repaired)),
        "base_link_rate": len(base) / eligible_n if eligible_n else np.nan,
        "repaired_link_rate": len(repaired) / eligible_n if eligible_n else np.nan,
        "links_removed": int(len(base) - len(repaired)),
        "median_s_text_repaired": repaired["s_text"].median() if len(repaired) else np.nan,
        "median_composite_score_repaired": repaired["composite_score"].median() if len(repaired) else np.nan,
        "median_margin_repaired": repaired["top1_top2_margin"].median() if len(repaired) else np.nan,
    }


def _drop_extra_attr_cols(frame: pd.DataFrame) -> pd.DataFrame:
    # Keep source/candidate administrative fields because they justify the rule;
    # drop long duplicated text columns from link outputs.
    drop_cols = [c for c in frame.columns if c.endswith("_objet_clean")]
    return frame.drop(columns=drop_cols, errors="ignore")


def main() -> None:
    cfg = load_config(ROOT)
    out_dir = cfg.paths.real_linkage_repair_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    attrs = _attrs()
    sources = _read_csv_drop_header_rows(ROOT / "data/processed/boamp_only/boamp_only_sources.csv")
    for col in ["publication_date", "start_date", "estimated_end_date", "study_end_date"]:
        if col in sources.columns:
            sources[col] = pd.to_datetime(sources[col], errors="coerce")

    base_gbm = _base_gbm_links()
    base_composite = _base_composite_links(cfg)
    repaired_gbm = _apply_repair(base_gbm, "primary_gbm", attrs, cfg)
    repaired_composite = _apply_repair(base_composite, "composite_balanced", attrs, cfg)

    repaired_gbm = _drop_extra_attr_cols(repaired_gbm)
    repaired_composite = _drop_extra_attr_cols(repaired_composite)
    repaired_gbm.to_csv(out_dir / f"primary_gbm_{RULE_VERSION}_links.csv", index=False)
    repaired_composite.to_csv(out_dir / f"composite_balanced_{RULE_VERSION}_links.csv", index=False)

    extra_cols = [
        "repair_rule_version",
        "rule_role",
        "repair_failure_reasons",
        "source_etat",
        "candidate_etat",
        "source_annonce_lie",
        "candidate_annonce_lie",
        "source_token_count",
        "candidate_token_count",
        "gradient_boosting_score",
        "transfer_score",
        "threshold_used",
        "model_name",
        "benchmark_version",
        "threshold_source",
    ]
    survival_gbm = build_survival_dataset(
        sources,
        repaired_gbm,
        f"primary_gbm_{RULE_VERSION}",
        cfg,
        extra_link_cols=extra_cols,
    )
    survival_composite = build_survival_dataset(
        sources,
        repaired_composite,
        f"composite_balanced_{RULE_VERSION}",
        cfg,
        extra_link_cols=extra_cols,
    )
    survival_gbm.to_csv(
        ROOT / f"data/processed/boamp_only/boamp_only_survival_primary_gbm_{RULE_VERSION}.csv",
        index=False,
    )
    survival_composite.to_csv(
        ROOT / f"data/processed/boamp_only/boamp_only_survival_composite_balanced_{RULE_VERSION}.csv",
        index=False,
    )

    method_summary = pd.DataFrame(
        [
            _summary_row("primary_gbm", base_gbm, repaired_gbm, sources),
            _summary_row("composite_balanced", base_composite, repaired_composite, sources),
        ]
    )
    audit_diagnostic = pd.DataFrame(
        [
            _audit_diagnostic_for_rule("primary_gbm"),
            _audit_diagnostic_for_rule("composite_balanced"),
        ]
    )
    method_summary.to_csv(out_dir / "repair_rule_v1_real_link_summary.csv", index=False)
    audit_diagnostic.to_csv(out_dir / "repair_rule_v1_audit_diagnostic.csv", index=False)
    _write_rule_audit(base_gbm, repaired_gbm, out_dir / "primary_gbm_repair_rule_v1_audit.csv")
    _write_rule_audit(base_composite, repaired_composite, out_dir / "composite_balanced_repair_rule_v1_audit.csv")
    manifest = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "rule_version": RULE_VERSION,
        "rule_status": "REPAIR_CANDIDATE_REQUIRES_FRESH_VALIDATION",
        "text_min": TEXT_MIN,
        "min_token_count": MIN_TOKEN_COUNT,
        "criteria": [
            "base maintained method accepts the link",
            "source_etat == INITIAL",
            "candidate_etat == INITIAL",
            "candidate_annonce_lie does not point to source and source_annonce_lie does not point to candidate",
            "source_token_count >= 4",
            "candidate_token_count >= 4",
            "s_text >= 0.30",
        ],
        "preferred_candidate_for_next_validation": "composite_balanced",
        "scientific_caveat": (
            "This rule was motivated by the completed stratified audit. Its same-audit diagnostics are "
            "not final precision estimates. A fresh probability-designed validation sample is required."
        ),
        "outputs": {
            "primary_gbm_links": str((out_dir / f"primary_gbm_{RULE_VERSION}_links.csv").relative_to(ROOT)),
            "composite_links": str((out_dir / f"composite_balanced_{RULE_VERSION}_links.csv").relative_to(ROOT)),
            "summary": str((out_dir / "repair_rule_v1_real_link_summary.csv").relative_to(ROOT)),
            "audit_diagnostic": str((out_dir / "repair_rule_v1_audit_diagnostic.csv").relative_to(ROOT)),
        },
    }
    (out_dir / "repair_rule_v1_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    _write_report(method_summary, audit_diagnostic, cfg.paths.manual_audit_repair_rule_report)
    print(f"WROTE {out_dir.relative_to(ROOT)}")
    print(f"WROTE {cfg.paths.manual_audit_repair_rule_report.relative_to(ROOT)}")
    print(method_summary.to_string(index=False))
    print(audit_diagnostic.to_string(index=False))


def _write_rule_audit(base: pd.DataFrame, repaired: pd.DataFrame, path: Path) -> None:
    base_enriched = add_repair_features(base, _attrs())
    cols = [
        "source_notice_id",
        "candidate_notice_id",
        "repair_rule_pass",
        "repair_failure_reasons",
        "s_text",
        "s_cpv",
        "composite_score",
        "gradient_boosting_score",
        "top1_top2_margin",
        "source_etat",
        "candidate_etat",
        "source_annonce_lie",
        "candidate_annonce_lie",
        "source_token_count",
        "candidate_token_count",
    ]
    base_enriched[[c for c in cols if c in base_enriched.columns]].to_csv(path, index=False)


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    cols = list(df.columns)
    rows = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for record in df.fillna("").astype(str).to_dict(orient="records"):
        rows.append("| " + " | ".join(record[c].replace("|", "\\|") for c in cols) + " |")
    return "\n".join(rows)


def _write_report(summary: pd.DataFrame, audit: pd.DataFrame, path: Path) -> None:
    text = f"""# Manual-Audit Repair Rule v1

Generated at UTC: `{datetime.now(timezone.utc).isoformat()}`

Rule version: `{RULE_VERSION}`

## Verdict

The first completed manual audit showed that the existing accepted-link rules
transfer poorly to real BOAMP. Repair rule v1 is a conservative, interpretable
candidate designed to remove the dominant observed failure modes before building
new validation material.

This is **not** the final real-BOAMP linkage rule. It was derived after looking
at the first audit, so its same-audit diagnostic performance is optimistic until
validated on a fresh probability-designed sample.

## Rule

Keep a link only if the maintained method already accepted it and all conditions
hold:

- `s_text >= {TEXT_MIN}`;
- `source_etat == INITIAL`;
- `candidate_etat == INITIAL`;
- no explicit `annonce_lie` reference between source and candidate;
- source and candidate object texts each have at least `{MIN_TOKEN_COUNT}` tokens.

## Real BOAMP Link Counts

{_markdown_table(summary)}

## Same-Audit Diagnostic

{_markdown_table(audit)}

## Interpretation

The preferred repair candidate for fresh validation is
`composite_balanced_{RULE_VERSION}` because it preserved more manually confirmed
correct links in the diagnostic audit than the GBM repair while removing most
wrong reviewed links.

Do not use this same-audit diagnostic as final precision. The next step is a
new validation sample with saved stratum populations and inclusion weights.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
