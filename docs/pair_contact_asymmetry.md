# The two posts of a paired probe do not press equally, and the gel is why

Measured 2026-09-07 on 9DTact_soft_3mm_r1 with pair100, by turning the TOOL
180 degrees about the probe's own axis between two otherwise identical runs.
Nothing was re-seated: the sensor stayed in its holder and the probe stayed in
the tool, so the only thing that changed was which post sat on which side.

## What was seen

Across 153 measurement points the weaker post's darkening reached only
0.45-0.99 of the stronger one's, median 0.76. That is not noise, and it decides
verdicts: the resolution test judges the dip against the WEAKER peak, so a
lopsided contact fails a pair that a square one resolves.

Two causes were possible. The gel could sit tilted under the probe even after
the alignment (we align the tool to each unit's MEASURED gel plane, but that
plane is itself a fit). Or the probe's two printed posts could differ in
length. They are separable: rotate the probe 180 degrees and the gel's low
side stays where it is in the image, while a short post moves to the other
side.

    depth    left  right   weak side
    0 deg    2.09   2.70   left      ratio 0.77
             3.41   5.11   left            0.67
             5.37   7.01   left            0.77
    180 deg  1.32   2.41   left            0.55
             2.01   4.02   left            0.50
             4.08   6.18   left            0.66

The weak side did NOT move. Writing log(left/right) = S + P at 0 degrees and
S - P at 180 degrees, where S is fixed in the image and P follows the post:

    S (gel)    -0.440 +- 0.060   left reads 0.64x right
    P (probe)  +0.131 +- 0.029   1.14x

Both differ from zero (7.3 and 4.5 sigma), and the gel term is 3.4x the probe
term.

## What follows

The probe's contribution is real but small. An earlier worry -- that comparing
gaps was really comparing how evenly each of the four probes had been printed
-- was overstated and is withdrawn.

The residual gel tilt is what matters, and it survives our per-sensor
alignment, so it is the plane FIT that is imperfect, not the idea of aligning.
The two effects also partly cancelled before the rotation and reinforced after
it, which is why the ratio got worse at 180 degrees (0.77 -> 0.55): the short
post had been sitting on the gel's high side.

Symmetry is now recorded for every measurement point, so it can be used as a
covariate rather than left as an unmeasured confound. Note it is entangled with
gel thickness in this dataset -- the 2 mm units both resolve best and sit
squarest (mean symmetry 0.84, against 0.73 and 0.64) -- so a thickness effect
cannot be claimed from these data without controlling for it.

## A note on the method

The rotation was commanded as a Cartesian pose, letting inverse kinematics find
the joints. That was a mistake: on a large wrist turn the solver jumped branches,
first driving joint 6 into its limit and then, while recovering, throwing the arm
into an unrelated configuration 617 mm above the gel. Nothing was damaged --
every one of those moves was in free air -- but a rotation about the tool axis
should be commanded as a joint-6 move, where no branch choice exists.
