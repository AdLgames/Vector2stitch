"""Per-format limits.

The engine's own table, deliberately not read from the writer library: these
are the numbers our checks and splitting logic are built on, and a library
upgrade that quietly widened a limit should fail a test, not change output.
`test_export.py::test_our_limits_are_no_wider_than_the_writers` enforces that.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FormatLimits:
    """What one machine format can represent."""

    extension: str
    unit_mm: float
    max_move_mm: float
    """Longest single move, jump or stitch. Longer travel is split."""
    supports_thread_colors: bool
    """False means the file carries a colour *sequence* but not the thread
    identities; the worksheet is how the shop knows what to hang."""
    color_change_as_stop: bool


DST = FormatLimits(
    extension="dst",
    unit_mm=0.1,
    max_move_mm=12.1,
    supports_thread_colors=False,
    color_change_as_stop=True,
)
PES = FormatLimits(
    extension="pes",
    unit_mm=0.1,
    max_move_mm=12.7,
    supports_thread_colors=True,
    color_change_as_stop=False,
)
JEF = FormatLimits(
    extension="jef",
    unit_mm=0.1,
    max_move_mm=12.7,
    supports_thread_colors=True,
    color_change_as_stop=False,
)
EXP = FormatLimits(
    extension="exp",
    unit_mm=0.1,
    max_move_mm=12.7,
    supports_thread_colors=False,
    color_change_as_stop=False,
)

FORMATS: dict[str, FormatLimits] = {fmt.extension: fmt for fmt in (DST, PES, JEF, EXP)}


class UnsupportedFormat(ValueError):
    """A format the engine does not write."""


def limits_for(extension: str) -> FormatLimits:
    """Look up limits by file extension, with or without the dot."""
    key = extension.lower().lstrip(".")
    if key not in FORMATS:
        raise UnsupportedFormat(
            f"{extension!r} is not a supported output format; have {sorted(FORMATS)}"
        )
    return FORMATS[key]
