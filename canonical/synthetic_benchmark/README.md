# Canonical Synthetic Benchmark

Frozen benchmark version:

```text
v0_4_population_alias_revision
```

Canonical benchmark paths:

- observed synthetic records:
  `data/processed/synthetic_benchmark/v0_4_population_alias_revision/*/world_*/corruption_*/observed_notices.parquet`
- hidden truth:
  `data/processed/synthetic_benchmark/v0_4_population_alias_revision/*/world_*/corruption_*/true_relations.parquet`
- generation manifest:
  `reports/tables/synthetic_benchmark/v0_4_population_alias_revision/generation_manifest.json`
- readiness:
  `reports/tables/synthetic_benchmark/v0_4_population_alias_revision/readiness/`
- method benchmark:
  `reports/tables/synthetic_benchmark/v0_4_population_alias_revision/linkage_algorithm_benchmark/`

Supported use:

- controlled synthetic method comparison under explicit assumptions
- provisional method selection under benchmark assumptions
- transfer-risk diagnostics and audit prioritization

Unsupported use:

- real BOAMP precision or recall
- true BOAMP renewal prevalence
- final real-BOAMP algorithm ranking
- final survival conclusions

`moderate` is byte-identical to `central_provisional` and must be excluded from
unique cross-scenario counts.
