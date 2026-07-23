# Validation Framework for the BOAMP Synthetic Record-Linkage Benchmark

**Prepared:** 23 July 2026  
**Purpose:** research and implementation specification, with no code implementation  
**Benchmark reviewed:** `v0_3_temporal_candidate_revision`

## Executive conclusion

The current generator is a credible prototype, but it is not yet a fully validated benchmark. It already has the most important architectural property: it separates a BOAMP-like observed table from hidden truth. It also distinguishes parameters that are observable in real BOAMP, approximated from silver-standard evidence, and unidentified. The latest version reproduces several conditional and short-horizon candidate-environment properties and is suitable for beginning linkage experiments.

The remaining gap is not “one more goodness-of-fit test.” The benchmark needs a layered validation protocol:

1. **Internal validity:** prove that code output agrees with the declared data-generating process and hidden truth.
2. **Fidelity:** compare observable real and synthetic BOAMP properties with effect sizes, uncertainty, and predeclared tolerances.
3. **Benchmark validity:** demonstrate that the candidate sets, ambiguity, hard negatives, true-match corruption patterns, and temporal difficulty are BOAMP-like.
4. **Downstream utility:** test whether conclusions about linkage algorithms are stable over realistic parameter and scenario uncertainty.
5. **Privacy and memorisation:** verify that the generator has not copied real records or rare combinations too closely.

No single test can validate all five layers. A benchmark should pass a matrix of checks, with critical failures blocking release and noncritical discrepancies documented as a “fidelity budget.” Statistical non-rejection is not evidence of equivalence. With large samples, negligible differences will often be significant; with small subgroups, important differences may be missed. Decisions should therefore be based primarily on confidence intervals, practical tolerances, standardized effect sizes, graphical diagnostics, and scenario coverage.

## 1. Evidence reviewed and its status

### 1.1 Available benchmark evidence

The reviewed development sequence contains:

- Notebook 04: calibration of observable BOAMP properties, separating `OBSERVABLE`, `SILVER_STANDARD`, and `UNIDENTIFIED` parameters.
- Notebook 05: initial latent-world, observed-corruption, and hidden-relation generation.
- Notebooks 06–08: marginal and conditional fidelity diagnosis and the v0.2 revision.
- Notebooks 09–10: temporal and production Layer-1 candidate-environment validation and the v0.3 revision.
- Notebook 11: final real-versus-synthetic comparison.
- The v0.3 technical report.
- The uploaded *Internship Guide – Predictive Modeling*.

Only the internship guide was physically available in this turn. The benchmark summary below also uses the saved notebook and report findings already reviewed in the immediately preceding project conversation. The underlying datasets were not available for independent reruns in that review.

### 1.2 What the internship guide establishes

The guide defines the operational objective: use procurement history to study renewal timing, technological trends, and text signals. It explains why linkage is needed before survival analysis. It is an operational brief, not empirical evidence that the proposed renewal assumptions are true. In particular, its six-month matching window, suggested linking rate, or renewal interpretation must not be converted into ground truth.

## 2. What the current generator does

### 2.1 Architecture

The generator creates two deliberately separated layers.

**Observed layer**

A BOAMP-like notice table containing only fields available to a linkage method. It represents notice dates, buyer information, identifiers, CPV information, duration, procurement text, schema or notice type, and their missing or corrupted forms.

**Hidden-truth layer**

A protected evaluation table containing synthetic entity identifiers, contract-family identifiers, latent notice/cycle relationships, corruption history, and scenario labels. These fields define true matches, non-matches, family membership, and the mechanism that produced each observed defect.

This separation prevents target leakage if access controls are enforced. It also makes tests possible that cannot be conducted on real BOAMP, such as exact candidate recall, relation-level precision and recall, and recovery by corruption type.

### 2.2 Latent and observed process

The generator appears to follow this conceptual sequence:

1. Generate buyers and buyer activity.
2. Generate latent contract families and cycles.
3. Generate notice events and dates within those families.
4. Generate substantive attributes such as CPV, duration, buyer identity, and procurement text.
5. Apply missingness and field corruptions, including identifier and buyer-name variation.
6. Export an observed table stripped of truth information.
7. Export hidden family and relation truth with corruption provenance.
8. Build or evaluate the same candidate environment used in the real Layer-1 pipeline.

The active v0.3 output contains **9,471 observed notices**, **6,866 latent cycles**, and **6,866 truth-relation rows**. The reported zero-candidate rate is **63.0%**, compared with **60.9%** in the real Layer-1 scope. Conditional and short-horizon temporal gates passed. The 60-month runway comparison failed, and the candidate-count upper tail remained weaker than the real data.

### 2.3 Information already available

- Observable marginal and conditional calibration targets.
- Provenance classes for at least some parameters.
- Explicit scenario treatment for unidentified recurrence properties.
- Latent family and relationship truth.
- Corruption histories and scenario labels.
- Temporal and candidate-environment diagnostics.
- A versioned development history showing how failed diagnostics changed the generator.

### 2.4 Important information still missing or insufficiently demonstrated

1. **Executable specification of the data-generating process.** Every distribution, conditioning set, support restriction, random seed, and transformation needs a machine-readable specification tied to a version.
2. **Formal invariant tests.** There is not yet enough evidence that every hidden relation is logically consistent, acyclic where required, temporally valid, and exactly reconstructable from family/cycle truth.
3. **Uncertainty on calibration targets.** Point targets alone hide sampling uncertainty and sparse-subgroup instability.
4. **Held-out real-data validation.** If the same BOAMP rows shaped and evaluated the generator, reported fidelity is optimistic.
5. **Joint dependence coverage.** Passing marginal and selected conditional checks does not establish multivariate fidelity.
6. **Missingness and corruption interactions.** Co-occurrence needs explicit joint and conditional validation, not only fieldwise rates.
7. **Text realism evidence.** Lexical, semantic, structural, duplication, and conditional text fidelity need separate checks.
8. **Identifier/name variation calibration.** Edit types, distances, alias multiplicity, source dependence, and temporal persistence require distributions, not only examples.
9. **Hard-negative realism.** The benchmark must reproduce near-duplicate non-matches, popular buyers, repeated CPVs, generic text, and dense temporal neighborhoods.
10. **Long-tail candidate complexity.** The reported weak candidate-count tail and failed 60-month runway remain material.
11. **Privacy/memorisation audit.** There is no demonstrated exact-copy, near-copy, rare-combination, or membership-inference assessment.
12. **Algorithmic validity.** `READY_FOR_LINKAGE` means ready to test algorithms, not already proven to rank them as real BOAMP would.
13. **Parameter robustness.** A single calibrated parameter vector cannot represent unidentified real recurrence and corruption mechanisms.
14. **Release governance.** Truth-table isolation, schema contracts, checksums, seeds, and benchmark versioning need formal controls.

## 3. Validation concepts

| Concept | Question | Real BOAMP needed? | Hidden truth needed? |
|---|---|---:|---:|
| Fidelity | Does the synthetic observed table resemble observable BOAMP? | Yes | No |
| Internal validity | Did the generator implement its declared mechanism correctly? | No | Yes |
| Benchmark validity | Does the synthetic linkage task contain BOAMP-like ambiguity and difficulty? | Descriptive/silver reference | Yes |
| Downstream utility | Are algorithm comparisons stable across credible BOAMP-like scenarios? | Optional descriptive anchor | Yes |
| Privacy/memorisation | Are records copied or training membership exposed? | Yes, securely | Sometimes |

Fidelity is not truth validity. A generator can closely match observed BOAMP and still use the wrong latent recurrence mechanism. Conversely, several latent mechanisms can generate similar observed data. Those mechanisms are **partially identified or unidentified** and must be represented by scenarios.

## 4. Statistical decision principles

### 4.1 Do not use “fail to reject” as “equivalent”

For a difference parameter \(\theta=\theta_S-\theta_R\), a classical test uses
\(H_0:\theta=0\). Failure to reject can mean either similarity or low power.

For practical equivalence, predeclare bounds \((-\Delta,\Delta)\) and use two one-sided tests:

\[
H_{01}:\theta\le -\Delta,\qquad H_{02}:\theta\ge \Delta.
\]

Equivalence is supported only if both null hypotheses are rejected, equivalently when the appropriate \(100(1-2\alpha)\%\) confidence interval lies wholly inside \((-\Delta,\Delta)\). Bounds must come from linkage relevance, measurement resolution, or a smallest effect size of interest, not from observed results. See Lakens (2017, 2018).

### 4.2 Use effect sizes and uncertainty

Every comparison should report:

- real and synthetic estimates;
- absolute and relative difference;
- a standardized effect size or probability distance;
- a bootstrap confidence interval, clustered at buyer or family level when needed;
- effective sample size;
- the predeclared tolerance;
- pass, warning, or fail status.

P-values are secondary. Multiple comparisons should use false-discovery-rate control for exploratory screens, while preregistered critical gates should remain individually interpretable.

### 4.3 Calibrate tolerances to use

Suggested starting tolerances are provisional and must be stress-tested:

- standardized mean difference: \(|\mathrm{SMD}|\le0.10\) good, \(0.10\)–\(0.20\) warning;
- categorical total-variation distance: \(\mathrm{TV}\le0.05\) overall and \(\le0.10\) in adequately sized subgroups;
- proportion difference: \(\le2\) percentage points for common fields, or \(\le10\%\) relative error for rare categories;
- correlation difference: \(|\Delta r|\le0.05\);
- quantile relative error: \(\le10\%\) at P50/P75/P90 and \(\le20\%\) at P95/P99;
- candidate zero-rate difference: \(\le3\) percentage points;
- candidate-count quantile error: \(\le10\%\) through P90 and \(\le20\%\) at P95/P99;
- exact real-row copies: zero unless explicitly whitelisted structural templates;
- linkage ranking stability: Kendall \(\tau\ge0.8\) across central scenarios, with no unexplained rank reversal.

These are governance defaults, not universal scientific constants.

## 5. Validation matrix

### 5.1 Marginal distributions

| Test or diagnostic | Definition and hypotheses | Assumptions, sensitivity, limitation | Effect size and plot | Scope and BOAMP use |
|---|---|---|---|---|
| Standardized mean difference | \(\mathrm{SMD}=(\bar x_S-\bar x_R)/\sqrt{(s_S^2+s_R^2)/2}\). TOST may test \(|\mu_S-\mu_R|<\Delta\). | Meaningful for numeric variables; affected by skew and outliers. Large \(n\) narrows CIs but does not change SMD. | SMD with cluster-bootstrap CI; mirrored density and ECDF. | Fidelity. Apply to duration, text length, dates transformed to elapsed time, and candidate counts. |
| Quantile difference | \(d_p=Q_S(p)-Q_R(p)\), or scaled \(d_p/\mathrm{IQR}_R\). Bootstrap CI; equivalence against quantile-specific bounds. | No parametric assumption. Tail estimates are unstable in sparse subgroups. | Absolute/relative quantile error; Q–Q plot with tolerance ribbon. | Fidelity. Essential for duration and heavy-tailed buyer activity/candidate counts. |
| Kolmogorov–Smirnov | \(D=\sup_x|\hat F_R(x)-\hat F_S(x)|\). \(H_0:F_R=F_S\); \(H_1:F_R\ne F_S\). | Continuous iid samples; ties/discreteness require permutation/bootstrap calibration. Very sensitive at large \(n\), less tail-sensitive. | Report \(D\), not only \(p\); ECDF difference plot. | Fidelity screen for continuous/date-derived variables. Do not declare equivalence from non-rejection. |
| Cramér–von Mises / Anderson–Darling | Integrated squared CDF difference; AD weights tails more strongly. Same equality null. | Distribution-free variants exist; dependence requires clustered resampling. Large samples detect tiny differences. | Standardized statistic plus quantile errors; P–P or tail Q–Q plot. | Fidelity for duration and buyer-activity tails. |
| Wasserstein-1 distance | \(W_1(F_R,F_S)=\int_0^1|Q_R(u)-Q_S(u)|du\). No required hypothesis test. | Requires comparable units; scale before aggregating fields. Interpretable in original units. | \(W_1/\mathrm{IQR}_R\); quantile transport plot. | Fidelity and robustness. Useful for dates, durations, lengths, and candidate counts. |
| Categorical TV / Jensen–Shannon | \(\mathrm{TV}=\frac12\sum_k|p_{Rk}-p_{Sk}|\). \(\mathrm{JS}=\frac12 KL(P\|M)+\frac12 KL(Q\|M)\). | Sparse categories require pooling or Bayesian smoothing. JS is finite with zeros. Chi-square p-values become unhelpful at large \(n\). | TV, JS, max category gap; sorted proportion/difference bars. | Fidelity for schema, notice type, CPV division, department, identifier source, scenario-observable proxies. |
| Cramér’s \(V\) for contingency tables | From Pearson \(\chi^2\), \(V=\sqrt{\chi^2/[n\min(r-1,c-1)]}\). Equality null for distributions. | Expected cell counts must be adequate or use exact/permutation methods. \(V\) depends on table dimensions. | \(V\), cellwise standardized residuals; mosaic/heatmap. | Fidelity of categorical marginals and associations. |

### 5.2 Conditional and subgroup fidelity

| Test or diagnostic | Definition and hypotheses | Assumptions, sensitivity, limitation | Effect size and plot | Scope and BOAMP use |
|---|---|---|---|---|
| Stratified distribution distances | Compute TV, \(W_1\), SMD, or quantile errors within subgroup \(g\), then aggregate \(D_w=\sum_g w_gD_g\) and report worst cases. | Sparse strata create noisy extremes. Predefine minimum \(n\), pool hierarchically, and retain an “insufficient evidence” status. | Weighted mean, P90 and maximum subgroup discrepancy; heatmap. | Fidelity by year, schema, notice type, department, CPV division, buyer activity, identifier source. |
| Conditional model comparison | Fit the same model in real and synthetic data: \(g(E[Y|X])=\alpha+\beta^\top X\). Compare \(\hat\beta_S-\hat\beta_R\) and predicted response surfaces. | Model is a probe, not necessarily the true DGP. Interactions and nonlinear terms should reflect linkage-relevant relations. | Standardized coefficient differences, CI overlap, prediction RMSE; coefficient/partial-dependence plots. | Fidelity. Model missing SIRET, duration, generic CPV, and text weakness from observed covariates. |
| Classifier two-sample test / pMSE | Label combined records \(T=1\) synthetic. Fit \(\hat p_i=P(T_i=1|X_i)\); \(\mathrm{pMSE}=N^{-1}\sum_i(\hat p_i-c)^2\), \(c=n_S/N\). \(H_0\): indistinguishable under the chosen classifier/model. | Strongly depends on classifier, preprocessing, train/test split, and class balance. Flexible models may exploit harmless artifacts. Must use held-out cross-fitting. | Standardized pMSE, classifier AUC and calibration; feature-importance and residual-by-subgroup plots. | Global fidelity diagnostic. Localize discrepancies rather than using AUC alone as a gate. Snoke et al. derive null behavior for logistic pMSE. |

### 5.3 Multivariate dependence

| Test or diagnostic | Definition and hypotheses | Assumptions, sensitivity, limitation | Effect size and plot | Scope and BOAMP use |
|---|---|---|---|---|
| Correlation/association matrix difference | \(\Delta_C=\|C_S-C_R\|_F\), plus cellwise \(\Delta r\). Use Pearson, Spearman, Cramér’s \(V\), or correlation ratio according to types. | Pairwise measures miss higher-order dependence; Pearson misses nonlinear dependence. CIs require cluster bootstrap. | Frobenius norm and max \(|\Delta r|\); paired heatmaps/difference heatmap. | Fidelity for missingness indicators, duration, text length, CPV quality, identifiers, and buyer activity. |
| Maximum Mean Discrepancy | \(\mathrm{MMD}^2=E k(X,X')+E k(Y,Y')-2E k(X,Y)\). \(H_0:P_R=P_S\). | Kernel and bandwidth choices matter; mixed data need appropriate kernels. Quadratic estimator can be costly. High power at large \(n\). | MMD with permutation CI/reference distribution; witness-function or subgroup contribution plot. | Multivariate fidelity on mixed feature embeddings. Use buyer-cluster permutations. Gretton et al. (2012). |
| Energy distance | \(\mathcal E=2E\|X-Y\|-E\|X-X'\|-E\|Y-Y'\|\). Zero iff distributions agree under standard conditions. | Numeric embedding and scaling matter; ordinary Euclidean distance can be dominated by high-dimensional noise. | Normalized energy distance; distance-distribution plot. | Multivariate fidelity as a robustness check to MMD. |
| Copula/rank dependence | Compare empirical copulas \(C_R,C_S\), tail-dependence coefficients, and rank correlations. | Requires careful handling of discrete variables and ties. Pairwise copulas still miss high-order structure. | Integrated copula distance, tail-dependence gaps; copula contour or rank scatter. | Fidelity of joint extremes such as highly active buyers with weak identifiers and dense candidates. |

### 5.4 Temporal, longitudinal, buyer, and family structure

| Test or diagnostic | Definition and hypotheses | Assumptions, sensitivity, limitation | Effect size and plot | Scope and BOAMP use |
|---|---|---|---|---|
| Count-rate and seasonal-profile comparison | For period \(t\), compare \(N_t\), shares, seasonal indices, and rate ratios. Poisson/negative-binomial probe: \(\log E[N_t]=\alpha+f(t)+\gamma^\top Z_t\). | Overdispersion and structural changes invalidate simple Poisson SEs. Calendar definition must match. | Rate-ratio CIs, normalized RMSE, seasonal amplitude/phase gap; aligned time-series plot. | Fidelity by month/year, schema, CPV, and notice type. |
| Autocorrelation and spectral comparison | \(\rho(k)=\mathrm{Cov}(X_t,X_{t-k})/\mathrm{Var}(X_t)\); compare \(\rho_S(k)-\rho_R(k)\) and periodograms. | Needs sufficiently long, regularly indexed series; trends must be treated consistently. Short series have wide uncertainty. | Max ACF gap, integrated spectral distance; ACF and periodogram overlays. | Fidelity of publication intensity and buyer-level activity. |
| Inter-event-time distribution | \(\Delta t_{ij}=t_{i,j}-t_{i,j-1}\). Compare via \(W_1\), quantiles, survival curves, and hazard estimates. | Right/left truncation and observation windows must match. Within-buyer dependence requires clustering. | Quantile ratios, integrated survival difference; Kaplan–Meier or cumulative-incidence plot. | Fidelity for observable buyer notice activity. Hidden family gaps are internal/scenario properties, not real-ground-truth targets. |
| Runway/window sensitivity | Recalculate temporal metrics and candidate distributions over windows \(w\in\{6,12,\ldots,60\}\) months. | Longer windows create unequal exposure near corpus boundaries. Use common support or exposure weighting. | Error curve across \(w\); window-by-metric heatmap. | Fidelity and benchmark validity. Directly addresses the failed 60-month v0.3 comparison. |
| Buyer activity distribution | \(A_b=\#\) notices per buyer or buyer-period. Compare zero-truncated counts, concentration, Lorenz curve, Gini \(G\), and top-share \(S_q\). | Buyer identifiers are imperfect in real BOAMP; definitions must be repeated by identifier source and silver-standard grouping. | \(W_1\) on \(\log(1+A_b)\), Gini gap, top 1/5/10% share gaps; log-log CCDF and Lorenz curves. | Fidelity, with explicit sensitivity to buyer resolution. |
| Family-size distribution | \(F_c=\#\) notices/cycles per synthetic contract family. Validate observed output against declared scenario distribution and analytic/Monte Carlo expectations. | No real truth target exists. Any real comparison is silver-standard and linkage-contaminated. | Parameter recovery, empirical-versus-target TV/\(W_1\); PMF/CCDF. | Internal validity and scenario coverage only. |

### 5.5 Missingness, corruption, identifiers, and names

| Test or diagnostic | Definition and hypotheses | Assumptions, sensitivity, limitation | Effect size and plot | Scope and BOAMP use |
|---|---|---|---|---|
| Missingness-rate and pattern comparison | Let \(M_j=1\) if field \(j\) is missing. Compare \(P(M_j=1)\), joint patterns \(P(M=m)\), and pattern entropy \(H(M)\). | Rare patterns need smoothing or top-pattern plus “other.” Missingness tokens must be standardized. | Rate gaps, TV/JS over patterns, entropy gap; UpSet plot and rate heatmap. | Fidelity for SIRET/SIREN, CPV, duration, text, and unresolved award fields. |
| Missingness dependence models | For each \(j\), fit \(\operatorname{logit}P(M_j=1|X_{\mathrm{obs}})=\alpha_j+\beta_j^\top X\), including other missingness indicators and interactions. Compare coefficients/predictions. | MAR/MNAR cannot generally be distinguished from observed data. Model misspecification is possible. | Predicted-risk calibration gap, coefficient differences, conditional AUC; partial-dependence plots. | Fidelity. Reproduce dependence on year, schema, type, buyer activity, CPV, and identifier source. |
| Little’s MCAR test | Compares pattern-specific observed means with common means; statistic is asymptotically \(\chi^2\). \(H_0\): MCAR. | Rejection only says “not MCAR”; non-rejection does not prove MCAR. Sensitive to normality, sample size, and variable choice. | Test statistic plus pattern effect sizes; pattern-specific mean plot. | Descriptive fidelity only. Do not use it to identify MAR versus MNAR. Rubin’s framework governs interpretation. |
| Error co-occurrence | For corruption indicators \(E_j\), compare \(P(E_j,E_k)\), lift \(L_{jk}=P(E_j,E_k)/[P(E_j)P(E_k)]\), odds ratios, and higher-order patterns. | Real BOAMP reveals defects, not latent “corruption events.” Define observable error proxies consistently. | Log-odds-ratio gap, TV over patterns; clustered heatmap/UpSet plot. | Fidelity for observable proxies; internal validity for generator-labelled corruption history. |
| Identifier validity and variation | Check syntactic constraints and check digits where applicable. Within latent buyer \(b\), compare number of observed variants and transition probabilities between valid, truncated, malformed, and missing states. | Real entity grouping is uncertain; use only high-precision identifiers or labelled silver groups. | Invalid-rate gaps, variant-count \(W_1\), transition TV; state-transition diagram and variant CCDF. | Fidelity plus internal validity. Never infer true buyer continuity from the existing linker. |
| Buyer-name variation | For pairs within a buyer group, compute normalized edit distance, Jaro/Jaro–Winkler, token Jaccard/cosine, abbreviation and legal-form changes. Compare distributions by same-time and time gap. | Silver groups based on strong identifiers overrepresent cleaner cases. String metrics are language and preprocessing dependent. | \(W_1\)/KS effect size for similarities; mixture separation/AUC as descriptive only; ridgeline by time gap and error type. | Fidelity using strong-ID silver groups; hidden-truth validation for synthetic same-buyer and different-buyer pairs. Jaro (1989), Cohen et al. (2003). |

### 5.6 Text-field realism

| Test or diagnostic | Definition and hypotheses | Assumptions, sensitivity, limitation | Effect size and plot | Scope and BOAMP use |
|---|---|---|---|---|
| Surface and lexical profile | Compare length, sentence count, character classes, digit rate, vocabulary, type-token ratio, n-gram frequencies, TF–IDF distributions, boilerplate share, and language-ID confidence. | Tokenization and length strongly affect metrics. Rare n-grams are unstable and may signal copying. | SMD/\(W_1\), JS on n-grams; Zipf, length ECDF, and top residual n-gram plots. | Fidelity by notice type, CPV, schema, year, and text-quality group. |
| Semantic distribution comparison | Embed texts using a fixed French or multilingual encoder. Compare with MMD/energy distance or a classifier two-sample test. | Encoder choice imports external bias; embeddings may miss numbers and procurement-specific wording. | MMD, energy distance, classifier AUC; UMAP only as an exploratory plot, plus centroid-distance heatmap. | Fidelity conditional on CPV, notice type, and buyer activity. |
| MAUVE | Quantizes text embeddings and summarizes a divergence frontier between real and generated text distributions. Higher is closer under the chosen representation. | Sensitive to embedding model, number of clusters, sample size, and text length. Designed for open-ended generation, so use as supporting evidence. | MAUVE with bootstrap CI; divergence-frontier plot. | Extended text-fidelity diagnostic. Pillutla et al. (2021). |
| Pairwise semantic preservation/corruption | For latent related notice pairs, calculate cosine or BERTScore-style contextual similarity; compare by corruption type and time gap. | BERTScore was developed for reference-based NLG, not entity resolution; it should not be treated as truth. | Similarity distributions and scenario effect sizes; ridgeline/violin plot. | Internal validity and benchmark difficulty. Ensure related records are similar but not trivially identical. |
| Text duplication and memorisation | Exact normalized matches, longest common substring, rare n-gram overlap, MinHash/Jaccard, and nearest-neighbor embedding similarity between synthetic and real texts. | Legitimate BOAMP boilerplate creates high overlap. Separate templates from record-specific spans. | Exact-copy count; P1/P5 nearest-neighbor distances relative to real holdout baseline; match-review table. | Privacy/memorisation. Any full record-specific copy is a critical failure. |

### 5.7 Candidate environment and linkage difficulty

| Test or diagnostic | Definition and hypotheses | Assumptions, sensitivity, limitation | Effect size and plot | Scope and BOAMP use |
|---|---|---|---|---|
| Candidate-count distribution | \(C_i=\#\{j:j\in\mathcal C(i)\}\). Compare zero rate, mean, quantiles, tail index, conditional distributions, and composition. | Must use identical candidate-generation rules and observation support. Real counts are observable but depend on pipeline design. | Zero-rate gap, \(W_1\), P50–P99 errors; log-scale CCDF and conditional boxplots. | Fidelity and benchmark validity. Critical because v0.3 underrepresents the upper tail. |
| Blocking recall / pairs completeness | \(\mathrm{PC}=|\mathcal C\cap M|/|M|\), where \(M\) is the set of true matching pairs. | Requires hidden truth; cannot be computed on real BOAMP without labels. | PC with family-cluster bootstrap CI; recall by corruption/scenario plots. | Internal and linkage evaluation. It must be high enough that comparison models, rather than blocking, are being tested. |
| Reduction ratio and pairs quality | \(\mathrm{RR}=1-|\mathcal C|/|\mathcal U|\); \(\mathrm{PQ}=|\mathcal C\cap M|/|\mathcal C|\), where \(\mathcal U\) is all eligible pairs. | RR alone rewards overly aggressive blocking; always pair it with PC. | RR, PQ, and PC frontier; efficiency frontier plot. | Hidden-truth validation and algorithm evaluation. |
| Hard-negative similarity | For candidate non-matches \(N\), compare each field-similarity vector \(z_{ij}\) and aggregate similarity distribution to true matches. Measure overlap, e.g. \(O=\int\min(f_M,f_N)\). | Real match class is unavailable. Real candidate distribution can anchor overall and silver subsets only. | Overlap coefficient, standardized gaps, classifier AUC; match/non-match density and field-agreement heatmaps. | Benchmark validity. Generate non-matches sharing buyers, CPV, time, generic text, or identifiers. |
| Ambiguity/rank diagnostics | For query \(i\), margin \(m_i=s_{i,(1)}-s_{i,(2)}\), true-match rank, candidate entropy, and number above score bands. | A score is algorithm-specific and must not define truth. Use several frozen probe linkers, not the production acceptance threshold. | Margin/rank distributions, MRR, entropy; recall-at-rank and margin plots. | Benchmark validity and downstream utility. Scores are probes only, never calibration truth. |
| Relation and family metrics | Pair precision/recall/F1; family B-cubed precision/recall; adjusted Rand index; variation of information; graph edge and connected-component errors. | Pairwise metrics can hide catastrophic over-merging; cluster metrics depend on singleton treatment. | All metrics with family bootstrap CI and error taxonomy; family-size/error plots. | Linkage evaluation against hidden truth. |
| Calibration and decision curves | For predicted match probability \(\hat p\), Brier \(=n^{-1}\sum(\hat p-y)^2\), log loss, calibration slope/intercept, expected calibration error, and precision–recall curves. | Requires probabilistic outputs and adequate positives. ECE depends on bins; use calibration curves and proper scores. | Brier/log loss, calibration slope, AUPRC; reliability and PR plots. | Linkage-algorithm evaluation. Prefer PR to ROC under extreme imbalance. |

### 5.8 Privacy, downstream utility, and robustness

| Test or diagnostic | Definition and hypotheses | Assumptions, sensitivity, limitation | Effect size and plot | Scope and BOAMP use |
|---|---|---|---|---|
| Exact and near-copy audit | Compare record hashes after canonicalization; mixed-type Gower distance \(d_G\); distance to closest real record \(\mathrm{DCR}(s)=\min_r d_G(s,r)\); nearest-neighbor distance ratio. | Distance depends on scaling and field weights. DCR/NNDR do **not** establish privacy and can miss membership leakage. | Exact-copy count, DCR quantiles relative to real–real and holdout–train baselines; ECDF. | Privacy screening. Review nearest pairs manually with template fields masked. |
| Rare-combination disclosure | For quasi-identifier pattern \(q\), compute real equivalence-class size \(k(q)\), synthetic reproduction, and uniqueness rate. | Classical \(k\)-anonymity is not a complete privacy guarantee and procurement entities may be public. Still relevant for accidental copying. | Count of reproduced real uniques/rare combinations; risk-by-frequency plot. | Privacy/memorisation. Define quasi-identifiers and legitimate public identifiers explicitly. |
| Membership-inference audit | Given member and non-member real records, attack score \(a(x)\); report ROC-AUC, TPR at low FPR, and attack advantage \(\max_t[\mathrm{TPR}(t)-\mathrm{FPR}(t)]\). Null baseline AUC \(=0.5\). | Requires a proper train/holdout split and threat model. Attack failure does not prove privacy; attack success is evidence of leakage. | AUC CI, advantage, TPR@1% FPR; ROC and risk-by-rarity plots. | Extended privacy validation. Hayes et al. (2019); van Breugel et al. (2023). |
| Train-synthetic-test-real / train-real-test-synthetic | Train the same downstream probe on one domain and test on a labelled held-out domain. Compare task loss and performance gaps. | Real BOAMP lacks linkage truth, so real linkage TSTR is impossible. It can still be used for observable auxiliary tasks such as notice type or CPV when labels are native. | Relative performance gap with paired bootstrap CI; performance-by-subgroup plot. | Downstream observable utility, not real linkage accuracy. |
| Algorithm ranking stability | For scenario \(s\), obtain metric vector \(m_{as}\) for algorithms \(a\). Compare rankings with Kendall \(\tau\), rank intervals, and probability of being best. | Results depend on algorithm set, tuning budget, and scenario weights. Avoid tuning and testing on the same seeds. | Kendall \(\tau\), rank reversal count, regret; rank heatmap/critical-difference plot. | Core downstream utility. The benchmark is useful if conclusions are stable across credible scenarios, not only one seed. |
| Parameter sensitivity and uncertainty | Sample parameter vectors \(\theta\) from calibrated uncertainty/scenario ranges. Estimate \(Y=f(\theta)\); use variance decomposition or Sobol indices \(S_i=\mathrm{Var}_{\theta_i}(E[Y|\theta_i])/\mathrm{Var}(Y)\). | Sobol analysis assumes a defined parameter distribution and can be expensive. Correlated parameters require suitable designs. | Sobol indices, response ranges, failure probabilities; tornado and response-surface plots. | Robustness and scenario validation. Focus on recurrence, corruption, missingness dependence, buyer concentration, and temporal windows. |
| Replicate/seed stability | Generate \(B\) datasets for each scenario. Decompose metric variance into scenario, seed, and algorithm components with a hierarchical model or ANOVA probe. | Replicates must be independent and code/version fixed. | Intraclass correlation, coefficient of variation, rank stability; variance-component plot. | Internal validity and downstream utility. One realization is insufficient. |

## 6. Internal-validity suite

Internal checks should run before any real-versus-synthetic comparison:

1. **Schema and support:** types, allowed values, date ranges, required uniqueness, and no hidden columns in observed data.
2. **Truth consistency:** every observed row maps to exactly one latent notice/cycle; every declared edge references existing nodes; relation types agree with family IDs.
3. **Temporal logic:** predecessor dates precede successor dates; no impossible negative gaps; boundary censoring is explicit.
4. **Graph invariants:** relations obey declared direction, multiplicity, and acyclicity; connected components agree with contract-family IDs.
5. **Corruption replay:** starting from pristine latent values and applying stored corruption events reproduces observed values exactly.
6. **Parameter recovery:** generated empirical moments and conditional probabilities fall inside Monte Carlo intervals implied by the declared DGP.
7. **Seed reproducibility:** same version, parameters, and seed produce identical checksums; different seeds produce distinct records but stable aggregate properties.
8. **Leakage isolation:** truth identifiers, corruption labels, and scenario labels are absent from observed exports, filenames, indexes, text, and metadata.
9. **Negative controls:** deliberately broken generators must fail the relevant test. This checks that the validation suite has power.
10. **Unit-of-analysis checks:** notice, cycle, relation, family, buyer, and candidate-pair counts reconcile.

## 7. Minimum required test suite

The benchmark should not be released for algorithm comparison unless all critical gates below pass.

| Gate | Required checks | Initial decision rule |
|---|---|---|
| Internal integrity | All ten checks in Section 6 | Zero invariant, leakage, or replay failures |
| Core marginals | TV/JS for categorical fields; quantile error and \(W_1\) for numeric fields | Within declared tolerances overall; warnings documented |
| Core conditionals | Year, schema, notice type, department, CPV division, buyer activity, identifier source | No critical subgroup outside tolerance; sparse groups labelled inconclusive |
| Missingness | Field rates, joint pattern TV, missingness dependence models | Reproduce common patterns and main directional dependencies |
| Temporal | Monthly/yearly profiles, inter-event times, 6–60 month runway sensitivity | Boundary-adjusted window curves acceptable; 60-month failure resolved or scoped out |
| Buyer/activity | Activity count distribution, concentration, top shares | Central and upper-tail errors within tolerance |
| Candidate environment | Zero rate, P50–P99 counts, conditional counts, hard-negative profile | Fix the candidate upper-tail deficit before claiming broad BOAMP-like difficulty |
| Text | Length/lexical profile, semantic two-sample distance, duplication audit | Conditional distributions plausible; zero unapproved record-specific copies |
| Names/identifiers | Validity, missingness, variant counts, within-buyer similarities | Match observable and silver-standard targets with bias caveat |
| Hidden-truth difficulty | Blocking PC/RR/PQ; match/non-match overlap; family metrics | High blocking PC and nontrivial overlap across all central scenarios |
| Algorithm utility | At least three substantively different linkage methods, held-out seeds, subgroup metrics | Conclusions not driven by one scenario; report rank uncertainty |
| Robustness | Multiple seeds and low/central/high unidentified scenarios | No unexplained critical metric or ranking instability |

## 8. Extended research-grade suite

Add the following for a thesis-quality benchmark:

- held-out real BOAMP years or buyers never used during generator design;
- nested bootstrap respecting buyer and family clusters;
- MMD and energy tests on mixed-feature representations;
- copula and tail-dependence diagnostics;
- classifier two-sample diagnostics with cross-fitting and local explanations;
- complete missingness-pattern and error co-occurrence models;
- temporal spectral, autocorrelation, change-point, and exposure-boundary analyses;
- MAUVE and procurement-domain embedding comparisons;
- rare n-gram, exact-copy, near-copy, DCR/NNDR, and membership-inference audits;
- hard-negative taxonomy and controlled counterfactual pairs where exactly one field is degraded;
- factorial scenario design over recurrence, buyer concentration, missingness, name corruption, text corruption, CPV quality, and temporal density;
- global sensitivity analysis and variance components across seeds;
- calibration, precision–recall, pairwise and cluster-level evaluation;
- error costs under several operational loss functions;
- algorithm-ranking stability, regret, and probability-of-best analysis;
- comparison against simple generators and deliberately misspecified ablations;
- expert review of a small, blinded sample for face validity, without treating expert opinions as real ground truth.

## 9. Decision framework and fidelity budget

Use three statuses:

- **Pass:** confidence interval lies within the practical tolerance or the invariant is exact.
- **Warning:** estimate crosses the tolerance, evidence is sparse, or a noncritical discrepancy remains.
- **Fail:** a critical invariant breaks, leakage occurs, or a core benchmark property falls materially outside tolerance.

Do not average all checks into one quality score. A high average can conceal a fatal defect. Instead, maintain:

1. critical gates that must all pass;
2. domain-level summaries;
3. a discrepancy register with magnitude, likely cause, linkage relevance, and accepted limitation;
4. a “fidelity budget” showing which real properties were intentionally simplified.

## 10. What cannot be validated from real BOAMP

Without reliable real-world ground truth, the following are not identified:

- true recurrence or renewal prevalence;
- the real distribution of contract-family sizes;
- true pairwise or family linkage accuracy;
- true match-score distributions;
- true false-positive and false-negative rates of the existing pipeline;
- the correct acceptance threshold;
- the true causal mechanism producing missing identifiers or corrupted fields;
- whether two semantically similar notices represent the same procurement;
- whether algorithm rankings on synthetic data exactly equal rankings under real BOAMP truth.

Existing accepted links, thresholds, scores, event rates, and the six-month window can be used only as:

- observable outputs of a particular pipeline;
- silver-standard subsets with explicit construction and expected bias;
- sensitivity anchors;
- descriptive candidate-environment references.

They must never calibrate hidden truth as if they were labels.

## 11. Concrete implementation plan for Codex

### Phase 0: Freeze definitions

1. Create a benchmark data dictionary and unit-of-analysis table.
2. Create a parameter registry with value/range, conditioning variables, provenance class, source notebook/table, uncertainty, and version.
3. Write a DGP specification describing generation order and conditional dependencies.
4. Define release scenarios for all unidentified parameters: at minimum low, central, and high recurrence/difficulty.
5. Predeclare critical metrics, tolerances, and boundary-handling rules.

### Phase 1: Internal validation

1. Build deterministic schema and truth-graph checks.
2. Implement corruption replay and count reconciliation.
3. Add Monte Carlo parameter-recovery tests.
4. Add leakage scans and checksum-based reproducibility.
5. Add negative-control tests that intentionally corrupt the generator.

### Phase 2: Real-data reference construction

1. Split real BOAMP into generator-development and held-out validation partitions, preferably by time plus a buyer holdout.
2. Produce a common analysis table with consistent preprocessing.
3. Estimate reference metrics with buyer-cluster bootstrap intervals.
4. Preserve raw, adjusted-for-exposure, and subgroup estimates.
5. Mark silver-standard results in a separate namespace and never merge them into truth parameters.

### Phase 3: Fidelity modules

Implement one module per domain:

- marginals;
- conditional/subgroup fidelity;
- multivariate dependence;
- temporal structure;
- buyer activity;
- missingness and error co-occurrence;
- names and identifiers;
- text;
- candidate environment;
- privacy.

Each module should write a machine-readable long table with:

`benchmark_version, scenario, seed, scope, subgroup, property, metric, real_estimate, synthetic_estimate, difference, effect_size, ci_low, ci_high, tolerance, status, provenance, notes`.

### Phase 4: Benchmark-difficulty validation

1. Run the production candidate logic without acceptance thresholds.
2. Measure candidate counts and composition on real and synthetic observed data.
3. On synthetic truth, measure PC, RR, PQ, true-match rank, hard-negative overlap, and performance by corruption/scenario.
4. Use several frozen probe linkers: deterministic rules, Fellegi–Sunter, and a supervised or modern similarity model.
5. Diagnose whether synthetic success comes from unintended shortcuts using ablation and feature-only probes.

### Phase 5: Downstream study

1. Separate generator tuning, algorithm tuning, and final evaluation seeds.
2. Run multiple seeds per scenario.
3. Report pairwise, cluster-level, calibration, and operational-cost metrics.
4. Estimate algorithm-by-scenario interactions and ranking uncertainty.
5. Publish conclusions only when they are stable across a declared scenario envelope, or state precisely where rankings reverse.

### Phase 6: Privacy and release

1. Canonical exact-copy scan.
2. Template-aware text-copy and mixed-type near-neighbor audit.
3. Rare-combination analysis.
4. Membership-inference audit if the generator was fitted to row-level BOAMP.
5. Remove truth from the algorithm-facing package and test package isolation.
6. Version observed data, truth, parameters, seeds, code commit, validation results, and release notes together.

### Phase 7: Reporting

Produce:

- validation summary;
- full metric table;
- parameter-provenance inventory;
- discrepancy register;
- scenario manifest;
- minimum-suite gate report;
- extended-suite appendix;
- reproducibility manifest.

The first implementation priority should be the internal-invariant suite and the candidate-count tail/runway failure. Broad multivariate tests should follow, because they can locate remaining dependencies that marginal gates missed.

## 12. Recommended report figures

1. Architecture diagram showing latent DGP, corruption, observed export, and sealed truth.
2. Parameter-provenance map: observable, silver-standard, unidentified/scenario.
3. Real-versus-synthetic SMD/TV heatmap by field and subgroup.
4. Q–Q panels for duration, buyer activity, text length, and candidate count.
5. Missingness UpSet plots and co-occurrence difference heatmap.
6. Buyer activity log-log CCDF and Lorenz curves.
7. Temporal count and inter-event-time panels with boundary-adjusted runway curves.
8. Candidate-count CCDF through P99, stratified by buyer activity and identifier quality.
9. Match versus hard-negative similarity distributions by field and scenario.
10. Algorithm precision–recall, calibration, and rank-stability plots.
11. Parameter sensitivity tornado/Sobol plot.
12. Privacy nearest-neighbor baseline comparison and flagged near-copy table.

## 13. Verified methodological references

1. Fellegi, I. P., & Sunter, A. B. (1969). “A Theory for Record Linkage.” *Journal of the American Statistical Association*, 64(328), 1183–1210. [Publisher page](https://www.tandfonline.com/doi/abs/10.1080/01621459.1969.10501049)
2. Jaro, M. A. (1989). “Advances in Record-Linkage Methodology as Applied to Matching the 1985 Census of Tampa, Florida.” *Journal of the American Statistical Association*, 84(406), 414–420. [JSTOR record](https://www.jstor.org/stable/2289924)
3. Christen, P. (2012). *Data Matching: Concepts and Techniques for Record Linkage, Entity Resolution, and Duplicate Detection*. Springer. [Springer reference](https://link.springer.com/rwe/10.1007/978-1-4899-7502-7_712-1)
4. Ferrante, A., & Boyd, J. (2012). “A Transparent and Transportable Methodology for Evaluating Data Linkage Software.” *Journal of Biomedical Informatics*, 45(1), 165–172. [DOI](https://doi.org/10.1016/j.jbi.2011.10.006)
5. Snoke, J., Raab, G. M., Nowok, B., Dibben, C., & Slavković, A. (2018). “General and Specific Utility Measures for Synthetic Data.” *Journal of the Royal Statistical Society: Series A*, 181(3), 663–688. [Article](https://academic.oup.com/jrsssa/article/181/3/663/7072005)
6. Gretton, A., Borgwardt, K. M., Rasch, M. J., Schölkopf, B., & Smola, A. (2012). “A Kernel Two-Sample Test.” *Journal of Machine Learning Research*, 13, 723–773. [JMLR](https://www.jmlr.org/papers/v13/gretton12a.html)
7. Székely, G. J., & Rizzo, M. L. (2013). “Energy Statistics: A Class of Statistics Based on Distances.” *Journal of Statistical Planning and Inference*, 143(8), 1249–1272. [DOI](https://doi.org/10.1016/j.jspi.2013.03.018)
8. Rizzo, M. L., & Székely, G. J. (2016). “Energy Distance.” *WIREs Computational Statistics*, 8(1), 27–38. [DOI](https://doi.org/10.1002/wics.1375)
9. Rubin, D. B. (1976). “Inference and Missing Data.” *Biometrika*, 63(3), 581–592. [JSTOR](https://www.jstor.org/stable/2335739)
10. Little, R. J. A. (1988). “A Test of Missing Completely at Random for Multivariate Data with Missing Values.” *Journal of the American Statistical Association*, 83(404), 1198–1202. [DOI](https://doi.org/10.1080/01621459.1988.10478722)
11. Carpenter, J. R., & Smuk, M. (2021). “Missing Data: A Statistical Framework for Practice.” *Biometrical Journal*, 63(5), 915–947. [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC7615108/)
12. Lakens, D. (2017). “Equivalence Tests: A Practical Primer for t Tests, Correlations, and Meta-Analyses.” *Social Psychological and Personality Science*, 8(4), 355–362. [PMC](https://pmc.ncbi.nlm.nih.gov/articles/PMC5502906/)
13. Lakens, D., Scheel, A. M., & Isager, P. M. (2018). “Equivalence Testing for Psychological Research: A Tutorial.” *Advances in Methods and Practices in Psychological Science*, 1(2), 259–269. [Publisher](https://journals.sagepub.com/doi/10.1177/2515245918770963)
14. Pillutla, K., Swayamdipta, S., Zellers, R., Thickstun, J., Welleck, S., Choi, Y., & Harchaoui, Z. (2021). “MAUVE: Measuring the Gap Between Neural Text and Human Text using Divergence Frontiers.” *NeurIPS 2021*. [Proceedings](https://proceedings.neurips.cc/paper/2021/hash/260c2432a0eecc28ce03c10dadc078a4-Abstract.html)
15. Zhang, T., Kishore, V., Wu, F., Weinberger, K. Q., & Artzi, Y. (2020). “BERTScore: Evaluating Text Generation with BERT.” *ICLR 2020*. [OpenReview](https://openreview.net/forum?id=SkeHuCVFDr)
16. Cohen, W. W., Ravikumar, P., & Fienberg, S. E. (2003). “A Comparison of String Distance Metrics for Name-Matching Tasks.” *IIWeb Workshop at IJCAI*. [Paper](https://www.cs.utexas.edu/~ai-lab/pubs/kdd03.pdf)
17. Hayes, J., Melis, L., Danezis, G., & De Cristofaro, E. (2019). “LOGAN: Membership Inference Attacks Against Generative Models.” *Proceedings on Privacy Enhancing Technologies*, 2019(1), 133–152. [Paper](https://petsymposium.org/popets/2019/popets-2019-0008.pdf)
18. van Breugel, B., Sun, H., Qian, Z., & van der Schaar, M. (2023). “Membership Inference Attacks against Synthetic Data through Overfitting Detection.” *AISTATS 2023*, PMLR 206. [PMLR paper](https://proceedings.mlr.press/v206/breugel23a/breugel23a.pdf)
19. Shringarpure, J. D., & de Rooij, C. P. B. M. (2021). “Measuring the Privacy of Synthetic Data.” *Transactions on Data Privacy*, 14. [DOI](https://doi.org/10.2478/tdp-2021-0004)
20. Fazekas, M., & Kocsis, G. (2020). “Uncovering High-Level Corruption: Cross-National Objective Corruption Risk Indicators Using Public Procurement Data.” *British Journal of Political Science*, 50(1), 155–164. [Cambridge University Press](https://www.cambridge.org/core/journals/british-journal-of-political-science/article/uncovering-highlevel-corruption-crossnational-objective-corruption-risk-indicators-using-public-procurement-data/8A1742693965AA92BE4D2BA53EADFDF0)

## Final assessment

The v0.3 generator has moved beyond a simple synthetic-table exercise. Its hidden truth, parameter provenance, conditional revision history, and candidate-environment checks form a sound base. But the label `READY_FOR_LINKAGE` should currently be interpreted narrowly: ready to begin controlled algorithm experiments.

Before the benchmark supports defensible algorithm comparisons, the project should:

1. formalize and test internal invariants;
2. resolve or explicitly scope the 60-month runway and candidate-tail failures;
3. validate multivariate, missingness, corruption, text, name, and identifier structure;
4. audit copying and membership risk;
5. demonstrate algorithm conclusions over multiple seeds and unidentified scenarios.

The strongest defensible claim will not be “the benchmark is equivalent to real BOAMP.” It will be:

> Within declared observable tolerances and a documented scenario envelope, the synthetic benchmark reproduces selected BOAMP structures and candidate difficulties; its hidden truth is internally correct; and conclusions about linkage algorithms are reported with sensitivity to the real properties that remain unidentified.
