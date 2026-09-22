# Working in this repo

Read `docs/embroidery-digitizing-quality.md` (what "good" means) and
`docs/embroidery-digitizing-build-plan.md` (what to build, in what order)
before changing engine behaviour. Current milestone status:
`docs/m0-status.md`.

## Rules that are not negotiable

1. **The engine is a pure library.** `engine/` never imports from a service,
   web app or editor, and never touches a network, database or queue.
2. **No magic numbers in engine logic.** Every density, length, compensation
   and threshold comes from a fabric profile or from the IR. If a generator
   needs a new number, it gets a new profile field.
3. **Millimetres everywhere until `engine/export`.** That module is the only
   place machine units exist, via `engine.units`.
4. **Stitches are regenerated from objects, never edited.** A fix belongs in
   the object parameters or the generator, not in the stitch stream.
5. **Determinism is a test, not an aspiration.** Same input, same settings,
   same bytes -- on any host. No unseeded randomness, no set iteration, no
   wall-clock timestamps in output.
6. **Refuse rather than fail silently.** An object kind or artwork the engine
   cannot do well raises and names the milestone that will cover it. A
   confident bad file is the worst outcome this product can produce.
7. **Every delivered file records engine, profile and schema version.**
8. **Machine profiles never change a stitch.** Hardware differences are
   refused or warned about, never silently digitized around -- otherwise the
   same design on two machines is two designs. Machine data may set speed and
   tension on the worksheet, and may block a file outright.

9. **An override must carry its reason.** A shop's change to a profile is
   recorded with why, and every delivered file names the fields that were not
   ours. A number nobody can explain later is worse than a wrong one.

## Before you push

```sh
ruff check .
pytest -q
v2s-lab golden        # real designs against approved output
```

If the golden suite or `tests/fingerprints.json` fails, engine output moved. That is allowed and
is how the engine improves -- but never incidentally. Find out what moved,
regenerate the file deliberately, and say so in the PR. Once the golden suite
exists (M2) a metric shift also needs digitizer sign-off.

## Ground truth

A render is not proof of quality, and neither is a passing test suite. The
only ground truth is thread on fabric. Nothing in this repo has been sewn yet,
and no fabric profile is calibrated -- `calibrated: false` in every profile
says so, and the worksheet prints it for the operator.
