# Measurement protocol — what the robot does, move by move

> **Status: collection closed 2026-09-12.** Nothing more is measured. The
> move-by-move description below is the shape of every run that was taken, and
> the coordinate frames, the motion-enable sequence and the failure modes are
> all accurate as run. Some of its numbers are not: parts were written for the
> force-ladder protocol at 5 N. What the campaign actually ran is summarised in
> the next section, and `config/sensor_registry.yaml` + `config/probes.yaml`
> remain the machine-readable source of truth.
>
> **Two things changed after this file was written.** The substrate-stiffening
> alarm became record-only (2026-09-07, in the table below), and the
> maximum-force test was re-run on both principles with one probe, `ball8`,
> after the five ceilings declared on `ball4` turned out to sit deeper than the
> ball's own diameter — the contact was the shank, not a sphere
> (`force_ceiling.md` §6.3). The area watchdog used during those ramps was
> removed: it could not separate gel destruction from detector failure
> (`force_ceiling.md` §6.5b).

---

## The protocol as it was run — final

**Two passes.** Pass A: shape reconstruction and spatial resolution, seven
probes over a shared depth ladder — complete for 9DTact's 17 units; for the
DIGIT family it covered the photometric calibration grid and the shape probes,
but **two-point resolution was dropped** (one DIGIT unit only; DIGIT_Marker not
at all, operator's decision 2026-09-11). Pass B: force estimation with `ball8`,
complete for all 53 units, then the maximum-force test last because it damages
gels — 9DTact 17/18 and DIGIT 18/18 on `ball8`, DIGIT_Marker on `ball4` only.

### Ranges and limits

| | value | why |
|---|---|---|
| Normal range | **0–2 N** | fixed and identical for every unit, so force-estimation errors are comparable. 3 N was reachable by only 10 of 18 units, 2 N by 15; the three short of it (soft 2 mm pair, hard_1mm_r1) sit at 1.8–2.0 N. |
| Shear range | **0–0.5 N** | a quarter of the normal range. Friction is not the constraint: mu >= 0.59 on the 1.2 N hold carries 0.71 N. |
| Shear hold | **1.2 N** | 60 % of the normal range. |
| Depth backstop | **(thickness + 1.0 mm) × 0.9** | binds in every phase. `thickness_mm` names the TRANSLUCENT gel; a 9DTact has a black gel cast over it, so the compliant stack is about a millimetre thicker than the label. Without the offset a 1 mm unit was held to 0.90 mm and about 1 N. |
| characterize ceiling | **range / 0.9 + 0.65 = 2.87 N** | stop once the unit has demonstrably cleared the range it will be collected over. Finding where a gel actually gives out is test 4's job. |
| Frame budget | **1000 per unit** | equal for every unit, so units are compared on the sensor and not on dataset size. |
| Ramp mode | **continuous, paced** since the 12th unit (`9DTact_hard_1mm_r1`); the first eleven were **stepped** | The probe glides instead of stepping 0.1 N at a time. What makes it faster is not removing the pauses but PACING the glide: a frame is kept only if its force differs by 0.02 N from one already in its bin, and frames arrive every 0.206 s, so the force has to move ~0.1 N/s. Each segment aims at 0.25 N and 1.7 s, its length and velocity from the stiffness measured on the segment before; the arm's mm/s at 100 % is learned from each glide's elapsed time rather than assumed. A fixed 0.5 % gave 0.035 N/s and no gain. The shear RETURN is deliberately NOT paced — it retraces forces already covered, and pacing it cost 426 s of a 788 s collect — it runs at 0.6 mm/s in three segments. **Measured: collect 434 s at 50 % acceptance, whole run 7.6 min, against 713 s at 30 % and 12–15 min stepped.** Labels, bins, separation, budget and range are identical; the gel's loading history is not. |
| Ramp anchors, ramp settle | **0.1 N, 0.15 s** — a 0.5 N / 0.05 s trial on `9DTact_medium_3mm_r1` was reverted | Load steps did get faster (1.03 → 0.41 s, matching unload) but collect did not: 726 s against 678–723 s on the units before, because the run needed 10+12 cycles instead of 7–8 + 9–10. The frames that fill the force bins are the ones captured while the probe pauses at a rung; shorten the pause and each pass contributes fewer distinct-force frames, so more passes are needed. Time per saved frame stayed at 0.7 s. Only that one unit was collected at the trial pacing (labels and bins unaffected). |
| Between stages | **no park** from the same unit on | `pass_b_sensor.sh` stage 1 leaves the probe where contactmap ended; stage 2 starts within a second by lifting 3 mm and re-centring. The 45 s round trip to 78 mm was waste. The script's EXIT trap still parks if stage 2 never completes. The first ten units were collected with the park. |
| Substrate-stiffening alarm | **records, does not stop** (since 2026-09-07 20:44) | The local force–depth exponent crossing 2.0 marks the backing taking load. It was a stop condition while there was no depth limit; with the backstop as the safety it only truncated the range. On `9DTact_soft_1mm_r2` with ball8 it fired at 1.32 mm / 1.76 N — a real 2.45, soft top over a stiff floor — on a unit that had carried 9.09 N at 4.12 mm with no permanent set, and the image was still answering at 1.71 lvl/N. A 4 mm sphere's contact is 3 mm wide at that depth, so it feels a 2 mm stack's floor early. The crossing depth is written to the registry as `exponent_first_over_mm`; `--exp-alarm-stops` restores the old behaviour. |

The range does **not** set the collection time. Total ramp steps are
`budget × bin_width / (frames_per_cell × ramp_step)`, in which the range
cancels — measured 109/101/105/103 steps at 3.0/2.5/2.0/1.5 N. So the range is
chosen on data quality alone, and a narrower one puts more frames in each
0.05 N bin (13 at 2 N, against 9 at 3 N).

### Timing, measured 2026-09-07

A full sensor is about **13 minutes**, of which `collect` is **10**. It was 24
minutes until the camera fix below.

| step | s |
|---|---|
| collect | 608 |
| characterize | ~70 |
| contactmap | ~25 |
| enable → touchcheck | ~63 |
| retract, zerocheck, summary, park | ~19 |

### The camera was throwing away every second frame

`CAP_PROP_BUFFERSIZE = 1` is right for single-shot use and wrong for
continuous capture: while the reader holds the only buffer the driver has
nowhere to put the next frame. Measured at 1080p YUYV, 204.7 ms exposure
(4.89 fps is the sensor's own limit):

| | fps | gaps |
|---|---|---|
| BUFFERSIZE=1 | 2.48 | 58 of 59 exactly **two** frame periods |
| BUFFERSIZE=4 | 4.93 | every gap one period |

`collect` alone asks for four buffers; every other phase keeps one, because a
reader that pauses comes back to a backlog. Frames are timestamped from the
driver (`CAP_PROP_POS_MSEC`, CLOCK_MONOTONIC) rather than from the clock at
retrieval — retrieval is a stable 207 ms late even when keeping up, and up to
1502 ms late after a stall. Every force label is aligned to the driver stamp.

### Contact must be on the sensor axis, and it does not stay there

`collect` aborts past 0.3 mm off the sensor axis. This is an **absolute
position check, not a drift check** — it fails just as readily on a run that
started off-centre and never moved. Two things push the tip off:

* `--test-up` travels along base +Z and the sensor axis is **1.06° off base Z**,
  so the 37.85 mm drop to the search start alone costs 0.70 mm.
* `_move_along_normal` chains each target off the pose just achieved rather
  than off a fixed origin, so MoveL's ~3 µm per-move Cartesian bias
  accumulates: measured on the axis to 0.000 mm after both the search and the
  touch check, then 0.329 mm off by the time collect started, gained inside
  zero/characterize/contactmap.

So the run re-centres twice: after the fast drop, and again immediately before
collect (lifting 3 mm first — align moves sideways at constant height, which
off the gel is safe and on it would drag the probe across the surface). Once
each is enough; collect's own ramps go through `_seek_force`, which IS
origin-anchored, and the radial held to 0.010 mm across a full cycle.

### The probe is lifted clear on every exit path

A failed run used to skip the park step, and on 2026-09-07 a probe sat resting
on `9DTact_hard_3mm_r1` for 28 minutes after `collect` aborted. `run_one_sensor`
now lifts on every path — failure, exception, Ctrl-C — by talking to
`move_probe` directly rather than re-entering itself, because the emergency
lift must not need the registry, the probe file or a valid sensor id, which
are exactly the things that may be what failed. It is loud when it cannot do it.

### What the F/T can actually resolve

ATI Mini45 (SI-145-5, serial FT29831) on an NI PCIe-6343. Measured unloaded
over four baseline runs, 10 s each at 2 kHz, linear trend removed. The
manufacturer quotes one figure for all three force axes; the axes do not
behave alike.

| axis | quantisation only | gauge noise propagated | measured 1 sample | 0.1 s average | ATI spec |
|---|---|---|---|---|---|
| Fx | 0.0030 N | 0.0234 N | 0.0204 N | 0.0029 N | 1/16 = 0.0625 N |
| Fy | 0.0030 N | 0.0227 N | 0.0194 N | 0.0040 N | 1/16 = 0.0625 N |
| **Fz** | 0.0052 N | 0.0467 N | **0.0502 N** | **0.0155 N** | 1/16 = 0.0625 N |
| Tx/Ty | 0.07 mN·m | 0.62–0.65 | 0.52–0.54 | 0.13–0.20 | 1/752 = 1.33 mN·m |
| Tz | 0.05 mN·m | 0.41 | 0.50 | 0.14 | 1/1504 = 0.66 mN·m |

The rig meets the datasheet and beats it: Fz by 1.2x on a single sample, Fx/Fy
by 3.1x, and Fz by 4x once the protocol's 0.1 s average is applied — which is
what ATI's own note ("can be improved with filtering") points at.

**The 1/16 N is analog noise, not bit depth.** Propagating the DAQ's 305 µV
LSB through the FT29831 UserAxis matrix gives an Fz quantisation limit of
0.0052 N, twelve times finer than the spec. Propagating the measured gauge
noise (619–922 µV rms) gives 0.0467 N, which matches the measured 0.0502 N to
7 %. The DAQ is not the limiting element, so a higher-bit card would buy
nothing.

**Why Fz is the worst axis** is visible in the calibration matrix: its row is
`+34.4 +1.7 +33.7 +1.5 +33.6 +1.2` — three large coefficients of the same
sign, so three gauges' noise accumulates in quadrature at full weight. Fx has
only two (`-24.1`, `+23.7`). ATI's single number is the worst axis; Fx and Fy
come out better for free.

Averaging is **sub-root-N** — 0.1 s should give 0.0040 N by white-noise scaling
and gives 0.0155 N, and going to 1.0 s buys only 2.3x for ten times the wait —
so 0.1 s is the operating point. Mains is 1.6 % of the noise power.

In campaign terms: 0.016 N (1 sigma) on a 2 N range is 0.78 %, about 129
distinguishable levels; the binner's `--min-sep 0.02 N` matches it; contact
detection at 0.11 N is 7 sigma.

**Drift is larger than noise.** Across one 10-minute collect the Fz zero walked
0.115 N at 4 minutes and 0.172 N at 10, and 0.362 N by the post-run check —
ten times the noise. Frames carry drift-corrected labels, but the correction
interpolates between only three checks per run.

### Where the data lives

`data/<principle>/<date>_<pass>_<probe>/<sensor_id>/`, exactly one run per
(pass, sensor). Runs that are not the one to analyse — earlier attempts,
protocol variants, wrong-sensor mountings — are in
`data/_discarded/<principle>/<dataset>/<run>/`, one directory deeper so the
`data/*/*/state.json` and `data/*/*/*/state.json` globs the analysis uses do
not reach them. Nothing is deleted. Which attempt a kept run was is recorded
in its own `state.json` as `run_dir_was`.

An analysis result must not change when unused data is filed elsewhere. It did:
moving four runs that carried trusted image scales shifted the median scale
4.9 % and moved the dip of every unit without a scale of its own. The scale
scan now covers both trees and prefers kept runs over set-aside ones
explicitly, rather than taking whichever sorted first.

---

Written 2026-09-02, after the protocol was validated on `9DTact_hard_3mm_r1`,
`9DTact_soft_1mm_r1` and `9DTact_hard_1mm_r1`.

Everything below is executed by `scripts/run_one_sensor.py`, which runs the
steps in order and stops at the first one whose result fails its own check.
Nothing is positioned by hand once a run starts.

**Speed is 5 % with an override of 10 % throughout, and every MoveL is sent with
`blendR = -1`, which blocks until the point is reached.** A blending radius
would let the controller return before arriving, and the next step would then be
computed from a pose the robot had already left.

---

## Coordinates

| | |
|---|---|
| Tip position | tool 1, `[0.003, 0.322, 36.794, 0, 0, 0]` mm, centre of the printed sphere |
| Sensor plane | the ATI wrench origin, at `[38.096, 362.351, 12.317]` mm in the base frame |
| Sensor normal | `[-0.0069, 0.016, 0.9998]` — 1.0° off base +Z |
| Height | distance along that normal, above the sensor plane |
| Depth | distance below the gel surface, **always read back from the robot** |

Depth is never counted from the commands issued. Summing 39 commanded steps of
0.05 mm drifted 0.217 mm from where the robot actually went — 11 % — and made
the gel look 16 % stiffer than it is.

---

## Step 1 — `enable`  ·  no motion

`ResetAllError` → `Mode(0)` → `RobotEnable(1)` → `SetSpeed(5)`.

Auto mode, in that order. The jog GUI uses `Mode(1)` and works, which is the
manual path; protocol MoveL needs auto. **Any hand jogging drops the controller
back to manual**, so this runs at the start of every sensor.

## Step 2 — `liftoff`  ·  0 or 1 move

Reads the tip height and compares it against this sensor's last recorded gel
surface. If the clearance is under 1.0 mm, it lifts to clear + 2.0 mm.

Judged on **geometry, not force**. A run leaves the tip wherever its last step
put it, which after a force ladder is inside the gel; taring there defines the
contact load as zero, and every force check afterwards then passes by
construction. That happened once: the reference image was of a gel already
indented 0.13 mm and the fitted exponent came out 0.67 against Hertz's 1.5.

## Step 3 — `align`  ·  1 move

One MoveL that puts the tip on the sensor axis with the probe normal to the gel,
**at unchanged height**. MoveL travels a straight line, so with both endpoints at
the same distance along the normal, no point between them is any closer to the
gel — the alignment cannot dip into it however far it travels sideways.

Typical travel 0.03–3.8 mm. Joint ceiling 15°, which is the *positioning*
ceiling; probe steps use 1°.

**Then it is verified**: radial offset ≤ 0.05 mm and tilt ≤ 0.10°, or the run
stops. Achieved values have been 0.005–0.023 mm and 0.002–0.022°.

## Steps 4–6 — `newrun`, `tare`, `reference`  ·  no motion

Open a run directory, zero the F/T over 2 s, capture the unloaded gel image.

The reference is retaken per run, never borrowed: subtracting it is what makes
contact visible at all, and it only cancels the illumination pattern and
fixed-pattern noise if it was taken with the same settings on the same gel at
rest.

## Step 7 — `qc`  ·  no motion

Saturation and black clipping in the centre must be under 0.5 %; frame-to-frame
brightness scatter under 1.0.

Absolute brightness is recorded, **not failed on**. A window taken from one 3 mm
sensor reading 190 rejected a 1 mm one at 82 that had no clipping at either end
and the steadiest image of the set. Thickness and hardness change the optical
path; that is not a fault.

## Step 8 — `search`  ·  20–120 moves

Descends along the sensor normal looking for first contact.

```
0.2  mm steps while the force is at the noise floor
0.05 mm steps once |F| exceeds 0.05 N
stop when |F| exceeds 0.11 N on two consecutive readings
abort at 5 N, or after 60 mm of travel
```

0.11 N is five times the 0.022 N scatter this loop actually sees. It used to be
0.3 N, taken from a 0.057 N figure measured on single samples — but every
reading here averages a tenth of a second, so 0.3 N was fourteen sigma and the
tip was already 0.32 mm into the gel before contact was declared. On a 1 mm
elastomer that is a third of the depth budget spent on detection.

Observed: 20 steps from 3.5 mm up, 30 from 5.3 mm, 122 from 13.8 mm.

## Step 9 — `touchcheck`  ·  no motion

The search leaves the tip in contact. One frame is taken and compared to the
reference — but **only after the F/T confirms at least 0.08 N**. Asking only
whether pixels moved passed a frame taken at −0.01 N with the probe hanging two
millimetres above the gel; noise and drift alone move a few per cent of them.

## Step 10 — `characterize`  ·  1 + 7–22 moves

One move down to the estimated surface, then 0.1 mm steps until one of three
limits:

| Limit | Value |
|---|---|
| Depth | 0.7 mm (1 mm gel), 1.2 mm (2 mm), 2.2 mm (3 mm) |
| Force | **2.87 N** (was 5 N) — see *Current protocol at a glance* |
| Substrate stiffening | local force–depth exponent above 2.0 |

The exponent alarm needs **three things at once**: every force in its window
above 0.5 N, depth past 25 % of the elastomer thickness, and two consecutive
windows over the threshold. Without those gates it fired at 0.35 mm on a 3 mm
gel, fitting a log-log slope across forces of 0.06 to 0.37 N against a 0.02 N
noise floor.

The fit then places its own surface: `F = a·(d − d₀)^1.5` with `d₀` free.
Anchoring depth to the search's contact point plus a guessed margin was wrong by
up to 0.25 mm — two samples in one run read *negative* force where the axis said
they were 0.2 mm in.

Result is written to the registry: coefficient, exponent, corrected surface,
safe depth and force, and how many ladder rungs the sensor can reach.

## Step 10 (cont.) — image saturation: the maximum force the image can measure

`characterize` now takes a frame at every step and tracks **how much the image
differs from the unloaded reference** (mean |frame − reference| over the
central half, in grey levels) against force. The slope of that curve — grey
levels per newton, fitted over the last 3 steps spanning ≥ 0.08 N — is the
sensor's remaining image response. When it falls under **15 % of its own peak**
for 2 consecutive steps, at ≥ 0.3 N, the ramp stops there: past that force the
gel keeps carrying load but the picture no longer changes, so the force cannot
be read from the image, which is the only thing a VBTS reads. The force where
the slope first fell under threshold is written to the registry as
`image_response.max_measurable_force_N` and becomes the sensor's ceiling for
`collect`.

If the force limit is reached first, the record says "not reached"
and gives the slope at the stop as a fraction of the peak. Per-step frames and
numbers are in `characterize/`.

## Step 10b — `contactmap`  ·  2 + ~6 moves

Two probes every sensor gets identically, after `characterize`:

```
rise clear, re-zero, descend to the surface
press 0.5 mm in (geometric, from the recorded surface), settle 1 s, frame
back to the surface, 3 s recovery
seek 0.5 N (closed loop), settle 1 s, frame
back to the surface, rise 2 mm clear
```

Each frame is compared with the reference: pixels that differ by more than
**max(3, 4 % of the reference centre brightness)** grey levels after a 5 px blur
form the deformed region; its largest connected blob gives **area, equivalent
radius √(A/π), enclosing-circle radius and centroid — in pixels** (no
mm-per-pixel calibration exists for the camera; add `calibration.mm_per_px`
to `camera_config.yaml` and the mm figures appear alongside). A sensor whose
limits do not reach 0.5 mm or 0.5 N is measured at its limit and the record
says so. Results: `contactmap/contactmap.yaml` (+ frame, diff, mask images),
`state.json: contact_map`, and `contact_map` on the registry entry.

## Step 11 — `collect`  ·  2 + (cycles × 30–400) moves

One phase replaces the two ladders. The camera runs for the whole of it and
**every frame is saved and labelled**, up to a fixed budget that is the same
for every sensor (`capture_policy.frames_per_sensor` in the registry, **1000**;
it was 3000 when this was written).

Rises 2 mm clear at the free speed, **re-zeroes**, descends at the free speed
to 0.3 mm above the surface and at the contact speed the rest of the way.

**Normal block** — until half the budget is on disk:

```
load    : from the surface, raise the force **0.1 N** per step until the
          collection ceiling (**2 N**, or lower if characterize found the image
          saturating or the substrate stiffening); one model-plus-feedback
          step per target, 0.15 s settle, no waiting to converge
unload  : lower the force 0.1 N per step until it is under 0.06 N, then land
          exactly on the surface
dwell   : 1 s at the surface, recorded — the gel is still recovering
repeat
```

A settled **anchor sample** is taken every 0.10 N on the way up, exactly as the
old ladder took one per rung, so `samples.csv`, the Hertz fit and the campaign
status are unchanged in meaning. A soft 1 mm gel needs ~25 steps and ~50 frames
per cycle and runs ~30 cycles; a hard 3 mm gel needs ~200 steps per cycle and
runs 3–4. **Both end with the same number of frames.**

The no-contact abort is travel-based: over 60 % of the 5 mm depth backstop
with the force still under 0.06 N is a probe in air. It is not step-based, because after
the first unload a 1 mm gel sat 0.15 mm lower for several seconds and three
small steps read 0.010 N with the gel right there.

Rises 2 mm clear for a **mid-run zero check**, then descends to the hold depth.

**Shear block** — until the budget is spent:

```
for each of +X, −X, −Y, +Y (sensor axes):
    re-seat the normal load to 60 % of the ceiling   (a converging seek)
    shear out in rungs of 0.2/0.4/0.6/0.8/1.0 × min(1.0 N, μ × measured load)
    anchor sample at each rung
    back to centre in three steps, recorded
repeat
```

The normal load is re-seated before **every** axis. In the ladder version it
was set once and fell 12 % on 3 mm gels and up to 40 % on 1 mm gels across the
four directions, so "shear at a held load" was not what was recorded.

Then unload to the surface, rise 2 mm clear, and take the **end zero check**.

The frame budget is split exactly: the recorder stops saving at the block's
share, the motion completes unrecorded, and the next block starts. Without
that, a 5 N sensor's last normal cycle would have eaten 400 frames of the
shear share and a 0.5 N sensor's would not.

## Steps 12–15 — `retract`, `zerocheck`, `summary`, `park`  ·  2 moves

Lift 5 mm, measure how far the F/T zero drifted across the run (about
0.0012 N·m per minute here), write `samples.csv` and `summary.yaml`, then
`park`: lift a further 60 mm (`--park-mm`) so the sensor can be swapped by
hand. Park runs after the data is written and retries at half height and then
10 mm if the planner refuses, so it can never cost a completed run.

---

## Move count per sensor

| Step | Moves |
|---|---|
| liftoff | 0–1 |
| align | 1 |
| search | 20–120 |
| characterize | 8–23 |
| contactmap | ~8 |
| park | 1 |
| collect | 300–1200 |
| retract | 1 |
| **Total** | **330–1350** |

Thin, soft sensors make many short cycles, stiff thick ones a few long ones;
the frame count is the same either way. Measured on a soft 1 mm gel at 5 fps:
300 frames in 96 s of `collect`, about 3.1 frames per second once zero checks,
re-seats and the unrecorded cycle tails are included. **A 1000-frame run is
about 16 min of `collect` plus 3 min for the other steps — roughly 19 min per
sensor, 17 h for 54.** At 15 fps (MJPG, see `camera_config.yaml`) the same
budget takes about a third of that.

Speeds: probe steps and anything ending on the gel run at **15 %**, rises and
retracts at **30 %** (measured 2026-09-04: a 2 mm free move 8.0 s at 5 %, 2.7 s
at 15 %, 1.4 s at 30 %; at 30 % a 0.05 mm step read back 0.111 mm before
settling, which is why contact stays at 15).

---

## Depth limit — removed 2026-09-04, reinstated the same day, offset 2026-09-07

> Superseded. The limit in force today is `(thickness_mm + 1.0) * 0.9` from the
> gel surface, binding in every phase — see *Current protocol at a glance*.
> The history below is why a blanket removal was wrong.


The per-thickness depth limits (0.7 / 1.2 / 2.2 mm for 1 / 2 / 3 mm gels) no
longer bind. A 9DTact soft 1 mm sensor was driven to 1, 2, 3, 5 and 8 N in
turn with the limit lifted: 5 N took 3 mm of TCP travel, the Hertz exponent
stayed 1.6–1.7 throughout, the image kept responding (core radius ∝ F^0.24, no
pixel clipping), and the image change at 0.5 N repeated to ±2.5 % across the
probes — no permanent set. Ramps now end at the force ceiling (5 N), at image
saturation, or at the substrate-stiffening alarm. A 5 mm backstop remains as
protection against a probe that never finds the gel.

## What stops a run

| Check | Where |
|---|---|
| Route leaves via the default gateway | every robot script |
| Manual mode, e-stop, safety stop, controller error, already running | before every move |
| Joint change over 1° for a probe step, 15° for a positioning move | every move |
| Active tool is not the indenter | before any contact |
| Probe tilt over 3° from the sensor normal | before contact |
| Alignment over 0.05 mm / 0.10° after aligning | wrapper |
| Reference taken with something touching | reference |
| Centre clipped, or brightness unsteady | qc |
| Image unchanged under a confirmed contact | touchcheck |
| Force under 0.06 N past 60 % of the depth budget | collect (normal) |
| Normal load under 40 % of the hold before shearing | collect (shear) |
| Force over the sensor's characterised ceiling | collect |
| Depth over the 5 mm backstop (the per-thickness limit was removed 2026-09-04) | collect |
| Camera or F/T thread reports an error | collect |
| Image change per newton under 15 % of its peak (2 steps, ≥ 0.3 N) | characterize — stops the ramp, sets the ceiling |

The joint-change ceiling is the one that matters most. Measured on this robot,
for one unchanged target pose: `config = -1` solves 0.000° from the current
joints, `config = 0` solves 219° away, `config = 3` solves 243°. Same point in
space, completely different arm postures — and with the probe above the sensor,
a 219° reconfiguration sweeps the arm through it. Every move is planned with
`config = -1` and refused if the joints would move further than a step should.
