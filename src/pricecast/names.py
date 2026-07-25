"""Canonicalisation of county / market / commodity strings.

One shared implementation so ingest, the geo registry, and the API agree on
what a place is called. Getting this wrong silently merges or splits series, so
it lives in one place and is unit-tested.

Two real defects in the source data motivated this module:
  * counties arrive hyphenated and inconsistently cased ('Uasin-Gishu',
    'Homa-bay') while the registries use spaced Title Case;
  * the same physical market appears as 'Kajiado' and 'Kajiado Market'.
"""
from __future__ import annotations

import re

_WS_RE = re.compile(r"\s+")
_MARKET_SUFFIX_RE = re.compile(r"\s+markets?$", re.IGNORECASE)

# Post-normalisation county spellings that need an explicit canonical form.
COUNTY_ALIASES = {
    "muranga": "Murang'a",
    "murang a": "Murang'a",
    "elgeyo marakwet": "Elgeyo Marakwet",
    "keiyo marakwet": "Elgeyo Marakwet",
    "tharaka nithi": "Tharaka Nithi",
    "homa bay": "Homa Bay",
    "trans nzoia": "Trans Nzoia",
    "uasin gishu": "Uasin Gishu",
    "taita taveta": "Taita Taveta",
    "tana river": "Tana River",
    "west pokot": "West Pokot",
    "nairobi city": "Nairobi",
}

_LOWER_WORDS = {"wa", "na", "of", "the"}


def squash(value: object) -> str:
    """Trim and collapse internal whitespace; None/NaN -> ''."""
    if value is None:
        return ""
    text = str(value)
    if text.strip().lower() in {"nan", "none", "nat"}:
        return ""
    return _WS_RE.sub(" ", text).strip()


def _title(text: str) -> str:
    parts = []
    for i, word in enumerate(text.split(" ")):
        low = word.lower()
        if i and low in _LOWER_WORDS:
            parts.append(low)
        elif "-" in word:
            parts.append("-".join(p.capitalize() for p in word.split("-")))
        else:
            parts.append(word[:1].upper() + word[1:].lower() if word else word)
    return " ".join(parts)


def canonical_county(value: object) -> str:
    """'Uasin-Gishu' / 'uasin gishu' -> 'Uasin Gishu'; 'Muranga' -> \"Murang'a\"."""
    text = squash(value).replace("-", " ")
    text = _WS_RE.sub(" ", text).strip()
    if not text:
        return ""
    key = text.lower().replace("'", " ")
    key = _WS_RE.sub(" ", key).strip()
    if key in COUNTY_ALIASES:
        return COUNTY_ALIASES[key]
    return _title(text)


def canonical_market(value: object, aliases: dict[str, str] | None = None) -> str:
    """Strip a trailing ' Market'/' Markets' and apply the operator alias table.

    Within one county 'Kajiado' and 'Kajiado Market' are always the same place,
    so the suffix is dropped unconditionally. Anything subtler (Kibuye vs
    Kisumu Kibuye) belongs in market_aliases.csv, which is applied last so an
    operator can always override the rule.
    """
    text = squash(value)
    if not text:
        return ""
    if aliases and text in aliases:
        return aliases[text]
    stripped = _MARKET_SUFFIX_RE.sub("", text).strip()
    text = stripped or text
    if aliases and text in aliases:
        return aliases[text]
    return text


def canonical_commodity(value: object) -> str:
    return squash(value)


def is_junk_market(market: str, county: str, junk: set[str]) -> bool:
    """Filter obvious test/placeholder rows (KAMIS contains a 'test market')."""
    if not market:
        return True
    if market.strip().lower() in junk:
        return True
    return not county
