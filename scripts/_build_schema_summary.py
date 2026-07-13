"""One-off helper (Step 2): builds reports/tables/boamp_source_schema_summary.csv
from reports/tables/boamp_observed_columns.csv plus schema-discovery notes
recorded during source investigation (see reports/run_logs/run_log.md)."""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TABLES_DIR = PROJECT_ROOT / "reports" / "tables"

obs = pd.read_csv(TABLES_DIR / "boamp_observed_columns.csv")
obs_map = obs.set_index("column").to_dict("index")

rows = []


def add(field, dtype, interp, useful, example_override=None):
    o = obs_map.get(field, {})
    rows.append({
        "field_name": field,
        "data_type": dtype,
        "non_null_rate": o.get("non_null_rate"),
        "example_values": example_override or o.get("sample_values"),
        "interpretation": interp,
        "useful_for_m0": useful,
    })


add("idweb", "string", "Unique BOAMP notice identifier (e.g. 24-10724). Used as notice_id.", "YES - primary key")
add("objet", "string", "Free-text procurement object/title.", "YES - text similarity (s_text)")
add("famille", "categorical", "Publication tier: MAPA (<90k EUR), FNS (90k EUR-EU threshold), JOUE (EU threshold), DSP (concessions).", "Indirect - affects schema_family of donnees")
add("code_departement", "string (list)", "Notice/buyer department code(s). Server-side filtered to Pays de la Loire (44,49,53,72,85) at download time.", "YES - defines the geographic scope")
add("dateparution", "date", "Notice publication date.", "YES - publication_date, temporal ordering")
add("datefindiffusion", "date", "End-of-diffusion date (notice removed from site).", "Auxiliary only")
add("datelimitereponse", "datetime", "Tender response deadline.", "Auxiliary only")
add("nomacheteur", "string", "Buyer/contracting authority name, as published.", "YES - buyer_name_raw / NAME_FALLBACK key")
add("titulaire", "string (list)", "Winning bidder name(s), only populated on ATTRIBUTION notices.", "Not used in M0 (no external enrichment of winner identity)")
add("perimetre", "categorical", "Legal regime (MAPA / FNSimple / DIRECTIVE-XX).", "Indirect")
add("nature", "categorical", "Notice type: APPEL_OFFRE, ATTRIBUTION, RECTIFICATIF, MODIFICATION, ANNULATION, PRE-INFORMATION, EX_ANTE_VOLONTAIRE, PERIODIQUE, INTENTION_CONCLURE, AUTRE.", "YES - notice_type_raw/normalized, defines source vs candidate pool")
add("descripteur_code", "string (list)", "BOAMP internal keyword-thesaurus codes (NOT official CPV codes - coarser, ~300 values).", "NO - true CPV taken from nested donnees instead")
add("type_marche", "categorical", "TRAVAUX / SERVICES / FOURNITURES.", "Not used directly in M0 v0, available for future refinement")
add("annonce_lie", "string (list)", "idweb(s) of a linked prior notice (e.g. ATTRIBUTION -> its APPEL_OFFRE). Native BOAMP cross-reference.", "YES - start_date_source=LINKED_ATTRIBUTION_DATE")
add("annonces_anterieures", "string/JSON", "Prior-notice reference block, populated on RECTIFICATIF-type notices.", "Not used in M0 v0")
add("source_schema", "string", "BOAMP XSD version tag (e.g. 3.2.5). Present for LEGACY-schema notices only.", "Diagnostic only")
add("url_avis", "string", "Public URL of the notice on boamp.fr.", "Traceability only")
add("donnees", "JSON (nested, schema varies)", "Full notice payload. Two structures observed: legacy BOAMP-XSD-derived JSON (FNS/MAPA/DSP, all years) and EU eForms/UBL JSON (JOUE, from ~late 2023). Source of SIRET/SIREN, true CPV, duration, org details.", "YES - via adaptive extraction (src/utils/boamp_schema.py)")
add("gestion", "JSON (nested)", "Redundant indexing metadata, duplicates top-level flat fields. Dropped at download time (select= param) to cut payload size ~7x.", "NO - not retrieved")
add("siret_candidates_raw (derived)", "string (list)", "SIRET-shaped (14-digit) values found by recursive key-pattern search inside donnees.", "YES - buyer_siret_raw/clean")
add("siren_candidates_raw (derived)", "string (list)", "SIREN-shaped (9-digit) values found the same way. Empirically ~0 percent - SIREN is recovered instead by truncating a valid SIRET.", "YES - buyer_siren_clean (mostly via derivation, not raw field)")
add("cpv_candidates_raw (derived)", "string (list)", "8-digit CPV codes found near a key containing \"cpv\" (legacy: CPV.objetPrincipal.classPrincipale; eForms: ItemClassificationCode).", "YES - cpv_clean, hierarchy fields, and the digital-scope hard filter (CPV divisions 32/35/48/72)")
add("duration_months_raw (derived)", "float", "Contract duration in months, from dureeMois/nbMois (legacy) or DurationMeasure+unitCode (eForms).", "YES - declared_duration_months, estimated_end_date")

pd.DataFrame(rows).to_csv(TABLES_DIR / "boamp_source_schema_summary.csv", index=False)
print(f"wrote {len(rows)} rows -> {TABLES_DIR / 'boamp_source_schema_summary.csv'}")
