# Human-review guide (Work Package 11)

**Purpose.** Use human review to calibrate difficult mechanisms in the synthetic
benchmark generator, not to claim definitive ground truth about the real BOAMP
corpus. There are zero completed manual-validation labels anywhere in this
project (`docs/methodology.md` §9); this review does not change that fact by
itself — it only prepares the queue. A human still has to do the actual
reviewing, and the exit criterion below applies to what happens *after* that.

The queue itself is built in `notebooks/04_synthetic_benchmark_calibration.ipynb`
§15d (Work Package 11) and exported to:

- `reports/tables/synthetic_calibration/human_review_queue_blinded.csv` — the
  file a reviewer actually works from.
- `reports/tables/synthetic_calibration/human_review_queue_technical_join.csv`
  — pipeline scores, confidence tier, and layer, kept **separate** and joined
  back only after labels are recorded, so the reviewer's judgment is not
  anchored on the pipeline's own decision.
- `reports/tables/synthetic_calibration/calib_human_review_stratum_counts.csv`
  — how many cases were sampled per stratum.

## Strata reviewed

Up to 8 cases each, sampled from real Layer 1/Layer 2 pipeline outputs (not
hand-picked):

- **high_score_layer1_links** — Layer 1 balanced-variant links with
  `confidence_tier == HIGH`.
- **low_margin_layer1_links** — Layer 1 balanced-variant links with
  `confidence_tier == POTENTIAL` (top1-top2 margin below
  `config/pipeline.yaml`'s `confidence_tiers.potential_margin_max`, 0.05).
- **layer2_only_links** — a source Layer 2 (enriched) links but Layer 1 never
  links at all.
- **same_buyer_hard_negatives** — reused directly from §15b's
  `text_hard_negative_sample.csv` (Work Package 6): same buyer, same CPV
  division, high text similarity, distinct detailed CPV.
- **pairs_outside_six_month_window** — candidate pairs with `gap_months > 6`,
  i.e. outside the frozen temporal window (`config/pipeline.yaml`
  `temporal_window.expected_value_months`).
- **split_or_merge_candidates** — sources with ≥3 candidates and a near-zero
  top1-top2 margin: genuine multi-candidate ambiguity for a human to
  adjudicate, not something a detector already decided.
- **sources_with_no_candidates** — from the true eligible-source population
  (`data/processed/boamp_only/boamp_only_sources.csv`, 3,159 rows), sources
  for which the pipeline generated zero candidates.
- **very_active_buyers** — pairs whose source belongs to the `21+` buyer
  activity tier.

## Labels

Use the frozen recurrence ontology (`config/synthetic/recurrence_ontology.yaml`,
Work Package 10): `NEXT_CYCLE`, `PARTIAL_RECURRENCE`, `SPLIT`, `MERGE`,
`SAME_THEME_DIFFERENT_NEED`, `UNRELATED`, `NO_SUCCESSOR`, plus `UNCERTAIN`
(allowed here — real-data review, not synthetic generation, where ground
truth is exact by construction and `UNCERTAIN` must never appear). Do not
infer a label from anything other than the blinded evidence in front of you:
the technical join table exists for analysis *after* labeling, not before.

## What to record

For every case in the blinded queue:

- `reviewer` — your identifier.
- `evidence` — what in the source/candidate text, dates, buyer names, or CPV
  actually supports your decision.
- `decision` — one label from the frozen ontology above.
- `confidence` — your own confidence in that decision (e.g. HIGH/MEDIUM/LOW).
- `disagreement` — filled in only when a second reviewer, or a delayed
  repeat-round review of the same case (see
  `reports/final_single_reviewer_audit_guide.md`'s disguised-repeat-subset
  practice), disagrees with the first decision.
- `final_adjudication` — the resolved decision after any disagreement is
  discussed; leave blank if there was none.

## What this review should answer

- Are the relation classes realistic — does every case fit one of the 7
  synthetic-eligible types, or does `UNCERTAIN` come up often enough to mean
  the ontology is missing something?
- Do split and merge cases actually occur in this corpus, and how often?
- How strong can text drift be between a true successor and its source
  (vocabulary change, template drift, length change)?
- How often does CPV actually change between a source and its true successor,
  and at what level of the CPV hierarchy (category/class/group/division)?
- What difficult false candidates should the synthetic generator's hard-negative
  process include, beyond what §15b already samples?

## Exit criterion

The review should refine scenario ranges in
`reports/tables/synthetic_calibration/calib_unidentified_parameters_scenarios.csv`
(Work Package 4/§14) — e.g. narrowing the proposed range for true recurrence
prevalence, or adding a new scenario knob this review surfaces — **not**
produce a single claimed real precision or recall estimate. A precision claim
computed from ~80 single-reviewer cases across 8 deliberately different
strata would not generalize to the full corpus and must not be reported as
if it did.
