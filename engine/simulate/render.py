"""Stitch simulation.

Renders what the machine will actually do, by reading the written machine file
back -- never the plan or the IR. If the engine and the writer disagree, the
picture shows the writer's version, which is the one the shop will sew.

M0 draws flat lines: penetrations joined in sew order, travel dashed. Shaded
capsules with thread-width highlight and a fabric ground come with the editor
(M5). Either way the disclaimer from the quality doc stands: a render is not
proof of quality. Only thread on fabric is.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pyembroidery

from engine.units import units_to_mm

_STITCH = pyembroidery.STITCH
_JUMP = pyembroidery.JUMP
_TRIM = pyembroidery.TRIM
_COLOR_CHANGE = pyembroidery.COLOR_CHANGE
_UNIT_MM = 0.1
_FALLBACK_COLORS = ["#1a1a1a", "#c81e1e", "#1e5fc8", "#1e8c3a", "#c8a01e", "#7a1ec8"]


@dataclass(frozen=True)
class RenderOptions:
    """How the picture is drawn, not what it contains."""

    scale: float = 4.0
    """Pixels per millimetre."""
    margin_mm: float = 4.0
    stitch_width_mm: float = 0.35
    """Roughly the width 40 wt thread covers. Makes density legible at a glance."""
    show_travel: bool = True
    background: str = "#f4f1ea"


def _fmt(value: float) -> str:
    """Fixed-precision formatting, so the same file always renders byte-identically."""
    return f"{value:.3f}".rstrip("0").rstrip(".") or "0"


def _thread_colors(pattern: pyembroidery.EmbPattern, needed: int) -> list[str]:
    """Colour per block, falling back where the format carries no threads (DST)."""
    colors: list[str] = []
    for index in range(needed):
        thread = pattern.get_thread_or_filler(index) if pattern.threadlist else None
        if thread is not None and getattr(thread, "color", None) is not None:
            colors.append(f"#{thread.color & 0xFFFFFF:06x}")
        else:
            colors.append(_FALLBACK_COLORS[index % len(_FALLBACK_COLORS)])
    return colors


def render_file(
    path: str | Path,
    out_path: str | Path,
    options: RenderOptions | None = None,
) -> Path:
    """Render a written machine file to SVG."""
    options = options or RenderOptions()
    path, out_path = Path(path), Path(out_path)

    pattern = pyembroidery.read(str(path))
    if pattern is None:
        raise ValueError(f"{path.name} could not be read for rendering")

    stitches = [(x, y, command & pyembroidery.COMMAND_MASK) for x, y, command in pattern.stitches]
    points = [(x, y) for x, y, cmd in stitches if cmd in (_STITCH, _JUMP)]
    if not points:
        raise ValueError(f"{path.name} contains no stitches to render")

    min_x = min(p[0] for p in points)
    max_x = max(p[0] for p in points)
    min_y = min(p[1] for p in points)
    max_y = max(p[1] for p in points)

    margin = options.margin_mm
    width_mm = units_to_mm(max_x - min_x, _UNIT_MM) + 2 * margin
    height_mm = units_to_mm(max_y - min_y, _UNIT_MM) + 2 * margin

    def project(x: int, y: int) -> tuple[float, float]:
        return (
            units_to_mm(x - min_x, _UNIT_MM) + margin,
            units_to_mm(y - min_y, _UNIT_MM) + margin,
        )

    blocks = sum(1 for _, _, cmd in stitches if cmd == _COLOR_CHANGE) + 1
    colors = _thread_colors(pattern, blocks)

    sewn: dict[int, list[str]] = {index: [] for index in range(blocks)}
    travel: list[str] = []
    block = 0
    previous: tuple[int, int] | None = None
    for x, y, cmd in stitches:
        if cmd == _COLOR_CHANGE:
            block += 1
            previous = None
            continue
        if cmd == _TRIM:
            previous = None
            continue
        if cmd not in (_STITCH, _JUMP):
            continue
        if previous is not None:
            x1, y1 = project(*previous)
            x2, y2 = project(x, y)
            line = f'<line x1="{_fmt(x1)}" y1="{_fmt(y1)}" x2="{_fmt(x2)}" y2="{_fmt(y2)}"/>'
            if cmd == _JUMP:
                travel.append(line)
            else:
                sewn[min(block, blocks - 1)].append(line)
        # A jump lays no thread, but it does move the needle, so it anchors the
        # stitch that follows.
        previous = (x, y)

    scale = options.scale
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{_fmt(width_mm * scale)}" '
        f'height="{_fmt(height_mm * scale)}" viewBox="0 0 {_fmt(width_mm)} {_fmt(height_mm)}">',
        f'<rect width="100%" height="100%" fill="{options.background}"/>',
    ]
    for index in range(blocks):
        if not sewn[index]:
            continue
        parts.append(
            f'<g stroke="{colors[index]}" stroke-width="{_fmt(options.stitch_width_mm)}" '
            'stroke-linecap="round" fill="none">'
        )
        parts.extend(sewn[index])
        parts.append("</g>")
    if options.show_travel and travel:
        parts += [
            '<g stroke="#d02b2b" stroke-width="0.08" stroke-dasharray="0.6 0.6" '
            'fill="none" opacity="0.8">',
            *travel,
            "</g>",
        ]
    parts.append("</svg>")

    out_path.write_text("\n".join(parts) + "\n", encoding="utf-8")
    return out_path
