# Machine profiles: describing your own hardware

A fabric profile says how to sew a material. A **machine profile** says what
the hardware in your room actually does. Both feed the worksheet, and together
they decide whether the engine agrees to produce a file at all.

The two are split because they have different owners. Fabric profiles are
ours -- versioned with the engine, changed by release, backed by calibration
sew-outs. Machine profiles are **yours**: measured on your floor, different
between two machines of the same model, and meant to be edited.

## What ships, and why you should not use it as-is

Two templates ship with the engine:

```sh
v2s machines
```

```
multineedle_6head@1      template / not calibrated  6-head, 15 needles, cap driver
single_head@1            template / not calibrated  1-head, 6 needles, flat only
```

Both say `calibrated: false`, and they mean it. The speeds are what a machine
of that class typically holds, not what yours holds; the tension block is
commented out entirely, because nobody has put a gauge on your bobbin case.

## Describing your machines

```sh
mkdir -p ~/shop/machines
cp "$(python -c 'import engine.machines, pathlib; print(pathlib.Path(engine.machines.__file__).parent / "data")')"/multineedle_6head@1.yaml \
   ~/shop/machines/barudan_left@1.yaml
$EDITOR ~/shop/machines/barudan_left@1.yaml     # set name: barudan_left
export V2S_MACHINE_DIR=~/shop/machines
v2s machines
```

A file of your own **shadows** a shipped one of the same name completely --
it is not merged, so you never end up with half our numbers and half yours.

Then digitize against it:

```sh
v2s digitize logo.ir.json --out out --machine barudan_left
```

Search order, nearest first: `--machine-dir`, then `$V2S_MACHINE_DIR`, then
the shipped templates.

## What is in the file

| Field | What it means | How to get it right |
|---|---|---|
| `calibrated` | Whether these numbers came off this machine | Set `true` only once they did |
| `heads`, `needles_per_head` | Hardware layout | From the machine |
| `speed.max_spm_flat` | The speed it **holds**, not its nameplate | Run a dense design at rising speeds until thread breaks start; back off |
| `speed.max_spm_cap` | Same, on the cap driver | Always lower than flat |
| `fields.*` | Usable sew field in mm -- the machine's reach, not the hoop | From the manual, then verified |
| `capabilities.auto_trim` | Whether it trims for you | `false` means every trim stops the machine |
| `capabilities.cap_driver` | Whether caps are possible at all | A cap placement is refused without it |
| `capabilities.formats` | What the controller reads | From the machine |
| `tension` | Gauge readings from **this** machine | Optional; omit until measured |

Versioning works like fabric profiles: `name@version.yaml`, and older versions
stay loadable. Bump the version when a machine is re-timed or re-gauged, so a
job sewn last month can still be reproduced with the setup it actually had.

## What a machine profile changes -- and what it never changes

It changes:

- **The speed ceiling.** The slower of the fabric's recommendation and the
  machine's is used, and the worksheet says which one won.
- **The tension targets.** A gauged machine's readings replace the fabric
  profile's generic range; until then the sheet says the numbers are generic.
- **Whether a file is produced.** A cap placement on a machine with no cap
  driver, or a design larger than the sew field, is refused outright. Nothing
  is written -- no half-delivery for someone to pick up by mistake.
- **What the operator is warned about.** More colours than needles (a
  rethread mid-run), trims on a machine with no trimmer, a format the
  controller cannot read, an uncalibrated machine.

It never changes **a single stitch coordinate**. Hardware differences are
handled by refusing or warning, never by quietly generating the design
differently -- otherwise the same design on two machines stops being the same
design, and the golden suite, the fingerprints and every reproducibility claim
in this repo become false. A design that does not fit the field is refused,
not shrunk; resizing is a re-digitize, at the new size, with the feature-size
checks re-run.

## Without a machine profile

Everything still works. The worksheet prints the fabric profile's generic
numbers and says plainly that no machine was specified and nothing was checked
against a real sew field. A shop that has not described its hardware yet is
not blocked -- it is just told what it is not getting.
