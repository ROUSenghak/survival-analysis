# Integrated M1 Enrichment and Profile-Audit Report

Generated: 2026-07-15

## Figures

- Pipeline diagram: `reports/figures/m1_enrichment_profile_pipeline.png` and `.pdf`.
- Reproducible run-flow diagram: `reports/figures/m1_reproducible_runflow.png` and `.pdf`.

## Pipeline Summary

M0 is the BOAMP-only baseline. M1 is a separate SIREN-enriched sensitivity specification that keeps the M0 source population, scoring components, ranking logic, and balanced threshold, while changing buyer blocking through validated SIRET/SIREN and conservative historical aliases. The procurement-profile audit is a second-stage evidence overlay; it annotates aliases and links but never creates buyer identity.

## M0 to M1 Results

- Eligible sources: 3,159.
- Candidate pairs: M0 6,137; M1 8,228.
- Accepted balanced links: M0 618; M1 847.
- Proxy-recurrence rate: M0 19.6%; M1 26.8%.
- Incremental M1 links: 273.
- Link-set Jaccard overlap: 0.644.

## SIREN Evidence

- Direct SIREN enrichment covers 2024, 2025, and 2026.
- Overall BOAMP SIRET-derived SIREN versus enriched SIREN agreement: 87.4%.
- Identifier conflicts exported for inspection: 1,002.
- Historical aliases eligible for automatic propagation: 1,247.
- Ambiguous or review-only aliases: 1,912.

## Procurement-Profile Evidence

- Profile rows: 23,260.
- Distinct normalized profile domains: 4,700.
- Generic-platform domains: 1,408.
- Alias profile-evidence counts: {"NO_PROFILE_EVIDENCE": 2423, "NEUTRAL_SHARED_PLATFORM": 593, "STRONG_SUPPORT": 110, "AMBIGUOUS": 29, "WEAK_SUPPORT": 4}.
- Incremental-link profile-evidence counts: {"STRONG_SUPPORT": 86, "NO_PROFILE_EVIDENCE": 76, "NEUTRAL_SHARED_PLATFORM": 59, "WEAK_SUPPORT": 50, "AMBIGUOUS": 2}.

## Profile-Audited Variant

The profile-audited M1 variant removes only explicit profile-domain conflicts among historical-alias candidate pairs. Under the conservative rule, no explicit conflicts were found, so the variant is identical to M1:

- Profile-audited accepted links: 847.
- Links removed versus M1: 0.
- Jaccard versus M1: 1.000.

## Interpretation

The SIREN enrichment increases coverage and link yield, but it remains a sensitivity specification until the incremental links are manually validated. Procurement-profile domains add useful manual-review context and weak support for some aliases, but they are often shared platforms and should not be treated as legal identifiers. M0 remains the primary conservative baseline; M1 and the profile-audited M1 remain sensitivity analyses.

## Reproducibility

```bash
python3 scripts/build_m1_buyer_siren_experiment.py
python3 scripts/build_m1_profile_domain_audit.py
MPLCONFIGDIR=/tmp/matplotlib-m1-report python3 scripts/make_m1_academic_diagrams.py
```
