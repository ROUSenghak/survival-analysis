# Data-Generating Process Specification — BOAMP Synthetic Record-Linkage Benchmark

**Applies to:** `v0_3_temporal_candidate_revision`
**Companion registries:** `reports/tables/synthetic_benchmark/<version>/registries/`
**Validation suite:** `scripts/validate_synthetic_benchmark.py`

This is the Phase 0 specification the validation framework tests against. It states
the order in which the generator draws things, what each step conditions on, and —
just as importantly — which parts of the mechanism are *not* recoverable from the
saved outputs. A validation suite that has no written specification to compare
against can only confirm that the code did what the code does.

## 1. Two layers and why they are separate

The generator emits two disjoint sets of tables.

**Observed layer** (`observed_notices.parquet`) is a BOAMP-like notice table
containing only fields a linkage method could actually read: publication date,
notice type, schema family, raw buyer identifiers and name, department, CPV,
declared duration, procurement text, and the linked-call reference. Every defect a
real linker must survive — missing SIRET, absent CPV, drifted buyer names,
boilerplate text — is present here and nowhere labelled as such.

**Truth layer** (all other tables) carries latent entities, cycle chains, the
successor relation, per-notice pre-corruption values, and a complete corruption
log. These fields define what a correct answer is.

The separation is what makes the benchmark useful: exact blocking recall, recovery
by corruption type, and cluster-level accuracy are all computable here and none of
them is computable on real BOAMP. It is also what makes leakage a release-blocking
failure rather than an annoyance — a truth column reaching the observed table
would turn every downstream accuracy number into an artifact.

## 2. Generation order and conditioning

The generator draws in the following order. Each step conditions only on steps
above it, which is what makes the chain replayable.

| # | Step | Module | Draws | Conditions on |
|---|------|--------|-------|---------------|
| 1 | Buyers | `buyers.py` | buyer id, SIREN, department, type, activity rate/tier, alias propensity, identifier-quality propensity | scenario `quality_class_mix`, observation window |
| 2 | Establishments | `establishments.py` | establishment ids and SIRETs under each buyer | buyer SIREN, buyer active window |
| 3 | Needs | `needs.py` | recurring need, CPV, base concepts/vocabulary, duration profile, recurrence propensity | buyer, buyer activity tier |
| 4 | Cycles | `cycles.py` | cycle chain per need: start date, true duration, expected end | need recurrence propensity, scenario `cycle_gap_distribution`, `max_cycles_per_need`, observation window |
| 5 | Relations | `relations.py` | `NEXT_CYCLE` / `NO_SUCCESSOR` per cycle, true gap, strict/broad labels | realized cycle chains |
| 6 | Notices | `notices.py` | CALL and optional AWARD notice per cycle, publication date, schema family, notice type | cycle dates, real by-year EFORMS adoption share |
| 7 | Clean values | `text_generation.py`, notices | true identifiers, CPV, duration, buyer name, procurement text | buyer, establishment, need vocabulary |
| 8 | Corruption | `corruption.py`, `missingness.py` | observed identifier/CPV/duration/text/name values plus a log row per change | clean values, schema family, publication year, notice type, buyer activity tier, quality class |
| 9 | Export | `pipeline.py` | observed table stripped of truth; truth tables with provenance | all of the above |

### 2.1 Cycle timing, precisely

For each need, cycle 1 starts inside its buyer's active window. Each subsequent
cycle is realized only if both a successor draw succeeds and the resulting start
date still falls inside the observation window (2015-01-01 to 2026-07-31); the
chain otherwise terminates and `relations.py` records `NO_SUCCESSOR`.

The successor gap is drawn from the scenario's `cycle_gap_distribution` — a normal
truncated below at `min_months` — **except** for needs whose CPV division falls in
the scoped set, which draw from a near-window component with probability
`near_window_share`.

This right-censoring by the observation window is not a detail. It means the gaps
that reach the truth table are systematically shorter than the declared
distribution, and any recovery test that simulates the unconditional draw will
fail for reasons that have nothing to do with the generator. The suite's Monte
Carlo reference therefore censors each simulated gap by the headroom actually
remaining to its own source cycle.

### 2.2 What deliberately does not match the production pipeline

The gap distribution is centred well outside the production linker's 6-month
blocking window, on purpose. A benchmark whose true successors all fell inside the
window would report a blocking recall that says nothing about renewal timing. The
consequence, measured by the difficulty gate, is that the production window
recovers roughly a third of in-scope true matches — a property of that window
against these gaps, not a generator defect.

## 3. Parameter provenance

Every scenario parameter belongs to exactly one class, recorded in
`registries/parameter_registry.csv`:

- **EMPIRICAL_OBSERVABLE** — calibrated to a measurable real-BOAMP quantity
  (identifier presence by year and schema, CPV missingness by schema and notice
  type, buyer-name variation rates, text reuse).
- **SILVER_STANDARD_APPROXIMATION** — estimated from a documented imperfect
  proxy, such as checksum-valid SIREN groupings used where real buyer entities
  are not observed.
- **SCENARIO_UNIDENTIFIED** — an assumption about something real BOAMP cannot
  identify: true recurrence prevalence, the gap distribution, text drift severity,
  the specific CPV corruption mode. These must be varied across scenarios, never
  quoted as estimates.
- **FIDELITY_TARGET** — an observable property used only to judge realism, not to
  define synthetic truth. Candidate-count tails and text-duplication rates belong
  here when they are used as held-out diagnostics.
- **ALGORITHM_PARAMETER** — linkage/blocking settings such as score weights,
  thresholds, caps, or temporal windows. These may be reported for operational
  comparison but must never define synthetic truth.
- **IMPLEMENTATION_CONSTANT** — a technical choice with no empirical
  interpretation.

The registry records, for each parameter or validation rule, its definition,
value or distribution, source population, estimation code, uncertainty,
version, rationale, whether it may be used for calibration, whether it must
remain held out, and known limitations. Scenario assumptions must stay
explicitly labelled; a swept value chosen to improve candidate realism is not an
empirical estimate of the real renewal process.

`registries/scenario_manifest.csv` separately records configured scenarios and
generated artifacts. `CONFIG_ONLY` means the scenario can be loaded by the
generator but has not been released as a generated benchmark world; it is not
multi-seed evidence and cannot support algorithm-ranking claims.

## 4. Current reproducibility status and remaining recovery warnings

These are recorded here because a reader should find the explanation next to the
specification, not only in a CSV.

1. **The v0.3 scenario file now reproduces the released central dataset.** The
   selected scoped-candidate parameters are written directly in
   `config/synthetic/scenarios/central_provisional.yaml` and also retained under
   `generation_metadata.json#candidate_revision` as selection provenance. The
   generation metadata stores `resolved_scenario` and
   `resolved_benchmark_defaults` snapshots.

2. **Canonical replay passes.** `scripts/replay_synthetic_benchmark.py`
   regenerates the benchmark from the recorded seeds and compares canonical
   content hashes, rather than Parquet byte hashes, for all observed and truth
   tables. The saved replay result is
   `reports/tables/synthetic_benchmark/v0_3_temporal_candidate_revision/validation_framework/replay_comparison.json`.
   `scripts/replay_synthetic_benchmark_replicates.py` additionally passes for
   every generated artifact in the expanded scenario/seed grid.

   Canonical content hashing tolerates Parquet writer differences but **not** a
   different NumPy build: the generator and reduction kernels are bit-stable per
   build, not across builds, so a different NumPy replays every count and
   identity while differing in the last unit in the last place of float columns
   — enough to change a SHA-256. `requirements-lock.txt` pins the environment,
   `generation_metadata.json#runtime_environment` records what each artifact was
   generated under, and `replay_comparison.json` reports
   `environment_drift_since_generation` so such a mismatch is diagnosable rather
   than mistaken for generator drift.

3. **The true-gap mean recovers under the declared mechanism.** Simulating the
   base/near-window mixture with window censoring reproduces the observed mean
   gap. The current run's realised mean and its 99% Monte Carlo interval are in
   `validation_metrics_long.csv`
   (`specification_recovery / mean_true_gap_months_in_monte_carlo_interval`);
   they are not repeated here, because a number copied into prose is a number
   that goes stale.

   An earlier revision reported this as a warning and attributed the miss to
   the hard-negative chain-alignment step not being replayed. That explanation
   was wrong. Chain alignment translates a whole distinct-need chain by one
   constant offset, so `target_start - source_expected_end` is unchanged by
   construction and the step cannot move the gap distribution at all. The
   actual defect was in the diagnostic: it measured each source's remaining
   window from `start_date_true` while the generator stops a chain when
   `expected_end + gap > observation_end`. That overstated the available
   headroom by one cycle duration (13.2 months on average), under-truncated the
   simulated draws, and biased the interval upward by roughly 0.7 months.

   The diagnostic now censors from `source_expected_end` and carries no
   status softening, so a genuine gap misspecification fails the gate. The
   `shifted_true_gaps` negative control asserts that it still does so with the
   scoped candidate block and chain alignment enabled.

## 5. What this specification cannot establish

Fidelity to observable BOAMP does not make the latent mechanism correct. Several
different recurrence processes produce similar observed notice tables, so the
recurrence parameters are partially identified at best. The following remain
outside what any comparison against real BOAMP can settle, and must be handled by
scenario coverage rather than calibration:

- true renewal prevalence and the real distribution of contract-family sizes;
- true pairwise or family-level linkage accuracy of any pipeline;
- the correct acceptance threshold, or the true error rates at one;
- the causal mechanism behind missing identifiers and corrupted fields;
- whether algorithm rankings measured here equal rankings under real BOAMP truth.

Existing accepted links, pipeline scores and the six-month window may be used as
observable pipeline outputs, explicitly-constructed silver-standard subsets, or
descriptive anchors. They must never be treated as labels.
