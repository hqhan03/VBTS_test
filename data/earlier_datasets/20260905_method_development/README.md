# Method development, 2026-09-05 — NOT campaign data

These runs established the Pass A method and must not be pooled with it.

- `9DTact_medium_2mm_r1*` — the damaged unit, used deliberately as the shakedown
  target for brand-new code. It found five defects before any healthy gel was
  at risk: a failed search returning success, the wrong Python interpreter, the
  F/T tared while the probe sat in the gel, the zero phase pressing deeper than
  the ladder it supports, and two crashes on write.
- `9DTact_hard_1mm_r1` / `__2` — the first healthy sensor. `__2` is the same
  sensor and the same probe turned 180 deg in its holder: the reversal test that
  showed the contact asymmetry is the gel's (82 %) and not the probe's (18 %).
  These runs also produced the depth-zero repeatability (0.0062 mm, identical
  across both), the image scale, and the 2.94 deg gel plane tilt.

They were taken with three zero approaches and a 0.1 mm coarse step; the
campaign settled on two and 0.2 mm. Same phases, different settings, so the
numbers are comparable in kind but not interchangeable.
