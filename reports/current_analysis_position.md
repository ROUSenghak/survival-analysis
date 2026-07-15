# Current analysis position

Generated: 2026-07-15

## Decision

The official result for the study is the BOAMP-only M0 balanced specification.
M1 is retained as a buyer-identity enrichment sensitivity analysis, not as a
replacement for M0.

This means:

- M0 is the primary event definition used for the main survival analysis.
- M1 is used to test whether SIREN-based buyer reconciliation changes coverage
  and link yield.
- M1 outputs should be reported after M0, under sensitivity or robustness
  results.
- Neither M0 nor M1 should be described as verified legal renewal. Both define
  constructed proxy recurrence events.

## Primary M0 result

Source table: `reports/tables/m0_m1_linkage_comparison.csv`.

For the quantitative survival-sensitivity conclusion attached to this primary
M0 result, see `reports/survival_sensitivity_conclusion.md`.

- Eligible sources: 3,159.
- Sources with at least one candidate: 1,236.
- Zero-candidate sources: 1,923.
- Blocking coverage: 39.1%.
- Candidate pairs: 6,137.
- Accepted balanced links: 618.
- Overall proxy-recurrence rate: 19.6%.
- Unique selected candidates: 443.
- Candidate reuse rate: 27.3%.
- Maximum candidate multiplicity: 6.

Interpretation: M0 is conservative and reproducible, but incomplete. Its main
limitation is blocking coverage: most eligible sources never enter a scored
candidate pool.

## M1 sensitivity result

Source tables:

- `reports/tables/m0_m1_linkage_comparison.csv`
- `reports/tables/m0_m1_link_status_changes.csv`
- `reports/tables/m1_incremental_recovery_mechanisms.csv`
- `reports/tables/m1_incremental_link_score_diagnostics.csv`

M1 keeps the M0 eligible source population, temporal window, TF-IDF text score,
CPV score, temporal score, ranking logic, and balanced threshold. The controlled
change is buyer identity: direct BOAMP SIRET, validated same-SIREN
reconciliation, conservative historical aliases, then M0 name fallback.

- Eligible sources: 3,159.
- Sources with at least one candidate: 1,504.
- Zero-candidate sources: 1,655.
- Blocking coverage: 47.6%.
- Candidate pairs: 8,228.
- Accepted balanced links: 847.
- Overall proxy-recurrence rate: 26.8%.
- Unique selected candidates: 570.
- Candidate reuse rate: 29.5%.
- Maximum candidate multiplicity: 8.

Compared with M0:

- Sources with no M0 candidate but at least one M1 candidate: 269.
- Incremental M1 links: 273.
- M0 links not retained in M1: 44.
- Identical links in both methods: 574.
- Same source but different selected candidate: 43.
- Link-set Jaccard overlap: 0.644.

Incremental M1 links by recovery mechanism:

- Historical alias reconciliation: 198.
- Same-SIREN reconciliation: 75.

Interpretation: M1 shows that buyer-name fragmentation suppresses some
recurrence detection in M0. However, the incremental links are not yet manually
validated and include many historical-alias links, so M1 should remain a
sensitivity specification.

## Credibility position

M1 improves coverage and raises the proxy-recurrence rate, but a higher event
rate is not by itself evidence of better validity. The incremental M1 links have
weaker internal text and margin diagnostics than unchanged M0 links:

- Median text similarity, unchanged M0 links as scored in M1: 0.175.
- Median text similarity, incremental M1 links: 0.078.
- Median top-1/top-2 margin, unchanged M0 links as scored in M1: 0.080.
- Median top-1/top-2 margin, incremental M1 links: 0.070.

Therefore the defensible current conclusion is:

> M0 remains the primary conservative BOAMP-only specification. M1 is an
> informative sensitivity analysis showing that buyer enrichment increases
> candidate coverage and link yield, but it should not replace M0 until the
> incremental links are manually validated.

## What remains unvalidated

- No completed manual-validation matrix exists yet.
- The unlabeled validation files are prepared, but reviewer labels are still
  empty.
- Incremental M1 links should be reviewed separately from unchanged M0 links.
- Historical-alias links require special scrutiny because same legal-unit
  identity does not always imply the same procurement unit or recurring need.
- Candidate reuse remains nontrivial and should not be interpreted as verified
  one-to-one renewal.

## Reporting instruction

Use this ordering in the report:

1. Present M0 as the main BOAMP-only recurrence proxy.
2. Report the survival analysis primarily on M0 balanced.
3. Present M1 after M0 as a sensitivity analysis of buyer reconciliation.
4. State that M1 improves coverage, but not yet verified credibility.
5. Make manual validation the next methodological step.

Use `reports/survival_sensitivity_conclusion.md` when citing the quantitative
survival robustness result in prose.
