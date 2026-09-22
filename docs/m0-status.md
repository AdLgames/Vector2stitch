# Milestone status: M0 done in software, M1 started

**Build plan reference:** milestone M0 -- IR schema v1, profile loader, CLI
skeleton, pyembroidery wrapper with round-trip tests, basic simulator.

**Acceptance criterion:** *a hand-written IR with one run object exports to DST
and PES, loads on the lab machines, and sews.*

**Status: software complete, acceptance NOT met.** The export half is done and
tested; the hardware half cannot be claimed from this repo. Nothing here has
been sewn. Until a file off this engine runs on the lab machines, M0 is open.

---

## What is built

| Piece | Where | State |
|---|---|---|
| IR schema v1 (Pydantic, versioned, deterministic JSON) | `engine/ir/` | Done |
| Schema migration chain | `engine/ir/migrate.py` | Done (empty at 1.0, by design) |
| Fabric profiles: twill, pique, cap | `engine/profiles/` | Loadable, versioned on disk; **none calibrated** |
| Machine setup per fabric profile (thread, needle, speed, tension) | `engine/profiles/data/` | Done |
| Machine profiles: the shop's own hardware, designer-edited | `engine/machines/` | Done; templates only, none calibrated |
| Shop overrides on fabric profiles, with reasons recorded | `engine/profiles/overrides.py` | Done |
| Parameter resolution with provenance | `engine/stitchgen/params.py` | Done |
| Run stitch generation, ties, short-stitch filter, bean | `engine/stitchgen/run.py` | Done |
| Satin: zigzag, pull comp, short stitches, auto-split (M1) | `engine/stitchgen/satin.py` | Done |
| Tatami fill: scanlines, holes, sections, stagger, compensation (M1) | `engine/stitchgen/fill.py` | Done |
| Underlay: center run, edge run, zigzag, fill edge run, low tatami (M1) | `engine/stitchgen/underlay.py` | Done |
| Polygon offsetting (Clipper) | `engine/stitchgen/offset.py` | Done |
| Plan assembly: travel, trims, colour changes | `engine/stitchgen/__init__.py` | Done |
| Machine file writers: DST, PES, JEF, EXP | `engine/export/` | Done |
| Round-trip verification on every file | `engine/export/roundtrip.py` | Done |
| Format limits and long-move splitting | `engine/export/limits.py`, `writer.py` | Done |
| Basic simulator (SVG from the machine file) | `engine/simulate/` | Done |
| Production worksheet | `engine/cli/worksheet.py` | Done (text; PDF/HTML at M7) |
| CLI: `digitize`, `render`, `profiles` | `engine/cli/main.py` | Done |
| Checks: blocking validators + structured report (M2) | `engine/checks/` | Done |
| Golden suite: 23 designs, metric comparison, CI job (M2) | `lab/golden.py`, `golden/` | Done |
| Calibration patterns + measurement sheets | `engine/lab/` | 7 of 8 build; only text pending |
| Sew-out log, defect taxonomy, `v2s-lab` | `lab/` | Done |
| Determinism tests + committed fingerprints | `tests/test_determinism.py` | Done |
| CI: lint, tests on 3.11/3.12, determinism on two OS images | `.github/workflows/ci.yml` | Done |

410 tests pass; `ruff check` is clean.

## Try it

```sh
pip install -e ".[dev]"
v2s profiles
v2s digitize examples/m0_single_run.ir.json --out out --formats dst,pes
v2s render out/m0_single_run.dst
```

`digitize` writes the machine files, verifies each one by reading it back, and
writes the operator worksheet beside them.

## What M0 does not do

- **No text.** Text objects raise `UnsupportedObject` naming M6: they need
  licensed embroidery fonts, not a generator. This is the refusal rule, not an
  oversight.
- **Satin takes rails, not outlines.** The IR holds rail pairs and the
  generator uses them. Deriving rails from an outline is the medial-axis work
  in M3, so today a satin object has to be authored with its rails.
- **No ingest.** The IR is hand-authored. SVG/PDF in is M3.
- **No text calibration.** The text ladder is the one pattern still waiting,
  on fonts. Everything else in the set builds, so density, column width, pull
  compensation, registration, trim threshold and corner behaviour can all be
  measured now.
- **No sequencing.** Objects sew in `sequence`, or by z-order then id. Travel
  is an honest jump or trim; hiding travel under later objects is M4.
- **Compensation now bites.** Every satin column is stitched wider than
  drawn by the profile's per-side value -- measured at exactly +0.35 mm on
  twill across the whole column ladder. Whether that is the *right* value is
  what the sew-out decides.
- **No curve shortening.** A run through a tight corner keeps its target
  length and will visibly cut the corner. M1.

## Machine profiles

The generic values above are a starting point; the hardware in a given room is
not generic. `engine/machines/` holds designer-owned machine profiles -- speed
the machine actually holds, sew field, cap driver, auto trimmer, readable
formats, and locally gauged tension -- resolved against the fabric profile to
produce the setup on the worksheet. Two templates ship, both uncalibrated;
`docs/machines.md` covers describing your own.

A machine profile can refuse a file (cap placement with no cap driver, design
larger than the field) and can change the speed and tension on the sheet. It
can never change a stitch coordinate: the same design on two machines has to
stay the same design.

## Reconciled against commercial machine standards

`docs/machine-standards.md` compares every shipped value against commercial
practice. Three things changed as a result: pique fill spacing moved from
0.42 mm to 0.45 mm (it was below the commercial range), pique gained a
water-soluble topping, and every profile now carries the machine setup --
thread weight and type, needle, speed ceiling, gauge-measured bobbin tension
and the top-to-bobbin ratio -- which the worksheet prints.

The engine now also refuses a profile on any thread weight but 40 wt, because
density, underlay and compensation are all sized to what 40 wt covers.

One conflict is unresolved and cannot be settled by reading: whether our pull
compensation convention (per side) matches the figures the standard quotes.
Calipers on the calibration shapes settle it. See §4 of that doc.

## What M1 has added so far

Satin columns generate: an arc-length-paired zigzag with pull compensation
applied per side along the stitch, short stitches that relieve a crowded inner
rail on curves, automatic splitting into lanes past the profile's width limit,
and the three satin underlay recipes the profiles already named.

Tatami fill generates: scanlines at the profile's angle, holes excluded by
even-odd pairing, rows grouped into sections that sew continuously, stagger so
penetrations do not line up, pull compensation along the rows and push
compensation across them, plus the fill underlay recipes. Polygon offsetting
is done with Clipper rather than by hand.

Building both turned up bugs that a render would not have shown:

1. **A stitch running along a rail instead of across the column.** The lane
   emission order was wrong; it would have sewn as a visible line down the
   edge. The short-stitch filter was quietly dropping the evidence.
2. **Underlay runs at the fill stitch length.** A satin's `stitch_length_mm`
   defaults to the fill length, so underlay under a 2 mm column was stepping
   3.5 mm. Underlay runs are runs, whatever is on top of them.
3. **Floating stitches that the width limit was supposed to prevent.** The top
   layer split correctly past 7 mm, but the underlay zigzag spanned the full
   width, and the edge run crossed the whole column at its turn. Being
   underneath does not hold a stitch down. Both are now split or separated,
   and an invariant test covers every satin object on every profile.
4. **An underlay run that stitched across a hole.** Resampling a ring purely
   by arc length drops its corners, and the chord across a hole's corner goes
   straight through the window. Ring resampling now keeps corners.
5. **A duplicate penetration at every object start.** The tie-in ends on the
   anchor, and the path began on the same point -- two stitches in one hole,
   on every object ever generated. This is what moved the fingerprints.
6. **A 35 mm stitch inside a fill.** Where two rows overlap only slightly the
   turn travels most of a row's width; left as one stitch, the writer split it
   into penetrations we never planned, which the round-trip check caught as a
   changed penetration count. Turns are now subdivided at the stitch length.
7. **Our own idea of the format limit was wrong.** We treated the 12.1 mm DST
   limit as a Euclidean distance. It is per axis: these formats encode a move
   as one delta per axis, each with its own field, so a diagonal move of
   12.1 mm in x and 12.1 mm in y is 17.1 mm long and perfectly legal. Both the
   splitting and the round-trip check now work per axis, which is what the
   writer library was doing all along.

## Decisions taken here, worth knowing about

**Engine y is up; pyembroidery's is down.** The negation happens once, in
`engine/export/writer.py`, and nowhere else. A round-trip test cannot prove
the design lands right way up on a real hoop -- the acceptance sew-out can.
Check it first when the lab file goes on a machine.

**JEF embeds a creation timestamp**, so written files differed on every write.
Output is now stamped with a fixed timestamp (`FIXED_FILE_TIMESTAMP`),
overridable per call. Reproducibility beats a header field no operator reads;
real provenance lives in the worksheet and the delivery record.

**PES rewrites thread colours.** It stores the nearest Brother palette entry,
not our RGB: `#1a1a1a` comes back as `#132b1a`. The simulator shows the file's
colours, so PES previews are slightly off from the thread chart. Expected, not
a bug -- but the customer-facing render (M7) should come from DST or from the
IR's thread codes, not from a PES read-back.

**Round-trip asserts penetrations and colour changes, reports trims.** Formats
legitimately differ on trims: DST encodes one as a jump sequence, PES inserts
implicit ones. Asserting equality there would fail on correct files.

**Our format limits are our own table**, not read from the writer library, with
a test that they stay inside what the library will emit. A dependency upgrade
that widened a limit should fail a test rather than quietly change output.

## To close M0

1. Write `examples/m0_single_run.ir.json` to DST and PES.
2. Load both on the commercial multi-needle and the single-head machine.
3. Sew on twill, with the worksheet's stabilizer.
4. Confirm orientation, that the ties hold, and that the design measures what
   it declares.
5. Record the sew-out. Then M0 closes and M1 starts -- and M1 is the milestone
   the product actually lives or dies on.

## One deviation from the build plan, flagged

The build plan puts the calibration pattern generator and the sew-out log app
inside M1, alongside the stitch primitives they are meant to measure. They are
the measuring instrument: building them first makes M1 a measurable loop
instead of build-and-hope, and they do not depend on satin or fill existing.
Recommend pulling both forward -- they are small, and `v2s calibrate` is
already stubbed for exactly this.
