# Elastomer Thickness, Hardness, and Pixel Density in Vision-Based Tactile Sensors: Contact Response and Task-Dependent Sampling Requirements

> Draft for ICRA 2027 (IEEE conference template `template/ieeeconf_letter.doc`, US-letter, two-column; limit 6 + 2 pages including references).
> Paragraph tags in brackets (`[ABS]`, `[I-1]`, …) pair each paragraph with the same paragraph in `paper_draft_kr.md`. Do not delete or renumber them.
> `[AUTHOR CHECK: …]` marks a place the authors must confirm before submission; all are collected under *Open items* at the end.
> Every number in this text comes from `result/results_single_sensor.md`, `result/single/**/*.csv`, `paper/figures/*.csv`, or `docs/*.md`. All results use the 27 gel units of the campaign, one specimen per condition (Section III-B).

**Authors:** [AUTHOR CHECK: author list and affiliations]

---

## Abstract

[ABS] Vision-based tactile sensors deliver high-resolution contact information, but the elastomer and the pixel density are fixed early in a design and set the data volume the camera, electronics, and network carry. We report a controlled comparison of how elastomer thickness and hardness appear in the contact image, in force and shape estimation accuracy, and in the pixel density each task requires. Three configurations (depth-referenced, photometric, and photometric with markers) received gels at three Shore OO hardness levels and three thicknesses (1, 2, 3 mm), measured with one robot and one protocol. We measured imprint growth, two-contact separation, and image saturation, and evaluated force and shape estimation at twelve pixel densities (about 10^4 to 0.1 px/mm^2) by area-averaging the same 1920 × 1080 frames. At equal indentation, thickness changed the imprint (up to 1.3× larger for thinner gels) and hardness did not; at equal force, hardness separated the brightness response of the depth-referenced design almost twofold while the thickness separation of imprint diameter collapsed. Two-contact separation in the depth-referenced design followed thickness (1.10 to 2.50 mm spacing); every photometric specimen separated the narrowest pair tested. The depth at which the image saturated followed thickness in both configurations measured, but the force at that depth rose with thickness in one and fell in the other. Neither estimation accuracy (after multiple-comparison correction) nor the pixel density at which error reached a 10 % plateau tracked thickness or hardness. The plateau density did track the task and the tolerance: medians ranged from 2 px/mm^2 (cylinder depth) to 83 px/mm^2 (cube depth), with force at 6 to 72 px/mm^2, and moving the tolerance from 5 % to 20 % shifted them by up to an order of magnitude. Gel choice should follow the contact regime and force range, pixel density the task and tolerance, both verified on the designer's own pipeline.

[AUTHOR CHECK: abstract is 1,998 characters with spaces (309 words), inside the 2,000-character target. The first paragraph of the Introduction re-expands the VBTS acronym.]

---

## I. INTRODUCTION

[I-1] Vision-based tactile sensors (VBTS) image the deformation of an elastomer with a camera and recover contact geometry and force from the image [1]–[3]. The approach yields far more spatial information than a discrete taxel array, but that information has a cost: every sensor is a video stream, and as robot hands acquire more fingertips the bandwidth, storage, and inference load scale with the number of sensors and with the pixels each one produces. Two design decisions fix that load before any learning is done. The gel (its thickness, hardness, and layer structure) determines what a contact looks like, and the pixel density of the imaging path determines how finely that appearance is sampled. Both are chosen at the start of a design, and both constrain the camera module, the electronics, and the network downstream.

[I-2] Many VBTS designs have been reported, and several have been characterised individually. Yet experimental evidence that varies the gel systematically while also measuring how much image each estimation task needs is scarce. Prior work has linked thickness and hardness separately to spatial resolution and to measurement range [4]–[6], and a few studies have reported the input resolution at which one sensor and one task saturate [7], [8]. What is missing is a comparison in which thickness, hardness, and pixel density are varied together, on the same hardware and protocol, so that a designer can see which of them a given specification actually depends on.

[I-3] This paper reports such a comparison. We built three sensor configurations, each with gels at three hardness levels and three thicknesses, and measured every specimen with one robot, one force/torque sensor, and one protocol. For each specimen we characterised the physical contact response (imprint growth, two-contact separation, and image-response saturation) and evaluated force and shape estimation at twelve pixel densities obtained by down-scaling the same frames. Our aim is not a universal design table. It is to show, with measured trends, which parameters a designer must check under which conditions, and to make explicit how strongly each answer depends on the task, the tolerance, and the processing pipeline.

[I-4] The three configurations cover the two imaging principles that dominate current intensity-based VBTS. Depth-referenced sensors such as 9DTact [3] read the transmittance of a pigmented layer, so brightness maps to indentation depth directly; photometric sensors such as DIGIT [2] read surface shading under directional colour illumination, as in GelSight [1]. Both use one camera and no moving parts, and both are compact enough for fingertips, which is why we compare them rather than binocular or event-based designs. Because markers are the most common addition to a photometric gel, we included a marker variant on the same body and optics to see what changes when the same sensor is fitted with a marked gel.

[I-5] The contributions are (i) a 3 × 3 × 3 measurement campaign (configuration × hardness × thickness) with a shared protocol and open data tables; (ii) a characterisation of how thickness and hardness appear in imprint growth, two-contact separation, and image saturation; (iii) force- and shape-estimation error curves over twelve pixel densities, with the density at which each task plateaus reported for three tolerances; and (iv) an account of what this design could and could not resolve, so that the trends can serve as a starting point for design guidelines rather than as the guidelines themselves.

---

## II. RELATED WORK

### A. Gel Design and Physical Properties

[II-A1] The relationship between gel mechanics and sensor behaviour has mostly been described one parameter at a time. GelSlim [4] motivated a thin, stiff gel by arguing that spatial resolution improves as gel compliance decreases. Halwani et al. [5] studied a multi-layered gel parametrically and associated stiffness with measurement range, in simulation. TacEva [6] evaluated four commercial sensors and associated thicker gels with lower spatial resolution, but thickness and hardness there were properties of the devices, not variables under control. Simulation studies of VBTS optics [9] and learning-based designs [10] treat the gel as a fixed input. What is known, therefore, is a set of directional tendencies for thickness, hardness, and support structure, each established on a different sensor and rarely with the other two held fixed.

### B. Image Reduction and Task-Specific Performance

[II-B1] Several groups have asked how much image a tactile task needs. Minsight [7] reported that three-axis force and contact-position estimation saturated at 82 × 60 pixels (about 1.7 px/mm) for one gel. Shepherd et al. [8] found that texture classification with a TacTip saturated at 25 % of the original image. Learning-based force estimators [11] and self-supervised tactile representations [12] commonly resize inputs to 224 × 224 by convention rather than by measurement. These results establish that large reductions are often possible, but each is one sensor, one gel, and one task, so the reader cannot tell whether the reported saturation would move with the gel.

### C. Question Addressed Here

[II-C1] We combine the two lines. With the gel varied systematically on three configurations, we ask how thickness and hardness appear in the physical contact response and, on the same specimens, how much pixel density each estimation task requires. Because the comparison is within one campaign, the gel dependence (or independence) of the sampling requirement can be observed directly rather than inferred across papers.

---

## III. METHODS

### A. Sensor Hardware

[III-A1] Two imaging principles were implemented in two sensor bodies, each with a replaceable gel module (Fig. 1a). The depth-referenced body follows 9DTact [3]: white light enters from below through a transparent base layer, and a translucent layer under a black opaque skin transmits more light where it is compressed, so pixel brightness increases with local indentation depth. The photometric body follows DIGIT [2]: three colour LEDs illuminate a white reflective skin from the sides, and the shading of the deformed surface encodes its gradient, which is integrated to a height map. The marker variant uses the photometric body and optics unchanged and differs only in the gel, which carries a printed dot grid below the reflective layer. Within a family, therefore, every unit is the same body with only the gel exchanged, and a within-family comparison is a gel comparison.

[III-A2] Layer stacks, from the camera outward, were: depth-referenced, 2 mm acrylic window, 4.5 mm transparent silicone (Smooth-On Solaris), the translucent sensing layer whose thickness was varied (1, 2, or 3 mm), and a 0.5 mm black skin; photometric, 3 mm acrylic window, the transparent gel whose thickness was varied (1, 2, or 3 mm), and a sprayed white reflective skin. "Thickness" throughout this paper refers to the varied layer only. The depth-referenced stack has a 4.5 mm compliant base under the varied layer, whereas the photometric gel rests directly on acrylic; this difference matters for the saturation results in Section IV-C. [AUTHOR CHECK: the layer thicknesses and skin materials are from the authors' design record and are not in the repository configs; the depth safety backstop in the software assumes the black skin adds about 1.0 mm, not 0.5 mm.]

[III-A3] The same camera module (Sincerefirst SF-YL0320-V1 with a D140 lens) was used in both bodies, streaming 1920 × 1080 uncompressed YUYV frames at a measured 4.9 fps. Exposure, white balance, and gamma were fixed manually and held constant within each family: exposure 205 ms on the depth-referenced body and 60 ms on the photometric body, whose side illumination is brighter; white balance 4600 K; gamma and contrast at driver defaults. With these settings the frame-to-frame brightness scatter fell from 20.4 to 0.09 grey levels. Field of view was measured per unit by a lateral displacement calibration; medians were 21.9 × 13.4 mm for the depth-referenced body and 18.5 × 10.5 mm for the photometric body, giving full-frame pixel densities of about 7.8 × 10^3, 1.04 × 10^4, and 1.29 × 10^4 px/mm^2 for the depth-referenced, photometric, and marker configurations. Gel thickness changes the distance from camera to surface and hence the magnification (pixels per millimetre correlated with thickness at ρ = −0.81 to −0.94 across units), so the mechanical and optical effects of thickness are not separated by this design; all image sizes are reported in pixels of the unit's own frame, and densities are computed per unit. [AUTHOR CHECK: camera model name; the config files name the board YJX-YL0320-2740. Exposure values: one analysis note lists 205 ms for all units, the camera configs list 60 ms for the photometric body.]

### B. Elastomer Specimens

[III-B1] Gel modules were cast for a full factorial of 3 configurations × 3 hardness levels × 3 thicknesses, 27 units in total, one per condition (Table I). Hardness was set by formulation and measured on the cured material in Shore OO. The two families do not share a hardness scale. The depth-referenced gels span OO-30 to OO-70 across two product lines (Ecoflex and Dragon Skin); the photometric gels are one Solaris formulation with a plasticiser (Slacker) ratio of 4, 2, and 1, and span only OO-51 to OO-57. The 40-point range of the first family is 6.7 times the 6-point range of the second, so every hardness result below must be read within a family, and for the photometric family within that narrow range. Marker gels are cast from the same formulations as the plain photometric gels but were measurably stiffer under a sphere (Hertz stiffness ratio 1.64, higher in 12 of 13 pairs matched by formulation and thickness); the marker variant is therefore a different gel as well as a different image.

**TABLE I. Formulations of the sensing layer (mass ratios) and measured Shore OO hardness.**

| Configuration | Grade | Shore OO | Formulation |
|---|---|---|---|
| Depth-referenced | soft | 30 | Ecoflex 00-30, A : B = 1 : 1 |
| Depth-referenced | medium | 50 | Ecoflex 00-50, A : B = 1 : 1 |
| Depth-referenced | hard | 70 | Dragon Skin 20 : Dragon Skin 30 = 1 : 0.8 (each A : B = 1 : 1) |
| Photometric, marker | soft | 51 | Solaris A : B : Slacker = 1 : 1 : 4 |
| Photometric, marker | medium | 54 | Solaris A : B : Slacker = 1 : 1 : 2 |
| Photometric, marker | hard | 57 | Solaris A : B : Slacker = 1 : 1 : 1 |

Skins: depth-referenced black skin, Ecoflex 00-10 with black pigment, 0.5 mm; photometric white skin, Ecoflex 00-10 with white pigment and NOVOCS Matte, airbrushed. Marker gels carry a dot grid (dot diameter 1.0 mm, pitch 2.5 mm, both measured on the part) printed on water-transfer paper and placed 0.5 mm below the reflective layer.

[III-B4] Not every measurement was made on every configuration (Table II). Imprint growth and image saturation are reported for the two configurations indented with the ⌀8 mm sphere; two-contact separation was not measured on the marker configuration; and shape reconstruction was not attempted on it, because the dots occlude the shading the photometric method depends on. The learned force estimator used the input representation native to each configuration: three channels (reference, brightening, darkening) for the depth-referenced sensor as in [3]; the raw colour frame for the photometric sensor; and the colour frame with the marker dots removed by inpainting for the marker variant. The marker comparison in Section V-A is therefore a comparison of the marked sensor processed by inpainting against the unmarked one, not a test of the information carried by the dots.

**TABLE II. Measurements made per configuration (one specimen per condition).**

| Measurement | Probe | Depth-referenced | Photometric | Photometric + marker |
|---|---|---|---|---|
| Imprint growth vs. depth and force (IV-A) | ⌀8 mm sphere | 9 | 9 | not measured |
| Two-contact separation (IV-B) | two ⌀1 mm posts | 9, six spacings | 9, two spacings | not measured |
| Image-response saturation (IV-C) | ⌀8 mm sphere | 9 | 9 | not measured |
| Force estimation vs. pixel density (V-A) | ⌀8 mm sphere | 9 × 12 densities | 9 × 12 | 9 × 12 |
| Shape reconstruction vs. pixel density (V-B) | ⌀4 mm cylinder, 4 mm cube | 9 × 12 | 9 × 12 | not measured |

### C. Apparatus, Probes, and Protocol

[III-C1] Indentation was performed by a FAIRINO FR5 six-axis arm carrying the probe on an ATI Mini45 six-axis force/torque sensor (SI-145-5 calibration; Fx, Fy ±145 N, Fz ±290 N) read through a National Instruments PCIe-6343 at 2 kHz and logged as 20 ms averages. F/T noise at zero load was the same for all three configurations (standard deviation 0.015 N in Fz, 0.002 N laterally, on 20 ms averages); zero drift over a ten-minute run (up to 0.17 N) exceeded the noise and was removed by interpolating between three tare checks per run. Robot positioning was verified rather than taken from a datasheet: the alignment gate before contact required ≤ 0.05 mm radial and ≤ 0.10° tilt error (achieved 0.005–0.023 mm and 0.002–0.022°), the repeatability of a return to the contact origin was ±0.007 mm, and the run-to-run repeatability of the fitted gel surface was 0.029 mm. Remounting the same gel shifted the contact by 0.09 mm laterally and 0.07 mm in height, which is the floor for all unit-to-unit comparisons.

[III-C2] Four probe geometries were used (Table II): a ⌀8 mm sphere, a ⌀4 mm flat-ended cylinder, a 4 mm cube pressed on a face, and two-post probes made of two ⌀1.0 mm cylinders at edge gaps of 0.10, 0.25, 0.50, 0.75, 1.00, and 1.50 mm (centre spacings 1.10 to 2.50 mm). Each probe was fitted once and carried across all sensors before the next probe was fitted, because re-fitting introduces a contact asymmetry (0.09 mm) comparable to the effects under study. The gel plane and zero surface were re-measured after every gel change, and the probe was aligned to each unit's measured gel normal.

[III-C3] For every probe and unit the true gel surface was found by approaching in 0.02 mm steps to a depth of 0.30 mm and fitting a contact law to the force–depth record (Hertz F ∝ (d − d0)^1.5 for spheres, F ∝ (d − d0) for flat tips); the fitted zero d0 (σ ±0.003 mm for flat tips, ±0.014 mm for spheres) is the depth reference for that unit and probe. Shape data were collected on a depth ladder from 0.1 to 0.6 mm in 0.1 mm steps, three passes, retracting to air between rungs; two-post data on a ladder from 0.1 to 0.9 mm (0.6 mm for 1 mm gels), one frame per rung after settling. Force-estimation data were collected with the ⌀8 mm sphere in a continuous run of 1000 frames per unit: half in normal-force cycles from 0 to 2.0 N, ramped at about 0.15 N/s with a held sample every 0.1 N and a 1 s dwell at the surface between cycles, and half in shear glides of 0.8 to 1.05 mm in the four sensor axes under a 1.2 N normal preload re-seated before every direction, with a commanded shear target of 0.5 N (measured peak |Fxy| 0.52 to 0.94 N, set by friction). Every unit followed the same programme; the number of cycles needed to fill the budget varied from about five for the softest gels to about thirty for the stiffest. The saturation ramp (Section IV-C) was always the last measurement on a unit because it can damage the gel.

[III-C4] Camera frames were paired with the F/T stream by driver timestamp. The label of a frame is the mean of the F/T samples inside its exposure window (205 ms on the depth-referenced body, 60 ms on the photometric body); an ablation showed that this exposure-matched window gave the lowest error, that narrowing it to an instantaneous sample raised the normal-force error of the depth-referenced sensor by 1.48× (p = 0.007), and that widening it improved nothing; shear was insensitive to the window. The force moves during the exposure, and that motion, not F/T noise, sets the label floor: the second-difference label noise in Fz is 0.028 N, and the best learned Fz error is 1.8 times that value, so absolute accuracies in Section V are bounded by the labels and only comparisons between units are meaningful.

---

## IV. CONTACT RESPONSE

### A. Imprint Growth and Optical Response

[IV-A1] The first question is how thickness and hardness appear in the raw contact image. For each unit we tracked the imprint diameter (pixels) and the mean brightness change over the central half of the frame (grey levels) along the sphere ramp, and interpolated the three units of each thickness, or of each hardness, onto a common axis. Table III gives the spread of the group medians (largest divided by smallest) at one reference depth and one reference force per configuration. Two reference variables are needed because the robot commands depth while the F/T sensor reads force, and which gel variable separates the curves depends on which of the two is held fixed.

**TABLE III. Spread of group medians (max / min over the three levels) of imprint diameter and brightness response at a common depth and at a common force. ⌀8 mm sphere. Reference points are the upper end of the depth or force range common to all nine units.**

| Configuration | Reference | Diameter, by thickness | Diameter, by hardness | Brightness, by thickness | Brightness, by hardness |
|---|---|---|---|---|---|
| Depth-referenced | depth 1.08 mm | 1.33 (1 > 2 > 3 mm) | 1.11 | 1.28 | 1.30 (not ordered) |
| Depth-referenced | force 2.36 N | 1.01 | 1.10 | 1.68 (1 mm lowest) | 1.91 (soft > medium > hard) |
| Photometric | depth 0.75 mm | 1.34 (1 > 2 > 3 mm) | 1.10 | 1.67 (1 > 2 > 3 mm) | 1.26 |
| Photometric | force 5.62 N | 1.11 | 1.04 | 1.28 | 1.13 |

[IV-A2] At equal indentation depth, thickness separated the curves in both configurations and in the same direction: the thinner the gel, the larger and brighter the imprint (diameter spread 1.33 and 1.34×, monotonic in thickness). Hardness did not separate the diameter curves at equal depth (1.10 and 1.11×), and where the brightness curves did spread by hardness (1.30× in the depth-referenced configuration) the order was not monotonic. The physical reading is that at a fixed depth the proximity of the rigid substrate governs how far the deformation spreads laterally, so thickness dominates.

[IV-A3] At equal force the picture changes, and it changes differently in the two families. In the depth-referenced configuration the thickness separation of imprint diameter collapsed (1.01×) while hardness separated the brightness response almost twofold (1.91×, soft brightest), because a softer gel reaches a greater depth at the same force and its pigmented skin transmits more light. The brightness curves still spread by thickness at equal force (1.68×), but with the 1 mm gel lowest rather than in a monotonic order. In the photometric configuration, thickness separation weakened at equal force (diameter 1.11×) and hardness remained weak (1.04×). The weak hardness effect in the photometric family cannot be read as insensitivity, because the three grades differ by only 6 Shore OO points (Section III-B); in the depth-referenced family, where hardness spans 40 points, the effect at equal force is real and large.

[IV-A4] Two consequences follow for gel characterisation. First, "same load" is not one condition: a specification stated at fixed indentation and one stated at fixed force answer different questions, and thickness and hardness swap roles between them. Second, the unit-to-unit spread within a nominal condition is not small. The slope of imprint diameter against depth varied by up to 3× among units of the same nominal family, and this spread was not ordered by hardness; assembly, coating thickness, actual cured thickness, and adhesion were not controlled separately in this campaign, and any one of them could contribute.

### B. Paired-Contact Separation

[IV-B1] Two-contact separation was evaluated with the two-post probes on the depth ladder. From each difference image the brightness profile was taken along the major axis of the imprint pair (the principal axis of its second-moment matrix), averaged over a strip 0.8 mm wide and binned at 0.02 mm; the two peaks were located within ±0.35 mm of the expected post centres and the trough within ±0.20 mm of the midpoint. The dip was scored as Dip = (P − T)/P, where P is the height of the *weaker* of the two peaks above background and T the trough, so that an unequal pair is not credited with a dip it does not have. A rung of the ladder was called *resolved* only if three gates were passed: a signal gate (P ≥ 2.5 grey levels, about two standard deviations of the depth-zero uncertainty expressed in brightness), a noise gate (Dip ≥ 3 × the dip noise propagated from the profile noise), and the Rayleigh criterion (Dip ≥ 0.265, two Airy peaks at the Rayleigh spacing). A contrast criterion of Dip ≥ 0.667 (MTF ≥ 0.5) was also recorded but is not used for the tables. A unit was scored as resolving a spacing if any rung of the ladder passed all three gates; the depth range over which it passed is reported alongside.

**TABLE IV. Finest resolved centre spacing (mm) and resolved depth range (mm) at full resolution, depth-referenced configuration. All nine photometric specimens resolved the narrowest spacing tested (1.10 mm); 1 mm photometric gels resolved it to 0.6 mm depth and 2–3 mm gels to 0.9 mm.**

| Hardness | 1 mm | 2 mm | 3 mm |
|---|---|---|---|
| soft | 1.50 (0.2–0.6) | 1.75 (0.1–0.9) | 2.00 (0.3–0.3) |
| medium | 1.10 (0.1–0.6) | 1.10 (0.1–0.9) | 2.50 (0.5–0.9) |
| hard | 1.25 (0.1–0.6) | 1.25 (0.1–0.9) | 2.50 (0.4–0.9) |

[IV-B2] In the depth-referenced configuration the finest resolved spacing ranged from 1.10 to 2.50 mm and followed thickness: Spearman ρ = +0.75 (p = 0.021) for the finest spacing, −0.71 (p = 0.031) for the number of spacings resolved, and −0.74 (p = 0.023) for the best dip, with 3 mm gels resolving only the widest pairs. Hardness was not associated with any of the three (|ρ| ≤ 0.32, p ≥ 0.41). In the photometric configuration every specimen resolved the 1.10 mm pair (edge gap 0.10 mm) at full resolution, so the measurement gives an upper bound on the resolvable spacing rather than a value, and no thickness or hardness dependence can be claimed for that family. The only distinction among photometric gels was the depth range: 1 mm gels resolved the pair up to 0.6 mm indentation and thicker gels up to 0.9 mm, but 1 mm gels were also limited to 0.6 mm by the ladder, so this is not a resolution difference either.

[IV-B3] Three qualifications apply. First, separation has an optimal depth. For spacings up to 2.00 mm every resolved rung in the depth-referenced data lay at 0.1 to 0.3 mm indentation; deeper rungs darkened further but the trough between the posts disappeared, and no alternative analysis or lower threshold recovered it without also declaring "two contacts" on a single-post control. Only at 2.50 mm did separation persist through 0.9 mm. Two-point resolution should therefore be quoted with the depth at which it holds. Second, the verdict is sensitive to the gates: of the 120 rungs whose dip exceeded the Rayleigh value, 38 were rejected by the signal gate and one by the noise gate, and lowering the signal gate from 2.5 to 2.0 grey levels raised the number of specimens resolving 1.25 mm from four of nine to five of nine. The shallowest rungs, where the two imprints are most distinct, are also where the imprint is too faint to score. Third, the two posts did not load equally: the weaker post reached a median 0.76 of the stronger one's darkening, and a rotate-the-probe experiment attributed most of this to residual gel tilt rather than to the probe. Seating symmetry was best on the 2 mm units, which also resolved best, so the thickness trend above is entangled with seating in this dataset.

[IV-B4] To place two-contact separation on the same axis as the estimation tasks, the decision was repeated with the input frames area-averaged to the twelve widths of Section V, keeping the gates unchanged and scaling only the detector's morphological kernel. For the depth-referenced configuration and the 2.00 mm pair (27 rungs: 9 units × 3 depths), the outcomes fall into three classes, which must be kept apart: resolved; contact detected but not separated; and contact not detected at all. At full resolution (R ≈ 7.9 × 10^3 px/mm^2) 12 rungs were resolved and 15 were detected but not separated, 14 of those failing the signal gate: the dip itself was not shallower (0.38 against 0.47 at 426 px) but the per-pixel noise was five times higher (0.109 against 0.023) and the median imprint level (2.15) fell below the gate. The resolved count peaked at 19 of 27 (70 %) from 426 to 854 px (R ≈ 390 to 1600), and fell with density to 16 at 320 px (R ≈ 220), 11 at 80 px (R ≈ 14), 5 at 32 px (R ≈ 2.2), and 0 at 16 px, while detection failures rose from 0 at 426 px to 3 at 320 px, 12 at 80 px, 16 at 32 px, and all 27 at 8 px. Below R ≈ 200, therefore, "not resolved" is increasingly "not detected", and values there bound the failure rather than measure it. The full-resolution loss held for the 1.50 to 2.50 mm pairs and reversed for the two narrowest. We do not convert the density at which the resolved fraction peaks into a requirement comparable to the 10 % plateau of Section V, because the two are defined by different rules; what the sweep shows is that the two-contact decision uses pixels one to two orders of magnitude above the force and shape plateaus of the same camera, and that full resolution is not its best operating point. The photometric configuration behaved differently: its resolved count for the 1.10 mm pair fell monotonically with density with no full-resolution penalty (63 of 72 rungs at full frame, 39 at 80 px), and the rule still returned "resolved" for half the rungs at 16 px width. At that width one pixel spans about 1.2 mm, more than the post spacing, so we read those verdicts as behaviour of the detector on two- or three-pixel imprints and do not interpret them.

### C. Image-Response Saturation

[IV-C1] The maximum force a sensor can report is not the force the gel survives but the force at which the image stops changing. Each unit was driven in depth steps with the ⌀8 mm sphere while force and a frame were recorded at every step. The response is the slope of the mean absolute image change per newton over a three-step window; the maximum response is the median of the three highest windows; and saturation is declared when the response falls below 15 % of that maximum for two consecutive steps, the ceiling being the force at the first of the two. A 10 N floor prevented an early stop, and the depth and force safety limits were not the binding condition for the units reported here.

**TABLE V. Image-response ceiling (N) and the indentation depth at saturation (mm), ⌀8 mm sphere.**

| Configuration | Hardness | 1 mm | 2 mm | 3 mm | Depth at saturation |
|---|---|---|---|---|---|
| Depth-referenced | soft | 27.8 | 30.2 | 31.0 | 4.3 – 6.8 mm |
| | medium | 31.0 | 30.2 | 38.5 | (2.0 – 4.7 × thickness) |
| | hard | 27.5 | 43.3 | 63.2 | |
| Photometric | soft | 22.4 | 17.7 | 11.8 | 1.1 – 2.1 mm |
| | medium | 18.2 | 14.1 | 14.4 | (0.6 – 1.3 × thickness) |
| | hard | 19.5 | 22.4 | 11.8 | |

[IV-C2] Two observations are robust across the table. First, the depth at which the image saturates followed thickness in both configurations (ρ = +0.95 and +0.95; p ≤ 0.001) and did not follow hardness (|ρ| ≤ 0.05). Second, the force at that depth moved with thickness in opposite directions in the two families: the ceiling rose with thickness in the depth-referenced configuration (ρ = +0.63, p = 0.068; hard 27.5 → 43.3 → 63.2 N) and fell in the photometric one (ρ = −0.90, p = 0.001). Hardness was not associated with the ceiling in either configuration (ρ = +0.37 and +0.05; p ≥ 0.33), but in the depth-referenced family the hard-to-soft ceiling ratio grew with thickness, from 0.99 at 1 mm to 1.43 at 2 mm and 2.04 at 3 mm, so hardness and thickness act multiplicatively rather than additively there.

[IV-C3] These are descriptive trends and we do not fit a mechanism to them. One reading that is consistent with the depths in Table V is the following. The depth-referenced probe reaches 2 to 4.7 times the thickness of the varied layer before the image saturates; at declaration the local force–depth exponent was 2.1 to 2.5 (Hertz: 1.5), i.e. the probe has passed through that layer and is loading the compliant base and, through it, the substrate, so the mechanics of the whole stack enter the ceiling, and a thicker or harder layer carries more force before the pigmented skin stops changing. The photometric probe saturates at 0.6 to 1.3 times the thickness, while the gel is still within its own layer against a rigid acrylic window; there the optics saturate first, and a thicker gel, whose shading is more spread and less contrasted (Section IV-A), reaches that point at a lower force. Two things follow. Shore hardness, a static surface-indentation test on a thick block, does not by itself describe the effective indentation stiffness of a thin layer on a support, which rises with the ratio of contact radius to layer thickness [13], [14]. And the ceiling of the depth-referenced design can be adjusted by gel choice (27.5 to 63.2 N, 2.3×), whereas that of the photometric design cannot be ordered by hardness within the range tested. We predict, but have not tested, that a depth-referenced gel supported directly on acrylic would show the photometric thickness trend.

[IV-C4] The criterion is relative to each unit's own peak response, which makes the ceilings of weakly responding units come out higher; with a fixed absolute threshold the gap between the two families widens from 1.8× to 4.3 to 6.6×. We therefore use these values within a configuration only.

---

## V. ESTIMATION PERFORMANCE VERSUS PIXEL DENSITY

[V-0] We compared trends of estimation error with thickness and hardness, and then asked at what pixel density the error of each task reaches a plateau. Pixel density R is defined per unit as the total number of pixels at a given ladder rung divided by the area of gel surface that unit's camera sees, R = (s·k)^2 with s the unit's full-frame pixels per millimetre and k the down-scaling factor; it is the quantity that can be compared across units and configurations, whereas pixel width alone cannot. On accuracy, 9 of 40 uncorrected Spearman tests (Fz, shear, cylinder and cube depth; MAE and R^2; thickness and hardness; three configurations) were significant at p < 0.05, all nine on thickness, but none survived Benjamini–Hochberg correction [15] (smallest q = 0.185), and the direction differed between configurations (Fz MAE against thickness: ρ = +0.69 in the depth-referenced sensor, −0.74 in the photometric ones). On the plateau density, none of 20 tests approached significance (smallest q = 0.51). The two families of tests are separate and are not pooled.

### A. Force Estimation

[V-A1] Protocol and data are as in Section III-C: one ⌀8 mm sphere at the centre of the gel, 1000 frames per unit, normal cycles to 2.0 N and shear glides under a 1.2 N preload. Frames with Fz above 2 N (overshoot on the stiffest gels) were excluded, so the evaluated range is 0 to 2.1 N. The data were split by loading cycle, not by frame, so that neighbouring frames of one cycle never appear on both sides of the split: the last 30 % of normal cycles and the last 30 % of shear cycles in chronological order form validation and test (0.70 / 0.15 / 0.15), with at least 8 % of frames in test. Splitting the same data by random frames instead lowers the reported error by about 20 % on both channels, which measures the leakage a random split would hide.

[V-A2] A ResNet-18 [16] pretrained on ImageNet with a six-output head was trained per unit and per resolution with an L1 loss (sum reduction), Adam at 5 × 10^−4 with weight decay 10^−4 and linear decay, an effective batch of 64 held constant by gradient accumulation, 30 epochs, and the epoch chosen on the validation set. Three random seeds were run for widths up to 854 px and their median reported; the two highest rungs were trained with one seed. Input frames were area-averaged to twelve widths (1920, 1280, 854, 640, 426, 320, 160, 80, 48, 32, 16, and 8 px at 16 : 9), which spans R ≈ 7.8 × 10^3 to 0.14, 1.04 × 10^4 to 0.18, and 1.29 × 10^4 to 0.22 px/mm^2 for the three configurations. Area averaging was chosen because Fz is, to first order, an integral of the image, which this operation preserves; it also means that the ⌀8 mm sphere cannot by itself reveal a gel-dependent Fz saturation, because the sphere rather than the gel sets the imprint shape (contact radius varied 1.7× across all units and 1.2× across thickness). The reported metrics are the Fz MAE and the shear MAE, defined as (MAE_Fx + MAE_Fy)/2, both over the test frames. A constant-mean predictor scores about 0.28, 0.32, and 0.44 N in Fz on the three configurations. [AUTHOR CHECK: whether the Fz column of the axis-wise sweep is over all test frames or the normal block only; constant-mean baseline values (outline: 0.288 / 0.305 / 0.443 N; recomputed from the per-unit CSVs: 0.281 / 0.325 / 0.437 N).]

[V-A3] The plateau density of a unit is the lowest rung whose MAE lies within (1 + τ) of that unit's own minimum over the ladder. We use τ = 10 % as the reference because the argmin itself jumps between rungs on the flat part of the curve under seed noise, and we report τ = 5 % and 20 % alongside. The summary statistic is the median over units of the per-unit plateau density; the plateau of the median curve is a different number (given in Table VI for reference) and the two must not be mixed.

**TABLE VI. Force estimation (n = 9 per configuration): minimum MAE (median over units of each unit's best rung) and the pixel density R (px/mm^2) at which error enters the plateau, for three tolerances. Brackets give the pixel width of the median rung; the last column is the plateau of the median curve at τ = 10 %.**

| Configuration | Axis | Min. MAE (N) | R at τ = 5 % | R at τ = 10 % | R at τ = 20 % | Per-unit range at 10 % | Median-curve plateau |
|---|---|---|---|---|---|---|---|
| Depth-referenced | Fz | 0.042 | 218 [320] | 17.3 [80] | 13.6 [80] | 1.7 – 880 | 4.9 [48] |
| Depth-referenced | shear | 0.023 | 15.4 [80] | 5.9 [48] | 2.2 [32] | 1.9 – 45 | 4.9 [48] |
| Photometric | Fz | 0.055 | 17.4 [80] | 13.3 [80] | 2.9 [32] | 2.2 – 293 | 2.8 [32] |
| Photometric | shear | 0.027 | 85.8 [160] | 6.3 [48] | 2.9 [32] | 2.4 – 590 | 6.4 [48] |
| Photometric + marker | Fz | 0.077 | 27.0 [80] | 23.0 [80] | 8.3 [48] | 2.8 – 455 | 361 [320] |
| Photometric + marker | shear | 0.031 | 90.3 [160] | 71.7 [160] | 10.2 [48] | 16.5 – 5,900 | 22.6 [80] |

[V-A4] Fig. 2 shows the error curves, split once by thickness and once by hardness, and Table VI the summary. Four points stand out. (i) At τ = 10 % the markerless configurations plateau at R ≈ 13 to 17 px/mm^2 for Fz (80 px width) and R ≈ 6 px/mm^2 for shear (48 px width); at full resolution their median error is 20 to 35 % above the plateau minimum, i.e. the highest rungs over-fit. (ii) In neither split of Fig. 2 do the three group medians separate from the spread of the individual specimens: the plateau density is not associated with thickness or hardness in any of the six force rows (|ρ| ≤ 0.58, q ≥ 0.51). (iii) The requirement depends on the tolerance: tightening τ to 5 % moves the depth-referenced Fz plateau from 17 to 218 px/mm^2 and the photometric shear plateau from 6 to 86, whereas loosening it to 20 % brings almost every row to 2 to 14 px/mm^2; the ordering of normal and shear even reverses between tolerances. (iv) Per-unit plateau densities spread over two to three orders of magnitude within a configuration (Table VI, range column), far wider than any systematic separation between the thickness or hardness groups. A gel effect smaller than that spread could not have been detected with nine specimens per configuration; the null result is a statement about detection power, not a demonstration of independence.

[V-A5] The resultant-force error is often the quantity a user wants. Because the sweep stored only per-axis MAE, the exact expected vector error E‖F̂ − F‖ cannot be computed; by Jensen's inequality the quantity L = (MAE_x^2 + MAE_y^2 + MAE_z^2)^1/2 is a lower bound on it, with equality only if the three axes err together on every frame. That bound floors at 0.058, 0.073, and 0.095 N for the three configurations and reaches its 10 % plateau at R ≈ 14, 18, and 361 px/mm^2; Fz contributes 63 to 79 % of the sum of squares at every density, so the bound has the shape of the Fz curve. We report it only as a bound and do not read its plateau as that of the true vector error.

[V-A6] The marker variant, processed by inpainting, had the highest Fz floor (0.077 N against 0.042 and 0.055) and required the most pixels for shear (71.7 px/mm^2 at τ = 10 %, 160 px width). Its Fz floor is consistent with a smaller image response per newton: inside the contact, the brightness change at 2 N was 0.20 to 0.56 times that of the depth-referenced sensor, and the dots occlude 9 to 14 % of the contact. Its shear curve, however, has a different shape from the other two: 7 of the 9 marker specimens had lower shear error at 1920 px than at 80 px, against 1 of 9 depth-referenced and none of the 9 photometric specimens. The effect is small (median −0.0015 N, 4.5 % of the floor, below the seed spread of a single specimen), so it is the contrast between configurations, not the size, that is the finding. Because the input representations differ between configurations, this comparison cannot separate the marker information from the preprocessing; a within-sensor comparison of raw against inpainted marker frames would be needed for that.

### B. Shape Reconstruction

[V-B1] Shape data come from the depth ladder of Section III-C with the ⌀4 mm cylinder and the 4 mm cube at the gel centre, 0.1 to 0.6 mm in 0.1 mm steps (18 cylinder frames and 6 cube frames per unit). A sphere of known radius was pressed on the same ladder to calibrate the two reconstruction pipelines; those frames are not scored. [AUTHOR CHECK: the calibration sphere's diameter is omitted here; restore it if the Methods section must be reproducible.] The reference shape is the known probe geometry placed at the robot's fitted indentation depth (Section III-C): the ground-truth height map is the probe's end face at depth d below the fitted zero surface, and no independent surface scan was used. Because the reference is the rigid probe and not the deformed gel surface, the elastic sink-in around a flat punch counts as error for every method equally.

[V-B2] The depth-referenced sensor was reconstructed with a brightness-to-depth lookup table, calibrated per unit on the sphere ladder from the known sphere geometry and applied pixelwise as in [3], after resampling each frame through the unit's measured pixel-scale Jacobian and correcting the sphere ladder for the Hertz zero bias. The photometric sensor needed a different pipeline, built for this study: on a 5 × 3 grid of sphere contacts at 0.15 and 0.30 mm depth, together with the sphere ladder frames, the per-pixel true surface gradient is known from the sphere geometry, a small network mapping (colour difference, pixel position) to (g_x, g_y) is fitted per unit, and the gradient field is integrated by a Poisson solve with a discrete cosine transform. Both pipelines are calibrated on sphere frames disjoint from the scored cylinder and cube frames. The scored quantity is the imprint depth: for the depth-referenced sensor the median reconstructed depth within 1.0 mm of the imprint centre, for the photometric sensor the deepest reconstructed level after plane detrending, each compared with the robot depth and averaged over rungs (MAE, mm). The depth-referenced sensor also reports the equivalent diameter of the half-depth contour (recovered lateral size). All frames were area-averaged to the same twelve widths as in Section V-A, and R is defined as before. One caveat applies to the photometric family: within a unit the reconstructed depth tracked the true depth with correlation +0.98, but the slope of predicted against true depth varied from 0.16 to 0.92 between units (Fig. 3b), because the visible contact cap is shallower than the probe travel and the scale correction depends on the indenter shape. Photometric absolute depths are therefore unit-specific, and only the shape of the error-versus-density curve is compared across units.

**TABLE VII. Shape reconstruction: depth MAE on the plateau (median over units, range of the three thickness medians) and the pixel density at which error enters the 10 % plateau (median of per-unit values; brackets give the median rung width and the per-unit range).**

| Configuration | Probe | Plateau MAE (mm) | R at τ = 10 % (px/mm^2) | Per-unit range |
|---|---|---|---|---|
| Depth-referenced | ⌀4 mm cylinder | 0.064 – 0.072 | 5.5 [48] | 1.7 – 1,550 |
| Depth-referenced | 4 mm cube | 0.062 – 0.124 | 4.9 [48] | 2.2 – 7,830 |
| Photometric | ⌀4 mm cylinder | 0.042 – 0.084 | 2.2 [32] | 0.2 – 1,110 |
| Photometric | 4 mm cube | 0.030 – 0.096 | 83.2 [160] | 0.2 – 1,200 |

[V-B3] Depth error is flat over a wide range of density (Fig. 3c and the gel-split curves of Fig. 3e). The photometric cylinder MAE stayed within 0.043 to 0.058 mm from the full frame (R ≈ 1.06 × 10^4, 0.047 mm) down to 32 × 18 px (R ≈ 2.9, 0.058 mm) and only then rose (0.079 mm at 16 × 9, 0.130 mm at 8 × 5). The depth-referenced cylinder was flat at 0.061 to 0.072 mm from R ≈ 4.9 to R ≈ 900 with its minimum at R ≈ 390, rose to 0.117 mm at the full frame, and collapsed below R ≈ 2 (0.21 mm at 8 × 5). Three of the four task rows plateau between 2 and 6 px/mm^2; the photometric cube is the exception at 83 px/mm^2, and that spread of nearly forty times between two probes on one sensor is the strongest evidence in this study that the task, not the gel, sets the requirement. As in Section V-A, none of the four shape rows shows an association of plateau density with thickness or hardness (|ρ| ≤ 0.58, q ≥ 0.51), and the unit-to-unit spread of the plateau MAE (2.6× for the depth-referenced cylinder, 3.8× for the photometric one) exceeds the change produced by six rungs of down-scaling (1.9× and 1.1×). The depth-referenced lookup table degrades at the highest densities because it loses grey levels rather than pixels: correcting for the grey-level loss brings the full-frame error to 0.048 mm and flattens the curve.

[V-B4] The plateau density depends on the processing scale as much as on the sensor. Both pipelines originally applied filters of fixed pixel size (a 7 × 7 Gaussian in the depth-referenced pipeline, a 3 × 3 morphological opening in the photometric contact mask). Fixed in pixels, those filters grow relative to the imprint as the input shrinks; at 16 × 9 px the opening removed an 18-pixel imprint entirely and 74 % of frames predicted exactly zero depth. Scaling the kernels with the down-scaling factor changed nothing at 1920 px but moved the depth-referenced cylinder MAE at 48 px from 0.155 to 0.072 mm and at 80 px from 0.087 to 0.062 mm, and moved its median plateau density from R ≈ 55 to R ≈ 5.5, a factor of ten. Before that change both pipelines appeared to saturate at 80 × 45 px for unrelated reasons. A pixel-density requirement is therefore a statement about a pipeline, including its preprocessing scale, and not about the sensor alone.

[V-B5] Lateral size does not plateau the way depth does (Fig. 3d). For the depth-referenced sensor the recovered diameter of the ⌀4 mm cylinder stayed within ±0.1 mm of the true value from 32 px to the full frame (median 3.95 mm at 1920 px, 4.09 mm at 80 px, 4.06 mm at 32 px) and failed below 16 px, where the half-depth contour fills the frame; the 4 mm cube read large over the whole range (4.53 mm at 1920 px, 4.75 mm at 640 px, 4.40 mm at 80 px, 4.30 mm at 48 px). The over-size of the cube is the half-depth contour of a flat punch standing outside the true edge; its shrinkage at low density is blur pulling that contour inward, i.e. two errors partly cancelling rather than a better measurement. The recovered size also grew monotonically with thickness in the depth-referenced sensor (cylinder median +0.08, +0.27, +0.72 mm at 1, 2, 3 mm; cube +0.34, +0.54, +1.24 mm), which is the lateral spreading of contact by a thicker gel appearing in the reconstruction rather than a reconstruction error; the photometric sensor did not show a monotonic trend, so this is not read as a gel property.

---

## VI. LIMITATIONS AND FUTURE WORK

### A. Limitations of This Study

[VI-A1] *One specimen per condition.* Each cell of the design holds a single gel, so variation between nominally identical gels cannot be separated from the design factors. The cost is visible in the spread between the nine specimens of one configuration: plateau densities range over two to three orders of magnitude (Table VI) and plateau shape errors over 2.6× and 3.8× (Section V-B), both wider than any systematic difference between the thickness or hardness groups. The negative results on plateau density are therefore limits of detection rather than evidence of independence, and the positive trends (thickness in two-contact separation and in saturation depth) are the ones large enough to clear that spread.

[VI-A2] *Support condition.* The depth-referenced gel sits on a 4.5 mm compliant base and the photometric gel on acrylic. The opposite thickness trends of the ceiling in Section IV-C may be a support effect rather than an imaging-principle effect; the design does not separate the two.

[VI-A3] *Photometric separation limit not reached.* All photometric specimens resolved the narrowest pair (1.10 mm centre spacing). Their two-contact limit is below that and was not measured, so no thickness or hardness dependence can be stated for that family. The depth-referenced trend is also entangled with seating symmetry, which was best on the 2 mm units.

[VI-A4] *Ranges and configurations.* Hardness spans 40 Shore OO points in one family and 6 in the other; thickness spans 1 to 3 mm; only two imaging principles and one camera were used. The photometric hardness null results are indistinguishable from a range limitation. Hardness labels were verified on the cured material, but a flat-punch stiffness measurement did not order the photometric grades consistently, so "hardness" in that family should be read as a formulation label.

[VI-A5] *Down-scaled images are not low-resolution cameras.* Area-averaging a 1920 × 1080 frame preserves the integral and suppresses noise, whereas a low-resolution sensor has its own pixel size, noise, and optics. The plateau densities are those of this reduction, and Section IV-B shows one case where the full-resolution frame was the worse input for the decision rule used.

[VI-A6] *Pipeline dependence.* The plateau density moved tenfold when the preprocessing scale was corrected (Section V-B), the resultant-force error is available only as a lower bound, the two highest force rungs were trained with one seed, and the three configurations were trained on different input representations (three-channel, raw colour, inpainted), which limits direct comparison between them. Absolute force accuracies are bounded by the label floor set by force motion within the exposure window, and thickness changes magnification as well as mechanics.

### B. Directions for Verification

[VI-B1] The cheapest next experiment is to cast the depth-referenced gel on acrylic, as the photometric one is, and repeat the saturation ramp; this tests the support hypothesis of Section IV-C with one family re-made. Further steps, in order of cost: at least three specimens per condition to measure casting repeatability against design effects; an absolute saturation criterion (a fixed level-per-newton threshold normalised by each family's image noise) so that ceilings compare across families, reported with the fraction of ramps it truncates; narrower two-post probes and shallower ladder rungs to find the photometric separation floor; matched hardness ranges across families; a within-sensor comparison of raw against inpainted marker frames to isolate what the dots contribute; and per-axis label-noise estimates so that shear floors are bounded as Fz is now.

[VI-B2] For sensor builders, the campaign also identified factors beyond thickness and hardness that moved the numbers by amounts comparable to the design variables: assembly and coating, the actual cured thickness, adhesion to the window, seating tilt, and the scale of preprocessing filters. A gel described by its formulation alone is not reproducible to the level at which these trends were measured; we suggest reporting the imprint-diameter slope and the two-contact dip at a stated depth alongside the formulation, both of which can be measured in a few minutes with a single probe.

---

## VII. CONCLUSION

[VII-1] We evaluated three vision-based tactile sensor configurations, each with gels at three hardness levels and three thicknesses, at twelve pixel densities from the full 1920 × 1080 frame down to 8 × 5 pixels, with one robot and one protocol.

[VII-2] In the tested configurations, thickness changed how a contact appears: at equal indentation, thinner gels gave larger and brighter imprints in both configurations measured; two-contact separation followed thickness in the depth-referenced design (its photometric counterpart resolved every pair we could make); and the depth at which the image saturates followed thickness in both, while the force at that depth rose with thickness in one design and fell in the other. Hardness appeared where it was varied widely and the load was stated as force: in the depth-referenced design it separated the brightness response at equal force and scaled the saturation ceiling multiplicatively with thickness. Estimation accuracy and the pixel density at which estimation error plateaus showed no thickness or hardness association that survived correction, but the plateau density differed by task and by tolerance by more than an order of magnitude.

[VII-3] For design, this means that a gel should be chosen against the contact regime (fixed depth or fixed force) and the force range the application needs, and that pixel density should be chosen against the target task and the tolerance one is prepared to accept, with a check that the preprocessing scales with the image. The specific numbers reported here are statements about our criteria and our pipeline. We have shown which quantities move and by how much; a designer should measure them on their own sensor rather than adopt ours.

---

## ACKNOWLEDGMENT

[ACK] [AUTHOR CHECK: funding and acknowledgments.]

---

## REFERENCES

[1] W. Yuan, S. Dong, and E. H. Adelson, "GelSight: High-resolution robot tactile sensors for estimating geometry and force," *Sensors*, vol. 17, no. 12, p. 2762, 2017.

[2] M. Lambeta *et al.*, "DIGIT: A novel design for a low-cost compact high-resolution tactile sensor with application to in-hand manipulation," *IEEE Robot. Autom. Lett.*, vol. 5, no. 3, pp. 3838–3845, 2020.

[3] C. Lin, H. Zhang, J. Xu, L. Wu, and H. Xu, "9DTact: A compact vision-based tactile sensor for accurate 3D shape reconstruction and generalizable 6D force estimation," *IEEE Robot. Autom. Lett.*, vol. 9, no. 2, pp. 923–930, 2024.

[4] E. Donlon, S. Dong, M. Liu, J. Li, E. Adelson, and A. Rodriguez, "GelSlim: A high-resolution, compact, robust, and calibrated tactile-sensing finger," in *Proc. IEEE/RSJ Int. Conf. Intell. Robots Syst. (IROS)*, 2018, pp. 1927–1934.

[5] M. Halwani *et al.*, "Enhancing sensitivity and measurement range by multi-layered vision-based tactile sensor (ML-VBTS): A parametric study and comparative benchmarking," *Measurement*, 2025. [TO VERIFY: volume, article number]

[6] Q. Cong *et al.*, "TacEva: A performance evaluation framework for vision-based tactile sensors," *Adv. Intell. Syst.*, 2026. [TO VERIFY: volume, article number]

[7] I. Andrussow, H. Sun, K. J. Kuchenbecker, and G. Martius, "Minsight: A fingertip-sized vision-based tactile sensor for robotic manipulation," *Adv. Intell. Syst.*, vol. 5, no. 8, p. 2300042, 2023.

[8] D. R. Shepherd *et al.*, "Texture and friction classification: Optical TacTip vs. vibrational piezoelectric and accelerometer tactile sensors," *Sensors*, 2025. [TO VERIFY: volume, article number, author list]

[9] A. Agarwal, T. Man, and W. Yuan, "Simulation of vision-based tactile sensors using physics based rendering," in *Proc. IEEE Int. Conf. Robot. Autom. (ICRA)*, 2021, pp. 1–7.

[10] V. Kakani, X. Cui, M. Ma, and H. Kim, "Vision-based tactile sensor mechanism for the estimation of contact position and force distribution using deep learning," *Sensors*, vol. 21, no. 5, p. 1920, 2021. [TO VERIFY]

[11] A. Shahidzadeh *et al.*, "FeelAnyForce: Estimating contact force feedback from tactile sensation for vision-based tactile sensors," in *Proc. IEEE Int. Conf. Robot. Autom. (ICRA)*, 2025. [TO VERIFY]

[12] C. Higuera *et al.*, "Sparsh: Self-supervised touch representations for vision-based tactile sensing," in *Proc. Conf. Robot Learning (CoRL)*, 2024.

[13] K. L. Johnson, *Contact Mechanics*. Cambridge, U.K.: Cambridge Univ. Press, 1985.

[14] E. K. Dimitriadis, F. Horkay, J. Maresca, B. Chadwick, and R. S. Chadwick, "Determination of elastic moduli of thin layers of soft material using the atomic force microscope," *Biophys. J.*, vol. 82, no. 5, pp. 2798–2810, 2002.

[15] Y. Benjamini and Y. Hochberg, "Controlling the false discovery rate: A practical and powerful approach to multiple testing," *J. R. Stat. Soc. B*, vol. 57, no. 1, pp. 289–300, 1995.

[16] K. He, X. Zhang, S. Ren, and J. Sun, "Deep residual learning for image recognition," in *Proc. IEEE Conf. Comput. Vis. Pattern Recognit. (CVPR)*, 2016, pp. 770–778.

[17] B. Ward-Cherrier *et al.*, "The TacTip family: Soft optical tactile sensors with 3D-printed biomimetic morphologies," *Soft Robot.*, vol. 5, no. 2, pp. 216–227, 2018.

[18] [TO VERIFY: "FEATS" force-distribution estimation reference (arXiv 2411.03315) cited in the outline for the output-resolution convention; add with full citation or drop.]

[19] [TO VERIFY: "Krohn" reference listed in the outline under image reduction; add or drop.]

---

## FIGURE CAPTIONS

**Fig. 1.** Question and design. (a) Gel design: three hardness levels × three thicknesses, cast for two sensor bodies (depth-referenced, photometric) plus a marker variant of the photometric gel. (b) Two distinct contacts: the same hard gel, the same two-post probe (⌀1.0 mm posts, 2.00 mm centre spacing), the same 0.30 mm indentation, differing only in thickness (1 mm and 3 mm); display range and contrast scaling are shared. The profile across the two posts shows the dip that is scored, with the 2.5-level decision floor. (c) Task input resolution: one contact frame area-averaged to three pixel densities, and the force error of one specimen against pixel density R. Panels (b) and (c) are deliberately not connected by an arrow: their independence is not established by these data. (File: `figures/fig1_question_and_design.pdf`, single column.)

**Fig. 2.** Force-estimation error against pixel density R (px/mm^2). Rows: depth-referenced (9DTact-type), photometric (DIGIT-type), photometric with markers. Columns: Fz and shear ((MAE_Fx + MAE_Fy)/2). The left four panels split the same nine specimens by thickness and the right four by hardness; thin lines are the seed medians of individual specimens and are identical in both halves, thick lines are group medians. The triangle under each axis marks the start of the 10 % plateau of the median curve. In both splits the three group medians lie within the spread of the individual specimens. Linear y axes from zero; y is shared within each measure. (File: `figures/fig2_force_vs_resolution.pdf`, double column.)

**Fig. 3.** Shape reconstruction. Top: one held-out photometric frame (⌀4 mm cylinder) reconstructed from 320 × 180, 80 × 45, and 16 × 9 px inputs, shared colour scale, with a 4 mm bar; the contact centre was located once at full resolution and reused. (a) Cross-section through the contact at the three widths against the true depth. (b) Shape against depth scale for two photometric units: the profile shape is recovered in both, but the depth is 0.90× and 0.60× the true value. (c) Depth MAE against pixel density for cylinder and cube (thin: units; thick: medians), photometric. (d) Recovered lateral size against pixel density, depth-referenced sensor, against the true 4 mm. (e) Error curves split by thickness and by hardness, four rows (configuration × probe), from `figures/fig4b_shape_by_gel.pdf`; y axes are shared within a configuration only, because the two pipelines evaluate different depth ranges. (Files: `figures/fig4_shape.pdf` and `figures/fig4b_shape_by_gel.pdf`, to be merged into one double-column figure per outline §0.1.)

**Supplementary (optional, per outline §0.1):** `figures/fig2b_resultant_force.pdf`, the lower bound on resultant force error in the layout of Fig. 2; the caption must state that y is a lower bound.

---

## OPEN ITEMS / TO RESOLVE

1. **Abstract length.** Now 1,998 characters with spaces. If the template counts differently, the sentence on saturation depth vs. force direction is the next cut.
2. **Uploaded outline vs. data (IV-A).** The outline states that at equal *force* the imprint diameter differed by thickness (thinner = larger). The CSVs show the thickness separation of diameter collapsing at equal force in the depth-referenced sensor (1.01×) and weakening in the photometric family (1.1×), with hardness separating the depth-referenced brightness (1.9×). The text follows the data; outline rev. 2 (`paper/outline.txt` §IV-A) makes the same correction. Source: `result/single/*/data/{optical,force}_by_group_*.csv`, ratios recomputed for this draft.
3. **Uploaded outline vs. data (V-A, V-B).** The outline's "resultant-force plateau 6.4–13.6 px/mm^2" and "shape plateau 2.9–6.3 px/mm^2" do not match the CSVs (resultant lower bound 13.7 / 18.3 / 361; shape 5.5 / 4.9 / 2.2 / 83.2). Tables VI and VII use the CSV values and per-axis MAE as the primary metric, as in outline rev. 2.
4. **Aggregation order.** All plateau densities in the text are medians of per-unit values; Table VI also lists the plateau of the median curve. Keep one convention everywhere, including the abstract.
5. **Force protocol numbers.** The text uses the registry values (normal 0–2 N, commanded shear 0.5 N, 1.2 N preload); `docs/methods.md` §5.2 still carries the earlier 0.1–5.0 N ladder and 1.0 N shear target. Confirm and retire the stale text.
6. **Constant-mean baseline** (outline 0.288 / 0.305 / 0.443 N vs. recomputed 0.281 / 0.325 / 0.437 N) and **Fz column definition** (all test frames vs. normal block): confirm against `docs/force_estimation.md` and `force_vs_resolution_axes.csv`.
7. **Camera and exposure.** Module name (Sincerefirst SF-YL0320-V1 / D140 in the outline; YJX-YL0320-2740 in the configs) and the photometric exposure (60 ms in `camera_digit.yaml`; one analysis note lists 205 ms for all units).
8. **Layer-stack details** (acrylic 2 / 3 mm, 4.5 mm Solaris, 0.5 mm skin, NOVOCS Matte, water-transfer marker paper) are from the authors' design record, not from the repository.
9. **Robot positioning repeatability** is quoted as measured on the rig; add the FR5 datasheet value if required.
10. **Figures.** Three figures are cited (Fig. 1–3); `figures/fig3_gel_and_repeatability.pdf` is not used and the shape figure has been renumbered from Fig. 4 to Fig. 3. Decide whether Fig. 3 and `figures/fig4b_shape_by_gel.pdf` are merged into one double-column figure, and whether `figures/fig2b_resultant_force.pdf` is included.
11. **References [5], [6], [8], [10], [11], [18], [19]** marked [TO VERIFY].
12. **Page budget.** Sections I–VII are about 7,535 words (tables and captions excluded), plus seven tables and three figures; this is roughly 9–10 pages in the IEEE template against a limit of 8 including references, so about 2,000–2,500 words must come out. Recommended order of cuts: (a) merge IV-A4 into IV-A3 and drop the second half of IV-B3 (asymmetry) into one sentence; (b) shorten IV-B4 to the three-class result and the full-resolution loss (drop the per-width counts); (c) compress III-C3/C4 to protocol essentials; (d) drop Table III's brightness columns or fold Table III into text; (e) drop the 5 %/20 % columns of Table VI into one sentence; (f) shorten V-B2 (pipeline description) and V-B5 (lateral size); (g) merge VI-A into three paragraphs. Do not cut IV-B3's optimal-depth finding or V-B4's preprocessing-scale finding.
