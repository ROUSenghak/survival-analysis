# M1 procurement-profile domain audit

Generated: 2026-07-15

## Resource

- Source page: `https://www.data.gouv.fr/datasets/liste-des-profils-d-acheteurs-par-entites-adjudicatrices`.
- Downloaded resource: `profils-acheteurs.csv` from data.gouv resource metadata.
- Producer: DonnéesPubliques.org.
- License: `lov2`.
- Local file: `data/raw/procurement_profiles/profils-acheteurs.csv`.

The row unit is a buyer-name / profile-domain / participation-domain summary row with a latest observed BOAMP date and latest-site indicator. It does not contain BOAMP notice IDs, SIREN, SIRET, postcode, or city, so joins to M1 are name-based and are treated as supporting or conflict evidence only.

## Dataset Quality

- Rows: 23260.
- Observed date range: 2015-03-02 to 2020-12-31; metadata period says 2015-2022.
- Distinct normalized buyer names: 15039.
- Distinct normalized profile domains: 4700.
- Distinct normalized participation domains: 900.
- Malformed profile URL rows: 396.
- Malformed participation URL rows: 22.

Domain classification found 1,408 generic-platform domains and 433 buyer-specific or highly concentrated domains. The largest platforms are broad shared portals, so a shared domain is usually weak identity evidence.

## Alias Evidence

- All alias rows evaluated: 3,159; status counts: {"NO_PROFILE_EVIDENCE": 2423, "NEUTRAL_SHARED_PLATFORM": 593, "STRONG_SUPPORT": 110, "AMBIGUOUS": 29, "WEAK_SUPPORT": 4}.
- Auto-propagation-eligible M1 aliases evaluated: 1,247; status counts: {"NO_PROFILE_EVIDENCE": 928, "NEUTRAL_SHARED_PLATFORM": 253, "STRONG_SUPPORT": 53, "AMBIGUOUS": 12, "WEAK_SUPPORT": 1}.
- Historical-alias incremental links covered: 198; profile statuses: {"STRONG_SUPPORT": 68, "NEUTRAL_SHARED_PLATFORM": 54, "WEAK_SUPPORT": 41, "NO_PROFILE_EVIDENCE": 34, "AMBIGUOUS": 1}.

## Profile-Audited Variant

The profile-audited variant removes only explicit profile conflicts among historical-alias candidate pairs. It does not create any buyer match from a profile domain.

- M1 links: 847; profile-audited links: 847.
- M1 blocking coverage: 47.610%; profile-audited blocking coverage: 47.610%.
- M1 linking rate: 26.812%; profile-audited linking rate: 26.812%.
- Links removed versus M1: 0.
- Candidate reuse rate: M1 29.474%; profile-audited 29.474%.
- Link-set Jaccard versus M1: 1.000.

## Recommendation

Procurement-profile domains should be retained as a manual-review aid and conflict-detection tool, not as a buyer identifier. The profile-audited variant should remain a sensitivity specification, not replace M1 or M0. The evidence is useful for flagging a subset of suspicious historical-alias merges, but coverage is name-based and many domains are shared commercial or institutional platforms.

Final consistency checks passed: 14/14.

## Pipeline Figures

These figures show where procurement-profile evidence enters the M1 audit without creating buyer identity matches.

- `reports/figures/m1_enrichment_profile_pipeline.png`
- `reports/figures/m1_enrichment_profile_pipeline.pdf`
- `reports/figures/m1_reproducible_runflow.png`
- `reports/figures/m1_reproducible_runflow.pdf`
- Integrated synthesis: `reports/m1_integrated_enrichment_pipeline_report.md`
