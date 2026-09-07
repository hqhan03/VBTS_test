# ATI Mini45 → FR5 frame integration

Status as of 2026-08-26: **no transformation is defined, and none should be
written yet.** Every wrench this codebase produces is in `ATI_sensor_frame` and
stays there until the measurements below have been made.

This document records what the sensor frame currently means, what is missing
before it can be related to the robot, and the order in which to close the gap.

Generated companion data: `data/frame_analysis/frame_analysis.yaml`
(regenerate with `scripts/analyze_ft_robot_frame.py`).

---

## 1. Current ATI frame

### Definition

| | |
|---|---|
| Frame name | `ATI_sensor_frame` (`ati_calibration.SENSOR_FRAME`) |
| Force unit | N |
| Torque unit | N·m |
| Sensor | ATI Mini45 s/n FT29831, SI-145-5 (145 N / 5 N·m) |
| Calibration | `FT29831.cal`, native units N and N-m, `<UserAxis>` matrix |
| Origin | shifted from the mounting face by `<BasicTransform>` Dz = **6.858 mm** |

No scale factor, gain correction, or software compensation exists anywhere in
the chain. The calibration file is used exactly as ATI supplied it.

### Sign convention

Established by manual 6-axis excitation with a healthy sensor
(`data/manual_ft_excitation_final/20260826_091843`, Task 17):

| Axis | Positive direction | Evidence |
|---|---|---|
| **+Fx** | operator's **left** | +86.5 / +92.9 N over two passes |
| **+Fy** | operator's **back** (toward the operator) | +106.5 / +103.7 N |
| **+Fz** | **up**, away from the mounting surface — compression reads **negative** | vertical press gave −153.2 N |
| **+Tz** | **counter-clockwise** seen from above | +3.977 / +3.978 N·m |

The frame is **right-handed and self-consistent**. That was verified
independently of the sign table: a horizontal force applied at height *h* above
the origin must produce `Ty = h·Fx` and `Tx = −h·Fy`. Across eight lateral
pushes the implied *h* came out positive every time and clustered at
**9.6–14.3 mm**, from two different axis pairs. One physical contact height
explaining both pairs is what makes the result trustworthy.

### The problem with this convention

**"Left" and "back" are relative to where the operator happened to be
standing.** They are not durable references and cannot be used to build a
transform. The axis directions have to be re-expressed against something fixed
— the optical table's axes, or the robot base — before any of this is usable
for integration. This is the first thing the procedure below fixes.

---

## 2. Why this rig is not the usual case

The common arrangement bolts the F/T sensor to the robot flange, so the sensor
frame rides with the TCP and the transform of interest is sensor → flange → TCP,
changing with every robot pose.

Here the sensor is **stationary** and the robot moves against it:

```
VBTS  →  3D printed holder  →  ATI Mini45  →  mount  →  optical table
```

So the transform of interest is a **fixed rigid transform between the ATI
sensor frame and the robot BASE frame**. It does not change as the robot moves.

That makes it easier — six numbers, measured once — but it has a consequence
worth being explicit about: **the FR5's tool and workpiece coordinate registers
cannot help.** Those registers describe frames attached to the robot. A
table-mounted sensor is invisible to them. `GetToolCoordWithID`,
`GetActualTCPNum` and friends will never report anything about the ATI. The
sensor's pose has to be established by touching it with the robot, or by
measuring the mount mechanically.

---

## 3. Robot-side information available

From `config/robot_config.yaml` (read-only; not modified):

| | |
|---|---|
| Controller | FR5 at 192.168.58.2 |
| Tool register | `default_tool_id: 0` |
| Workpiece register | `default_user_frame_id: 0` |
| Units | mm, deg, deg |
| Pose convention | `[x, y, z, rx, ry, rz]`, **fixed-axis (extrinsic) RPY** |
| `operation_mode` | `null` — still unverified on hardware |
| TCP calibration | **not performed** |

Same pose convention as the F/T side uses for its own reporting, so no unit or
angle-convention conversion is needed once the frames are related.

What the robot can report during a read-only connection:

| API | Returns |
|---|---|
| `GetActualTCPPose` | TCP pose in the robot base frame |
| `GetActualToolFlangePose` | flange pose in the robot base frame |
| `GetActualTCPNum` / `GetActualWObjNum` | which register is active |
| `GetToolCoordWithID` | a stored tool frame, relative to the flange |
| `GetForwardKin` / `GetInverseKin` | joint ↔ Cartesian, both base-frame |

Note also that the FR5's 20004 real-time stream carries `toolCoord` and
`wobjCoord`, but `fr5_io.RealtimeState` currently parses only as far as the
safety block. Reading them would need the nested struct sizes that sit between.
They describe robot-attached frames, so this does not block the work here.

---

## 4. What a transform requires

```
W_base = [ R       0 ]  W_sensor
         [ [t]× R  R ]
```

Forces rotate. Torques rotate **and** pick up `t × F` from the origin shift.

| Quantity | Meaning | DOF | Status |
|---|---|---|---|
| `R` | rotation, ATI sensor frame → robot base frame | 3 | **UNKNOWN** |
| `t` | ATI sensor origin, in robot base coordinates | 3 | **UNKNOWN** |

Both are constant, since the sensor is bolted to the table and the robot base
does not move.

**Note the asymmetry.** Expressing *forces* in the base frame needs only `R`.
Torques, and any statement about *where* on the sensor contact occurred,
additionally need `t`. If an early experiment only needs contact force
magnitude and direction, `R` alone is enough and `t` can wait.

### Known

- The ATI wrench is a right-handed, self-consistent 6-axis frame.
- Every axis sign, relative to the operator's position.
- Units are N and N·m throughout; no scale factor anywhere.
- The sensor is rigidly fixed to the table, so `R` and `t` are constants.

### Missing

- **`R`** — orientation of the sensor frame with respect to the robot base.
- **`t`** — position of the sensor origin in robot base coordinates.
- **Where the wrench origin physically sits.** `<BasicTransform>` already moved
  it 6.858 mm along z from the mounting face, so a mechanically measured
  translation must account for that or `t` will be wrong by that amount.
- ~~**A calibrated robot TCP.**~~ **RESOLVED 2026-08-31.** The indenter is now a
  monolithic printed part and its TCP has been calibrated to
  `[-0.049, 0.370, 36.831]` mm in the flange frame (`docs/tcp_calibration_history.md`).
  Not yet written to the controller. The earlier steel-ball indenter is obsolete.
- **A durable reference for the axis directions.** Task 17 fixed them relative
  to the operator, not to the table or the robot.

---

## 5. Recommended procedure

### Step 1 — TCP calibration of the indenter

**DONE 2026-08-31** — see `docs/tcp_calibration_history.md`. Calibrated offline
by least squares from 8 manually taught poses, not by the controller's 4-point
routine, and not yet written to a tool register. The steel-ball indenter this
section was written for no longer exists.

The original plan, retained for reference:

- `SetTcp4RefPoint(1..4)` at four orientations about a fixed tip position
- `ComputeTcp4()` → tool frame, returned as `[x, y, z, rx, ry, rz]`
- `SetToolCoord(id, coord, ...)` to store it

Until this exists there is no robot-side reference, so every later step is
blocked on it. Confirmed present in the installed SDK (`robot.h:863, 870, 883`).

### Step 2 — Establish `R` by axis-aligned probing

With the sensor tared and the VBTS in place, press the indenter onto the sensor
along the robot base **+X**, then **+Y**, then **+Z**, one direction at a time,
recording the F/T reading for each.

Each push gives a measured force direction in the sensor frame for a known
direction in the base frame. Three independent directions determine `R`.

Do this properly rather than reading off signs:

- collect the three measured unit vectors into a matrix,
- **orthonormalise** it (SVD, nearest orthogonal matrix),
- **report the residual** — how far the raw measurement was from a valid
  rotation. That residual is the honest error bar on the whole transform, and
  it will also catch a mistake such as a mis-set axis or an unnoticed friction
  component.

Task 17 measured 0.6–3.6° of direction repeatability by hand, so a robot-driven
version should do considerably better. If the residual is large, something is
wrong — do not orthonormalise it away and move on.

### Step 3 — Establish `t`

Either:

- **Probe** — move the TCP to several points whose position is known in the
  sensor frame (mount holes, holder features) and read `GetActualTCPPose` for
  each, or
- **Measure** — take the mount geometry mechanically.

Either way, subtract the 6.858 mm `<BasicTransform>` offset so `t` refers to the
actual wrench origin and not to the mounting face.

### Step 4 — Verify against a load the transform never saw

Push along a direction **not** used to fit `R`, and check that the transformed
force points where the robot thinks it pushed.

Fitting three directions and then testing on a fourth is what separates a real
calibration from a tautology. Skipping this step means the transform is only
guaranteed to reproduce the data it was fitted to.

---

## 6. Constraints for whoever implements this

- `FT29831.cal`, `ati_calibration.py` and the wrench conversion logic are not to
  be modified. A transform belongs in a **new** module that consumes
  `ATI_sensor_frame` output; it does not belong inside the calibration path.
- No software gain, scale factor, or compensation. If a transform disagrees with
  a measurement, the transform or the wiring is wrong — not the calibration.
- Wrench data written to disk should keep carrying its `frame` field. Once a
  transform exists there will be two frames in play, and a stored measurement
  that does not say which one it is in is not recoverable later.
- `all_channels_healthy` and `channel_mapping_confirmed` in `ft_config.yaml`
  are separate flags on purpose. A confirmed mapping does not mean every mapped
  channel carries a signal; conflating them is what let a dead SG5 produce
  authoritative-looking forces for five tasks.

---

## 7. Current usability

| Use case | Ready? |
|---|---|
| Contact force magnitude in the sensor frame | **Yes** |
| Contact detection against the noise floor (σ_Fz ≈ 57 mN) | **Yes** |
| Force direction in the sensor frame | **Yes** |
| Force expressed in robot base coordinates | No — needs `R` |
| Contact location on the sensor surface | No — needs `R` and `t` |
| Anything referencing the robot TCP | No — needs TCP calibration first |
