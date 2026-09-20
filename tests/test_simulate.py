"""The simulator draws the file, not the plan."""

from __future__ import annotations

import pytest

from engine.export import write
from engine.simulate import RenderOptions, render_file
from engine.stitchgen import generate


def test_render_produces_an_svg(tmp_path, two_color_design):
    plan = generate(two_color_design)
    path = write(plan, tmp_path / "design.dst")
    svg = render_file(path, tmp_path / "design.svg").read_text()
    assert svg.startswith("<svg")
    assert svg.rstrip().endswith("</svg>")


def test_render_draws_every_stitch_in_the_file(tmp_path, single_run_design):
    plan = generate(single_run_design)
    path = write(plan, tmp_path / "design.dst")
    svg = render_file(path, tmp_path / "design.svg").read_text()
    # One line per move between consecutive points; travel lines are drawn too.
    assert svg.count("<line") >= plan.stitch_count() - 1


def test_each_colour_block_is_drawn_in_its_own_colour(tmp_path, two_color_design):
    plan = generate(two_color_design)
    path = write(plan, tmp_path / "design.pes")
    svg = render_file(path, tmp_path / "design.svg").read_text()
    assert svg.count("<g stroke=") >= 2


def test_travel_can_be_hidden(tmp_path, two_color_design):
    plan = generate(two_color_design)
    path = write(plan, tmp_path / "design.dst")
    with_travel = render_file(path, tmp_path / "a.svg").read_text()
    without = render_file(
        path, tmp_path / "b.svg", RenderOptions(show_travel=False)
    ).read_text()
    assert with_travel.count("<line") > without.count("<line")


def test_render_is_byte_stable(tmp_path, single_run_design):
    plan = generate(single_run_design)
    path = write(plan, tmp_path / "design.dst")
    first = render_file(path, tmp_path / "a.svg").read_bytes()
    second = render_file(path, tmp_path / "b.svg").read_bytes()
    assert first == second


def test_rendering_a_file_with_no_stitches_is_refused(tmp_path):
    empty = tmp_path / "empty.dst"
    empty.write_bytes(b"")
    with pytest.raises(ValueError):
        render_file(empty, tmp_path / "empty.svg")
