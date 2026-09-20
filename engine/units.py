"""Unit handling.

Millimetres everywhere in the engine. Conversion to machine units happens only
in engine.export, via these helpers -- nothing else multiplies by 10.
"""

from __future__ import annotations

from decimal import ROUND_HALF_EVEN, Decimal


def mm_to_units(value_mm: float, unit_mm: float) -> int:
    """Quantize a millimetre value to integer machine units.

    Uses banker's rounding on Decimal rather than float round() so the result
    does not depend on binary representation of the input -- a determinism
    requirement, since the same design must export byte-identically on any host.
    """
    quotient = Decimal(str(value_mm)) / Decimal(str(unit_mm))
    return int(quotient.quantize(Decimal(1), rounding=ROUND_HALF_EVEN))


def units_to_mm(value_units: int, unit_mm: float) -> float:
    """Convert integer machine units back to millimetres."""
    return float(Decimal(value_units) * Decimal(str(unit_mm)))
