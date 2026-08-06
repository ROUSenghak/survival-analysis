# Canonical Downstream Gates

Event and censoring outputs exist only as provisional linkage-dependent outputs
until manual audit labels are complete.

Current status:

- event/censoring: `PROVISIONAL_LINKAGE_OUTPUT`
- final event dataset: `BLOCKED_BY_MANUAL_AUDIT`
- final survival conclusions: `BLOCKED_BY_MANUAL_AUDIT`
- technology-specific survival: `BLOCKED_BY_EXTERNAL_CLASSIFICATION`
- technology trend analysis: `BLOCKED_BY_EXTERNAL_CLASSIFICATION`
- technology change-point analysis: `BLOCKED_BY_EXTERNAL_CLASSIFICATION`

Gate helpers live in:

- `src/boamp/status.py`

An unlinked notice is operationally censored. It is not a confirmed
non-renewal.
