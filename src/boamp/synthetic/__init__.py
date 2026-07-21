"""Synthetic BOAMP-like linkage benchmark, v0.1 (provisional).

Adapts the gold-standard-and-corruption framework of Lam et al. (2024,
"Generating synthetic identifiers to support development and evaluation of
data linkage methods", IJPDS 9:1:18) to public-procurement recurrence
linkage: a clean latent procurement population (buyers, establishments,
procurement needs, contract cycles, known recurrence relations) is generated
first, then BOAMP-like publication notices are produced and subjected to
schema-dependent, attribute-dependent and co-occurring corruption, while a
separate known-truth relation table is retained and never exposed to the
Layer 1/Layer 2 linkage code.

See docs/methodology.md "Synthetic benchmark" section and
reports/generated/synthetic_benchmark/ for the full design rationale,
calibration provenance, and known limitations.
"""
