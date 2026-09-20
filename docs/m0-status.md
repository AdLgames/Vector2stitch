# M0 status: Foundations

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
| Parameter resolution with provenance | `engine/stitchgen/params.py` | Done |
| Run stitch generation, ties, short-stitch filter, bean | `engine/stitchgen/run.py` | Done |
| Plan assembly: travel, trims, colour changes | `engine/stitchgen/__init__.py` | Done |
| Machine file writers: DST, PES, JEF, EXP | `engine/export/` | Done |
| Round-trip verification on every file | `engine/export/roundtrip.py` | Done |
| Format limits and long-move splitting | `engine/export/limits.py`, `writer.py` | Done |
| Basic simulator (SVG from the machine file) | `engine/simulate/` | Done |
| Production worksheet | `engine/cli/worksheet.py` | Done (text; PDF/HTML at M7) |
| CLI: `digitize`, `render`, `profiles` | `engine/cli/main.py` | Done |
| CLI: `check`, `calibrate` | `engine/cli/main.py` | Stubs, exit 3 |
| Determinism tests + committed fingerprints | `tests/test_determinism.py` | Done |
| CI: lint, tests on 3.11/3.12, determinism on two OS images | `.github/workflows/ci.yml` | Done |

171 tests pass; `ruff check` is clean.

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

- **Only run objects.** Satin and fill raise `UnsupportedObject` naming M1;
  text names M6. This is the refusal rule, not an oversight.
- **No ingest.** The IR is hand-authored. SVG/PDF in is M3.
- **No checks.** `v2s check` exits 3. Every file goes through human review
  until M2, without exception.
- **No sequencing.** Objects sew in `sequence`, or by z-order then id. Travel
  is an honest jump or trim; hiding travel under later objects is M4.
- **No compensation applied.** Pull comp is resolved and carried on the plan,
  but a run stitch has no width to compensate. It first bites at M1, on satin.
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
