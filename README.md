# Vector2stitch

Auto-digitizing engine and service: artwork (vector, later raster) → parametric
embroidery objects → machine files (DST, PES, JEF, EXP) for commercial decorators.

## Documents

| Doc | What it covers |
|---|---|
| [`docs/embroidery-digitizing-quality.md`](docs/embroidery-digitizing-quality.md) | What "good" means: defect taxonomy, per-layer quality rules, fabric profiles, verification, metrics, and the commercial/operational choices that protect them |
| [`docs/embroidery-digitizing-build-plan.md`](docs/embroidery-digitizing-build-plan.md) | What to build, in what order, and the acceptance criteria for each milestone |
| [`docs/machine-standards.md`](docs/machine-standards.md) | Commercial machine-side standards, and where the engine's values agree, differ, or are still guesses |
| [`docs/calibration.md`](docs/calibration.md) | The loop that turns inherited defaults into measured ones: generate, sew, measure, record, read, change |
| [`docs/machines.md`](docs/machines.md) | Describing your own machines, so speed, tension and sew field match the hardware in your room |
| [`docs/overrides.md`](docs/overrides.md) | Overriding our fabric defaults with your own floor's numbers, and why the reason matters as much as the value |
| [`docs/m0-status.md`](docs/m0-status.md) | Where the code is against those criteria right now |

Read the quality doc first; the build plan is its companion and defers all
numeric defaults to it and to the fabric profile files.

## Running the engine

```sh
pip install -e ".[dev]"
v2s profiles                                              # what fabrics are supported
v2s machines                                              # machine profiles on the search path
v2s digitize examples/m0_single_run.ir.json --out out     # IR -> DST, PES, worksheet
v2s digitize logo.ir.json --out out --machine your_machine   # against your own hardware
v2s render out/m0_single_run.dst                          # SVG of the written file
v2s calibrate --profile twill@1 --out out/calibration     # patterns to sew + sheets to measure
v2s-lab record <targets.json> --measure square_01_x=19.8 ...   # record what came off the machine
v2s override init pique@1 --shop "Your Shop"              # adjust our defaults to your floor
```

Today the engine generates run objects from hand-authored IR. Satin and fill
arrive in M1, artwork ingest in M3. Nothing has been sewn yet and no fabric
profile is calibrated -- see [`docs/m0-status.md`](docs/m0-status.md).

## Working rules

The short version (full list in the build plan, §12):

1. The engine is a pure library — it never imports from `/service`, `/web`, or `/editor`.
2. No magic numbers in engine logic; values come from fabric profiles or the IR.
3. Millimetres everywhere until `/export`.
4. Stitches are regenerated from objects, never edited directly.
5. Every delivered file records engine, profile, and schema version.
6. The sew-out is ground truth. A render that disagrees with thread on fabric is a simulator bug.
