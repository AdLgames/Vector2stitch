# The checks

Every file the engine produces goes through these, and a blocking finding
means the file is not written. They are the last gate before a machine.

```sh
v2s check logo.ir.json --machine your_machine -v
```

```
PASS  not_empty: 2412 penetrations
PASS  stitch_length: every stitch is within its object's bounds
PASS  density_hotspot: peak 5 penetrations per 1.0 mm square
PASS  satin_width: 6 satin column(s) within bounds
PASS  tie_off_before_trim: every trim, stop and end is tied off
PASS  trim_budget: 10 trims, 4 per 1000 stitches
WARN  profile_calibrated: twill@1 is not calibrated ...
PASS  machine_fit: fits multineedle_6head@1
0 blocking, 1 warning, 8 rules run
```

## What they check, and what each one prevents

| Rule | Severity | The failure it catches |
|---|---|---|
| `not_empty` | block | A file with no stitches |
| `stitch_length_min` | block | Penetrations piling into one hole: thread break, then needle break |
| `stitch_length_max` | block | A stitch longer than the machine will sew |
| `density_hotspot` | block | Perforating the fabric rather than covering it, usually where layers meet |
| `satin_width_max` | block | A column that should have split: nothing holds the stitch's middle down, so it snags and loops |
| `satin_width_min` | warn | A column narrower than a run: it will sew, it just should have been a run |
| `tie_off_before_trim` | block | Thread cut without a tie, which pulls straight back out |
| `machine_fit` | block | A design bigger than the sew field, or a cap with no cap driver |
| `trim_budget`, `jump_budget` | warn | Machine time the customer pays for |
| `color_change_budget` | warn | Each change stops the machine for a rethread |
| `profile_calibrated` | warn | The profile's numbers have not been proven on a machine |

Passes are recorded rather than left as silence, because silence cannot
distinguish "fine" from "never looked".

Findings point at an **object**, not a stitch index. A stitch index is not
something a reviewer can act on; an object is what they edit.

Every rule runs even after one blocks. A report that gave up at the first
problem would send a reviewer round the loop once per defect.

## The exception worth knowing about

A fill turns at the end of every row, and that turn is about one row spacing
long — shorter where the shape's boundary runs diagonally to the rows. Those
turns are below the profile's minimum stitch length and they are **structural**:
filtering them deletes one end of every other row and the fill stops reaching
its own edge.

So the floor is per object kind. Fills are judged against
`fill.min_turn_fraction` of their row spacing; everything else against
`stitch.min_length_mm`. It is the fill's geometry that earns the exception,
not a blanket lowering of the floor — a run with a 0.2 mm stitch is still
blocked.

## What they found on their first run

The checks were written against output the engine was already producing, and
immediately blocked it: **19 untied trims** across two calibration patterns.
Satin and fill objects trim between their underlay layers and the top layer,
and only the object's *last* path was being tied off. Every one of those trims
was thread cut without a tie.

That is the check suite earning its place before a single customer file
existed. The generator now ties off before every trim and ties in again after
one — and does not add a second tie where an object has just ended, because
two ties in one spot is a stiff lump and a density hotspot, not twice the
security.

## The golden suite

Unit tests say a function still does what it did. The golden suite says the
*engine* still does.

```sh
v2s-lab golden                 # compare against approval
v2s-lab golden --approve       # record current output, deliberately
```

23 designs — every calibration pattern on every shipped profile, plus the
hand-authored examples — regenerated end to end and compared on metrics:
stitch count, trims, jumps, colour changes, threads, extents, the stitch
length *distribution*, and which findings the checks produced.

Metrics rather than bytes, on purpose. Byte equality fails on every harmless
refactor and teaches everyone to regenerate without looking, which is how a
regression net becomes a rubber stamp. Metrics fail when the stitches actually
move, and the diff says which way:

```
column_ladder__twill_at_1 (twill@1):
  stitch count 2392 -> 2461 (2.9%)
  stitch length distribution moved: 0.5 mm +48, 3.5 mm -12
```

Tolerances: stitch count within 1%, extents within half a machine unit, and
counts exactly. A tolerance that never fails is not a tolerance.

**Approving a change is deliberate.** `--approve` rewrites the recorded
metrics; the PR has to say what moved and why. Once there is a digitizer to
ask, a metric shift needs their sign-off as well — that is the build plan's
rule, and it is the one that keeps this from becoming a formality.

Real customer artwork joins the suite when ingest lands (M3). Until then it is
our own patterns, which is enough to catch a generator regression and not
enough to catch a classification one.
