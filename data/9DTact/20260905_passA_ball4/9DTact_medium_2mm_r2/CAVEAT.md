# 9DTact_medium_2mm_r2 / ball4 — the SPHERE's zero is not usable here

Two independent ball4 runs (2026-09-06), one at --settle 0.30 and one at 0.15,
both produced contact-law fits the quality gate rejected:

    settle 0.15   a = 0.36, 0.46, 0.06   R2 = 0.892, 0.883, 0.795
    settle 0.30   a = 1.17, 0.16         R2 = 0.862, 0.901

The fitted stiffness varies seven-fold between approaches on one mounting. The
surface recorded here rests on the "every approach failed the gate; using them
all" fallback and is uncertain by roughly 0.2 mm, twice the ladder's first
rung. This sensor's ball4 depth axis is not reliable -- use the flat-probe
surface instead (cyl4 26.?, cube4 26.7699).

## The sensor is fine; the probe is the problem

    cyl4  (flat, punch)   a = 1.71, 1.91, 1.75, 1.68   R2 = 0.992-0.998
    cube4 (flat, punch)   a = 2.40                     R2 = 0.9973, sigma 0.0051 mm
    ball4 (sphere, Hertz) as above

BOTH flat probes give a pristine zero, cube4 in a single approach, and cube4's
image-scale measurement passed too. An earlier version of this note blamed a
local defect in the gel surface -- a sphere touching a small area would land on
it while a 4 mm flat face averaged over it. That explanation is WRONG and is
withdrawn: a real surface defect would disturb a flat probe as well, and
neither flat probe shows anything.

What is left is the probe's contact law. F ~ d^1.5 has zero slope at contact,
so a sphere carries almost no information about where contact began; see
docs/hertz_zero_bias.md, where the same effect shows up campaign-wide as a
systematic +0.15 mm offset between flat-probe and sphere surfaces. This unit is
an extreme case of that, not a separate fault. Why it is extreme here is not
known.

Note 9DTact_medium_2mm_r1, the same specification, was withdrawn from the
campaign for gel damage. That is a coincidence of specification, not evidence
about this unit -- nothing measured here suggests damage.
