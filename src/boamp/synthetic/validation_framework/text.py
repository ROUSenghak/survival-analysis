"""Text realism and the duplication / memorisation audit.

Two different questions share this module because they are computed from the
same objects (Section 5.6 and the text half of Section 5.8):

* *fidelity* -- do synthetic procurement objects look like real ones in
  length, vocabulary, n-gram profile and internal duplication? Text is what a
  linker falls back on whenever identifiers are weak, so a corpus whose texts
  are too distinctive silently makes linkage easier than it really is.
* *memorisation* -- has the generator copied real notices? Real BOAMP text
  contains heavy shared administrative boilerplate, so raw overlap with real
  text is expected and is not by itself evidence of copying. What matters is
  whether *record-specific* wording is reproduced, so the audit reports exact
  copies both including and excluding the generator's own declared template
  pools, and compares nearest-neighbour similarity against a real-vs-real
  baseline rather than against zero.
"""

from __future__ import annotations

import re
from collections import Counter

import numpy as np
import pandas as pd

from boamp.synthetic.corruption import EXACT_TEMPLATE_POOL, GENERIC_BOILERPLATE_POOL
from boamp.synthetic.validation_framework.loaders import BenchmarkData
from boamp.synthetic.validation_framework.models import (
    MetricResult,
    Status,
    classify_abs,
    classify_upper,
)
from utils.text_clean import normalize_objet


TOLERANCES = {
    "text_length_quantile_rel": 0.15,
    "token_count_quantile_rel": 0.20,
    "unigram_js": 0.30,
    "bigram_js": 0.40,
    "type_token_ratio_abs": 0.15,
    "digit_rate_abs": 0.05,
    "internal_duplicate_rate_pp": 10.0,
    "record_specific_exact_copies": 0,
    "nearest_neighbour_margin": 0.10,
}

SAMPLE_SIZE = 4000
NN_SAMPLE_SIZE = 750
RANDOM_SEED = 20260723
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _metric(
    data: BenchmarkData,
    scope: str,
    subgroup: str,
    prop: str,
    metric: str,
    real,
    synthetic,
    diff,
    effect,
    tolerance,
    status: Status | str,
    provenance: str = "observable_real_vs_synthetic",
    notes: str = "",
) -> MetricResult:
    return MetricResult(
        benchmark_version=data.benchmark_version,
        scenario=data.scenario,
        seed=data.seed_label,
        scope=scope,
        subgroup=subgroup,
        property=prop,
        metric=metric,
        real_estimate=real,
        synthetic_estimate=synthetic,
        difference=diff,
        effect_size=effect,
        ci_low=None,
        ci_high=None,
        tolerance=tolerance,
        status=status,
        provenance=provenance,
        notes=notes,
    )


def _tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(str(text).lower())


def _js_divergence(real: Counter, synthetic: Counter) -> float:
    keys = set(real) | set(synthetic)
    if not keys:
        return float("nan")
    rn = sum(real.values()) or 1
    sn = sum(synthetic.values()) or 1
    p = np.array([real.get(k, 0) / rn for k in keys], dtype=float)
    q = np.array([synthetic.get(k, 0) / sn for k in keys], dtype=float)
    m = 0.5 * (p + q)

    def kl(a, b):
        mask = a > 0
        return float((a[mask] * np.log2(a[mask] / b[mask])).sum())

    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def _ngram_counter(texts: pd.Series, n: int) -> Counter:
    counter: Counter = Counter()
    for text in texts:
        toks = _tokens(text)
        if n == 1:
            counter.update(toks)
        else:
            counter.update(tuple(toks[i : i + n]) for i in range(len(toks) - n + 1))
    return counter


def _type_token_ratio(texts: pd.Series) -> float:
    total, types = 0, set()
    for text in texts:
        toks = _tokens(text)
        total += len(toks)
        types.update(toks)
    return float(len(types) / total) if total else float("nan")


def _digit_rate(texts: pd.Series) -> float:
    chars = texts.fillna("").astype(str).str.len().sum()
    digits = texts.fillna("").astype(str).str.count(r"\d").sum()
    return float(digits / chars) if chars else float("nan")


def _shingles(text: str, k: int = 5) -> set[str]:
    toks = _tokens(text)
    if len(toks) < k:
        return {" ".join(toks)} if toks else set()
    return {" ".join(toks[i : i + k]) for i in range(len(toks) - k + 1)}


def _max_jaccard_against(index: dict[str, set[int]], text: str) -> float:
    """Best Jaccard similarity of ``text`` against an inverted shingle index."""
    shingles = _shingles(text)
    if not shingles:
        return float("nan")
    hits: Counter = Counter()
    sizes: dict[int, int] = {}
    for shingle in shingles:
        for doc_id in index["postings"].get(shingle, ()):  # type: ignore[index]
            hits[doc_id] += 1
    if not hits:
        return 0.0
    sizes = index["sizes"]  # type: ignore[assignment]
    best = 0.0
    for doc_id, overlap in hits.most_common(50):
        union = len(shingles) + sizes[doc_id] - overlap
        if union:
            best = max(best, overlap / union)
    return float(best)


def _build_shingle_index(texts: list[str]) -> dict:
    postings: dict[str, list[int]] = {}
    sizes: dict[int, int] = {}
    for doc_id, text in enumerate(texts):
        shingles = _shingles(text)
        sizes[doc_id] = len(shingles)
        for shingle in shingles:
            postings.setdefault(shingle, []).append(doc_id)
    return {"postings": postings, "sizes": sizes}


def run_text_profile_metrics(data: BenchmarkData) -> list[MetricResult]:
    rng = np.random.default_rng(RANDOM_SEED)
    real_texts = data.real["objet_clean"].dropna().astype(str)
    syn_texts = data.observed["objet_clean"].dropna().astype(str)
    if real_texts.empty or syn_texts.empty:
        return [
            _metric(
                data, "text", "overall", "objet_clean", "availability",
                len(real_texts), len(syn_texts), None, None, "n>0", Status.INCONCLUSIVE,
                notes="no text on one side",
            )
        ]

    real_sample = real_texts.sample(min(SAMPLE_SIZE, len(real_texts)), random_state=RANDOM_SEED)
    syn_sample = syn_texts.sample(min(SAMPLE_SIZE, len(syn_texts)), random_state=RANDOM_SEED)
    metrics: list[MetricResult] = []

    for prop, real_values, syn_values, tol_key in [
        ("text_length_chars", real_texts.str.len(), syn_texts.str.len(), "text_length_quantile_rel"),
        (
            "token_count",
            real_texts.map(lambda t: len(_tokens(t))),
            syn_texts.map(lambda t: len(_tokens(t))),
            "token_count_quantile_rel",
        ),
    ]:
        for q in [0.50, 0.90, 0.99]:
            rq = float(real_values.quantile(q))
            sq = float(syn_values.quantile(q))
            rel = abs(sq - rq) / (abs(rq) if abs(rq) > 1e-9 else 1.0)
            metrics.append(
                _metric(
                    data, "text", "overall", prop, f"q{int(q * 100)}_relative_error",
                    rq, sq, sq - rq, rel, TOLERANCES[tol_key], classify_upper(rel, TOLERANCES[tol_key]),
                )
            )

    for n, tol_key in [(1, "unigram_js"), (2, "bigram_js")]:
        js = _js_divergence(_ngram_counter(real_sample, n), _ngram_counter(syn_sample, n))
        metrics.append(
            _metric(
                data, "text", "overall", f"{'uni' if n == 1 else 'bi'}gram_distribution", "JS",
                None, None, js, js, TOLERANCES[tol_key], classify_upper(js, TOLERANCES[tol_key]),
                notes=f"sampled {len(real_sample)} real / {len(syn_sample)} synthetic texts",
            )
        )

    ttr_real, ttr_syn = _type_token_ratio(real_sample), _type_token_ratio(syn_sample)
    metrics.append(
        _metric(
            data, "text", "overall", "type_token_ratio", "abs_diff",
            ttr_real, ttr_syn, ttr_syn - ttr_real, abs(ttr_syn - ttr_real),
            TOLERANCES["type_token_ratio_abs"],
            classify_abs(ttr_syn - ttr_real, TOLERANCES["type_token_ratio_abs"]),
            notes="lexical diversity; a synthetic corpus built from a small vocabulary reads as too repetitive",
        )
    )

    dr_real, dr_syn = _digit_rate(real_sample), _digit_rate(syn_sample)
    metrics.append(
        _metric(
            data, "text", "overall", "digit_rate", "abs_diff",
            dr_real, dr_syn, dr_syn - dr_real, abs(dr_syn - dr_real), TOLERANCES["digit_rate_abs"],
            classify_abs(dr_syn - dr_real, TOLERANCES["digit_rate_abs"]),
        )
    )

    # Internal duplication drives how much discriminating signal text carries:
    # a corpus where half the notices share wording forces the linker onto
    # other fields exactly as the real corpus does.
    real_norm = data.real["objet_normalized"] if "objet_normalized" in data.real.columns else real_texts.map(normalize_objet)
    syn_norm = syn_texts.map(normalize_objet)
    real_dup = float(real_norm.dropna().duplicated(keep=False).mean())
    syn_dup = float(syn_norm.dropna().duplicated(keep=False).mean())
    diff_pp = (syn_dup - real_dup) * 100
    metrics.append(
        _metric(
            data, "text", "overall", "internal_duplicate_share", "abs_diff_pp",
            real_dup, syn_dup, diff_pp, abs(diff_pp), TOLERANCES["internal_duplicate_rate_pp"],
            classify_abs(diff_pp, TOLERANCES["internal_duplicate_rate_pp"]),
            notes="share of notices whose normalized text is not unique in its own corpus",
        )
    )
    return metrics


def run_text_memorisation_audit(data: BenchmarkData) -> list[MetricResult]:
    """Exact-copy and near-copy audit of synthetic text against real text."""
    real_texts = data.real["objet_clean"].dropna().astype(str)
    syn_texts = data.observed["objet_clean"].dropna().astype(str)
    if real_texts.empty or syn_texts.empty:
        return []

    template_pool = {normalize_objet(t) for t in EXACT_TEMPLATE_POOL + GENERIC_BOILERPLATE_POOL}
    real_norm = set(real_texts.map(normalize_objet).dropna())
    syn_norm = syn_texts.map(normalize_objet).dropna()

    exact_hits = syn_norm[syn_norm.isin(real_norm)]
    # Template-derived text is generator-authored boilerplate that legitimately
    # resembles administrative phrasing; only non-template overlap is evidence
    # of the generator reproducing a specific real record.
    record_specific = exact_hits[~exact_hits.isin(template_pool)]
    n_record_specific = int(record_specific.nunique())

    metrics = [
        _metric(
            data, "privacy", "text", "exact_normalized_copy", "count_all",
            None, int(exact_hits.nunique()), None, None, "context_only", Status.PASS,
            provenance="privacy_audit",
            notes=(
                f"{int(exact_hits.nunique())} distinct synthetic strings also occur in real text; "
                "expected because both corpora share administrative boilerplate"
            ),
        ),
        _metric(
            data, "privacy", "text", "record_specific_exact_copy", "count",
            None, n_record_specific, n_record_specific, n_record_specific,
            TOLERANCES["record_specific_exact_copies"],
            Status.PASS if n_record_specific == 0 else Status.FAIL,
            provenance="privacy_audit",
            notes=(
                "exact real-text reproductions outside the generator's declared template pools; "
                "any non-zero value is release-blocking. Examples: "
                + "; ".join(list(record_specific.unique()[:3]))
            ),
        ),
    ]

    # Near-copy audit. A distance to the closest real record is only
    # interpretable against a baseline, so the same statistic is computed for a
    # held-out slice of real text against the rest of the real corpus: if
    # synthetic text is no closer to real text than real text is to itself,
    # there is no evidence of near-copying.
    rng = np.random.default_rng(RANDOM_SEED)
    real_pool = real_texts.sample(min(SAMPLE_SIZE, len(real_texts)), random_state=RANDOM_SEED).tolist()
    holdout_n = min(NN_SAMPLE_SIZE, len(real_pool) // 4)
    real_holdout = real_pool[:holdout_n]
    real_index_texts = real_pool[holdout_n:]
    index = _build_shingle_index(real_index_texts)

    syn_probe = syn_texts.sample(min(NN_SAMPLE_SIZE, len(syn_texts)), random_state=RANDOM_SEED).tolist()
    syn_nn = np.array([_max_jaccard_against(index, t) for t in syn_probe], dtype=float)
    real_nn = np.array([_max_jaccard_against(index, t) for t in real_holdout], dtype=float)

    for label, q in [("p95", 0.95), ("p99", 0.99)]:
        syn_q = float(np.nanquantile(syn_nn, q)) if syn_nn.size else float("nan")
        real_q = float(np.nanquantile(real_nn, q)) if real_nn.size else float("nan")
        margin = syn_q - real_q
        metrics.append(
            _metric(
                data, "privacy", "text", "nearest_real_neighbour_jaccard", f"{label}_excess_over_real_baseline",
                real_q, syn_q, margin, abs(margin), TOLERANCES["nearest_neighbour_margin"],
                classify_upper(margin, TOLERANCES["nearest_neighbour_margin"])
                if np.isfinite(margin)
                else Status.INCONCLUSIVE,
                provenance="privacy_audit",
                notes=(
                    f"5-token shingle Jaccard against {len(real_index_texts)} real texts; "
                    f"real-vs-real holdout baseline n={len(real_holdout)}, synthetic probe n={len(syn_probe)}. "
                    "Positive excess means synthetic text sits closer to real text than real text does to itself"
                ),
            )
        )
    return metrics


def run_text_validation(data: BenchmarkData) -> list[MetricResult]:
    return run_text_profile_metrics(data) + run_text_memorisation_audit(data)
