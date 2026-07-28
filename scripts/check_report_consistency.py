"""Fail if the technical report has drifted from the artifacts it reports on.

Six checks, each of which caught a real defect during the audit that introduced
this script:

1. **Values are current.** Re-derive every reported value from the artifacts and
   compare against the stored ``report_values.json``.
2. **No undefined macro.** Every ``\\rv...`` the document uses is defined.
3. **No unused clutter.** Report which defined macros the document never uses
   (informational, not fatal).
4. **No hand-typed statistic.** The report body must not contain a bare numeric
   literal outside comments, generated inputs, and a small whitelist of
   structural numbers (font sizes, widths, TikZ coordinates).
5. **Every figure and input exists.**
6. **The PDF is current and clean.** It exists, is newer than its inputs, and its
   log has no undefined reference, missing citation, or missing file.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
TEX = REPORTS / "synthetic_benchmark_technical_report.tex"
PDF = TEX.with_suffix(".pdf")
LOG = TEX.with_suffix(".log")
VALUES_JSON = REPORTS / "generated" / "synthetic_benchmark" / "report_values.json"
VALUES_TEX = REPORTS / "generated" / "synthetic_benchmark" / "report_values.tex"

# Numeric literals that legitimately appear in the report body: they are
# typography and mathematics, not reported statistics.
ALLOWED_LITERAL = re.compile(
    r"""
    (?:^|[^0-9])                       # not part of a longer number
    (?:
        0|1|2|3|4|5|6|7|8|9|10|12|25|36|90|95|99|100   # small structural integers
      | 0\.\d+                          # probabilities and widths
      | 1\.0                            # unit
      | 45\^2 | 90 | 400                # award-delay constants, stated in prose
    )
    (?:$|[^0-9])
    """,
    re.VERBOSE,
)


def _strip_comments(text: str) -> str:
    out = []
    for line in text.splitlines():
        idx = 0
        while True:
            idx = line.find("%", idx)
            if idx == -1:
                break
            if idx > 0 and line[idx - 1] == "\\":
                idx += 1
                continue
            line = line[:idx]
            break
        out.append(line)
    return "\n".join(out)


def check_values(failures: list[str], notes: list[str]) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "build_report_values.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
    )
    if result.returncode != 0:
        failures.append("report values are stale: " + (result.stderr.strip() or result.stdout.strip()))
    else:
        notes.append("report values match the current artifacts")


def check_macros(body: str, failures: list[str], notes: list[str]) -> None:
    if not VALUES_TEX.exists():
        failures.append(f"{VALUES_TEX.relative_to(ROOT)} missing")
        return
    defined = set(re.findall(r"\\newcommand\{\\(rv[A-Za-z]+)\}", VALUES_TEX.read_text(encoding="utf-8")))
    used = set(re.findall(r"\\(rv[A-Za-z]+)", body))
    undefined = sorted(used - defined)
    if undefined:
        failures.append("undefined report macros used in the report: " + ", ".join(undefined))
    else:
        notes.append(f"all {len(used)} report macros used are defined")
    unused = sorted(defined - used)
    if unused:
        notes.append(f"{len(unused)} defined macros are unused (informational)")


def check_no_hand_typed_numbers(body: str, failures: list[str], notes: list[str]) -> None:
    # Drop maths, tikz, verbatim-ish inline code and generated inputs first:
    # numbers there are structural, not reported statistics.
    def _blank(match: re.Match) -> str:
        # Preserve line count so reported line numbers match the source file.
        return "\n" * match.group(0).count("\n")

    scrubbed = body
    scrubbed = re.sub(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", _blank, scrubbed, flags=re.S)
    scrubbed = re.sub(r"\\begin\{(equation|align|displaymath)\*?\}.*?\\end\{\1\*?\}", _blank,
                      scrubbed, flags=re.S)
    scrubbed = re.sub(r"\$[^$]*\$", " ", scrubbed)
    scrubbed = re.sub(r"\\(code|file|texttt|includegraphics|input|usepackage|documentclass|"
                      r"definecolor|setlist|setlength|graphicspath|usetikzlibrary|label|ref|"
                      r"cite[a-z]*)\s*(\[[^\]]*\])?\{[^}]*\}", " ", scrubbed)
    scrubbed = re.sub(r"\\rv[A-Za-z]+", " ", scrubbed)

    # Structural literals: ordinals, section-style counts, calendar years the
    # prose names, the artifact directory index, and hash-family bit lengths.
    # Anything else must come from a \rv macro.
    allowed = (
        # ordinals, percentile labels and section-style counts
        {"0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "12",
         "60", "75", "90", "95", "99", "100"}
        # artifact directory indices and hash-family bit lengths
        | {"001", "128", "160", "256"}
        # calendar years the prose names
        | {"2015", "2020", "2021", "2022", "2023", "2024", "2025", "2026"}
        # generator version tokens (v0.1/v0.2/v0.3) and notebook indices
        | {"0.1", "0.2", "0.3", "01", "02", "03", "04"}
        # ratios stated inline as ratios, not as measured statistics
        | {"0.34", "0.8", "1.0"}
    )
    offenders = []
    for lineno, line in enumerate(scrubbed.splitlines(), start=1):
        for match in re.finditer(r"(?<![0-9A-Za-z.])(\d[\d,.]*)(?![0-9A-Za-z])", line):
            token = match.group(1).rstrip(".,")
            if token in allowed:
                continue
            offenders.append(f"line {lineno}: {token!r}")
    if offenders:
        failures.append(
            "hand-typed numeric literals in the report body (use a \\rv macro instead): "
            + "; ".join(offenders[:12])
            + (f" (+{len(offenders) - 12} more)" if len(offenders) > 12 else "")
        )
    else:
        notes.append("no hand-typed statistics in the report body")


def _expand_dirs(body: str) -> str:
    """Substitute the report's own path macros so paths can be resolved."""
    out = body
    for name, value in re.findall(r"\\newcommand\{\\([a-z]+dir)\}\{([^}]+)\}", body):
        out = out.replace("\\" + name, value)
    return out


def check_inputs_exist(body: str, failures: list[str], notes: list[str]) -> None:
    body = _expand_dirs(body)
    missing = []
    for rel in re.findall(r"\\input\{([^}]+)\}", body):
        candidate = REPORTS / (rel if rel.endswith(".tex") else rel + ".tex")
        if not candidate.exists():
            missing.append(rel)
    search = [REPORTS / "figures" / "synthetic_benchmark" / "report", REPORTS / "figures"]
    for rel in re.findall(r"\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}", body):
        found = any((d / rel).exists() or (d / f"{rel}.pdf").exists() or (d / f"{rel}.png").exists()
                    for d in search)
        if not found:
            missing.append(rel)
    if missing:
        failures.append("missing inputs or figures: " + ", ".join(sorted(set(missing))))
    else:
        notes.append("every \\input and \\includegraphics target exists")


def check_pdf(failures: list[str], notes: list[str]) -> None:
    if not PDF.exists():
        failures.append(f"{PDF.relative_to(ROOT)} has not been built")
        return
    pdf_mtime = PDF.stat().st_mtime
    stale = [p.relative_to(ROOT) for p in [TEX, VALUES_TEX] if p.exists() and p.stat().st_mtime > pdf_mtime]
    for tex in sorted((REPORTS / "generated" / "synthetic_benchmark" / "tables").glob("*.tex")):
        if tex.stat().st_mtime > pdf_mtime:
            stale.append(tex.relative_to(ROOT))
    if stale:
        failures.append("PDF is older than its inputs: " + ", ".join(str(p) for p in stale))
    else:
        notes.append("PDF is newer than every input it depends on")

    if not LOG.exists():
        failures.append("LaTeX log missing; cannot verify a clean build")
        return
    log = LOG.read_text(encoding="utf-8", errors="replace")
    problems = []
    if "There were undefined references" in log or "LaTeX Warning: Reference" in log:
        problems.append("undefined reference")
    if "Citation" in log and "undefined" in log:
        problems.append("undefined citation")
    if "LaTeX Warning: File" in log:
        problems.append("missing file")
    if re.search(r"^! ", log, flags=re.M):
        problems.append("LaTeX error")
    overfull = len(re.findall(r"Overfull \\hbox \((\d+(?:\.\d+)?)pt", log))
    bad_overfull = [float(v) for v in re.findall(r"Overfull \\hbox \((\d+(?:\.\d+)?)pt", log) if float(v) > 20]
    if problems:
        failures.append("LaTeX log reports: " + ", ".join(problems))
    else:
        notes.append("LaTeX log is free of undefined references, citations and missing files")
    if bad_overfull:
        failures.append(f"{len(bad_overfull)} overfull boxes exceed 20pt (worst {max(bad_overfull):.1f}pt)")
    elif overfull:
        notes.append(f"{overfull} overfull boxes, all within 20pt")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-pdf", action="store_true", help="Do not check the compiled PDF.")
    args = parser.parse_args()

    failures: list[str] = []
    notes: list[str] = []

    if not TEX.exists():
        raise SystemExit(f"{TEX} missing")
    body = _strip_comments(TEX.read_text(encoding="utf-8"))

    check_values(failures, notes)
    check_macros(body, failures, notes)
    check_no_hand_typed_numbers(body, failures, notes)
    check_inputs_exist(body, failures, notes)
    if not args.skip_pdf:
        check_pdf(failures, notes)

    report = {"status": "FAIL" if failures else "PASS", "failures": failures, "checks_passed": notes}
    print(json.dumps(report, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
