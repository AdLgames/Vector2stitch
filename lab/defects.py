"""The defect taxonomy, as a closed vocabulary.

Free-text defect notes cannot be counted, compared between reviewers, or
tracked across engine versions. These are the names from the quality doc's
taxonomy, with the engine cause each one usually points at, so a sew-out
score maps to something in the code rather than to an adjective.
"""

from __future__ import annotations

from enum import StrEnum


class Defect(StrEnum):
    GAPPING = "gapping"
    PUCKERING = "puckering"
    THREAD_BREAK = "thread_break"
    BULLETPROOF = "bulletproof"
    LOOPING_SATIN = "looping_satin"
    SUNKEN_STITCHES = "sunken_stitches"
    ILLEGIBLE_TEXT = "illegible_text"
    JAGGED_CURVES = "jagged_curves"
    VISIBLE_TRAVEL = "visible_travel"
    FILL_DISTORTION = "fill_distortion"


USUAL_CAUSE: dict[Defect, str] = {
    Defect.GAPPING: "pull comp too low; bad sequencing; weak underlay",
    Defect.PUCKERING: "density too high; insufficient underlay; sewing outside-in",
    Defect.THREAD_BREAK: "stitches too short; density hotspots; too many penetrations in one spot",
    Defect.BULLETPROOF: "overlapping layers without removing hidden stitches underneath",
    Defect.LOOPING_SATIN: "satin too wide without auto-split",
    Defect.SUNKEN_STITCHES: "missing or wrong underlay for the fabric's pile",
    Defect.ILLEGIBLE_TEXT: "text too small for thread weight; auto-traced instead of font-replaced",
    Defect.JAGGED_CURVES: "poor curve fitting; no short-stitching on tight inner curves",
    Defect.VISIBLE_TRAVEL: "travel runs not hidden under later objects; missing trims",
    Defect.FILL_DISTORTION: "no push compensation along stitch direction",
}
