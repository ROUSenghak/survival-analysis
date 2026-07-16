# Final Method-Selection Record

Generated: 2026-07-16

Repository state:

- Branch: `main`
- Commit: `cd3dbddd0f2f70ed5f99a05acf72f0f26302afb8`
- Short status at audit generation: `M reports/boamp_m0_technical_report.pdf
 M reports/boamp_m1_technical_report.pdf
 M reports/boamp_m1_technical_report.tex
 M reports/linkage_quality_evaluation.pdf
?? reports/final_method_selection_record.md
?? reports/final_reproducibility_manifest.md
?? reports/final_single_reviewer_audit_guide.md
?? reports/tables/final_authoritative_files.csv
?? reports/tables/final_blinded_single_reviewer_sample.csv
?? reports/tables/final_consistency_audit.csv
?? reports/tables/final_linkage_funnel.csv
?? reports/tables/final_linkage_funnel_stratified.csv
?? reports/tables/final_m0_m1_profile_source_comparison.csv
?? reports/tables/final_m0_m1_profile_status_summary.csv
?? reports/tables/final_method_comparison.csv
?? reports/tables/final_method_inventory.csv
?? reports/tables/final_source_linkage_diagnostics.csv
?? reports/tables/final_temporal_variant_comparison.csv
?? reports/tables/final_validation_technical_join_table.csv
?? scripts/analyze_manual_validation_labels.py
?? scripts/build_final_scientific_audit.py`

## Decision

The primary event definition remains **M0 balanced**, the BOAMP-only proxy
recurrence baseline. M1 buyer enrichment and profile-audited M1 are retained as
sensitivity/audit specifications, not replacements.

This decision is evidence-limited: no completed manual labels exist in the
repository. Therefore the study can select a reproducible primary proxy event
definition for exploratory survival analysis, but it cannot claim verified
renewal precision, legal renewal status, or operational accuracy.

## Exact Definitions

**M0 balanced.** BOAMP-only APPEL_OFFRE digital/ICT sources in Pays de la
Loire; candidate generation requires a nonmissing BOAMP-derived buyer key, a
later notice with the same buyer key, and publication inside the duration-
centered temporal window. Scoring is transparent TF-IDF text, CPV hierarchy,
temporal proximity, and buyer-key reliability. The balanced variant accepts the
rank-1 candidate at or above the current rank-1 median threshold. Current links:
618 / 3159
(19.6%).

**M1 buyer-enriched.** Same source population, temporal design, text/CPV/time
logic, and M0 balanced threshold, but buyer identity is reconciled using direct
BOAMP identifiers, same-SIREN reconciliation, and conservative historical
aliases. Current links: 847 / 3159
(26.8%).

**Profile-audited M1.** M1 links annotated with procurement-profile domain
evidence. Domains are supporting/conflict evidence, not legal identifiers and
not ground truth.

**Temporal variants.** Window variants alter the duration-centered candidate
window (6, 9, 12, 18 months). The no-temporal-score reference-pool variant
reranks the same reference candidate pool without the temporal score. The
forward-24m no-duration variant uses a forward publication horizon and avoids
duration-centered blocking/scoring; it is a sensitivity check for duration
circularity and rapid related procurement activity, not an adopted replacement.

## End-to-End M1 Data Preprocessing

M1 preprocessing is an additive branch over frozen M0 outputs. It begins with
the official M0 cleaned notices, source table, balanced links, candidate-pair
table, and survival handoff. It then loads and audits the external 2024--2026
buyer SIREN/SIRET Parquet files, verifies the one-to-one
`B_17_idweb -> notice_id` join key, and left-joins enrichment fields to the
cleaned BOAMP notices without overwriting BOAMP-provided identifiers.

The preprocessing cleans BOAMP and enriched SIREN/SIRET values separately,
flags BOAMP/enriched identifier conflicts, builds a conservative
name--department historical alias bridge from directly enriched non-conflicting
rows, and applies a priority rule: preserve BOAMP SIRET/SIREN first, then use
valid direct enrichment, then use an automatic historical alias only for older
rows with no BOAMP identifier, otherwise keep the original name fallback. The
result is the M1 source table with buyer identity, provenance, confidence, and
conflict fields attached to the same 3,159 source notices as M0.

Only after this preprocessing step does M1 generate candidate pairs. It reuses
M0 duration, estimated end dates, temporal window, TF-IDF text score, CPV score,
temporal score, score weights, candidate cap, and balanced threshold. The
controlled change is buyer compatibility through exact SIRET, same SIREN,
historical alias, or M0 name fallback. The profile-domain audit is a later
evidence overlay; it does not create legal identifiers or new buyer matches.

## Evidence Used

- `reports/tables/final_method_inventory.csv`
- `reports/tables/final_source_linkage_diagnostics.csv`
- `reports/tables/final_linkage_funnel.csv`
- `reports/tables/final_m0_m1_profile_source_comparison.csv`
- `reports/tables/final_temporal_variant_comparison.csv`
- `reports/tables/final_consistency_audit.csv`

## Why M0 Remains Primary

M0 is conservative, BOAMP-only, reproducible, internally coherent, and already
used for the official survival handoff. M1 improves candidate coverage and link
yield, but higher yield is not validation. Its incremental evidence still
requires single-reviewer plausibility review and, ideally, adjudication.

## Enrichment Gains

Current incremental M1 links are concentrated in:

- HISTORICAL_ALIAS_RECONCILIATION: 198 incremental links
- SAME_SIREN_RECONCILIATION: 75 incremental links

Thus the gain is not mainly from directly observed new identifiers alone; a
large share comes from historical-alias reconciliation, which is plausible but
manual-review sensitive.

## Why The Linkage Rate Is Low

The low M0 linkage rate is scientifically plausible for a conservative proxy
because most sources never enter the scored candidate pool. Primary source-level
diagnostic reasons:

- later_same_buyer_notice_outside_m0_window: 1125 sources
- no_later_same_buyer_notice_observed: 798 sources
- candidate_pool_below_balanced_threshold: 618 sources
- linked_m0_balanced_proxy_event: 618 sources

This does not prove the true renewal rate is low. It shows that under the
observable BOAMP-only M0 design, many sources have no usable later same-buyer
candidate inside the temporal rule.

## Temporal And Duration Sensitivity

| variant | window_months | n_links | event_rate | jaccard_vs_reference | event_status_changes_vs_reference | median_event_time |
| --- | --- | --- | --- | --- | --- | --- |
|  | 6 | 618 |  | 1 |  |  |
|  | 9 | 693 |  | 0.736424 |  |  |
|  | 12 | 754 |  | 0.578826 |  |  |
|  | 18 | 834 |  | 0.453453 |  |  |
| balanced_reference |  | 618 | 0.195632 | 1 | 0 | 37.6971 |
| no_temporal_score_reference_pool |  | 618 | 0.195632 | 0.414188 | 246 | 42.6413 |
| forward_24m_no_duration |  | 1105 | 0.349794 | 0.0642372 | 901 | 5.81472 |

Stable: the M0 handoff is internally consistent and the event is heavy-censored.
Design-dependent: event counts, event timing, and especially duration effects.
The forward no-duration variant is too different to replace M0 without
validation; it likely captures rapid related procurement activity as well as
recurrence.

## Validation Status

Manual labels are pending. Prepared files:

- `reports/tables/final_blinded_single_reviewer_sample.csv`
- `reports/tables/final_validation_technical_join_table.csv`
- `reports/final_single_reviewer_audit_guide.md`
- `scripts/analyze_manual_validation_labels.py`

The validation analysis will compute decided precision, lower and upper
credibility bounds, uncertainty rate, and breakdowns by method/stratum once
labels are complete. Until then, accepted-link precision must not be described
as overall accuracy.

## Unsupported Claims

- M0 or M1 links are verified legal renewals.
- `event = 0` means confirmed non-renewal.
- M1 is better because it has more links.
- Duration is a stable substantive predictor independent of event definition.
- Fellegi-Sunter, corruption recovery, or agreement with M0 is external ground truth.
