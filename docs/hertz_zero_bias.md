# The sphere's fitted zero sits ~0.15 mm too deep

Measured 2026-09-06 across three probe passes over the same 9DTact units.

## What was measured

Each pass finds the gel surface independently: approach from clear air in
0.02 mm steps, fit the probe's contact law with the contact point d0 free, and
take base_height - d0 as the surface. Comparing the surface the SAME sensor
gives under different probes is then a direct test, because the surface itself
does not change between passes by more than re-seating moves it.

    comparison        n    mean (mm)      s.e.      t    positive
    cube4 - ball4    17      +0.155      0.029    5.3     15/17
      of which r1     8      +0.168      0.035    4.9      8/8
      of which r2     9      +0.143      0.048    3.0      7/9
    cyl4  - ball4    17      +0.131      0.024    5.5     15/17
    cyl4  - cube4     8      -0.015      0.023    0.7      3/8

The r1 and r2 halves are physically different units and were measured on
different days, and they agree within each other's error (+0.168 vs +0.143).
The bias is a property of the contact law, not of particular sensors.

## What it means

The two FLAT probes agree with each other to -0.015 +- 0.023 mm, which is
indistinguishable from zero. Both disagree with the SPHERE by +0.13 to
+0.17 mm, in the same direction, on every sensor.

Two conclusions follow, and they are independent:

1. **The probe tips really are coincident.** "Every probe ends at the same
   point" was a design intent that had never been measured; cyl4 against cube4
   confirms it to +-0.023 mm. If tip lengths differed, the two flat probes
   would differ too, and they do not.

2. **The Hertz fit places the surface too low.** For a sphere F ~ d^1.5, whose
   slope is zero at contact, so the first fraction of a millimetre raises
   almost no force and the fit cannot see where contact began. It puts d0
   deeper than it is. A flat punch has F ~ d^1.0, a finite slope at contact,
   and pins the same point far better -- which also explains the other three
   things measured that day: over 33 ball4 fits the median sigma(d0) was
   0.0267 mm against 0.0089 mm for cyl4, ball4's median R2 was 0.976 against
   0.99+ for the flat probes, and ball4 needed repeat approaches far more often.

## Consequence for the campaign

A ladder rung commanded at "surface - 0.1 mm" under ball4 is really about
0.26 mm into the gel, because the surface it counted from was 0.155 mm low.
Every ball4 and ball8 depth is therefore about 1.5 ladder rungs deeper than its
label. This matters for two of the four tests:

  * shape reconstruction, where ball4's depth axis must be compared against
    cube4's, cyl4's and star10's;
  * force estimation, which uses ball8 exclusively.

The correction is available per sensor: every unit has a flat-probe surface
from the cyl4 and/or cube4 pass measured to sigma ~0.01 mm. Correct the sphere
passes onto the flat-probe surface rather than applying a single constant.

Do NOT "fix" this by fitting the sphere data differently. The bias is in what
the sphere data can support, not in the fitting; the flat probes are simply the
better instrument for locating a surface.
