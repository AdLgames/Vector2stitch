# Shop overrides: your floor against our defaults

Our fabric profiles hold industry-derived starting values. They are the same
for everyone, and **none of them has been calibrated** — `calibrated: false`
says so in every file.

A decorator who has run pique on their own stabiliser for ten years knows
something we do not. This is how they say so, without forking the profile and
without losing whatever we fix upstream.

```sh
v2s override init pique@1 --shop "Acme Decorators" --out ~/shop/overrides
$EDITOR ~/shop/overrides/pique@1.override.yaml
export V2S_PROFILE_DIR=~/shop/overrides
v2s override show
v2s digitize logo.ir.json --out out          # overrides apply automatically
```

## What an override looks like

```yaml
profile: pique@1
shop: "Acme Decorators"
recorded_on: 2026-09-18
note: "Our pique is a heavier 220gsm than most; we run it open."

overrides:
  density.fill_row_spacing_mm:
    value: 0.48
    reason: "0.45 puckers on our 220gsm pique with cutaway"
    evidence: "12 polo fronts, Jan-Mar 2026"
```

`reason` is required and the engine will not load a file without one. That is
not bureaucracy. An override with no reason cannot be reviewed, cannot be
aggregated, and cannot be told apart from a typo a year later — including by
the person who made it.

`evidence` is optional, and its absence is printed rather than hidden:
"experience, not measurement" is useful information about a number, not a
failing.

The profile reference is pinned to a version, because a shop's reasons were
formed against a specific set of our numbers. When we ship `pique@2` their
override does not silently carry over to values it was never about.

## What the engine does with it

- **Applies it**, to every file that shop generates.
- **Validates it** through the same model a shipped profile goes through, so
  an override cannot produce a profile that could not have shipped. A negative
  density is refused here exactly as it would be on disk.
- **Records it.** Every plan carries the list of overridden fields, and the
  worksheet prints each change with its reason. `pique@1` is not reproducible
  if the shop quietly runs a different pull compensation, so the file says
  which fields were not ours.
- **Flags a suspicious one.** Moving pull compensation from 0.175 to 0.22 is
  experience; moving it to 1.75 is a misplaced decimal point. A change of more
  than 2x is called out — and still applied. Their floor, their call.
- **Refuses a broken one.** A field that does not exist stops the job rather
  than being ignored, because an override silently doing nothing is worse than
  one that fails loudly.

## What it is not

**It is not a way to avoid measuring.** The numbers a shop can usefully
override are the ones they have evidence about. An override is one shop's
experience, recorded as exactly that.

**It is not a substitute for the defaults being right.** The product promise
is a file that sews clean the first time, not one the customer tunes. A
decorator buys a file because they do not want to digitize; "sews clean after
you adjust the density curve" is a different and much weaker product. If most
shops override the same field in the same direction, our default is wrong and
the fix belongs upstream in a new profile version.

**It does not make the profile calibrated.** `calibrated` stays ours: it is a
claim about our own testing, and the override template deliberately does not
offer it as an adjustable field.

## Why this matters more than it looks

Overrides are how the profiles get calibrated when there is no lab.

Every override is a measurement someone else already paid for. Forty shops
moving pique's fill spacing the same direction is calibration data, bought
with other people's machines and other people's stabiliser — which is why the
reason and the evidence are part of the file format rather than a comment.

It is slower than a lab and enormously cheaper. It still wants one anchored
sew-out somewhere to tell whether a shop's adjustment means our default is
wrong or their machine is out of timing: without a reference, a pile of
adjustments is a pile of disagreements. But **one** reference measurement is a
very different problem from a standing lab, and it can be bought from any
decorator with calipers.

## Relationship to machine profiles

Two layers, two owners, two different kinds of fact:

| | Machine profile | Shop override |
|---|---|---|
| Describes | This machine: speed it holds, field, tension, trimmer | This shop's fabric numbers: density, compensation, underlay |
| Varies by | Hardware, even between two of the same model | Fabric, thread, stabiliser, and the shop's experience |
| Can change stitches | No — it may refuse a file or set the worksheet | Yes, that is the point |
| Lives in | `$V2S_MACHINE_DIR` | `$V2S_PROFILE_DIR` |

A machine profile never changes a stitch coordinate; an override always can.
That is the line between "this hardware cannot do that" and "your defaults are
wrong for my fabric", and keeping the two apart is what makes either one
readable later.
