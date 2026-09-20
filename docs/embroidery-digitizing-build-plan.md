# Auto-Digitizing: Build Plan

**Companion to:** `embroidery-digitizing-quality.md` (the quality doc). That file says what "good" means; this file says what to build, in what order, and how to know each piece is done.

**Audience:** the engineering team, and any coding agent working in the repo. Each milestone has acceptance criteria; nothing is done until they pass.

> Numeric defaults (densities, stitch lengths, pull comp) live in the quality doc and in fabric profile files. Never hard-code them in engine logic.

---

## 1. What we are building (v1)

A web service where a commercial decorator uploads a logo, declares placement, size, fabric, and thread brand, gets an instant quote, and receives a machine file (DST, PES, JEF, EXP) plus an editable object file within the SLA. Behind it:

1. **Engine:** deterministic library that turns artwork into parametric embroidery objects, then into stitches.
2. **Checks:** automated validators that block bad files.
3. **Simulator:** realistic render of the stitch file.
4. **Review editor:** internal web tool where digitizers fix engine output; every fix is logged as a structured diff.
5. **Service:** upload, gatekeeping, quoting, queueing, delivery, outcome reporting, API.
6. **Lab tooling:** calibration pattern generator, sew-out logging, golden suite runner.

v1 scope limits: vector input first, 3 fabric profiles (twill, pique, cap), run/satin/tatami stitch types, font-replaced text. See quality doc §10.

---

## 2. Architecture

```
            ┌────────────┐     ┌──────────────┐
 Customer → │  Web app   │ ──→ │  API (HTTP)  │ ──→ Postgres, object storage
            └────────────┘     └──────┬───────┘
                                      │ enqueue
                               ┌──────▼───────┐
                               │   Workers    │  run the engine library
                               └──────┬───────┘
      ┌───────────┬───────────┬───────┴─────┬────────────┬──────────┐
      ▼           ▼           ▼             ▼            ▼          ▼
   ingest → classify → objects (IR) → stitchgen → sequence → export
                           │                                   │
                           ▼                                   ▼
                     review editor  ←── checks + simulator ────┘
                           │
                           ▼
                    edit-diff log → rules tuning / ML training
```

**Key rule:** the engine is a pure library with no web, database, or queue dependencies. The service calls it; the golden suite calls it; the lab tools call it. Same code path everywhere.

---

## 3. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Engine | Python 3.12, NumPy, Shapely 2 (GEOS), pyclipper, SciPy, NetworkX | Fast to iterate with a digitizer in the loop; geometry libs are mature |
| Hot paths (later) | Rust via PyO3 | Only after profiling shows need |
| File I/O | pyembroidery (MIT) | Reads/writes DST, PES, JEF, EXP and more |
| SVG parsing | svgelements (MIT) | Handles transforms, arcs, units |
| PDF / AI input | Convert to SVG via Inkscape CLI or pdf2svg in a sandboxed worker | Avoid linking AGPL libraries |
| Raster vectorizing (M8) | vtracer (MIT), OpenCV | Potrace is GPL; avoid |
| Sequencing | OR-tools (Apache) plus custom heuristics | Routing with precedence constraints |
| API | FastAPI, Pydantic v2 | The IR schema is Pydantic; one source of truth |
| Jobs | Postgres-backed queue first (e.g. Procrastinate), Temporal if workflows grow | Fewer moving parts early |
| Data | Postgres, S3-compatible object storage | |
| Web app and editor | TypeScript, React, canvas via PixiJS (WebGL) | Editor must pan/zoom 20k+ stitches smoothly |
| CI | GitHub Actions; golden suite on every engine PR | |

### Licensing guardrails (commercial product)
- **Do not copy or link:** Ink/Stitch (GPLv3), Potrace (GPL), CGAL (GPL/commercial), PyMuPDF (AGPL).
- Reading Ink/Stitch docs to learn the domain is fine; porting its code is not.
- Thread chart data (Madeira, Isacord, Robison-Anton): confirm usage terms with each manufacturer; store charts as data files with provenance.
- Embroidery fonts: license pre-digitized fonts or commission our own. Do not trace commercial typefaces without a license.

---

## 4. Repository layout

```
/engine
  /ir            object model (Pydantic), schema versioning, JSON serialization
  /ingest        svg, pdf->svg, raster (later), color quantization, thread charts
  /geometry      offsetting, medial axis, curve fitting, scanline utils
  /classify      width analysis, stitch-type assignment, text detection
  /fonts         embroidery font format + loader
  /stitchgen     run, satin, fill, underlay, compensation, tie-in/off
  /sequence      precedence graph, routing, entry/exit selection, travel
  /export        writers wrapper, format limits, round-trip verify
  /checks        validators, density map, report model
  /simulate      stitch renderer (PNG/SVG), used by web and lab
  /profiles      fabric profile files (YAML), versioned
  /cli           `digitize`, `check`, `render`, `calibrate`
/service         api, workers, quoting, routing rules, auth, billing hooks
/web             customer app
/editor          internal review editor
/lab             calibration patterns, sew-out log app, golden suite runner
/golden          designs, approved outputs, tolerances
/docs            this file, the quality doc, ADRs
```

---

## 5. The object model (IR): the heart of the system

Everything upstream produces it; everything downstream consumes it. Stitches are **never** edited directly; they are regenerated from objects.

```jsonc
{
  "schema_version": "1.0",
  "engine_version": "git-sha",
  "design": {
    "width_mm": 89.0, "height_mm": 52.0,
    "placement": "left_chest",
    "fabric_profile": "pique@3",
    "thread_brand": "madeira_polyneon_40"
  },
  "objects": [
    {
      "id": "obj_012",
      "kind": "satin",                       // run | satin | fill | text
      "shape": { "rails": [[...],[...]] },   // fill: polygon+holes; run: polyline
      "thread": { "chart": "madeira_polyneon_40", "code": "1800" },
      "params": {
        "density_mm": 0.40,
        "pull_comp_mm_per_side": 0.35,
        "underlay": ["edge_run"],
        "max_width_mm": 7.0,
        "short_stitch": true
      },
      "param_source": { "density_mm": "profile", "pull_comp_mm_per_side": "profile" },
      "z_order": 12,
      "entry": null, "exit": null,           // chosen by sequencer unless pinned
      "locks": { "sequence": false, "params": false },
      "flags": []                            // e.g. "small_text", "needs_review"
    }
  ],
  "sequence": ["obj_003", "obj_012", "..."],
  "review": { "status": "pending", "route": "auto" }
}
```

Rules:
- **Units are millimetres** everywhere in the IR. Conversion to 0.1 mm machine units happens only in `/export`.
- `param_source` records whether each value came from the profile, a rule, an ML suggestion, or a human. This is what makes edit logs meaningful.
- Pull compensation is defined **per side**, along stitch direction. State this in the schema docs; vendors differ.
- Schema is versioned with migrations. Old designs must always reopen.

### Edit-diff log
Every save in the review editor stores an RFC 6902 JSON Patch against the IR, plus a feature snapshot of each touched object (width stats, area, curvature, neighbors, fabric, size). Table: `edit_events(design_id, reviewer_id, engine_version, patch, features, seconds_spent, created_at)`.

---

## 6. Engine modules: specs

### 6.1 Ingest
- Parse SVG to flattened, transformed, closed paths in mm with fill/stroke colors. Resolve `use`, clip paths, groups, and stroke-to-outline conversion.
- Scale to declared physical size **before** any analysis.
- Simplify and curve-fit (tolerance tied to thread width, ~0.1 mm) to remove node noise.
- Resolve overlaps into a planar arrangement with z-order retained, so we know what is hidden and what is adjacent.
- Color: convert to Lab, merge near-identical colors, match to the customer's thread chart by ΔE; return the mapping for customer confirmation.

### 6.2 Geometry utilities
- **Medial axis:** Voronoi of densely sampled boundary (SciPy), pruned by branch length and angle. Gives local width everywhere and centerlines for satin.
- Robust offsetting via pyclipper (integer coordinates; scale by 1000).
- All randomness seeded; no unordered-set iteration in output paths. Determinism is a test (see §9).

### 6.3 Classification
- Per region, compute the width distribution along the medial axis.
- Apply thresholds from the profile (run / satin / fill). Regions with mixed widths are **split** at width transitions (e.g. a shape with a fat body and thin tail becomes fill + satin).
- Stroke-only paths become run or satin by stroke width.
- Text: if the SVG retains text elements, map to an embroidery font directly. If outlined, detect glyph-like clusters (size, baseline alignment, repetition) and flag `small_text` when cap height is under the profile minimum. v1 does not OCR; outlined text under the minimum routes to a human.

### 6.4 Stitch generation
- **Run:** resample polyline at target length; shorten on tight curves; optional bean (triple) stitch.
- **Satin:** derive rail pairs from the medial axis; place stitch pairs at density spacing along the centerline; angle follows the local perpendicular with smoothing; short-stitch the inner side when inner spacing drops below threshold; auto-split beyond max width; corners handled by mitre or cap depending on angle.
- **Fill (tatami):** rotate by fill angle, intersect scanlines at row spacing, decompose into monotone sections (boustrophedon decomposition) so each section sews without jumps, connect sections with travel runs under not-yet-sewn rows, apply stagger offsets so needle points do not line up.
- **Fill angle choice:** default to the region's principal axis ±45°, and differ from adjacent fills to improve contrast and reduce registration stress.
- **Underlay:** recipe from the profile keyed by object kind and width (quality doc §4.3). Underlay is inset from the edge so it never peeks out.
- **Compensation:** pull comp extends stitch ends along stitch direction; push comp trims fill extent at the ends perpendicular to it. Both from the profile, scaled by object width where the profile says so.
- **Tie-in / tie-off:** on every object start and before every trim.
- **Hidden stitch removal:** subtract fully covered areas from lower fills, leaving an overlap margin from the profile.
- Post-filter: merge or drop stitches under the minimum length.

### 6.5 Sequencing
- Build a precedence DAG: z-order overlaps, underlay before top, cap rule (center-out, bottom-up) when profile is cap.
- Group by color where precedence allows.
- Solve as routing with precedence: greedy construction, then 2-opt / or-opt improvement under the constraints; OR-tools for harder cases. Cost = color changes (heavy) + trims (medium) + travel length (light).
- Choose entry/exit per object from candidate points to minimize travel; prefer travel under later objects; trim when a jump exceeds the profile threshold.

### 6.6 Export
- Wrap pyembroidery. Enforce per-format limits (DST: 0.1 mm units, max 12.1 mm per move, color changes as stops, no palette; PES/JEF: embed thread colors, hoop size limits).
- Always write a production worksheet (PDF or HTML): color sequence with thread codes, size, stitch count, est. run time, fabric profile, stabilizer recommendation.
- Round-trip verify every file: write, read back, compare command stream.

### 6.7 Checks
Implements quality doc §6.1. Output is a structured report (`pass | warn | block` per rule, with object ids and locations) that the editor overlays on the canvas.

### 6.8 Simulator
- Render each stitch as a shaded capsule with thread-width and direction-dependent highlight, over a fabric texture. Output PNG for customers and a WebGL layer for the editor.
- Must draw exactly what `/export` wrote, read back from the machine file, not from the IR.

### 6.9 Fabric profiles
YAML files, versioned (`pique@3`). Contain thresholds, densities, stitch lengths, underlay recipes, compensation, trim threshold, min text height, overlap margin. Changing a profile is a release (quality doc §9).

---

## 7. Review editor

The second product. If it is slow or clumsy, edit-minutes never drop and the data is poor.

Must-haves for v1:
- Open a design: artwork layer, object layer, stitch simulation, check overlays.
- Select object → change kind, angle, density, underlay, pull comp; reshape nodes and satin rails; split and merge objects.
- Reorder sequence by drag; pin entry/exit points.
- Regenerate only affected objects, under 1 s for a typical edit.
- Stitch player (scrub through sew order).
- One-click outcome: approve untouched, approve with edits, reject to manual. Timer runs automatically.
- Every save writes an edit event (§5).

Not in v1: manual stitch-by-stitch editing. If a reviewer needs it, that is an engine gap to log, not a feature to add.

---

## 8. Service

- **Upload flow (gatekeeper):** implements quality doc §14: placement and dimensions required, fabric required, thread brand, resolution and feature checks, thread mapping confirmation, routing to auto or manual with instant quote.
- **Routing rules** are data (a rules file), not code, so ops can tune them.
- **Jobs:** `ingest → digitize → check → render → queue_for_review → deliver`. Idempotent steps; each records engine and profile versions.
- **Review queue:** ordered rush, revisions, standard by age. Intake cap computed from review-minutes (quality doc §13).
- **Delivery:** machine files, object file, worksheet, render; reorders free.
- **Outcome reporting:** follow-up with one-tap "sewed clean / had an issue" plus photo upload; issues open a revision ticket linked to the design and engine version.
- **API:** same endpoints the web app uses, with keys and webhooks.
- **Security:** artwork is confidential. Private buckets, short-lived signed URLs, reviewer access logged, encryption at rest, deletion on request.

Core tables: `accounts, designs, design_versions (IR blobs), jobs, check_reports, edit_events, deliveries, outcomes, sewouts, profiles, engine_releases`.

---

## 9. Testing strategy

| Level | What |
|---|---|
| Unit | Geometry utils, each stitch generator on primitive shapes |
| Property-based (Hypothesis) | For random valid polygons: no stitch under min length; all penetrations within shape + comp tolerance; fill coverage ≥ threshold; no NaNs; satin never exceeds max width |
| Determinism | Same input twice, and across CI OS images → byte-identical output |
| Round-trip | Every writer: write → read → equal command stream |
| Golden suite | Real designs with approved outputs; structural diff on IR, metric diff on stitches; tolerances per metric; digitizer sign-off on change |
| Hardware | Files load and run on the lab's real controllers before each release |
| Sew-out | Calibration set per quality doc §6.3 and §16 |

CI blocks merges to `/engine` on anything above hardware level.

---

## 10. Milestones

Durations assume 3–4 engineers plus the senior digitizer from day one. Order matters more than dates.

### M0. Foundations (2 weeks)
IR schema v1, profile loader, CLI skeleton, pyembroidery wrapper with round-trip tests, basic simulator.
**Done when:** a hand-written IR with one run object exports to DST and PES, loads on the lab machines, and sews.

### M1. Stitch primitives + calibration (5 weeks)
Run, satin, tatami fill, underlay, compensation, tie-offs, from **hand-authored** objects. Calibration pattern generator (`/lab`). Sew-out log app.
**Done when:** calibration patterns sew on twill and pique; measured dimensional error under 0.3 mm after profile tuning; digitizer rates satin edges and fill texture acceptable. **This is the riskiest milestone. Do not start ingest before it passes.**

### M2. Checks + golden suite harness (2 weeks, overlaps M1)
All blocking validators, density heat map, report model, golden runner in CI.
**Done when:** checks catch a seeded set of 30 known-bad files with zero misses.

### M3. Vector ingest + classification (5 weeks)
SVG/PDF in, planar arrangement, medial axis, region splitting, stitch-type assignment, thread mapping, angle selection.
**Done when:** 50 real vector logos produce valid IR with no crashes; digitizer agrees with stitch-type assignment on ≥ 85% of objects.

### M4. Sequencing + hidden stitch removal + cap profile (4 weeks)
**Done when:** on the 50-logo set, trims and color changes are within 15% of the digitizer's hand-sequenced versions; cap calibration sews clean.

### M5. Review editor (8 weeks, starts alongside M3)
**Done when:** digitizer can take engine output to shippable using only our editor, median under 10 minutes, with all edits logged.

### M6. Text via embroidery fonts (3 weeks)
Two licensed or commissioned fonts (block, script), live-text mapping, small-text flagging.
**Done when:** text ladder sews legibly down to the profile minimum.

### M7. Service + gatekeeper + delivery (6 weeks, overlaps M5–M6)
**Done when:** an outside decorator completes upload → quote → delivery → outcome report without help.

### M8. Private beta
10–20 decorators, 100% human review, free trial files, capped intake. Weekly metrics per quality doc §7 and §17.
**Exit when:** field first-sew success is at target over ≥ 300 files and median edit time is under 5 minutes.

### M9. After beta, in priority order
1. Rule tuning from edit logs (most edits cluster into a few fixable causes)
2. ML parameter suggestion (angle, pull comp, underlay) trained on edit events, always overridable, always logged in `param_source`
3. Raster ingest (vtracer + cleanup)
4. Zero-touch delivery for high-confidence files, staged per quality doc §9
5. API partners; fourth fabric profile

---

## 11. Risks and how we retire them early

| Risk | Mitigation |
|---|---|
| Stitch quality never reaches pro level | M1 before anything else; digitizer has veto; blind benchmark each quarter |
| Medial-axis satin rails are noisy on real logos | Prune aggressively; fall back to fill; let editor redraw rails; log every fallback |
| Fill decomposition bugs on complex holes | Property tests on random polygons with holes; visual fuzz gallery |
| Editor takes longer than engine | Start at M3, not after; ship ugly but fast |
| Non-determinism creeps in | Determinism test in CI from M0 |
| License contamination | Guardrails in §3; dependency license check in CI |
| Thread chart / font rights | Resolve during M3 and M6, not at launch |
| One digitizer is a bottleneck | Hire queue digitizers before beta (quality doc §11) |

---

## 12. Working rules for anyone building in this repo

1. Engine code never imports from `/service`, `/web`, or `/editor`.
2. No magic numbers in engine logic; values come from profiles or the IR.
3. Millimetres everywhere until `/export`.
4. Every engine PR runs the golden suite; metric shifts need digitizer sign-off in the PR.
5. Every delivered file records engine version, profile version, and schema version.
6. When a reviewer keeps making the same edit, fix the rule; do not add an editor shortcut.
7. If a render looks right but the sew-out is wrong, the sew-out wins, and the simulator gets a bug ticket too.
