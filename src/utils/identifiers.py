"""
Format validation for raw BOAMP-provided SIRET/SIREN identifiers.

No external enrichment happens here: these functions only validate the
*format* (digit-only, correct length, valid Luhn-style checksum) of
identifiers that are already present in the BOAMP notice payload. Nothing is
looked up, inferred from, or cross-checked against an external database.
"""

import re
import unicodedata

_DIGITS_RE = re.compile(r"^\d+$")


def _luhn_ok(digits: str) -> bool:
    """French SIREN/SIRET check digit: Luhn algorithm applied to the full
    number (doubling every second digit from the right, subtracting 9 if the
    doubled value exceeds 9). A small number of legacy identifiers (e.g. some
    La Poste SIRET) are known exceptions to this rule; those are flagged as
    format-valid-but-checksum-failed rather than discarded, since BOAMP is
    still the origin of the value (see buyer_siret_checksum_valid column)."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def validate_siret(raw) -> tuple[bool, bool]:
    """Return (format_valid, checksum_valid) for a candidate SIRET string."""
    if raw is None:
        return False, False
    v = str(raw).strip()
    if not _DIGITS_RE.match(v) or len(v) != 14:
        return False, False
    return True, _luhn_ok(v)


def validate_siren(raw) -> tuple[bool, bool]:
    """Return (format_valid, checksum_valid) for a candidate SIREN string."""
    if raw is None:
        return False, False
    v = str(raw).strip()
    if not _DIGITS_RE.match(v) or len(v) != 9:
        return False, False
    return True, _luhn_ok(v)


def siren_from_siret(siret: str) -> str:
    """Take the first 9 digits of a valid SIRET. This is internal cleaning
    of a BOAMP-provided value (SIRET = SIREN + 5-digit NIC), not enrichment:
    no data from outside the BOAMP notice is introduced."""
    return siret[:9]


def normalize_buyer_name(raw) -> str | None:
    """Lowercase, strip accents, collapse whitespace/punctuation noise. Kept
    deliberately mild: this is for buyer_key fallback matching, not display."""
    if raw is None:
        return None
    v = str(raw).strip()
    if not v:
        return None
    v = unicodedata.normalize("NFKD", v)
    v = "".join(c for c in v if not unicodedata.combining(c))
    v = v.lower()
    v = re.sub(r"[^\w\s-]", " ", v)
    v = re.sub(r"\s+", " ", v).strip()
    return v or None
