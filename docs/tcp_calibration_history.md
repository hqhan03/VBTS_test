# Indenter TCP calibration — history and current value

Three calibrations exist. **Run 2 and Run 3 measured the same physical indenter**
and agree to 0.160 mm, so together they are the current result. Run 1 measured a
different part and is kept for traceability, not for use.

**APPLIED 2026-08-31.** Tool register 1 holds `[0.003, 0.322, 36.794, 0, 0, 0]`
and is the active tool. Tool 0 is untouched at `[0,0,0,0,0,0]`.

The value was entered through the FAIRINO web UI, not over XML-RPC — see
"How it was applied" below, which matters if anyone tries to script this.

---

## Repeatability — Run 2 vs Run 3

Same indenter, never removed or re-seated between the two. Independent pose sets.

| | X | Y | Z |
|---|---:|---:|---:|
| Run 2 | −0.049 | 0.370 | 36.831 |
| Run 3 | 0.055 | 0.274 | 36.757 |
| Δ | +0.104 | −0.096 | −0.074 |

XY 0.142 mm, **3D 0.160 mm.** This is a true repeatability figure: the hardware
was identical, so the difference is procedure and seating alone.

Application candidates, none applied:

| | X | Y | Z | distance from CAD |
|---|---:|---:|---:|---:|
| A — Run 2 | −0.049 | 0.370 | 36.831 | 0.938 mm |
| B — Run 3 | 0.055 | 0.274 | 36.757 | 0.835 mm |
| C — mean | 0.003 | 0.322 | 36.794 | 0.885 mm |

---

## Run 3

| | |
|---|---|
| Date | 2026-08-31 |
| Data | `data/rig/tcp_calibration/20260831_130959/` |
| Purpose | same-indenter repeatability against Run 2 |
| **TCP (flange frame)** | **`[0.055, 0.274, 36.757]` mm** |
| Orientation | **not calibrated** — flange-aligned assumption |
| Poses | 8, all from `GetActualToolFlangePose` |
| rms / max residual | 0.147 / 0.226 mm |
| Condition number | 7.3 |
| Orientation spread | 63.0° max pairwise, 34.8° mean |
| Leave-one-out max shift | 0.098 mm |

---

## Run 2

| | |
|---|---|
| Date | 2026-08-31 |
| Data | `data/rig/tcp_calibration/20260831_125056/` |
| Indenter | monolithic Form 4 printed part, spherical tip printed as one piece |
| **TCP (flange frame)** | **`[-0.049, 0.370, 36.831]` mm** |
| Orientation | **not calibrated** — flange-aligned assumption |
| Poses | 8, all from `GetActualToolFlangePose` |
| rms / max residual | 0.143 / 0.238 mm |
| Condition number | 8.0 |
| Orientation spread | 53.8° max pairwise |

---

## Superseded — Run 1

| | |
|---|---|
| Date | 2026-08-26 |
| Data | `data/rig/tcp_calibration/20260826_234919/` |
| Indenter | printed body with a **Ø4 mm steel ball bonded on** with instant adhesive |
| TCP | `[0.127, 0.427, 36.847]` mm |
| rms | 0.454 mm, condition number 6.9 |
| **Status** | **OBSOLETE — measures a part that no longer exists** |

The ball detached during a later attempt, which is why the indenter was
redesigned as a single printed piece. Run 1's numbers are not wrong; they simply
describe different hardware.

---

## Obsolete constants

Both appear in older documents and in earlier revisions of
`scripts/prepare_tcp_calibration.py`. Neither is current.

| Value | Was | Now |
|---|---|---|
| CAD TCP z | `34.4` mm | `35.97` mm |
| Tip | Ø4 mm steel ball, adhesive-bonded | printed spherical tip, no ball, no adhesive |

They are retained in the script as `HISTORICAL_INDENTER` rather than deleted, so
that a reader who finds `34.4` in an old file can tell what it referred to.

---

## Why the runs agree

Run 2 vs Run 1 differ by 0.187 mm in 3D, but those runs used **different
indenters**, so that number bounds part difference and procedure repeatability
together and cannot separate them.

Run 3 vs Run 2 is the clean comparison: same part, never re-seated, independent
pose sets, 0.160 mm apart. That is the procedure's repeatability.

**All three runs land 0.79-0.86 mm above the CAD z**, and the spread among those
three offsets (0.074 mm) is smaller than any single run's rms residual. A random
error does not reproduce itself three times in the same direction at the same
magnitude. This is systematic and it is not measurement scatter.

It is specifically **not** explained by cone seating depth. In `R_i t + p_i = c`
the sphere-centre position `c` is solved for alongside `t`, so how deep the
sphere sits in the cone cancels out, provided it sits the same way each time.
Candidate causes, none investigated:

1. the printed part's actual flange-face-to-sphere-centre distance vs CAD
2. the FR5 flange frame origin vs the CAD mounting-face datum
3. printed spherical tip form error

Resolving this needs a direct measurement of the physical part, not another
calibration run.

---

## How it was applied — read this before scripting a tool write

**`SetToolList` over XML-RPC returns 0 and writes nothing on this firmware.**
It is not a missing method (that returns Fault -506); it reports success and has
no effect. All 16 registers were re-read immediately after and none had changed.

This was pinned down with a positive control: an obviously-fake `1.111 / 2.222 /
3.333` was entered from the web UI, and `GetToolCoordWithID(1)` returned it
exactly. So the read path is sound and the write API is the broken half.

`SetToolCoord` was never tried. It is documented as "set **and load**", so it
would also change the active tool; the web UI reached the same place without
needing it.

`scripts/apply_tcp_to_tool_register.py` still exists and its safety gates all
work — the route preflight genuinely stopped a write from going to the office
router when the robot's link dropped. What it cannot do on this firmware is make
the write take effect. Its read-back check is what caught that.

### The web UI activates on save

Saving a tool from the web UI sets it active. Active tool went 0 -> 1 without
being asked. Anyone editing a tool register there should expect that and check
`GetActualTCPNum` afterwards.

---

## Frame convention, confirmed on hardware

While the fake test value was loaded, the controller was checked against the
convention the calibration assumes:

```
p_TCP = p_flange + R_flange · t_tool          residual 0.002-0.003 mm
```

So tool offsets are applied in **flange coordinates**, and the controller's RPY
really is fixed-axis extrinsic with `R = Rz·Ry·Rx` — previously inferred from
SDK source, now measured. Runs 2 and 3 were solved on that convention, which
makes this a direct check on their validity.

The calibration data itself is unaffected by tool selection: every pose came
from `GetActualToolFlangePose`, which ignores the active tool.

---

## Caveats before this value is used

- **Orientation is undetermined and cannot be determined this way.** A sphere in
  a cone constrains position only. If a rotated tool frame is ever needed, the
  FR5 six-point method teaches axis directions separately.
- **CAD is not ground truth.** `[0, 0, 35.97]` is design intent, and is what the
  calibration was checked against — never a fallback value.
- **Not applied to the controller.** Writing a tool frame is a separate,
  deliberate act requiring explicit approval.
