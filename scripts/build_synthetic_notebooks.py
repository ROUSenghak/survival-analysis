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

Every real-vs-synthetic chart below uses the **same two colors** for the
same two series throughout (`COLOR_REAL` / `COLOR_SYNTHETIC`) so color
identity is never re-assigned mid-notebook; the freeze-gate scorecard uses a
separate, fixed status palette (never reused for series identity), since a
pass/fail state is a different kind of "job" than a real-vs-synthetic
comparison.
"""),
        code("""import sys
from pathlib import Path

PROJECT_ROOT = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D

from boamp.config import load_config
from boamp.reporting.figures import setup_style
from boamp.synthetic.compatibility import adapt_observed_notices_to_sources
from boamp.linkage.candidates import generate_pairs_single_key
from utils.identifiers import validate_siret

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
        md("""### Chart style

Categorical identity (real vs. synthetic) uses slots 1-2 of the validated
default palette (`references/palette.md` in the `dataviz` skill): blue for
"real corpus", orange for "synthetic pilot" — worst adjacent CVD deltaE 9.1,
comfortably clear of the deltaE>=8 target. Status colors (freeze-gate
scorecard) are a separate, fixed palette never reused for series identity.
"""),
        code("""COLOR_REAL = "#2a78d6"        # palette slot 1 (blue)  - "real corpus"
COLOR_SYNTHETIC = "#eb6834"   # palette slot 2 (orange) - "synthetic pilot"
COLOR_GRID = "#e3e2dd"
STATUS_COLOR = {
    "PASS": "#0ca30c", "PASS_WITH_LIMITATION": "#fab219",
    "NEEDS_REVISION": "#ec835a", "BLOCKED": "#d03b3b", "NOT_ASSESSED": "#9a9a95",
}
DIVERGING_CMAP = LinearSegmentedColormap.from_list("diverging_blue_red", ["#2a78d6", "#f0efec", "#e34948"])

def style_axes(ax, horizontal_grid=True):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(not horizontal_grid)
    ax.grid(axis="y" if horizontal_grid else "x", color=COLOR_GRID, linewidth=0.9, zorder=0)
    ax.set_axisbelow(True)

def real_synth_legend(ax, loc="upper right"):
    handles = [Line2D([0], [0], marker="s", linestyle="", color=COLOR_REAL, markersize=9, label="Real corpus"),
               Line2D([0], [0], marker="s", linestyle="", color=COLOR_SYNTHETIC, markersize=9, label=f"Synthetic ({SCENARIO})")]
    ax.legend(handles=handles, loc=loc, frameon=False)

def save(fig, name):
    fig.savefig(FIG_DIR / f"{name}.png", bbox_inches="tight", dpi=150)
    fig.savefig(FIG_DIR / f"{name}.pdf", bbox_inches="tight")"""),
        md("## 1. Volume and schema composition"),
        code("""fidelity_rows = []

def add_fidelity(dimension, real_value, synthetic_value, note=""):
    fidelity_rows.append(dict(dimension=dimension, real_value=real_value,
                               synthetic_value=synthetic_value, note=note))

real_schema_mix = {"LEGACY": 0.874, "EFORMS": 0.126}   # parameter_inventory.csv#schema_family_mix
syn_schema_mix = observed["schema_family"].value_counts(normalize=True).round(3).to_dict()
add_fidelity("schema_family_mix", "LEGACY=87.4%; EFORMS=12.6%", syn_schema_mix)

real_notice_type_mix = {"APPEL_OFFRE": 0.689, "ATTRIBUTION": 0.267, "OTHER": 0.045}   # parameter_inventory.csv#notice_type_mix
syn_notice_type_mix = observed["notice_type_normalized"].value_counts(normalize=True).round(3).to_dict()
add_fidelity("notice_type_mix", "APPEL_OFFRE=68.9%; ATTRIBUTION=26.7%; OTHER=4.5%", syn_notice_type_mix)

print("schema_family_mix  real:", real_schema_mix, " synthetic:", syn_schema_mix)
print("notice_type_mix    real:", real_notice_type_mix, " synthetic:", syn_notice_type_mix)"""),
        code("""fig, axes = plt.subplots(1, 2, figsize=(10, 4))

for ax, real_mix, syn_mix, title in [
    (axes[0], real_schema_mix, syn_schema_mix, "Schema family"),
    (axes[1], real_notice_type_mix, syn_notice_type_mix, "Notice type"),
]:
    categories = list(real_mix)
    x = np.arange(len(categories))
    width = 0.36
    ax.bar(x - width / 2, [real_mix[c] for c in categories], width, color=COLOR_REAL, zorder=3)
    ax.bar(x + width / 2, [syn_mix.get(c, 0.0) for c in categories], width, color=COLOR_SYNTHETIC, zorder=3)
    ax.set_xticks(x); ax.set_xticklabels(categories)
    ax.set_ylabel("share of notices")
    ax.set_title(title)
    style_axes(ax)

real_synth_legend(axes[1])
fig.suptitle(f"Composition: real corpus vs synthetic pilot ({SCENARIO})", y=1.03)
save(fig, "v0_1_composition_real_vs_synthetic")
plt.show()"""),
        code("""fig, ax = plt.subplots(figsize=(7, 3.5))
year_counts = observed.assign(year=observed["publication_date"].dt.year)["year"].value_counts().sort_index()
ax.bar(year_counts.index.astype(str), year_counts.values, color=COLOR_SYNTHETIC, zorder=3)
ax.set_title(f"Synthetic notice volume by year ({SCENARIO} pilot)")
ax.set_xlabel("year"); ax.set_ylabel("n_notices")
ax.tick_params(axis="x", rotation=45)
style_axes(ax)
save(fig, "v0_1_volume_by_year")
plt.show()"""),
        md("## 2. Buyer activity / concentration"),
        code("""def gini(x):
    x = np.sort(np.asarray(x, dtype=float))
    n = len(x)
    cum = np.cumsum(x)
    return (n + 1 - 2 * (cum.sum() / cum[-1])) / n

def lorenz_curve(x):
    x = np.sort(np.asarray(x, dtype=float))
    cum = np.cumsum(x) / x.sum()
    return np.concatenate([[0.0], np.arange(1, len(x) + 1) / len(x)]), np.concatenate([[0.0], cum])

real_gini = 0.832  # calib_buyer_concentration_lorenz.csv / parameter_inventory.csv (real corpus, n=5,268 buyers)
syn_gini = gini(buyers["activity_rate"])
add_fidelity("buyer_activity_gini", real_gini, round(syn_gini, 3),
             "real corpus n=5,268 buyers vs synthetic pilot n=2,000-equivalent-scale buyers (see generate_pilot n_buyers)")
print(f"real Gini = {real_gini}, synthetic Gini = {syn_gini:.3f}")"""),
        code("""real_lorenz_path = CALIB_DIR / "calib_buyer_concentration_lorenz.csv"
fig, ax = plt.subplots(figsize=(5.5, 5.5))

if real_lorenz_path.exists():
    real_lorenz = pd.read_csv(real_lorenz_path)
    ax.plot(real_lorenz["cum_share_buyers"], real_lorenz["cum_share_notices"],
            color=COLOR_REAL, linewidth=2, label=f"Real corpus (Gini={real_gini})")

syn_x, syn_y = lorenz_curve(buyers["activity_rate"])
ax.plot(syn_x, syn_y, color=COLOR_SYNTHETIC, linewidth=2, label=f"Synthetic pilot (Gini={syn_gini:.3f})")
ax.plot([0, 1], [0, 1], color="#9a9a95", linewidth=1.2, linestyle="--", label="Perfect equality")

ax.set_xlabel("cumulative share of buyers"); ax.set_ylabel("cumulative share of notices")
ax.set_title("Buyer-activity concentration (Lorenz curve)")
ax.legend(loc="upper left", frameon=False)
style_axes(ax, horizontal_grid=False)
ax.grid(color=COLOR_GRID, linewidth=0.9, zorder=0)
save(fig, "v0_1_buyer_lorenz_curve")
plt.show()"""),
        code("""establishments_per_buyer = establishments.groupby("buyer_id_true").size()
add_fidelity("establishments_per_buyer_mean", "n/a (not a real-corpus OBSERVABLE table)", round(establishments_per_buyer.mean(), 2),
             "no directly comparable real-corpus table exists (BOAMP does not expose a buyer->establishment hierarchy natively); reported for internal consistency only")
establishments_per_buyer.describe()"""),
        md("## 3-6. Identifier, CPV, duration and text availability"),
        code("""real_siret_share = 0.272  # parameter_inventory.csv#siret_vs_name_fallback_share: "Share of
# notices keyed by a *validated* SIRET vs falling back to a normalized-name key" -- checksum-valid,
# not merely non-null. The naive .notna() used in v0.1's first pass also counted corrupted-but-non-null
# SIRETs (INVALID_CHECKSUM outcomes from _corrupt_identifier) as "present", inflating the synthetic
# share; recomputed here with the same format+checksum validation the real metric uses.
syn_siret_valid = observed["buyer_siret_raw"].map(
    lambda v: validate_siret(v)[1] if pd.notna(v) else False
)
syn_siret_share = syn_siret_valid.mean()
add_fidelity("siret_present_share", real_siret_share, round(syn_siret_share, 3),
             "recomputed on checksum-validated presence (utils.identifiers.validate_siret), matching the "
             "real metric's definition -- not naive non-null share (see v0.1 fidelity report §2)")

real_cpv_missing = 0.1706
syn_cpv_missing = observed["cpv_clean"].isna().mean()
add_fidelity("cpv_missing_rate", real_cpv_missing, round(syn_cpv_missing, 3))

real_cpv_generic = 0.0714
syn_cpv_generic = (observed["cpv_clean"].fillna("").str[2:] == "000000").mean()
add_fidelity("cpv_generic_rate_among_present", real_cpv_generic, round(syn_cpv_generic, 3),
             "real value is conditional on CPV present; synthetic value here is marginal (not yet conditioned) - see freeze gate note")

real_duration_present = 0.1365
syn_duration_present = observed["declared_duration_months"].notna().mean()
add_fidelity("duration_present_rate", real_duration_present, round(syn_duration_present, 3))

real_median_len = 98.0
syn_median_len = float(observed["objet_clean"].dropna().map(len).median())
add_fidelity("median_text_length_chars", real_median_len, syn_median_len)

real_dup_rate = 0.5143
syn_dup_rate = 1 - (observed["objet_clean"].dropna().nunique() / observed["objet_clean"].notna().sum())
add_fidelity("exact_duplicate_template_rate", real_dup_rate, round(syn_dup_rate, 3))

rate_dims = ["siret_present_share", "cpv_missing_rate", "cpv_generic_rate_among_present",
             "duration_present_rate", "exact_duplicate_template_rate"]
rate_real = [real_siret_share, real_cpv_missing, real_cpv_generic, real_duration_present, real_dup_rate]
rate_syn = [syn_siret_share, syn_cpv_missing, syn_cpv_generic, syn_duration_present, syn_dup_rate]
for dim, r, s in zip(rate_dims, rate_real, rate_syn):
    print(f"{dim:35s} real={r:.3f}  synthetic={s:.3f}")"""),
        code("""fig, ax = plt.subplots(figsize=(7, 5))
y = np.arange(len(rate_dims))
height = 0.36
ax.barh(y + height / 2, rate_real, height, color=COLOR_REAL, zorder=3)
ax.barh(y - height / 2, rate_syn, height, color=COLOR_SYNTHETIC, zorder=3)
ax.set_yticks(y); ax.set_yticklabels(rate_dims)
ax.set_xlabel("rate (0-1)")
ax.set_title("Field-availability / quality rates: real vs synthetic")
ax.set_xlim(0, 1)
style_axes(ax, horizontal_grid=False)
ax.grid(axis="x", color=COLOR_GRID, linewidth=0.9, zorder=0)
real_synth_legend(ax, loc="lower right")
save(fig, "v0_1_rate_comparison")
plt.show()"""),
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
        code("""fig, ax = plt.subplots(figsize=(4.5, 4))
im = ax.imshow(phi.values, cmap=DIVERGING_CMAP, vmin=-1, vmax=1)
ax.set_xticks(range(len(phi.columns))); ax.set_xticklabels(phi.columns, rotation=40, ha="right")
ax.set_yticks(range(len(phi.index))); ax.set_yticklabels(phi.index)
for i in range(len(phi.index)):
    for j in range(len(phi.columns)):
        v = phi.values[i, j]
        ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                color="white" if abs(v) > 0.6 else "#0b0b0b", fontsize=9)
ax.set_title("Missingness co-occurrence (phi), synthetic pilot")
fig.colorbar(im, ax=ax, shrink=0.8, label="phi correlation")
save(fig, "v0_1_missingness_phi_heatmap")
plt.show()"""),
        md("## 8. Notice-family size"),
        code("""fam = pd.read_parquet(PILOT_DIR / "notice_family_membership.parquet")
fam_size = fam.groupby("cycle_id_true").size()
add_fidelity("notice_family_size_mean", "see notice_family_size_distribution.csv (real, provisional-family-based)", round(fam_size.mean(), 2))

fig, ax = plt.subplots(figsize=(5.5, 3.5))
counts = fam_size.value_counts().sort_index()
ax.bar(counts.index.astype(str), counts.values, color=COLOR_SYNTHETIC, zorder=3)
ax.set_xlabel("notices per cycle (CALL only vs CALL+AWARD)"); ax.set_ylabel("n_cycles")
ax.set_title("Notice-family size distribution (synthetic pilot)")
style_axes(ax)
save(fig, "v0_1_notice_family_size")
plt.show()"""),
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
        code("""fig, axes = plt.subplots(1, 2, figsize=(11, 4))

ax = axes[0]
cap = cand_per_source.quantile(0.99)
ax.hist(cand_per_source.clip(upper=cap), bins=30, color=COLOR_SYNTHETIC, zorder=3)
ax.axvline(3, color=COLOR_REAL, linewidth=2, linestyle="--", label="real median = 3")
ax.axvline(12, color=COLOR_REAL, linewidth=2, linestyle=":", label="real p90 = 12")
ax.set_xlabel("candidates per source (synthetic, clipped at p99)"); ax.set_ylabel("n_sources")
ax.set_title("Candidate-count distribution")
ax.legend(frameon=False)
style_axes(ax)

ax = axes[1]
labels = ["zero-candidate\\nrate", "median\\ncandidates/source", "p90\\ncandidates/source"]
real_vals = [0.609, 3, 12]
syn_vals = [zero_candidate_rate, cand_per_source.median(), cand_per_source.quantile(0.9)]
x = np.arange(len(labels)); width = 0.36
ax_twin_note = ax.bar(x - width / 2, real_vals, width, color=COLOR_REAL, zorder=3)
ax.bar(x + width / 2, syn_vals, width, color=COLOR_SYNTHETIC, zorder=3)
ax.set_xticks(x); ax.set_xticklabels(labels)
ax.set_title("Candidate-environment summary")
style_axes(ax)
real_synth_legend(ax)

fig.suptitle("Candidate environment: real Layer 1 production vs synthetic pilot (same production code)", y=1.04)
save(fig, "v0_1_candidate_environment")
plt.show()"""),
        md("## 10. Export fidelity tables"),
        code("""fidelity_df = pd.DataFrame(fidelity_rows)
fidelity_df.to_csv(TABLES_DIR / "v0_1_fidelity_summary.csv", index=False)
fidelity_df"""),
        md("""## 11. Fidelity scorecard (freeze gate)

Status colors are reserved for pass/fail state and never reused for series
identity elsewhere in this notebook (the real-vs-synthetic charts above use
`COLOR_REAL`/`COLOR_SYNTHETIC` throughout, never these).
"""),
        code("""gate = pd.read_csv(PROJECT_ROOT / "reports/tables/synthetic_benchmark/v0_1/benchmark_freeze_gate.csv")

fig, ax = plt.subplots(figsize=(8, 5.5))
y = np.arange(len(gate))[::-1]
colors = gate["status"].map(STATUS_COLOR)
ax.scatter(np.zeros(len(gate)), y, color=colors, s=140, zorder=3)
for yi, dim, status in zip(y, gate["dimension"], gate["status"]):
    ax.text(0.02, yi, f"{dim}  —  {status}", va="center", fontsize=9.5)
ax.set_xlim(-0.05, 1.6)
ax.set_yticks([])
ax.set_xticks([])
for spine in ax.spines.values():
    spine.set_visible(False)
ax.set_title("Synthetic benchmark v0.1_provisional — freeze-gate status by dimension")

legend_handles = [Line2D([0], [0], marker="o", linestyle="", color=c, markersize=10, label=s)
                   for s, c in STATUS_COLOR.items() if s in set(gate["status"])]
ax.legend(handles=legend_handles, loc="lower right", frameon=False, ncol=1)
save(fig, "v0_1_freeze_gate_scorecard")
plt.show()"""),
        md("""## 12. Discrepancy summary

Read together with `reports/tables/synthetic_benchmark/v0_1/benchmark_freeze_gate.csv`
and `reports/generated/synthetic_benchmark/v0_1_fidelity_report.md`.
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
