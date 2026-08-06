"""Validate the completed real-BOAMP manual audit workbook.

The uploaded XLSX is treated as human evidence. This script extracts the Review
sheet without requiring openpyxl, checks the controlled label vocabulary, compares
case IDs against the generated audit package, and writes canonical derived CSV
and report artifacts. It does not infer labels or modify the workbook.
"""

from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZipFile

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.config import load_config  # noqa: E402
from boamp.status import MANUAL_AUDIT_LABELS  # noqa: E402

NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_NS = {"rel": "http://schemas.openxmlformats.org/package/2006/relationships"}
RID = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

REQUIRED_COLUMNS = {
    "case_id",
    "audit_stratum",
    "reviewer_label",
    "reviewer_confidence",
    "needs_second_review",
    "review_date",
    "reviewer_notes",
    "source_notice_id",
    "candidate_notice_id",
    "gbm_decision",
    "composite_decision",
}
ALLOWED_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}
ALLOWED_SECOND_REVIEW = {"", "TRUE", "FALSE"}


def _column_index(cell_reference: str) -> int:
    letters = "".join(ch for ch in cell_reference if ch.isalpha())
    idx = 0
    for ch in letters:
        idx = idx * 26 + ord(ch.upper()) - 64
    return idx - 1


def _target_path(target: str) -> str:
    target = target.lstrip("/")
    return target if target.startswith("xl/") else f"xl/{target}"


def _shared_strings(zf: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in zf.namelist():
        return []
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    return ["".join(t.text or "" for t in si.findall(".//a:t", NS)) for si in root.findall("a:si", NS)]


def _cell_text(cell: ET.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(t.text or "" for t in cell.findall(".//a:t", NS))
    value = cell.find("a:v", NS)
    if value is None:
        return ""
    text = value.text or ""
    if cell_type == "s" and text:
        return shared_strings[int(text)]
    return text


def read_xlsx_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    with ZipFile(path) as zf:
        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        relmap = {r.attrib["Id"]: r.attrib["Target"] for r in rels.findall("rel:Relationship", REL_NS)}
        shared_strings = _shared_strings(zf)

        sheet_path = None
        for sheet in workbook.findall("a:sheets/a:sheet", {**NS, "r": RID}):
            if sheet.attrib["name"] == sheet_name:
                rel_id = sheet.attrib[f"{{{RID}}}id"]
                sheet_path = _target_path(relmap[rel_id])
                break
        if sheet_path is None:
            raise ValueError(f"Workbook has no {sheet_name!r} sheet")

        root = ET.fromstring(zf.read(sheet_path))
        rows: list[list[str]] = []
        max_col = 0
        for row in root.findall("a:sheetData/a:row", NS):
            cells: dict[int, str] = {}
            for cell in row.findall("a:c", NS):
                idx = _column_index(cell.attrib["r"])
                max_col = max(max_col, idx)
                cells[idx] = _cell_text(cell, shared_strings)
            if cells:
                rows.append([cells.get(i, "") for i in range(max_col + 1)])

    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows[1:], columns=rows[0])


def _clean_review_frame(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        out[col] = out[col].astype(str).str.strip()
        out.loc[out[col].isin({"nan", "None"}), col] = ""
    for col in ["composite_score", "gbm_score", "top1_top2_margin", "n_candidates_for_source"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def _rate(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _label_counts(df: pd.DataFrame) -> pd.DataFrame:
    counts = df["reviewer_label"].value_counts().reindex(sorted(MANUAL_AUDIT_LABELS), fill_value=0)
    return counts.rename_axis("reviewer_label").reset_index(name="n_cases")


def _stratum_summary(df: pd.DataFrame) -> pd.DataFrame:
    table = (
        df.pivot_table(
            index="audit_stratum",
            columns="reviewer_label",
            values="case_id",
            aggfunc="count",
            fill_value=0,
        )
        .reindex(columns=sorted(MANUAL_AUDIT_LABELS), fill_value=0)
        .reset_index()
    )
    table["n_cases"] = table[list(sorted(MANUAL_AUDIT_LABELS))].sum(axis=1)
    return table


def _decision_summary(df: pd.DataFrame, decision_col: str) -> dict:
    linked = df[decision_col].eq("LINKED")
    linked_known = linked & df["reviewer_label"].isin({"CORRECT_LINK", "WRONG_LINK"})
    correct = int((linked_known & df["reviewer_label"].eq("CORRECT_LINK")).sum())
    wrong = int((linked_known & df["reviewer_label"].eq("WRONG_LINK")).sum())
    not_linked = df[decision_col].isin({"NOT_LINKED", "NO_CANDIDATE"})
    rejection_known = not_linked & df["reviewer_label"].isin({"CORRECT_REJECTION", "MISSED_LINK"})
    correct_rejection = int((rejection_known & df["reviewer_label"].eq("CORRECT_REJECTION")).sum())
    missed = int((rejection_known & df["reviewer_label"].eq("MISSED_LINK")).sum())
    return {
        "method_decision_column": decision_col,
        "linked_reviewed": int(linked.sum()),
        "linked_known_correct_or_wrong": int(linked_known.sum()),
        "correct_links": correct,
        "wrong_links": wrong,
        "diagnostic_precision_excluding_insufficient": _rate(correct, correct + wrong),
        "not_linked_or_no_candidate_reviewed": int(not_linked.sum()),
        "rejection_known_correct_or_missed": int(rejection_known.sum()),
        "correct_rejections": correct_rejection,
        "missed_links": missed,
        "diagnostic_rejection_correct_rate_excluding_insufficient": _rate(
            correct_rejection, correct_rejection + missed
        ),
    }


def main() -> None:
    cfg = load_config(ROOT)
    workbook = cfg.paths.manual_audit_validated_workbook
    out_csv = cfg.paths.manual_audit_validated_labels
    out_dir = out_csv.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    review = _clean_review_frame(read_xlsx_sheet(workbook, "Review"))
    missing_columns = sorted(REQUIRED_COLUMNS - set(review.columns))
    labels = review["reviewer_label"].astype(str).str.strip() if "reviewer_label" in review else pd.Series(dtype=str)
    unknown_labels = sorted(set(labels[labels.ne("")]) - MANUAL_AUDIT_LABELS)
    blank_labels = int(labels.eq("").sum()) if len(labels) else 0
    duplicate_case_ids = sorted(
        review.loc[review["case_id"].duplicated(keep=False), "case_id"].astype(str).unique()
    ) if "case_id" in review else []
    unknown_confidence = sorted(
        set(review["reviewer_confidence"].dropna().astype(str).str.strip()) - ALLOWED_CONFIDENCE - {""}
    ) if "reviewer_confidence" in review else []
    unknown_second_review = sorted(
        set(review["needs_second_review"].dropna().astype(str).str.strip()) - ALLOWED_SECOND_REVIEW
    ) if "needs_second_review" in review else []

    original_path = ROOT / "reports/tables/real_linkage_freeze/real_audit_sample_100.csv"
    missing_original_case_ids: list[str] = []
    extra_case_ids: list[str] = []
    missing_original_source_ids: list[str] = []
    extra_source_ids: list[str] = []
    if original_path.exists() and "case_id" in review:
        original = pd.read_csv(original_path, dtype=str).fillna("")
        if "case_id" in original:
            original_case_ids = set(original["case_id"].astype(str))
            review_case_ids = set(review["case_id"].astype(str))
            missing_original_case_ids = sorted(original_case_ids - review_case_ids)
            extra_case_ids = sorted(review_case_ids - original_case_ids)
        elif "source_notice_id" in original and "source_notice_id" in review:
            original_source_ids = set(original["source_notice_id"].astype(str))
            review_source_ids = set(review["source_notice_id"].astype(str))
            missing_original_source_ids = sorted(original_source_ids - review_source_ids)
            extra_source_ids = sorted(review_source_ids - original_source_ids)

    checks = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_workbook": str(workbook.relative_to(ROOT)),
        "source_workbook_sha256": _sha256(workbook),
        "n_review_rows": int(len(review)),
        "n_labeled_rows": int(labels.ne("").sum()) if len(labels) else 0,
        "missing_columns": missing_columns,
        "blank_labels": blank_labels,
        "unknown_labels": unknown_labels,
        "duplicate_case_ids": duplicate_case_ids,
        "unknown_confidence": unknown_confidence,
        "unknown_needs_second_review_values": unknown_second_review,
        "case_ids_missing_from_validated_workbook": missing_original_case_ids,
        "case_ids_not_in_original_sample": extra_case_ids,
        "source_ids_missing_from_validated_workbook": missing_original_source_ids,
        "source_ids_not_in_original_sample": extra_source_ids,
        "label_counts": dict(Counter(labels)),
        "gbm_diagnostic": _decision_summary(review, "gbm_decision") if "gbm_decision" in review else None,
        "composite_diagnostic": (
            _decision_summary(review, "composite_decision") if "composite_decision" in review else None
        ),
        "population_precision_claim_supported": False,
        "population_recall_claim_supported": False,
        "reason_population_claim_not_supported": (
            "The audit sample is stratified/purposive with overlapping strata and no saved inclusion weights. "
            "Use it for transfer diagnostics and failure-mode evidence, not final population precision/recall."
        ),
    }

    hard_failures = [
        bool(missing_columns),
        blank_labels > 0,
        bool(unknown_labels),
        bool(duplicate_case_ids),
        bool(unknown_confidence),
        bool(unknown_second_review),
        bool(missing_original_case_ids),
        bool(extra_case_ids),
        bool(missing_original_source_ids),
        bool(extra_source_ids),
    ]
    checks["validation_status"] = "PASS" if not any(hard_failures) else "FAIL"

    review.to_csv(out_csv, index=False)
    _label_counts(review).to_csv(out_dir / "manual_audit_label_summary.csv", index=False)
    _stratum_summary(review).to_csv(out_dir / "manual_audit_stratum_label_summary.csv", index=False)
    (out_dir / "manual_audit_quality_checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    _write_report(review, checks, cfg.paths.manual_audit_validation_report)
    print(f"WROTE {out_csv.relative_to(ROOT)}")
    print(f"WROTE {(out_dir / 'manual_audit_quality_checks.json').relative_to(ROOT)}")
    print(f"WROTE {cfg.paths.manual_audit_validation_report.relative_to(ROOT)}")
    if checks["validation_status"] != "PASS":
        raise SystemExit(1)


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    import hashlib

    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _fmt_rate(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.3f}"


def _markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    cols = list(df.columns)
    rows = []
    rows.append("| " + " | ".join(str(c) for c in cols) + " |")
    rows.append("| " + " | ".join("---" for _ in cols) + " |")
    for record in df.fillna("").astype(str).to_dict(orient="records"):
        rows.append("| " + " | ".join(record[c].replace("|", "\\|") for c in cols) + " |")
    return "\n".join(rows)


def _write_report(review: pd.DataFrame, checks: dict, path: Path) -> None:
    labels = _label_counts(review)
    strata = _stratum_summary(review)
    gbm = checks["gbm_diagnostic"] or {}
    composite = checks["composite_diagnostic"] or {}

    label_md = _markdown_table(labels)
    stratum_md = _markdown_table(strata)
    text = f"""# Manual Audit Validation Report

Generated at UTC: `{checks['generated_at_utc']}`

Source workbook: `{checks['source_workbook']}`

Validation status: `{checks['validation_status']}`

## Gate Result

The uploaded workbook contains `{checks['n_labeled_rows']}` non-blank manual labels over
`{checks['n_review_rows']}` reviewed cases. The label vocabulary is valid.

This opens the initial manual-audit evidence gate, but it does **not** by itself
support a final population precision/recall claim because the sample is
stratified/purposive and has overlapping strata without saved inclusion weights.

## Label Counts

{label_md}

## Method Diagnostics

GBM linked reviewed cases with determinate link labels:
`{gbm.get('correct_links', 0)}` correct and `{gbm.get('wrong_links', 0)}` wrong,
diagnostic precision `{_fmt_rate(gbm.get('diagnostic_precision_excluding_insufficient'))}`.

Composite linked reviewed cases with determinate link labels:
`{composite.get('correct_links', 0)}` correct and `{composite.get('wrong_links', 0)}` wrong,
diagnostic precision `{_fmt_rate(composite.get('diagnostic_precision_excluding_insufficient'))}`.

GBM not-linked/no-candidate reviewed cases with determinate rejection labels:
`{gbm.get('correct_rejections', 0)}` correct rejections and `{gbm.get('missed_links', 0)}` missed links,
diagnostic rejection-correct rate `{_fmt_rate(gbm.get('diagnostic_rejection_correct_rate_excluding_insufficient'))}`.

Composite not-linked/no-candidate reviewed cases with determinate rejection labels:
`{composite.get('correct_rejections', 0)}` correct rejections and `{composite.get('missed_links', 0)}` missed links,
diagnostic rejection-correct rate `{_fmt_rate(composite.get('diagnostic_rejection_correct_rate_excluding_insufficient'))}`.

## Stratum By Label

{stratum_md}

## Scientific Use

Supported:
- failure-mode analysis;
- qualitative synthetic-to-real transfer assessment;
- deciding whether the provisional linkage rule needs repair before final survival claims;
- designing the next statistically interpretable audit.

Not supported:
- final real BOAMP precision;
- final real BOAMP recall;
- final event/censoring dataset freeze;
- final survival conclusions.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
