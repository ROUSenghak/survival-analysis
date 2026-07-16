# Final Single-Reviewer Plausibility Audit Guide

This audit is a single-reviewer evidence-based plausibility audit, not
verified expert ground truth. Labels should not be inferred from method
names, composite scores, thresholds, or acceptance status. The reviewer
file hides those technical fields; the join table keeps them separate
for analysis after labels are recorded.

Allowed labels:

- `credible_recurrence`
- `likely_not_recurrence`
- `uncertain`
- `insufficient_evidence`

Also record confidence, buyer-identity confidence, evidence category,
likely error mechanism, whether external evidence was consulted, whether
AI-assisted summarization was used, and a short justification.

A disguised repeat subset should be reviewed after a delay and stored
with the same schema plus a repeat-round marker before calculating
intra-reviewer agreement. Do not overwrite disagreements.
