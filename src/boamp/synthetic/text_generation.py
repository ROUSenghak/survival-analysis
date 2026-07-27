"""Structured French procurement text generation (Phase 4.7 / 6.5).

Uses fixed templates + a small synthetic technical vocabulary, never real
BOAMP titles. CPV-division-conditioned vocabulary is a v0.1 placeholder
taxonomy (spec §4.3: "use broad CPV-based technological groups if the final
manually validated taxonomy is not available" — no such taxonomy exists
anywhere in this repo).

Four separate mechanisms, each independently controllable (spec Phase 4.7 /
6.5):
- base need text (`sample_division_vocab` -> `render_text`)
- same-cycle publication variation (`apply_same_cycle_variation`)
- next-cycle recurrence drift (`apply_next_cycle_drift`)
- same-buyer hard-negative text (`generate_hard_negative_text`)
"""
from __future__ import annotations

import numpy as np

# CPV division -> (concept phrases, vocabulary tokens). Divisions 32/35/48/72
# are the pipeline's own digital-scope divisions (config/pipeline.yaml
# scope.digital_cpv_divisions); kept distinguishable from non-digital
# divisions so a future scope-filtered synthetic subset stays meaningful.
DIVISION_VOCAB: dict[str, dict[str, list[str]]] = {
    "45": {"concepts": ["travaux de voirie", "réfection de bâtiment", "rénovation énergétique",
                          "construction d'école", "aménagement urbain"],
           "vocabulary": ["travaux", "chantier", "bâtiment", "voirie", "réhabilitation",
                           "construction", "aménagement", "toiture"]},
    "71": {"concepts": ["maîtrise d'œuvre", "étude géotechnique", "assistance à maîtrise d'ouvrage",
                          "diagnostic technique"],
           "vocabulary": ["étude", "ingénierie", "architecture", "diagnostic",
                           "maîtrise d'oeuvre", "conception"]},
    "90": {"concepts": ["collecte des déchets", "entretien des espaces verts",
                          "nettoyage des locaux", "assainissement"],
           "vocabulary": ["déchets", "collecte", "nettoyage", "entretien",
                           "espaces verts", "assainissement"]},
    "79": {"concepts": ["prestations de conseil", "services juridiques", "traduction",
                          "communication institutionnelle"],
           "vocabulary": ["conseil", "prestation", "communication", "services", "accompagnement"]},
    "50": {"concepts": ["maintenance des ascenseurs", "entretien du parc automobile",
                          "maintenance des installations techniques"],
           "vocabulary": ["maintenance", "entretien", "réparation", "installation", "exploitation"]},
    "66": {"concepts": ["assurance responsabilité civile", "services bancaires", "assurance dommages"],
           "vocabulary": ["assurance", "garantie", "couverture", "sinistre", "contrat"]},
    "32": {"concepts": ["fourniture d'équipements réseau", "matériel de télécommunication"],
           "vocabulary": ["réseau", "télécommunication", "équipement", "matériel"]},
    "35": {"concepts": ["système de vidéoprotection", "équipement de sécurité incendie"],
           "vocabulary": ["sécurité", "vidéoprotection", "alarme", "surveillance"]},
    "48": {"concepts": ["développement logiciel", "maintenance applicative", "progiciel de gestion"],
           "vocabulary": ["logiciel", "application", "système d'information", "développement", "progiciel"]},
    "72": {"concepts": ["infogérance", "hébergement cloud", "assistance informatique", "cybersécurité"],
           "vocabulary": ["informatique", "numérique", "cloud", "cybersécurité",
                           "réseau informatique", "infogérance"]},
    "34": {"concepts": ["acquisition de véhicules", "location de flotte automobile"],
           "vocabulary": ["véhicule", "flotte", "transport", "location"]},
}
_DEFAULT_VOCAB = {"concepts": ["prestations de services divers", "fourniture de matériel"],
                   "vocabulary": ["marché", "prestation", "fourniture", "service"]}

DIGITAL_DIVISIONS = frozenset({"32", "35", "48", "72"})


def sample_division_vocab(cpv_division: str, rng: np.random.Generator) -> tuple[list[str], list[str]]:
    """Return (base_concepts, base_vocabulary) for a need's CPV division:
    1-2 concept phrases + the division's vocabulary token list."""
    entry = DIVISION_VOCAB.get(cpv_division, _DEFAULT_VOCAB)
    n_concepts = 1 if rng.random() < 0.6 else 2
    concepts = list(rng.choice(entry["concepts"], size=min(n_concepts, len(entry["concepts"])), replace=False))
    return concepts, list(entry["vocabulary"])


def render_text(base_concepts: list[str], base_vocabulary: list[str], buyer_name: str,
                 department: str, role: str, rng: np.random.Generator) -> str:
    """Render a non-copying BOAMP-like procurement object.

    Real BOAMP objects mix terse titles, medium administrative descriptions,
    and a visible long tail. Earlier synthetic texts were all one reference +
    lot pattern, which compressed q90/q99 and over-produced synthetic-only
    bigrams such as ``ref/lot``. This keeps the text generator fully
    synthetic while varying common public-procurement constructions.
    """
    concept = rng.choice(base_concepts)
    vocab_terms = list(rng.choice(base_vocabulary, size=min(2, len(base_vocabulary)), replace=False))
    prefix = "Avis d'attribution" if role == "AWARD" else "Marché public"
    terms = " et ".join(vocab_terms)
    descriptor = str(rng.choice([
        "périmètre",
        "besoins",
        "utilisateurs",
        "sites",
        "équipements",
        "continuité",
        "suivi",
        "mise en service",
        "support",
        "prestations",
        "coordination",
        "exploitation",
        "adaptation",
        "renouvellement",
        "déploiement",
        "appui",
    ]))
    draw = rng.random()

    if draw < 0.32:
        patterns = [
            f"{concept.capitalize()} pour {buyer_name} - {descriptor}.",
            f"{prefix} pour la {concept} - {buyer_name} - {descriptor}.",
            f"{concept.capitalize()} : {terms} pour {buyer_name} - {descriptor}.",
        ]
        return str(rng.choice(patterns))

    if draw < 0.80:
        patterns = [
            f"{prefix} de {concept} pour {buyer_name} : {terms} et {descriptor}.",
            f"Fourniture et prestations de {concept} pour les besoins de {buyer_name}, {descriptor}.",
            f"Accord-cadre relatif à {concept} et prestations associées pour {buyer_name}, {descriptor}.",
            f"Mise en oeuvre de {concept} avec {terms} pour {buyer_name}, {descriptor}.",
        ]
        return str(rng.choice(patterns))

    long_clauses = [
        "comprenant maintenance, assistance aux utilisateurs et suivi des prestations",
        "incluant fourniture, installation, mise en service et accompagnement",
        "avec prestations associées, réunions de suivi et reporting périodique",
        "dans le cadre d'un accord-cadre à bons de commande",
        f"sur le département {department}, avec coordination technique et appui au démarrage",
    ]
    lot_clause = (
        f" lot {int(rng.integers(1, 4))}"
        if rng.random() < 0.20
        else ""
    )
    return (
        f"{prefix} de {concept}{lot_clause} pour {buyer_name}, {str(rng.choice(long_clauses))} : {terms}."
    )


def apply_same_cycle_variation(text: str, severity: float, rng: np.random.Generator) -> str:
    """Light publication-level rewording between notices of the SAME cycle
    (e.g. call vs award of one procurement episode) — calibrated to stay
    close to the real corpus's same-family similarity target (~1.0,
    calibration_parameters_v0_1.yaml#text.same_cycle_publication_similarity_target).
    Deliberately much milder than next-cycle drift."""
    if rng.random() > severity:
        return text
    tokens = text.rstrip(".").split(" ")
    if len(tokens) > 4 and rng.random() < 0.5:
        i, j = sorted(rng.choice(len(tokens) - 1, size=2, replace=False))
        tokens[i], tokens[j] = tokens[j], tokens[i]
    return " ".join(tokens) + "."


def apply_next_cycle_drift(text: str, base_vocabulary: list[str], rng: np.random.Generator,
                            severity: float) -> str:
    """Token-replacement drift for a true successor cycle's own text,
    severity in [0,1] (scenario-controlled `text.next_cycle_drift_severity`
    — SCENARIO_PARAMETER, no empirical anchor: calib_unidentified_parameters_scenarios.csv
    #true_text_corruption_process). Higher severity replaces more tokens
    with alternative in-vocabulary or generic-boilerplate terms, lowering
    the resulting lexical overlap with the source cycle's text."""
    tokens = text.rstrip(".").split(" ")
    n_replace = int(round(severity * len(tokens) * 0.5))
    if n_replace <= 0:
        return text
    idx = rng.choice(len(tokens), size=min(n_replace, len(tokens)), replace=False)
    replacements = list(base_vocabulary) + ["mise à jour", "nouvelle consultation", "reconduction"]
    for i in idx:
        tokens[i] = str(rng.choice(replacements))
    return " ".join(tokens) + "."


def generate_hard_negative_text(base_vocabulary: list[str], buyer_name: str, department: str,
                                 rng: np.random.Generator) -> str:
    """Same-buyer, plausible-but-different-need text: shares theme
    vocabulary but a different concept, stress-testing linkers that over-rely
    on buyer+CPV-division blocking (spec Phase 4.3 hard-negative requirement)."""
    vocab_terms = list(rng.choice(base_vocabulary, size=min(2, len(base_vocabulary)), replace=False))
    return f"Marché public divers pour {buyer_name} (département {department}) : {' et '.join(vocab_terms)}."
