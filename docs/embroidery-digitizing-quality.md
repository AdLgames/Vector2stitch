# Auto-Digitizing: Product Quality Strategy

**Scope:** how we define, build in, measure, and protect output quality for an image/vector → stitch-file engine aimed at commercial decorators. Part I (§1–11) covers the engine and lab. Part II (§12–17) covers the commercial and operational choices that protect that quality.

**Core position:** in this market, quality *is* the product. A decorator who ruins one garment run because of our file will not come back. Speed and price only matter after the file sews cleanly the first time.

> All numeric values below are industry-typical starting defaults. Every one of them must be calibrated on our own machines through physical sew-outs before it is trusted.

---

## 1. What "quality" means here

A file is good only if all four are true:

1. **It sews.** No thread breaks, needle breaks, bird-nesting, or machine stops caused by the file.
2. **It looks right.** Registration between colors is tight, edges are clean, no fabric shows through, small details and text are legible, no puckering.
3. **It runs efficiently.** Minimal trims, jumps, and color changes; sensible stitch count. Machine time is the customer's money.
4. **It is editable.** A professional digitizer can open it, understand the object structure, and adjust it in minutes.

Screen previews prove none of these. **The only ground truth is thread on fabric.**

---

## 2. Quality principles

- **Deterministic core.** The same input and settings always produce the same stitches. ML may suggest parameters; it never emits coordinates.
- **Objects, not stitches.** Every stitch is regenerated from a parametric object (shape, stitch type, angle, density, underlay, pull comp, fabric profile). This makes fixes systematic rather than one-off.
- **Refuse rather than fail silently.** If artwork is outside what we can do well (2 mm text, photographic gradients), we flag it and route to a human. A confident bad file is the worst outcome.
- **Fabric is an input, not an afterthought.** No fabric profile, no file.
- **Every human correction is a bug report.** Edits made by our digitizers are logged structurally and fed back into rules and models.

---

## 3. Defect taxonomy

A shared vocabulary so sew-out failures map to engine causes.

| Defect | Visible symptom | Usual engine cause |
|---|---|---|
| Gapping / poor registration | Fabric shows between fill and border | Pull comp too low; bad sequencing; weak underlay |
| Puckering | Fabric ripples around design | Density too high; insufficient underlay; sewing outside-in |
| Thread breaks | Machine stops | Stitches too short; density hotspots; too many penetrations in one spot |
| Bulletproof patches | Stiff, thick areas | Overlapping layers without removing hidden stitches underneath |
| Looping / snagging satin | Loose long stitches | Satin too wide without auto-split |
| Sunken stitches | Detail disappears into pile | Missing or wrong underlay for fleece/terry/pique |
| Illegible text | Closed counters, merged letters | Text too small for thread weight; auto-traced instead of font-replaced |
| Jagged curves | Stair-stepped satin edges | Poor curve fitting; no short-stitching on tight inner curves |
| Visible travel | Stray lines across design | Travel runs not hidden under later objects; missing trims |
| Fill distortion | Shape pushed out at the ends | No push compensation along stitch direction |

---

## 4. Quality built into each pipeline layer

### 4.1 Ingest
- Reject or warn on raster input below a minimum effective resolution at target sew size.
- Quantize colors to a real thread chart (Madeira, Isacord, Robison-Anton), not arbitrary RGB.
- Curve-fit aggressively: fewer, smoother nodes produce better satin edges than faithful tracing of pixel noise.
- Compute feature sizes at **final physical dimensions**. A shape that is fine at 100 mm is unsewable at 60 mm.

### 4.2 Classification
| Feature width | Default stitch type |
|---|---|
| < ~1 mm | Run stitch (or bean stitch for weight) |
| ~1–7 mm | Satin |
| > ~7 mm | Tatami fill, or split satin |

- Detect text and replace with pre-digitized embroidery fonts. Minimum height ~4–5 mm with 40 wt thread; below that, require 60 wt thread and a smaller needle, or escalate to a human.
- Gradients and photographic regions: flag for human review in v1.

### 4.3 Stitch engine
- **Density:** ~0.4 mm row spacing as the baseline for both fill and satin; reduce on overlapping layers.
- **Stitch length:** fills ~3–4 mm, runs ~2–2.5 mm. Hard floor around 0.5 mm; filter anything shorter.
- **Satin:** short-stitch the inner side of tight curves to prevent penetration pile-up; auto-split beyond max width.
- **Underlay by object:**
  - Narrow satin (< ~2 mm): center run
  - Medium satin: edge run
  - Wide satin: edge run plus zigzag
  - Fills: low-density tatami underlay at a contrasting angle to the top layer, plus edge run
- **Pull compensation:** applied along stitch direction, scaled per fabric profile (see §5).
- **Push compensation:** shorten fills slightly at the ends perpendicular to pull.
- **Tie-in / tie-off** on every object start and before every trim.
- **Hidden-stitch removal** where objects fully overlap, leaving a small overlap margin for registration.

### 4.4 Sequencing
- Hard constraints: background before foreground; underlay before top; on caps, center-out and bottom-up.
- Soft objectives (optimized): fewest color changes, fewest trims, shortest travel, travel hidden under later objects.
- Nearest-point entry/exit selection per object so joins are invisible.

### 4.5 Export
- Respect format limits (e.g. DST: 0.1 mm units, max 12.1 mm per move; longer moves are split into jumps).
- Round-trip test every writer: write → read → diff stitch coordinates and command stream.
- Verify files load on real controllers (Tajima, Brother, Barudan, Ricoma), not only in software readers.

---

## 5. Fabric profiles

Each profile bundles pull comp, density modifier, underlay recipe, and stabilizer recommendation.

| Fabric | Pull comp (start) | Notes |
|---|---|---|
| Twill / canvas / denim | ~0.15–0.2 mm | Stable; the baseline profile |
| Pique polo | ~0.3–0.4 mm | Textured; heavier underlay to bridge the weave |
| Jersey / T-shirt knit | ~0.3–0.4 mm | Stretchy; lighten density to avoid puckering |
| Fleece / terry | ~0.4 mm+ | Full-coverage underlay; topping recommended |
| Structured cap | ~0.3 mm | Center-out sequencing; limited sew field height |
| Performance / thin poly | ~0.3 mm | Lightest density; most pucker-prone |

Ship v1 with 3 profiles done properly (twill, pique, cap) rather than 10 done approximately.

---

## 6. Verification

### 6.1 Automated checks (every file, blocking)
- Minimum and maximum stitch length
- Density heat map: flag penetration clusters above threshold per mm²
- Satin width bounds
- Stitch count and estimated run time vs. design area
- Trim, jump, and color-change counts vs. budget
- Missing tie-offs before trims
- Feature-size check against thread weight
- Design fits declared hoop / cap field

### 6.2 Golden test suite (every engine change)
- 200–500 real customer-style designs with approved reference output.
- Regression = structural diff on objects plus metric diff on stitches (count, length distribution, density map, trims).
- Any metric moving beyond tolerance requires digitizer sign-off.

### 6.3 Physical sew-out lab (weekly, and before every release)
- Fixed calibration set: test patterns for pull comp (circles and squares measured with calipers), column width ladders, text size ladders, registration targets.
- Matrix: each design × each supported fabric × fixed thread, needle, stabilizer, and speed.
- Every sew-out is photographed under consistent lighting, measured, scored against the defect taxonomy, and stored.
- Released parameter changes must show a sew-out improvement, not just a better render.

### 6.4 Human review gate (every customer file in v1)
- In-house digitizer reviews in our editor before delivery.
- Review outcome is logged: approved untouched, minor edit, major edit, rejected.
- Edits are captured as object-level diffs (what parameter changed, by how much, on what kind of shape).

---

## 7. Quality metrics

| Metric | Definition | v1 target |
|---|---|---|
| Zero-touch rate | Files shipped with no human edits | 30% → 70% over 12 months |
| Edit minutes per file | Median digitizer time to make it shippable | < 5 min, then < 2 min |
| First-sew success | Customer sews without requesting a revision | > 95% |
| Revision rate | Files returned for fixes | < 5% |
| Thread-break rate | Breaks per 10k stitches in our lab | At or below human-digitized baseline |
| Dimensional error | Sewn size vs. designed size on calibration shapes | < 0.3 mm |
| Escalation precision | Flagged-as-hard files that truly needed a human | > 80% |

Report weekly. Zero-touch rate never gets to rise at the expense of first-sew success.

---

## 8. Blind benchmark

Quarterly: take 50 designs, produce them with (a) our engine untouched, (b) our engine plus human edit, (c) a respected commercial digitizer. Sew all three. Have working decorators rank them blind.

This is the only honest answer to "are we industry-grade yet."

---

## 9. Release discipline

1. Engine change passes unit tests and automated checks.
2. Golden suite regression reviewed by a digitizer.
3. Calibration sew-out on all supported fabrics.
4. Staged rollout to internal review queue before any zero-touch delivery.
5. Parameter sets are versioned; every delivered file records the engine and profile version that made it, so any complaint is reproducible.

---

## 10. What we deliberately do not do in v1

- Photorealistic or gradient artwork
- Text under ~4 mm without human review
- Appliqué, 3D puff, sequins, chenille
- Fabrics without a calibrated profile

Saying no to these protects the first-sew success rate, which is the number the business lives on.

---

## 11. People and equipment

- **Senior digitizer (day one):** owns the defect taxonomy, golden suite approvals, and parameter sign-off. Has veto on releases. Sets standards and audits the review queue; does not work it full time.
- **Queue digitizers (1–2 junior or contract):** do the day-to-day file review and edits. Removes the single point of failure and keeps the senior free for standards work. Calibrate reviewers against each other monthly on a shared set of files so edit logs stay consistent.
- **Commercial multi-needle machine** plus a single-head consumer machine, so both DST and PES paths are tested on real hardware.
- **Consumables held constant:** one thread brand and weight, fixed needle sizes, fixed stabilizers, logged per sew-out. Uncontrolled variables make sew-out data worthless.

---

# Part II: Commercial and Operations

Every choice here is judged by one question: does it protect first-sew success and the data loop that improves it?

---

## 12. Pricing

- **Price at parity with premium human digitizers.** The customer is buying a file that sews clean the first time, not a cheap file. Discounting anchors the product in a low-value tier that is hard to leave.
- **Give a reason to switch at the same price.** A decorator already trusts their current digitizer. Our edge: instant quote at upload, an editable object file alongside the machine file, a stated remedy (§15), predictable turnaround, and API access for volume buyers.
- **Trial by free files, not discounts.** First 3 files free. The list price never moves.
- **Quote by placement and complexity class, not stitch count.** Customers cannot know stitch count upfront. Placement (left chest, cap front, full back, sleeve) implies size and hoop; the engine assigns a complexity class at upload and shows the price immediately.
- **Gated Custom/Manual tier.** Anything outside v1 limits (§10) is quoted separately at a premium. This protects unit economics and keeps hard cases flowing in as data rather than bouncing off a rejection.
- **Priced follow-ons:** revisions caused by us are free; customer-requested changes, resizes beyond ±10–15%, and new fabric profiles for an existing design are priced items. Reorders of an unchanged file are free forever.

### Accounting for review labor
- Labor spent fulfilling a paid order belongs in COGS on the books. Capitalizing it as R&D invites audit and diligence problems. Confirm treatment with an accountant.
- Internally, track a **data-acquisition allocation**: the share of review minutes that produced logged structural diffs. Report gross margin both ways (as booked, and net of data acquisition) so the path to healthy margins at 70% zero-touch is visible without distorting the books.

---

## 13. SLA and operational flow

- **Standard turnaround: 24 hours.** Reliable, and gives reviewers time to log edits properly instead of rushing them.
- **Paid rush: 2–4 hours.** Speed is the most monetizable thing automation gives us. Sell it; do not give it away.
- **No instant "surprise" delivery in v1.** It conflicts with the 100% human review gate, resets customer expectations so that 24 hours feels slow, and reveals which files were automated, which undermines parity pricing. If a file is ready early, release it within a consistent band (for example, no sooner than 2 hours on standard).
- **When zero-touch delivery is eventually enabled**, it goes through the staged rollout in §9 and is sold as the rush tier.
- **Capacity-capped intake.** Cap daily orders by available *review-minutes*, not order count: `daily cap = reviewer minutes available ÷ trailing median edit minutes per file`, with headroom for rush and revisions. Waitlist new accounts when the cap is reached. The < 5 min per file target is an outcome of engine quality; throttling protects review thoroughness, it does not create speed.
- **Queue order:** rush, then revisions, then standard by age.

---

## 14. Ingest gatekeeper (front end)

The upload flow is the first quality gate. Principle: **route, don't reject.** A hard stop loses the customer and the hard-case data. Anything the engine should not attempt goes to the Custom/Manual tier with a quote.

- **Resolution check.** Compute effective resolution at the declared sew size. Below threshold: explain why, ask for better art (vector preferred), or offer the manual tier.
- **Mandatory placement and physical dimensions.** No submission without them. All feature-size checks run at final size. If scaling takes text below ~4–5 mm, route to human review automatically and say so.
- **Forced fabric selection.** No default. Twill, pique, cap are supported; "Other / not listed" is allowed but routes to the manual tier and carries no first-sew remedy.
- **Thread color mapping with confirmation.** Ask which thread brand the shop stocks (Madeira, Isacord, Robison-Anton). Quantize to that chart, show the matched thread numbers next to the art, allow overrides, and accept Pantone references for brand colors.
- **Unsupported-feature detection.** Gradients, photographic regions, appliqué, 3D puff, sequins are intercepted and routed. This detector is a classifier with its own error rate; track its precision and recall like any other metric.
- **Honest previews.** Keep a short note that a render is not proof of quality, but do not rely on it; permanent disclaimers get ignored. Show real sew-out photos from our lab beside renders, per fabric, so customers see what the engine actually produces.

---

## 15. Guarantee, liability, and field feedback

- **Remedy, not a void clause.** We cannot verify what fabric a customer sewed on, and voiding a guarantee reads as adversarial. The offer: if a file on a supported profile does not sew clean, we revise it free within one business day when the customer submits a sew-out photo and their machine, thread, needle, and stabilizer details.
- **Liability capped at the file price** in the terms of service. Never garments, thread, or machine time. Recommend a test sew on scrap before any production run, in the delivery email and in the terms.
- **Unsupported fabrics:** best effort, paid revisions, stated clearly at order time.
- **One-tap outcome reporting.** A day or two after delivery, ask: "Sewed clean" or "Had an issue" (with photo upload). Without this, first-sew success cannot be measured. Issue photos are scored against the defect taxonomy (§3) and linked to the engine version that produced the file.
- **Do not publish the > 95% first-sew figure** until lab and field data support it. It is an internal target first.

---

## 16. Scaling the sew-out lab

Testing every design on every fabric does not survive a fourth profile. Move to risk-based sampling before expanding:

- **Always full:** the calibration set on all supported fabrics for any engine or parameter change.
- **Novelty sampling:** prioritize customer designs whose feature mix (widths, text sizes, layer counts, density) sits far from anything in the golden suite.
- **Random baseline:** a small fixed percentage of all delivered files, to catch what the novelty score misses.
- **Field data as a fourth signal:** customer issue reports and photos trigger a lab reproduction.
- **New profile entry bar:** a profile ships only after its calibration set passes and a minimum number of real designs have been sewn and scored on it.

---

## 17. Data rights, confidentiality, and integration

- **Training rights stated plainly in the terms:** we may use uploaded artwork, generated objects, reviewer edits, and sew-out reports to improve the engine. Offer an opt-out for enterprise accounts if needed; without these rights the data loop has no legal footing.
- **Artwork confidentiality.** Customers upload client logos and unreleased brand work. Designs are never shown publicly or used in marketing without permission. Access is limited to reviewers and is logged.
- **IP responsibility.** The customer warrants they have the right to embroider the artwork.
- **API for volume buyers** (contract decorators, print-on-demand platforms): same gates, same profiles, same routing to manual; quotes and status exposed programmatically. API customers count against the same review-minute cap.

### Added metrics (extends §7)

| Metric | Definition |
|---|---|
| Outcome response rate | Share of delivered files with a customer sewed-clean / issue report |
| Field first-sew success | Sewed-clean reports ÷ all reports, by fabric profile and engine version |
| Manual-tier routing rate | Share of uploads routed out of the automated path, by reason |
| Gatekeeper precision / recall | Accuracy of unsupported-feature and small-text detection |
| Review-minute utilization | Review minutes used ÷ available; drives the intake cap |
| Margin, as booked vs. net of data acquisition | Tracks the path to healthy unit economics |
| Trial conversion | Accounts that pay after the 3 free files |
