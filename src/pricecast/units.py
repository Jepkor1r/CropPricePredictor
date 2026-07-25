"""Price-unit normalisation and conversion to a common KES/kg basis.

KAMIS quotes prices as "<amount>/<unit>" where the unit is inconsistent across
commodities and eras: 'Kg', 'kg', 'Bag', 'Crate', 'Net', 'Tray', 'Litre',
'Piece'. The previous pipeline silently dropped every row whose unit was not
the commodity's modal unit, which is workable for four crops and fatal at 270.

Here we normalise the unit string, then convert to KES/kg when a mass
equivalence is known (globally, e.g. Tonne, or per-commodity via
data/registry/packaging.csv). Units with a non-mass basis (Litre for milk,
Piece for eggs) are kept on their own basis rather than force-converted, and
unconvertible rows are reported instead of being dropped in silence.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import registry

_PLURAL_RE = re.compile(r"(?<=[a-z])s$", re.IGNORECASE)

# Fallbacks used when data/registry/units.csv is absent (keeps the library
# importable in a bare checkout; the CSV is the source of truth in practice).
_BUILTIN_UNITS: dict[str, tuple[str, float | None, str]] = {
    "kg": ("Kg", 1.0, "mass"),
    "kilogram": ("Kg", 1.0, "mass"),
    "g": ("Gram", 0.001, "mass"),
    "gram": ("Gram", 0.001, "mass"),
    "tonne": ("Tonne", 1000.0, "mass"),
    "ton": ("Tonne", 1000.0, "mass"),
    "mt": ("Tonne", 1000.0, "mass"),
    "bag": ("Bag", None, "packaging"),
    "extendedbag": ("Extended Bag", None, "packaging"),
    "net": ("Net", None, "packaging"),
    "crate": ("Crate", None, "packaging"),
    "carton": ("Carton", None, "packaging"),
    "basket": ("Basket", None, "packaging"),
    "bunch": ("Bunch", None, "packaging"),
    "tray": ("Tray", None, "packaging"),
    "head": ("Head", None, "packaging"),
    "piece": ("Piece", None, "count"),
    "pc": ("Piece", None, "count"),
    "no": ("Piece", None, "count"),
    "dozen": ("Dozen", None, "count"),
    "litre": ("Litre", None, "volume"),
    "liter": ("Litre", None, "volume"),
    "l": ("Litre", None, "volume"),
    "ltr": ("Litre", None, "volume"),
}


@dataclass(frozen=True)
class Conversion:
    """Outcome of converting one quoted price to the KES/kg basis."""

    price_per_kg: float | None
    canonical_unit: str
    basis: str                 # mass | packaging | count | volume | unknown
    kg_equivalent: float | None
    reason: str                # 'converted', 'already_kg', or why it failed

    @property
    def ok(self) -> bool:
        return self.price_per_kg is not None


def normalize_unit(raw: str | None) -> str | None:
    """'kg ' -> 'Kg', 'Bags' -> 'Bag', '90kg bag' -> 'Bag'. None when unusable."""
    if raw is None:
        return None
    s = str(raw).strip().strip(".")
    if not s:
        return None
    key = re.sub(r"[^a-z0-9]", "", s.lower())
    key = re.sub(r"^\d+kg", "", key)          # '90kgbag' -> 'bag'
    key = _PLURAL_RE.sub("", key) if key not in {"gras", "s"} else key
    table = registry.units()
    if key in table:
        return table[key]["canonical"]
    if key in _BUILTIN_UNITS:
        return _BUILTIN_UNITS[key][0]
    # unseen unit: title-case it so at least the grouping is case-stable
    return s.title()


def _unit_meta(canonical: str) -> tuple[float | None, str]:
    key = re.sub(r"[^a-z0-9]", "", canonical.lower())
    table = registry.units()
    if key in table:
        return table[key]["kg_equivalent"], table[key]["basis"]
    if key in _BUILTIN_UNITS:
        _, kg, basis = _BUILTIN_UNITS[key]
        return kg, basis
    return None, "unknown"


def kg_equivalent(commodity: str, canonical_unit: str) -> float | None:
    """Kg in one `canonical_unit` of `commodity`, or None if unknown."""
    global_kg, _ = _unit_meta(canonical_unit)
    if global_kg is not None:
        return global_kg
    row = registry.packaging().get((commodity.strip().lower(), canonical_unit.strip().lower()))
    return row["kg_equivalent"] if row else None


def to_per_kg(price: float | None, unit_raw: str | None, commodity: str) -> Conversion:
    """Convert a quoted price to KES/kg where a mass equivalence is known."""
    canonical = normalize_unit(unit_raw)
    if canonical is None:
        return Conversion(None, "", "unknown", None, "missing unit")
    _, basis = _unit_meta(canonical)
    if price is None:
        return Conversion(None, canonical, basis, None, "missing price")
    if canonical == "Kg":
        return Conversion(float(price), canonical, "mass", 1.0, "already_kg")
    kg = kg_equivalent(commodity, canonical)
    if kg is None or kg <= 0:
        return Conversion(
            None, canonical, basis, None,
            f"no kg equivalence for {commodity!r} in {canonical!r}"
            " (add a row to data/registry/packaging.csv)",
        )
    return Conversion(float(price) / kg, canonical, basis, kg, "converted")
