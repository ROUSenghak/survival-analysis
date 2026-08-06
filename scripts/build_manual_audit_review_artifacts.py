"""Build reviewer-friendly manual audit artifacts.

Outputs an Excel-compatible XLSX workbook with dropdown labels and a read-only
HTML evidence report from the canonical real BOAMP audit sample.
"""

from __future__ import annotations

import html
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from boamp.status import MANUAL_AUDIT_LABELS

INPUT = ROOT / "reports/tables/real_linkage_freeze/real_audit_sample_100.csv"
OUT_DIR = ROOT / "reports/manual_audit"
XLSX_OUT = OUT_DIR / "real_audit_sample_100.xlsx"
HTML_OUT = OUT_DIR / "real_audit_evidence_100.html"

LABELS = [
    "CORRECT_LINK",
    "WRONG_LINK",
    "MISSED_LINK",
    "CORRECT_REJECTION",
    "INSUFFICIENT_INFORMATION",
]
CONFIDENCE = ["HIGH", "MEDIUM", "LOW"]
YES_NO = ["TRUE", "FALSE"]

REVIEW_COLUMNS = [
    "case_id",
    "audit_stratum",
    "reviewer_label",
    "reviewer_confidence",
    "needs_second_review",
    "review_date",
    "reviewer_notes",
    "source_notice_id",
    "candidate_notice_id",
    "gbm_candidate_notice_id",
    "composite_candidate_notice_id",
    "gbm_decision",
    "composite_decision",
    "buyer_name",
    "buyer_key_type",
    "buyer_n_sources",
    "source_date",
    "candidate_date",
    "gap_months",
    "source_cpv",
    "category_label",
    "duration_imputed",
    "s_text",
    "s_cpv",
    "s_time",
    "s_buyer",
    "composite_score",
    "gbm_score",
    "top1_top2_margin",
    "n_candidates_for_source",
    "source_text",
    "candidate_text",
    "reason_code",
    "rule_version",
    "benchmark_version",
]

WIDTHS = {
    "case_id": 10,
    "audit_stratum": 28,
    "reviewer_label": 28,
    "reviewer_confidence": 20,
    "needs_second_review": 20,
    "review_date": 16,
    "reviewer_notes": 48,
    "source_notice_id": 18,
    "candidate_notice_id": 18,
    "buyer_name": 34,
    "source_text": 70,
    "candidate_text": 70,
}


def main() -> None:
    if not INPUT.exists():
        raise FileNotFoundError(f"manual audit source not found: {INPUT}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    audit = pd.read_csv(INPUT, dtype=str).fillna("")
    audit.insert(0, "case_id", [f"AUDIT-{i:03d}" for i in range(1, len(audit) + 1)])
    for col in REVIEW_COLUMNS:
        if col not in audit.columns:
            audit[col] = ""
    audit = audit[REVIEW_COLUMNS]
    for col in ["reviewer_label", "reviewer_confidence", "reviewer_notes", "review_date", "needs_second_review"]:
        audit[col] = ""

    _write_xlsx(audit, XLSX_OUT)
    _write_html(audit, HTML_OUT)
    print(f"WROTE {XLSX_OUT.relative_to(ROOT)}")
    print(f"WROTE {HTML_OUT.relative_to(ROOT)}")


def _write_xlsx(audit: pd.DataFrame, path: Path) -> None:
    sheets = {
        "Review": _sheet_review(audit),
        "Instructions": _sheet_instructions(),
        "LabelGuide": _sheet_label_guide(),
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _content_types())
        zf.writestr("_rels/.rels", _root_rels())
        zf.writestr("xl/workbook.xml", _workbook_xml(list(sheets)))
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels(list(sheets)))
        zf.writestr("xl/styles.xml", _styles_xml())
        for idx, (name, xml) in enumerate(sheets.items(), start=1):
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", xml)


def _sheet_review(df: pd.DataFrame) -> str:
    rows = [_row_xml(1, df.columns, style=1)]
    for r_idx, row in enumerate(df.itertuples(index=False), start=2):
        style_map = {col: 2 for col in ["reviewer_notes", "source_text", "candidate_text"]}
        rows.append(_row_xml(r_idx, row, columns=df.columns, style_map=style_map))

    col_xml = []
    for idx, col in enumerate(df.columns, start=1):
        width = WIDTHS.get(col, 16)
        col_xml.append(f'<col min="{idx}" max="{idx}" width="{width}" customWidth="1"/>')

    label_col = _col_letter(df.columns.get_loc("reviewer_label") + 1)
    conf_col = _col_letter(df.columns.get_loc("reviewer_confidence") + 1)
    second_col = _col_letter(df.columns.get_loc("needs_second_review") + 1)
    last_row = len(df) + 1
    data_validations = f"""
<dataValidations count="3">
  <dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="{label_col}2:{label_col}{last_row}">
    <formula1>LabelGuide!$A$2:$A$6</formula1>
  </dataValidation>
  <dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="{conf_col}2:{conf_col}{last_row}">
    <formula1>LabelGuide!$B$2:$B$4</formula1>
  </dataValidation>
  <dataValidation type="list" allowBlank="1" showErrorMessage="1" sqref="{second_col}2:{second_col}{last_row}">
    <formula1>LabelGuide!$C$2:$C$3</formula1>
  </dataValidation>
</dataValidations>
""".strip()
    auto_filter = f'<autoFilter ref="A1:{_col_letter(len(df.columns))}{last_row}"/>'
    sheet_views = """
<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
""".strip()
    return _worksheet_xml(
        cols="\n".join(col_xml),
        rows="\n".join(rows),
        extra=f"{auto_filter}\n{data_validations}",
        sheet_views=sheet_views,
    )


def _sheet_instructions() -> str:
    rows = [
        ["Manual Audit Workbook"],
        ["Use the Review sheet to enter labels. The HTML file is easier for reading long evidence text."],
        ["Do not infer correctness from GBM, composite, thresholds, or confidence tier."],
        ["Allowed reviewer_label values are listed on LabelGuide."],
        ["Real precision and recall remain UNKNOWN until human labels are complete."],
        ["An unlinked notice is operationally censored, not a confirmed non-renewal."],
    ]
    xml_rows = [_row_xml(i, row, style=2 if i > 1 else 1) for i, row in enumerate(rows, start=1)]
    return _worksheet_xml(
        cols='<col min="1" max="1" width="120" customWidth="1"/>',
        rows="\n".join(xml_rows),
    )


def _sheet_label_guide() -> str:
    max_len = max(len(LABELS), len(CONFIDENCE), len(YES_NO))
    rows = [["reviewer_label", "reviewer_confidence", "needs_second_review"]]
    for i in range(max_len):
        rows.append([
            LABELS[i] if i < len(LABELS) else "",
            CONFIDENCE[i] if i < len(CONFIDENCE) else "",
            YES_NO[i] if i < len(YES_NO) else "",
        ])
    xml_rows = [_row_xml(i, row, style=1 if i == 1 else 0) for i, row in enumerate(rows, start=1)]
    return _worksheet_xml(
        cols='<col min="1" max="3" width="34" customWidth="1"/>',
        rows="\n".join(xml_rows),
    )


def _write_html(df: pd.DataFrame, path: Path) -> None:
    cards = []
    for _, row in df.iterrows():
        card = f"""
<article class="case">
  <header>
    <h2>{html.escape(row['case_id'])} · {html.escape(row['audit_stratum'])}</h2>
    <div class="meta">
      <span>Source {html.escape(row['source_notice_id'])}</span>
      <span>Candidate {html.escape(row['candidate_notice_id'] or 'NONE')}</span>
      <span>GBM {html.escape(row['gbm_decision'])}</span>
      <span>Composite {html.escape(row['composite_decision'])}</span>
    </div>
  </header>
  <section class="grid">
    {_kv('Buyer', row['buyer_name'])}
    {_kv('Buyer key', row['buyer_key_type'])}
    {_kv('Source date', row['source_date'])}
    {_kv('Candidate date', row['candidate_date'])}
    {_kv('Gap months', row['gap_months'])}
    {_kv('CPV', row['source_cpv'])}
    {_kv('s_text', row['s_text'])}
    {_kv('s_cpv', row['s_cpv'])}
    {_kv('s_time', row['s_time'])}
    {_kv('s_buyer', row['s_buyer'])}
    {_kv('Composite score', row['composite_score'])}
    {_kv('GBM score', row['gbm_score'])}
    {_kv('Margin', row['top1_top2_margin'])}
    {_kv('Candidate count', row['n_candidates_for_source'])}
  </section>
  <section class="texts">
    <div><h3>Source Text</h3><p>{html.escape(row['source_text'])}</p></div>
    <div><h3>Candidate Text</h3><p>{html.escape(row['candidate_text'] or 'No candidate generated.')}</p></div>
  </section>
  <section class="decision">
    <strong>Labels:</strong> {', '.join(html.escape(label) for label in LABELS)}
  </section>
</article>
""".strip()
        cards.append(card)

    label_badges = "".join(f"<code>{html.escape(label)}</code>" for label in LABELS)
    text = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Real BOAMP Manual Audit Evidence</title>
<style>
body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 0; background: #f7f7f4; color: #1f2933; }}
main {{ max-width: 1180px; margin: 0 auto; padding: 28px; }}
h1 {{ margin-bottom: 4px; }}
.subtitle {{ margin-top: 0; color: #5b6470; }}
.labels code {{ display: inline-block; margin: 3px 6px 3px 0; padding: 3px 6px; background: #eef2f7; border: 1px solid #d9e0ea; border-radius: 4px; }}
.case {{ background: white; border: 1px solid #d8dde6; border-radius: 6px; margin: 18px 0; padding: 18px; box-shadow: 0 1px 2px rgba(0,0,0,.04); }}
.case h2 {{ margin: 0 0 8px; font-size: 18px; }}
.meta {{ display: flex; flex-wrap: wrap; gap: 8px; color: #4b5563; }}
.meta span {{ background: #f1f5f9; border: 1px solid #e2e8f0; padding: 3px 7px; border-radius: 4px; }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 8px; margin-top: 14px; }}
.kv {{ border-top: 1px solid #edf0f4; padding-top: 6px; }}
.kv b {{ display: block; font-size: 12px; color: #64748b; }}
.texts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 16px; }}
.texts div {{ border: 1px solid #e5e7eb; background: #fcfcfb; padding: 12px; border-radius: 4px; }}
.texts h3 {{ margin-top: 0; font-size: 14px; }}
.texts p {{ white-space: pre-wrap; line-height: 1.45; }}
.decision {{ margin-top: 12px; color: #4b5563; }}
@media (max-width: 760px) {{ .texts {{ grid-template-columns: 1fr; }} main {{ padding: 16px; }} }}
</style>
</head>
<body>
<main>
<h1>Real BOAMP Manual Audit Evidence</h1>
<p class="subtitle">Read-only evidence for {len(df)} stratified cases. Enter labels in the XLSX workbook.</p>
<p class="labels">{label_badges}</p>
{''.join(cards)}
</main>
</body>
</html>
"""
    path.write_text(text, encoding="utf-8")


def _kv(label: str, value: object) -> str:
    return f'<div class="kv"><b>{html.escape(label)}</b><span>{html.escape(str(value or ""))}</span></div>'


def _worksheet_xml(cols: str, rows: str, extra: str = "", sheet_views: str | None = None) -> str:
    views = sheet_views or '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
{views}
<cols>{cols}</cols>
<sheetData>
{rows}
</sheetData>
{extra}
</worksheet>
"""


def _row_xml(row_idx: int, values, columns=None, style: int = 0, style_map: dict[str, int] | None = None) -> str:
    cells = []
    for idx, value in enumerate(values, start=1):
        col = columns[idx - 1] if columns is not None else None
        cell_style = style_map.get(col, style) if style_map else style
        s_attr = f' s="{cell_style}"' if cell_style else ""
        ref = f"{_col_letter(idx)}{row_idx}"
        text = "" if pd.isna(value) else str(value)
        cells.append(f'<c r="{ref}" t="inlineStr"{s_attr}><is><t>{xml_escape(text)}</t></is></c>')
    return f'<row r="{row_idx}">{"".join(cells)}</row>'


def _col_letter(idx: int) -> str:
    out = ""
    while idx:
        idx, rem = divmod(idx - 1, 26)
        out = chr(65 + rem) + out
    return out


def _content_types() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
<Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""


def _root_rels() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""


def _workbook_xml(sheet_names: list[str]) -> str:
    sheets = "\n".join(
        f'<sheet name="{xml_escape(name)}" sheetId="{idx}" r:id="rId{idx}"/>'
        for idx, name in enumerate(sheet_names, start=1)
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>
{sheets}
</sheets>
</workbook>
"""


def _workbook_rels(sheet_names: list[str]) -> str:
    rels = [
        f'<Relationship Id="rId{idx}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{idx}.xml"/>'
        for idx, _ in enumerate(sheet_names, start=1)
    ]
    rels.append(
        f'<Relationship Id="rId{len(sheet_names) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
{''.join(rels)}
</Relationships>
"""


def _styles_xml() -> str:
    return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>
"""


if __name__ == "__main__":
    missing = set(LABELS) - MANUAL_AUDIT_LABELS
    if missing:
        raise RuntimeError(f"labels not in canonical vocabulary: {sorted(missing)}")
    main()
