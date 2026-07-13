"""Transparent, minimal cleaning for the free-text procurement object
(`objet`). Deliberately avoids aggressive normalization (stemming, stopword
removal, accent stripping) so the cleaned text stays human-readable and
auditable; that heavier normalization is left to the TF-IDF vectorizer at
scoring time (Step 7), which handles it internally and reproducibly."""

import re

from bs4 import BeautifulSoup

_WS_RE = re.compile(r"\s+")


def clean_objet(raw) -> str | None:
    if raw is None:
        return None
    v = str(raw)
    if not v.strip():
        return None
    # Strip HTML tags/entities if any slipped into the free text.
    if "<" in v and ">" in v:
        v = BeautifulSoup(v, "html.parser").get_text(separator=" ")
    v = v.replace("\xa0", " ").replace("​", "")
    v = _WS_RE.sub(" ", v).strip()
    return v or None


def normalize_objet(clean: str | None) -> str | None:
    if clean is None:
        return None
    return clean.lower()
