# Canonical Reports and Manifests

Primary machine-readable manifest:

- `reports/run_logs/canonical_pipeline_manifest.json`

Core generated reports:

- `reports/generated/real_linkage_freeze_decision.md`
- `reports/generated/synthetic_benchmark/v0_4_population_alias_revision_report.md`
- `reports/generated/synthetic_benchmark/v0_4_linkage_algorithm_benchmark_report.md`
- `reports/generated/manual_audit_instructions.md`
- `reports/generated/manual_audit_validation_report.md`
- `reports/generated/manual_audit_failure_analysis.md`
- `reports/generated/manual_audit_repair_rule_v1.md`
- `reports/manual_audit/real_audit_evidence_100.html`

Core tables:

- `reports/tables/data_quality/`
- `reports/tables/real_linkage_freeze/`
- `reports/tables/manual_audit/`
- `reports/tables/real_linkage_repair/`
- `reports/tables/synthetic_benchmark/v0_4_population_alias_revision/`
- `reports/manual_audit/real_audit_sample_100.xlsx`
- `reports/manual_audit/real_audit_sample_100_validated.xlsx`

Core figures:

- `reports/figures/synthetic_benchmark/v0_4_population_alias_revision/`
- `reports/figures/real_linkage_freeze/`

Every headline number should be traceable through:

```text
input -> configuration -> code -> command -> run ID -> output -> report location
```
