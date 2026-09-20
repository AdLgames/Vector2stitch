# Calibration: turning inherited defaults into measured ones

Every number in every fabric profile is currently an industry-typical
starting default. `calibrated: false` says so, the worksheet prints it, and a
test asserts it. This document is how that flag becomes true.

The loop is:

```
generate  ->  sew  ->  measure  ->  record  ->  read  ->  change  ->  re-sew
```

Nothing in it is optional, and the only step that produces knowledge is the
one with a machine in it.

## 1. Generate

```sh
v2s calibrate --profile twill@1 --machine your_machine --out out/calibration
```

For each pattern you get five files:

| File | What it is |
|---|---|
| `.ir.json` | The design, in the same IR a customer job uses |
| `.dst`, `.pes` | Machine files, each round-trip verified before it is written |
| `.worksheet.txt` | Thread, needle, speed, tension, stabilizer -- the setup |
| `.measure.txt` | The sheet you write measurements on at the machine |
| `.targets.json` | The same targets, machine-readable, for recording results |

`v2s calibrate --list` shows the set:

```
dimension_grid         ready        Pull and push compensation, from squares and circles
registration_target    ready        Colour-to-colour registration offset
stitch_length_ladder   ready        Where a run stops reading as a line on this fabric
travel_and_trim        ready        Where an untrimmed travel becomes visible
corner_set             ready        Corner cutting at angles from 15 to 120 degrees
column_ladder          ready        Satin column widths: split point, edge quality, underlay
density_wedge          ready        Tatami fill at rising densities
text_ladder            needs M6     Lettering from 3 to 10 mm
```

One of the eight is not built. They are declared rather than omitted,
because what is missing is exactly what the lab exists to close. The text
ladder waits on licensed embroidery fonts, which is a purchasing decision more
than an engineering one.

Everything else can be measured now: dimensional accuracy, registration, run
length, trim threshold, corner behaviour, satin column width and where a
column has to start splitting, the underlay bands, and fill density.

The density wedge is where a fabric's limit actually shows up. Draw-in is the
number to measure: a denser panel pulls the fabric in harder, so the sewn
square comes out smaller, and where that stops being recoverable by
compensation is where the density limit sits. Puckering and thread breaks show
up on the same panels, and neither is visible on screen.

The column ladder is the most informative sheet for satin, because column
width decides four things at once: whether pull compensation is right, whether
the underlay recipe switches at the right widths, where splitting has to
start, and whether the edges are clean enough to sell. Its widest column is
past the profile maximum on purpose -- it is there to show what a split looks
like, not to pass.

Cap profiles get a shorter pattern set automatically -- a cap front is about
70 mm tall, and a pattern that cannot be hooped measures nothing.

## 2. Sew

Before anything is sewn, the machine has to be in calibration itself: hook
timing, needle bar height, belt tension, and a gauged bobbin. **A sew-out on
an out-of-calibration machine is not data.** It will move a parameter, and it
will move it for the wrong reason.

Hold the consumables constant across the whole run and write them on the
sheet: one thread brand and weight, one needle size, one stabilizer, one
speed. An unrecorded variable makes the measurement worse than useless.

Photograph every sew-out under the same lighting before it leaves the machine.

## 3. Measure

Calipers on every target on the sheet. Not a sample of them: an unmeasured
target fails rather than passing by omission, because a calibration run that
skipped half the measurements is not a pass.

## 4. Record

```sh
v2s-lab record out/calibration/twill_at_1/dimension_grid.targets.json \
  --operator kim --profile twill@1 --engine-version "$(git rev-parse --short HEAD)" \
  --machine your_machine \
  --thread "Madeira Polyneon 40" --needle 75/11 --stabilizer "cutaway 2.0 oz" --speed 850 \
  --measure square_01_x=19.8 --measure square_01_y=19.9 \
  --measure square_02_x=39.5 --measure square_02_y=39.7 \
  --defect gapping
```

```
target                  designed  measured    error
square_01_x                20.00     19.80    -0.20
square_02_x                40.00     39.50    -0.50  <-- out of tolerance
mean error: -0.34 mm
defects:
  gapping: usually pull comp too low; bad sequencing; weak underlay
FAIL
```

Exit 2 means out of tolerance. That is a result, not a tool failure -- it is
the one that means a parameter has to move. The record is appended either way:
a failing sew-out is data.

Defects come from a closed vocabulary (the quality doc's taxonomy), so a score
maps to something in the code instead of to an adjective.

## 5. Read

```sh
v2s-lab report --log lab/sewouts.jsonl --targets .../dimension_grid.targets.json
```

```
twill@1  dimension_grid: 1 sew-out(s)
  mean dimensional error -0.34 mm over 10 measurements
  features come out small: the profile is under-compensating for pull
```

Consistently negative means features sew smaller than designed: pull
compensation is too low. Consistently positive means it is too high. X and Y
moving differently is the signature of compensation being wrong on one axis --
which is why squares are measured on both, and why circles are in the set at
all: a circle that sews as an oval says the same thing unambiguously.

This is also what settles the open question in `docs/machine-standards.md`:
whether our per-side pull compensation convention matches the figures
commercial practice quotes. Measurement decides it; reading cannot.

## 6. Change, then re-sew

Editing a profile is a release, not an edit:

1. Copy `engine/profiles/data/twill@1.yaml` to `twill@2.yaml`, bump `version`.
2. Change the parameter the measurements point at -- one at a time.
3. Re-run from step 1 against `twill@2`.
4. When the calibration set passes on a profile, set `calibrated: true`, and
   change the test in `tests/test_profiles.py` that asserts it is false. That
   test exists so the flag can only be flipped by someone who did the work.

The old version stays on disk and stays loadable: a design delivered against
`twill@1` has to keep reproducing after `twill@2` ships.

## What "calibrated" will mean

A profile is calibrated when its calibration set has been sewn on the machines
that will run it, measured, recorded, and passes within tolerance -- dimensional
error under 0.3 mm on the shapes, registration inside 0.3 mm, no defects from
the taxonomy at the recorded settings. Not before, and not because the render
looked right.
