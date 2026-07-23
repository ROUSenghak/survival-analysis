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
- **DERIVED_RESWEPT** — a value with an empirical *target* that had to be re-swept
  because it passes through a severity multiplier before taking effect. The target
  is empirical; the number in the file is not.
- **SCENARIO_UNIDENTIFIED** — an assumption about something real BOAMP cannot
  identify: true recurrence prevalence, the gap distribution, text drift severity,
  the specific CPV corruption mode. These must be varied across scenarios, never
  quoted as estimates.
- **SCENARIO_TUNED_TO_CANDIDATE_TARGETS** — the v0.3 scoped-candidate block, tuned
  so emergent candidate counts resemble the real corpus. It controls recurrence
  timing and need clustering only; it never sets candidate counts, scores,
  accepted links, or thresholds directly.

## 4. Known specification defects

These are recorded here because the suite reports them as failures and a reader
should find the explanation next to the specification, not only in a CSV.

1. **The scenario file does not reproduce the v0.3 dataset.** The candidate sweep
   enables the scoped-candidate block *in memory* and records its chosen
   parameters in `generation_metadata.json` under `candidate_revision`. Loading
   `central_provisional.yaml` and re-running does not reproduce this benchmark.
   Until the selected parameters are written back into a versioned scenario file,
   the reproducibility manifest is the only complete record.

2. **The true-gap mean sits below its Monte Carlo interval.** Simulating the
   effective mixture with window censoring still over-predicts the mean gap by
   roughly half a month. The known unmodelled component is `cycles.py`'s
   hard-negative chain alignment, which relocates whole chains near a source's
   expected end and is not expressible in the saved parameter set.

3. **Byte-identical regeneration is untested.** The suite validates artifacts that
   already exist; it does not re-run the generator. Input checksums are recorded
   in every run manifest so a later regeneration can be compared against them, but
   determinism is reported `INCONCLUSIVE`, never `PASS`.

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
