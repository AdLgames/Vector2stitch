# Machine-side standards, and how the engine conforms

**Source:** the commercial production standards write-up covering digitizing
exports, machine load (OEE), stitch mechanics, calibration and QC. This file
keeps the parts that bind engine behaviour, records where our values agree or
disagree, and lists what is still an open question for the lab.

It is a reference, not a second source of truth: every number the engine uses
lives in a fabric profile (`engine/profiles/data/`). This file explains *why*
those numbers are what they are.

---

## 1. Density by substrate

Commercial practice, against what the engine ships:

| Substrate | Standard spacing | Engine profile | Conforms |
|---|---|---|---|
| Woven twill / canvas | 0.35 – 0.45 mm | `twill@1` fill 0.40 mm | Yes |
| Pique knit | 0.45 – 0.50 mm | `pique@1` fill 0.45 mm | Yes, **corrected** |
| Performance stretch | 0.50 – 0.60 mm | not shipped | v1 scope |
| Fleece / outerwear | ≤ 0.50 mm | not shipped | v1 scope |
| Terry | 0.55 – 0.70 mm | not shipped | v1 scope |
| Structured cap | not in the standard | `cap@1` fill 0.40, satin 0.38 mm | **Inferred** |

**Corrected:** pique shipped at 0.42 mm fill spacing, below the commercial
range. It is now 0.45 mm. Satin spacing stays at 0.40 mm: the ranges above
govern fill coverage, and a satin column is conventionally held denser than
the fill beside it.

**Inferred:** the cap profile has no counterpart in the standard. Its numbers
are reasoned from flat goods plus the constraints of a structured front, and
are the least trustworthy values we ship. The cap calibration sew-out matters
more than the others.

**Also corrected:** pique now specifies a water-soluble topping. The standard
is explicit that textured weaves swallow stitch edges without one, and the
profile said `topping: false`.

## 2. Underlay

The standard's point that underlay lets you *reduce* top density -- lower
stitch count, softer hand, same opacity -- is the reason `engine/profiles`
treats underlay as a per-width recipe rather than a flag. Recipes ship as
`center_run` / `edge_run` / `zigzag` / `tatami_low` by object kind and column
width; the generators for them land in M1.

## 3. Thread weight

40 wt is the benchmark the industry's digitizing defaults are built around,
and ours are too: density, underlay and compensation are all sized to what
40 wt covers. Running a 40 wt file on 60 wt leaves gaps; the reverse
over-stitches, stiffens the garment and snaps thread.

The engine refuses rather than pretends: a profile specifying any other weight
raises `UnsupportedProfile` naming what would have to be re-derived. Fine
lettering on 60 wt is M6, and it is a recalibration, not a setting.

Minimum text height in the profiles (4.5 mm twill, 5.0 mm pique and cap) sits
inside the standard's 4 – 5 mm floor for 40 wt.

## 4. Pull compensation -- **open question**

The standard quotes 0.35 mm for a cotton tee and 0.20 mm for rigid drill. Our
profiles hold 0.175 mm for twill and 0.35 mm for pique, **per side**.

Read as a total added width, our twill value matches the standard's rigid
figure almost exactly (0.175 × 2 = 0.35) -- but read as per-side, we are
compensating twill at the level the standard reserves for a knit. The source
does not say which convention it uses, and vendors differ; the IR documents
ours as per side.

This cannot be settled by reading. It is settled with calipers: sew the
calibration circles and squares, measure sewn against designed, and let the
< 0.3 mm dimensional error target pick the number. Until then the values
stand and are flagged uncalibrated.

## 5. Machine setup carried on the worksheet

The standard's point that tension set by feel is tension that drifts is now
reflected in the profiles: each carries thread weight and type, needle size, a
recommended speed ceiling, a gauge-measured bobbin tension range, and the
top-to-bobbin ratio. The worksheet prints all of it, and derives the top
tension target from the bobbin baseline rather than leaving it to the operator.

| Profile | Needle | Max speed | Bobbin | Top (derived) |
|---|---|---|---|---|
| `twill@1` | 75/11 | 1000 spm | 18 – 22 gf | ~38 gf |
| `pique@1` | 75/11 | 1000 spm | 18 – 22 gf | ~38 gf |
| `cap@1` | 75/11 | 600 spm | 25 – 30 gf | ~52 gf |

Cap runs slower and tighter: a structured front on a driver, with dense seams
that loop at flat-goods bobbin tension.

The run-time estimate on the worksheet now uses the profile's speed and says
"needle time only" -- trims, colour changes and hooping are what separate it
from a shop's real throughput.

## 6. Where the standard describes the machine, not the file

Rotary hook timing (195 – 200°, 0.1 – 0.3 mm hook-to-scarf clearance), needle
bar height, pantograph belt frequency, needle coatings and thread lubrication
are maintenance procedures, not engine inputs. They matter to us in one
direction: **a sew-out on an out-of-calibration machine is not data.** Before
any calibration sew-out is recorded, the machine's timing, tension and belt
tension have to be verified, and the consumables logged. An uncontrolled
variable makes the sew-out worse than useless, because it will move a
parameter for the wrong reason.

## 7. Resizing

The standard's warning -- that resizing an expanded DST past a few percent
pulls stitches apart or crushes them -- is a constraint the engine sidesteps
structurally rather than by policy. Stitches are never edited or scaled;
they are regenerated from objects at the new size, with feature-size checks
re-run at final physical dimensions. A resize is a re-digitize.

This is worth stating to customers: a resize request is not a file edit, and
it is why the commercial terms price resizes beyond ±10-15% as a new job.

## 8. Quality validation

Two standards bear on how we measure ourselves, neither yet implemented:

- **AQL 2.5** for major defects, sampled per ANSI/ASQ Z1.4. Our field
  first-sew metric is a customer-reported cousin of this. The lab's sampling
  (quality doc §16) should adopt the same framing rather than invent one.
- **AATCC TM61** for colourfastness. Thread selection, not engine output --
  but if we ever recommend a thread brand, this is the test that backs the
  recommendation.

## 9. Open questions for the lab

1. Is our pull compensation per side, or total, once measured? (§4)
2. Are the cap numbers defensible, or invented? (§1)
3. Does 0.40 mm satin spacing hold on pique at 0.45 mm fill spacing, or does
   the satin need to open up with the fill?
4. What speed do our machines actually hold on each profile without thread
   breaks? The profile ceilings are inherited, not measured.
