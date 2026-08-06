# Canonical BOAMP Pipeline Directory

This directory is the clean canonical entrypoint for the project. It does not
copy large data files or move legacy work. Instead, it points to the one
canonical implementation, the one canonical real-data layer, the frozen
synthetic benchmark, the provisional real-linkage outputs, and the scientific
gates that still block final claims.

## Canonical State

- Canonical real layer: `boamp_only`
- Frozen benchmark: `v0_4_population_alias_revision`
- Candidate generator: `dur_w6_same_buyer_expected_end_window_top30`
- Provisional primary practical method: gradient boosting under the predefined
  synthetic benchmark assumptions and operational criteria
- Transparent baseline: composite balanced
- Conservative policy: composite strict with `POTENTIAL` links dropped
- Real precision and recall: `UNKNOWN_REAL_PRECISION_RECALL`
- Manual audit gate: `BLOCKED_BY_MANUAL_AUDIT`
- Technology-specific gate: `BLOCKED_BY_EXTERNAL_CLASSIFICATION`

## Directory Map

- `config/` - canonical configuration pointers.
- `data/` - canonical real BOAMP corpus and data-quality pointers.
- `synthetic_benchmark/` - frozen synthetic benchmark pointers and limits.
- `linkage/` - candidate generation, method comparison, and real-linkage outputs.
- `audit/` - manual audit package and labels gate.
- `classification/` - teammate classification export contract and validator.
- `downstream/` - event/censoring, survival, and technology analysis gates.
- `reports/` - canonical manifests, generated reports, figures, and tables.

## Reproduce the Current Canonical Index

```bash
PYTHONPATH=src .venv/bin/python scripts/check_boamp_corpus_quality.py
PYTHONPATH=src .venv/bin/python scripts/build_real_audit_sample.py
PYTHONPATH=src .venv/bin/python scripts/build_canonical_run_manifest.py
```

The canonical machine-readable manifest is:

```text
reports/run_logs/canonical_pipeline_manifest.json
```

## Important Rule

Files in `archive/` and noncanonical report outputs are evidence, not the
current source of truth. Do not delete them without explicit approval.
