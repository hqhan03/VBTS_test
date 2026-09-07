# ATI sensor frame → robot base transform

Measured 2026-08-31. Data: `data/frame_transform/20260831_205135/transform.yaml`

The sensor is bolted to the table and the robot base does not move, so this is a
constant — six numbers measured once, not a per-pose calculation.

---

## The transform

**Rotation, sensor → base**

```
  +0.866216  -0.499622  -0.006933
  +0.499667  +0.866070  +0.016019
  -0.001999  -0.017340  +0.999848
```

azimuth about vertical **+29.979°**, sensor z axis **1.000°** off vertical.
det = +1.00000000, orthonormality error 2.2e-16.

**Sensor origin, in base coordinates**

```
  t = [38.096, 362.351, 12.317] mm
```

This is the **wrench origin**. `FT29831.cal`'s `<BasicTransform>` Dz = 6.858 mm
is already folded into the calibration matrix, so `t` refers to the shifted
origin. **Do not apply that 6.858 mm again.**

**Using it**

```
F_base = R @ F_sensor
T_base = R @ T_sensor + cross(t, R @ F_sensor)
p_base = R @ r_sensor + t
r_sensor = R.T @ (p_base - t)
```

---

## Accuracy

| | |
|---|---|
| Presses in the fit | 4, spanning 73 mm |
| Condition number | 5.1 |
| Residual rms / max | 0.675 / 0.973 mm |
| Held-back press | 1.167 mm, **1.7×** the in-fit rms |
| Independent session agreement | 0.27° in azimuth, 1.34 mm in origin |

The held-back press was not used in the fit. Predicting it to within 1.7× the
fit's own scatter is what says the transform describes the rig rather than the
four presses it was built from.

**Practical accuracy: rotation good to a few tenths of a degree, origin to
about 1 mm.** Contact *location* on the sensor does not depend on `t` at all —
the torque gives it directly — so the 1 mm figure limits only statements that
convert between base positions and sensor positions.

---

## Method, and why not the one in `ft_robot_frame_integration.md` §5

That section proposes pressing along base +X, +Y, +Z and reading the force
direction. It needs a **compliant** contact. With no VBTS mounted, a sideways
push on the rigid holder measures normal force plus friction, and the friction
coefficient is unknown, so the measured direction is not the pushed direction.

What was done instead:

**1. Gravity fixes the sensor z axis, with no contact at all.** A 1.004 kg mass
on the holder loads the sensor along base −Z exactly. Its direction in the
sensor frame pins two of the rotation's three degrees of freedom. Measured
9.791 N against 9.846 N expected, −0.56 %.

**2. Vertical presses supply the rest.** The robot reports the contact point in
base coordinates through the calibrated TCP; the sensor reports the torque it
makes. Those are tied by

```
T = r × F,    r = R(ψ)ᵀ (p − t)
```

solved for the azimuth ψ and the origin t together.

**The full cross product is used, not a vertical-force approximation.** Every
real press carries some sideways force — 1 % to 35 % here. Dropping the `r_z·F_xy`
term at r_z ≈ 18 mm and 15 % lateral misplaces each contact by about 3 mm, which
is larger than the quantity being measured. Keeping the term is also what makes
`t`'s component along the sensor z axis observable at all; with a purely vertical
force it is not.

That last point drives the procedure: **the sideways force must point in
different directions across presses.** If it always leans the same way, moving
the origin up its own axis and moving it sideways produce the same torque and
cannot be separated. `live_force_monitor.py` shows the lateral direction and the
widest unsampled arc for exactly this reason.

---

## What went wrong first, and how it was caught

The first attempt gave a residual of 4.4 mm and put the sensor origin **85 mm
above** the contact points — impossible, since the holder sits on top of the
sensor.

Two causes, found in this order:

**Lateral force all in one direction.** The first four presses leaned between
−56° and −102°, a 46° spread. The origin's height was therefore not separable
from its lateral position. Fixed by deliberately loading sideways in chosen
directions rather than accepting whatever the surface slope produced.

**Zero drift.** The tare was 3.5 hours old by the time the presses were taken.
Re-checking it showed the zero had moved **0.057 N·m** in torque — 126 % of the
residual being chased. Correcting for it dropped the residual from 4.4 to
2.4 mm and flipped the contact points from −24…−16 mm to +10…+18 mm, i.e. from
impossible to physical.

Re-measuring with a fresh zero and a check between every press brought the
residual to 0.675 mm.

**The drift rate is about 0.0012 N·m per minute** shortly after taring, and it
is not linear over hours — 3.5 hours gave 0.057 N·m, far less than a linear
extrapolation. It behaves like thermal settling. Practically: a tare is good for
a few minutes, and zero checks must be interleaved.

### The lesson worth keeping

A constant-magnitude, direction-scattered residual that does not shrink with
more data is the signature of a **zero that moved between measurements**, not of
a geometric error — a geometric error scales with the force, and this did not
(residual was flat from 5 N to 17 N).

---

## What this does not give

**Nothing.** All six numbers are determined. The earlier note that `t`'s
component along the sensor z axis is unobservable applies only to a
purely-vertical-force treatment; using the real lateral force recovers it.

Two things still worth doing when the VBTS is mounted:

- **Re-verify against a compliant contact.** A soft contact allows clean lateral
  pushes along known base directions, which tests `R` a different way than the
  torque-based fit does.
- **Check `t` against the mount geometry** if a Mini45 drawing turns up. None is
  in the project; `calibration/` is empty.

---

## Reproducing

```bash
/usr/bin/python3 scripts/measure_sensor_base_transform.py --self-test
/usr/bin/python3 scripts/measure_sensor_base_transform.py --phase tare       # nothing touching
/usr/bin/python3 scripts/measure_sensor_base_transform.py --phase gravity    # mass on
/usr/bin/python3 scripts/measure_sensor_base_transform.py --phase press      # repeat, 5-6x
/usr/bin/python3 scripts/measure_sensor_base_transform.py --phase zerocheck  # between presses
/usr/bin/python3 scripts/measure_sensor_base_transform.py --phase solve
```

`live_force_monitor.py` gives the operator a live readout while jogging. The DAQ
takes one task at a time, so it must be stopped before a press can be recorded.

The robot is never commanded. Every pose is jogged by the operator and only read
back.
