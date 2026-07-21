"""Build notebooks/05_synthetic_benchmark_generation.ipynb and
notebooks/06_synthetic_fidelity_validation.ipynb from source (nbformat),
so the notebook JSON is generated once, reviewably, from this script rather
than hand-edited. Execute afterwards with:

  .venv/bin/jupyter nbconvert --to notebook --execute --inplace \
      notebooks/05_synthetic_benchmark_generation.ipynb \
      notebooks/06_synthetic_fidelity_validation.ipynb
"""
from __future__ import annotations

from pathlib import Path

import nbformat as nbf

ROOT = Path(__file__).resolve().parents[1]


def md(src: str) -> nbf.NotebookNode:
    return nbf.v4.new_markdown_cell(src)


def code(src: str) -> nbf.NotebookNode:
    return nbf.v4.new_code_cell(src)


def build_notebook_05() -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    cells = [
        md("""# 05 — Synthetic benchmark v0.1: pilot generation walkthrough

Runs the reusable generator package (`src/boamp/synthetic/`) end-to-end for
one scenario and inspects the result. All generation logic lives in
`src/boamp/synthetic/*.py`; this notebook only calls it and displays outputs
(spec: "Do not place core generation logic only in the notebook").

Adapts the gold-standard-and-corruption framework of Lam et al. (2024) to
public-procurement recurrence linkage: a clean latent world (buyers,
establishments, needs, cycles, true relations) is generated first, then
BOAMP-like publication notices are corrupted into `observed_notices`, while
the truth tables are retained separately and never exposed to Layer 1/Layer 2.
"""),
        code("""import sys
from pathlib import Path

PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd

from boamp.synthetic.parameters import load_calibration_parameters
from boamp.synthetic.scenarios import VALID_SCENARIOS, load_benchmark_defaults, load_scenario
from boamp.synthetic.pipeline import generate_clean_world, generate_observed_world, write_pilot_outputs

pd.set_option("display.max_colwidth", 120)
print("Available scenarios:", VALID_SCENARIOS)"""),
        md("## 1. Load configuration and select a scenario"),
        code("""SCENARIO_ID = "central_provisional"

calib = load_calibration_parameters(PROJECT_ROOT)
defaults = load_benchmark_defaults(PROJECT_ROOT)
scenario = load_scenario(PROJECT_ROOT, SCENARIO_ID)

print("benchmark_id:", defaults.benchmark_id)
print("target_n_buyers:", defaults.target_n_buyers, " target_n_notices (approx):", defaults.target_n_notices)
print("seeds:", defaults.seed.latent_world_seed, defaults.seed.corruption_seed)
print()
print(f"Scenario: {scenario.display_name!r} ({scenario.scenario_id})")
print("Purpose:", scenario.purpose.strip())
print("base_recurrence_propensity:", scenario.recurrence.base_recurrence_propensity)
print("identifiers.siret_missing_rate:", scenario.identifiers.siret_missing_rate)
print("cpv.missing_rate:", scenario.cpv.missing_rate)"""),
        md("## 2. Run a small pilot (n_buyers below the full 2,000-buyer default, for a fast notebook run)"),
        code("""world = generate_clean_world(SCENARIO_ID, PROJECT_ROOT, n_buyers=300, world_seed=defaults.seed.latent_world_seed)
print("Clean-world structural validation:", "PASS" if world["_validation"].passed else world["_validation"].failures())

observed, corruption_log = generate_observed_world(world, SCENARIO_ID, PROJECT_ROOT, corruption_seed=defaults.seed.corruption_seed)
print("observed_notices rows:", len(observed), " corruption_log rows:", len(corruption_log))"""),
        md("## 3. Row counts"),
        code("""row_counts = {k: len(v) for k, v in world.items() if k != "_validation"}
row_counts["observed_notices"] = len(observed)
row_counts["corruption_log"] = len(corruption_log)
pd.Series(row_counts, name="n_rows").to_frame()"""),
        md("## 4. Structural checks"),
        code("""from boamp.synthetic.validation import run_full_structural_validation

result = run_full_structural_validation(world)
pd.Series(result.checks, name="passed").to_frame()"""),
        md("## 5. Clean -> corrupted examples"),
        code("""clean_idx = world["clean_notices"].set_index("notice_id_synthetic")
sample_ids = observed["notice_id_synthetic"].sample(5, random_state=1).tolist()

compare_cols = ["buyer_siret_raw", "buyer_siren_raw", "buyer_name_raw", "cpv_clean",
                "declared_duration_months", "objet_clean", "linked_call_notice_id"]
clean_compare_cols = ["siret_true", "siren_true", "buyer_name_true", "cpv_true",
                      "duration_true_months", "objet_true", "linked_call_notice_id_true"]

rows = []
for nid in sample_ids:
    c = clean_idx.loc[nid]
    o = observed[observed["notice_id_synthetic"] == nid].iloc[0]
    for cc, oc in zip(clean_compare_cols, compare_cols):
        rows.append({"notice_id": nid, "field": oc, "clean": c[cc], "observed": o[oc]})
pd.DataFrame(rows)"""),
        md("## 6. Corruption type summary"),
        code("""corruption_log["corruption_type"].value_counts().to_frame("n_events")"""),
        code("""corruption_log.groupby("field")["corruption_type"].value_counts().unstack(fill_value=0)"""),
        md("## 7. Recurrence (NEXT_CYCLE) and NO_SUCCESSOR examples"),
        code("""next_cycle_examples = world["true_relations"][world["true_relations"]["relation_type"] == "NEXT_CYCLE"].head(5)
next_cycle_examples[["source_cycle_id", "target_cycle_id", "true_gap_months", "source_expected_end", "target_start"]]"""),
        code("""no_successor_examples = world["true_relations"][world["true_relations"]["relation_type"] == "NO_SUCCESSOR"].head(5)
no_successor_examples[["source_cycle_id", "target_cycle_id", "source_expected_end"]]"""),
        code("""print("Relation type mix:")
print(world["true_relations"]["relation_type"].value_counts(normalize=True))
gaps = world["true_relations"].loc[world["true_relations"]["relation_type"] == "NEXT_CYCLE", "true_gap_months"]
print(f"\\ntrue_gap_months beyond the real pipeline's 6-month window: {(gaps > 6).mean():.1%} of NEXT_CYCLE edges")"""),
        md("""## 8. Full pilot outputs

The full 2,000-buyer pilot for all three scenarios (`clean_sanity`,
`central_provisional`, `adverse_identity`) was already generated via
`boamp.synthetic.pipeline.generate_pilot` and is on disk at:

`data/processed/synthetic_benchmark/v0_1_provisional/<scenario>/world_001/corruption_001/`

Each directory contains `latent_buyers.parquet`, `latent_establishments.parquet`,
`latent_needs.parquet`, `latent_cycles.parquet`, `true_relations.parquet`,
`notice_family_membership.parquet`, `clean_notices.parquet`,
`observed_notices.parquet`, `corruption_log.parquet`, and
`generation_metadata.json`. Structural validation results for all three are
in `reports/generated/synthetic_benchmark/v0_1_clean_world_validation.md`.
Fidelity validation against the real corpus is in
`06_synthetic_fidelity_validation.ipynb`.
"""),
        code("""import json
for scen in ["clean_sanity", "central_provisional", "adverse_identity"]:
    meta_path = PROJECT_ROOT / "data/processed/synthetic_benchmark/v0_1_provisional" / scen / "world_001/corruption_001/generation_metadata.json"
    meta = json.loads(meta_path.read_text())
    print(scen, "-> validation:", meta["validation_status"], " row_counts:", meta["row_counts"])"""),
    ]
    nb["cells"] = cells
    return nb


def build_notebook_06() -> nbf.NotebookNode:
    nb = nbf.v4.new_notebook()
    cells = [
        md("""# 06 — Synthetic benchmark v0.1: fidelity validation

Compares the `central_provisional` pilot's `observed_notices` against the
real BOAMP corpus's calibration tables
(`reports/tables/synthetic_calibration/`), then runs the *existing*
production Layer 1 candidate-generation code
(`boamp.linkage.candidates.generate_pairs_single_key`) on the synthetic
`observed_notices` (via a thin adapter,
`boamp.synthetic.compatibility.adapt_observed_notices_to_sources`) so
candidate-count statistics — an emergent property, never assigned during
generation — can be compared directly.

Per spec, this is diagnostic only: no linkage accuracy claim is made here
(Phase 12), and no synthetic-generation parameter is retuned to make a
preferred linkage method "win".
"""),
        code("""import sys
from pathlib import Path

PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from boamp.config import load_config
from boamp.reporting.figures import setup_style
from boamp.synthetic.compatibility import adapt_observed_notices_to_sources
from boamp.linkage.candidates import generate_pairs_single_key

cfg = load_config(PROJECT_ROOT)
setup_style()

TABLES_DIR = PROJECT_ROOT / "reports" / "tables" / "synthetic_benchmark" / "v0_1"
FIG_DIR = PROJECT_ROOT / "reports" / "figures" / "synthetic_benchmark" / "v0_1"
TABLES_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

CALIB_DIR = PROJECT_ROOT / "reports" / "tables" / "synthetic_calibration"

SCENARIO = "central_provisional"
PILOT_DIR = PROJECT_ROOT / "data/processed/synthetic_benchmark/v0_1_provisional" / SCENARIO / "world_001/corruption_001"
observed = pd.read_parquet(PILOT_DIR / "observed_notices.parquet")
clean = pd.read_parquet(PILOT_DIR / "clean_notices.parquet")
buyers = pd.read_parquet(PILOT_DIR / "latent_buyers.parquet")
establishments = pd.read_parquet(PILOT_DIR / "latent_establishments.parquet")
print(f"Loaded {SCENARIO} pilot: {len(observed)} observed notices, {len(buyers)} buyers")"""),
        md("## 1. Volume and schema composition"),
        code("""fidelity_rows = []

def add_fidelity(dimension, real_value, synthetic_value, note=""):
    fidelity_rows.append(dict(dimension=dimension, real_value=real_value,
                               synthetic_value=synthetic_value, note=note))

real_schema_mix = pd.read_csv(CALIB_DIR / "parameter_inventory.csv").set_index("parameter_name").loc["schema_family_mix", "estimate_or_range"]
syn_schema_mix = observed["schema_family"].value_counts(normalize=True).round(3).to_dict()
add_fidelity("schema_family_mix", real_schema_mix, syn_schema_mix)
print("real: ", real_schema_mix)
print("synthetic:", syn_schema_mix)"""),
        code("""real_notice_type_mix = pd.read_csv(CALIB_DIR / "parameter_inventory.csv").set_index("parameter_name").loc["notice_type_mix", "estimate_or_range"]
syn_notice_type_mix = observed["notice_type_normalized"].value_counts(normalize=True).round(3).to_dict()
add_fidelity("notice_type_mix", real_notice_type_mix, syn_notice_type_mix)
print("real: ", real_notice_type_mix)
print("synthetic:", syn_notice_type_mix)"""),
        code("""fig, ax = plt.subplots(figsize=(7, 3.5))
observed.assign(year=observed["publication_date"].dt.year)["year"].value_counts().sort_index().plot(kind="bar", ax=ax)
ax.set_title(f"Synthetic notice volume by year ({SCENARIO} pilot)")
ax.set_xlabel("year"); ax.set_ylabel("n_notices")
fig.savefig(FIG_DIR / "v0_1_volume_by_year.png", bbox_inches="tight")
fig.savefig(FIG_DIR / "v0_1_volume_by_year.pdf", bbox_inches="tight")
plt.show()"""),
        md("## 2. Buyer activity / concentration"),
        code("""def gini(x):
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    cum = np.cumsum(x)
    return (n + 1 - 2 * (cum.sum() / cum[-1])) / n

real_gini = 0.832  # calib_buyer_concentration_lorenz.csv / parameter_inventory.csv (real corpus, n=5,268 buyers)
syn_gini = gini(buyers["activity_rate"])
add_fidelity("buyer_activity_gini", real_gini, round(syn_gini, 3),
             "real corpus n=5,268 buyers vs synthetic pilot n=2,000-equivalent-scale buyers (see generate_pilot n_buyers)")
print(f"real Gini = {real_gini}, synthetic Gini = {syn_gini:.3f}")"""),
        code("""establishments_per_buyer = establishments.groupby("buyer_id_true").size()
add_fidelity("establishments_per_buyer_mean", "n/a (not a real-corpus OBSERVABLE table)", round(establishments_per_buyer.mean(), 2),
             "no directly comparable real-corpus table exists (BOAMP does not expose a buyer->establishment hierarchy natively); reported for internal consistency only")
establishments_per_buyer.describe()"""),
        md("## 3. Identifier availability"),
        code("""real_siret_share = 0.272  # parameter_inventory.csv#siret_vs_name_fallback_share
syn_siret_share = observed["buyer_siret_raw"].notna().mean()
add_fidelity("siret_present_share", real_siret_share, round(syn_siret_share, 3))
print(f"real SIRET-present share = {real_siret_share}, synthetic = {syn_siret_share:.3f}")"""),
        md("## 4. CPV quality"),
        code("""real_cpv_missing = 0.1706
syn_cpv_missing = observed["cpv_clean"].isna().mean()
add_fidelity("cpv_missing_rate", real_cpv_missing, round(syn_cpv_missing, 3))

real_cpv_generic = 0.0714
syn_cpv_generic = (observed["cpv_clean"].fillna("").str[2:] == "000000").mean()
add_fidelity("cpv_generic_rate_among_present", real_cpv_generic, round(syn_cpv_generic, 3))
print(f"real cpv_missing={real_cpv_missing}, synthetic={syn_cpv_missing:.3f}")
print(f"real cpv_generic={real_cpv_generic}, synthetic~={syn_cpv_generic:.3f} (marginal, not among-present)")"""),
        md("## 5. Duration availability"),
        code("""real_duration_present = 0.1365
syn_duration_present = observed["declared_duration_months"].notna().mean()
add_fidelity("duration_present_rate", real_duration_present, round(syn_duration_present, 3))
print(f"real={real_duration_present}, synthetic={syn_duration_present:.3f}")"""),
        md("## 6. Text length and exact duplication"),
        code("""real_median_len = 98.0
syn_median_len = observed["objet_clean"].dropna().map(len).median()
add_fidelity("median_text_length_chars", real_median_len, syn_median_len)

real_dup_rate = 0.5143
syn_dup_rate = 1 - (observed["objet_clean"].dropna().nunique() / observed["objet_clean"].notna().sum())
add_fidelity("exact_duplicate_template_rate", real_dup_rate, round(syn_dup_rate, 3))
print(f"median length: real={real_median_len} synthetic={syn_median_len}")
print(f"exact-duplicate rate: real={real_dup_rate} synthetic={syn_dup_rate:.3f}")"""),
        md("## 7. Missingness co-occurrence (dependent corruption check)"),
        code("""missing_flags = pd.DataFrame({
    "identifier_missing": observed["buyer_siret_raw"].isna() & observed["buyer_siren_raw"].isna(),
    "cpv_missing": observed["cpv_clean"].isna(),
    "duration_missing": observed["declared_duration_months"].isna(),
})
phi = missing_flags.astype(int).corr()
add_fidelity("missingness_phi_identifier_cpv", "see calib_missingness_phi_matrix.csv (real)",
             round(phi.loc["identifier_missing", "cpv_missing"], 3),
             "positive correlation here evidences the latent quality-class dependent-corruption mechanism (missingness.py)")
phi"""),
        md("## 8. Notice-family size"),
        code("""fam = pd.read_parquet(PILOT_DIR / "notice_family_membership.parquet")
fam_size = fam.groupby("cycle_id_true").size()
real_fam_note = "see notice_family_size_distribution.csv (real, provisional-family-based)"
add_fidelity("notice_family_size_mean", real_fam_note, round(fam_size.mean(), 2))
fam_size.value_counts().sort_index()"""),
        md("""## 9. Candidate-environment fidelity (Phase 12 compatibility check)

Runs the **existing, unmodified** Layer 1 candidate-generation code on the
synthetic `observed_notices` (via a thin schema adapter) so candidate-count
statistics — an emergent output, never set during generation — can be
compared to the real corpus's own candidate-environment numbers. This
proves the production linkage code can consume `observed_notices.parquet`
and gives a first-pass fidelity read; it is **not** a linkage-accuracy
claim (no synthetic ground truth is used by the candidate generator, and no
generator parameter is tuned based on this result).
"""),
        code("""sources_adapted = adapt_observed_notices_to_sources(observed)
pairs, window_months = generate_pairs_single_key(sources_adapted, cfg, verbose=True)

cand_per_source = pairs[pairs["candidate_rank"] == 1]["n_candidates_for_source"]
n_eligible = (sources_adapted["buyer_key_type"] != "MISSING").sum()
n_with_candidates = pairs["source_notice_id"].nunique()
zero_candidate_rate = 1 - (n_with_candidates / n_eligible)

print(f"window_months used: {window_months}")
print(f"eligible sources (buyer_key present): {n_eligible}")
print(f"sources with >=1 candidate: {n_with_candidates}")
print(f"synthetic zero-candidate rate: {zero_candidate_rate:.1%}  (real corpus, USE_AS_FIDELITY_TARGET: 60.9%)")
print(f"synthetic candidates-per-source median/p90: {cand_per_source.median():.0f} / {cand_per_source.quantile(0.9):.0f}  "
      f"(real corpus: median=3, p90=12)")

add_fidelity("zero_candidate_source_rate", 0.609, round(zero_candidate_rate, 3),
             "real value is Layer 1 production (algorithm-conditioned); synthetic value uses the same production candidate-generation code on synthetic data, per Phase 9/12")
add_fidelity("candidates_per_source_median", 3, round(cand_per_source.median()))
add_fidelity("candidates_per_source_p90", 12, round(cand_per_source.quantile(0.9)))"""),
        md("## 10. Export fidelity tables and figures"),
        code("""fidelity_df = pd.DataFrame(fidelity_rows)
fidelity_df.to_csv(TABLES_DIR / "v0_1_fidelity_summary.csv", index=False)
fidelity_df"""),
        code("""fig, ax = plt.subplots(figsize=(6, 4))
ax.bar(["real (60.9%)", f"synthetic ({SCENARIO})"], [0.609, zero_candidate_rate], color=["tab:gray", "tab:blue"])
ax.set_ylabel("zero-candidate source rate")
ax.set_title("Zero-candidate rate: real corpus vs synthetic pilot")
fig.savefig(FIG_DIR / "v0_1_zero_candidate_rate_comparison.png", bbox_inches="tight")
fig.savefig(FIG_DIR / "v0_1_zero_candidate_rate_comparison.pdf", bbox_inches="tight")
plt.show()"""),
        md("""## 11. Discrepancy summary (for the freeze gate)

Read together with `reports/tables/synthetic_benchmark/v0_1/benchmark_freeze_gate.csv`.
"""),
        code("""print(fidelity_df.to_string(index=False))"""),
    ]
    nb["cells"] = cells
    return nb


if __name__ == "__main__":
    nb05 = build_notebook_05()
    nb06 = build_notebook_06()
    (ROOT / "notebooks" / "05_synthetic_benchmark_generation.ipynb").write_text(nbf.writes(nb05))
    (ROOT / "notebooks" / "06_synthetic_fidelity_validation.ipynb").write_text(nbf.writes(nb06))
    print("wrote notebooks 05 and 06")
