# Canonical Configuration

Canonical configuration files:

- `config/pipeline.yaml`
- `config/paths.yaml`
- `config/synthetic/benchmark_defaults_v0_4.yaml`
- `config/synthetic/scenarios/v0_4/central_provisional.yaml`

Important frozen values:

- random seed: `20260713`
- candidate generator: `dur_w6_same_buyer_expected_end_window_top30`
- composite balanced threshold: `0.3431669423310381`
- composite strict threshold: `0.44206956893514254`
- GBM primary threshold: read from
  `reports/tables/synthetic_benchmark/v0_4_population_alias_revision/linkage_algorithm_benchmark/algorithm_thresholds.csv`

Do not tune thresholds to force a target link rate.
