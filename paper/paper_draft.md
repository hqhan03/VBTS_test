# Elastomer Thickness, Hardness, and Pixel Density in Vision-Based Tactile Sensors: Contact Response and Task-Dependent Sampling Requirements

> Draft for ICRA 2027 (IEEE conference template, two-column; limit 8 pages including references).
> **Shortened revision, 2026-09-15.** Section IV-A (imprint growth and optical response) was removed at the authors' request, and the body was cut from about 7,100 to about 5,750 words and the figure captions from about 1,650 to about 880. What was cut, and what was deliberately kept, is recorded under *Open items* §B; what is still over the page limit is item 20.
> Paragraph tags in brackets (`[ABS]`, `[I-1]`, …) pair each paragraph with the same paragraph in `paper_draft_kr.md`. Tags are **not** renumbered when a section letter changes, so Section IV-A carries the `[IV-B*]` tags and Section IV-B the `[IV-C*]` tags. Section VI is now two paragraphs, tagged `[VI-1]` and `[VI-2]`, and Section VII a single paragraph, `[VII-1]`.
> Figure captions sit in the body, at the point where each figure belongs, so that text, tables and captions paste in one pass.
> `[AUTHOR CHECK: …]` notes are no longer inline; they are collected under *Open items* so that this file can be pasted into the manuscript as it stands.
> Every number in this text comes from `result/results_single_sensor.md`, `result/single/**/*.csv`, `paper/figures/*.csv`, or `docs/*.md`. All results use the 27 gel units of the campaign, one specimen per condition (Section III-B).

**Authors:** Hyeokgyu Han, Dongchan Kim^1, and Hyung-soon Park^1*

---

## Abstract

[ABS] Vision-based tactile sensors deliver high-resolution contact information, but the elastomer and the pixel density are fixed early in a design and set the data volume the camera, electronics, and network carry. We report a controlled comparison of how elastomer thickness and hardness appear in the contact image and in the pixel density each estimation task requires. Three configurations (depth-referenced, photometric, and photometric with markers) received gels at three Shore OO hardness levels and three thicknesses (1, 2, 3 mm), measured with one robot and one protocol; force and shape estimation was evaluated at twelve pixel densities obtained by area-averaging the same 1920 × 1080 frames (about 10^4 to 0.1 px/mm^2). Two-contact separation in the depth-referenced design followed thickness (1.10 to 2.50 mm spacing), while every photometric specimen separated the narrowest pair tested. The depth at which the image saturated followed thickness in both configurations measured, but the force at that depth rose with thickness in one and fell in the other. Neither estimation accuracy nor the pixel density at which error reached a 10 % plateau tracked thickness or hardness after multiple-comparison correction; the plateau density tracked the task instead, with medians from 2 px/mm^2 (cylinder depth) to 83 px/mm^2 (cube depth) and force at 7 to 23 px/mm^2. Gel choice should follow the contact regime and the force range, pixel density the task and the tolerance, both verified on the designer's own pipeline.

---

## I. INTRODUCTION

[I-1] Vision-based tactile sensors (VBTS) image the deformation of an elastomer with a camera and recover contact geometry and force from the image [1]–[3]. They yield far more spatial information than a discrete taxel array, but every sensor is a video stream: as robot hands acquire more fingertips, bandwidth, storage, and inference load scale with the number of sensors and with the pixels each one produces. Two decisions fix that load before any learning is done — the gel, which determines what a contact looks like, and the pixel density of the imaging path, which determines how finely that appearance is sampled (Fig. 1).

[I-2] Many VBTS designs have been reported and several characterised individually, but evidence that varies the gel systematically while also measuring how much image each estimation task needs is scarce. Thickness and hardness have been linked separately to spatial resolution and to measurement range [4]–[6], and a few studies report the input resolution at which one sensor and one task saturate [7], [8]. What is missing is a comparison in which thickness, hardness, and pixel density are varied together on the same hardware and protocol.

[I-3] This paper reports such a comparison. We built three sensor configurations, each with gels at three hardness levels and three thicknesses, and measured every specimen with one robot, one force/torque sensor, and one protocol. For each we characterised the contact response — two-contact separation and image-response saturation — and evaluated force and shape estimation at twelve pixel densities obtained by down-scaling the same frames. The aim is not a universal design table but measured trends, with the conditions under which each was observed made explicit.

[I-4] The configurations cover the two imaging principles that dominate intensity-based VBTS. Depth-referenced sensors such as 9DTact [3] read the transmittance of a pigmented layer, so brightness maps to indentation depth directly; photometric sensors such as DIGIT [2] read surface shading under directional colour illumination, as in GelSight [1]. Both use one camera and no moving parts and are compact enough for fingertips, which is why we compare them rather than binocular or event-based designs. Markers are the most common addition to a photometric gel, so we included a marker variant on the same body and optics.

[I-5] The contributions are (i) a 3 × 3 × 3 campaign (configuration × hardness × thickness) under a shared protocol; (ii) a characterisation of how thickness and hardness appear in two-contact separation and in image saturation; (iii) force- and shape-estimation error curves over twelve pixel densities, with the density at which each task plateaus; and (iv) an account of what this design could and could not resolve, so that the trends can serve as a starting point for design guidelines rather than as the guidelines themselves.

**Fig. 1.** Where the two design variables of this study enter a sensor design. The user specification — (a) the target task, (b) the sensing principle — fixes the contact response the sensor must cover and the feature to be estimated; those fix an allowable force range and an allowable estimation error, which are what (c) the gel and (d) the pixel density are chosen against. In (c) the gels differ in thickness (top row) and in hardness (bottom row), each with the contact image it produces; in (d) one frame is shown at R = 220, 13.8, and 0.55 px/mm^2. The arrows are the order in which the questions arise in this study, not a validated design procedure.

---

## II. RELATED WORK

### A. Gel Design and Physical Properties

[II-A1] Gel mechanics and sensor behaviour have mostly been related one parameter at a time. GelSlim [4] motivated a thin, stiff gel by arguing that spatial resolution improves as compliance decreases. Halwani et al. [5] associated stiffness with measurement range in a parametric simulation of a multi-layered gel. TacEva [6] evaluated four commercial sensors and associated thicker gels with lower spatial resolution, but there thickness and hardness were properties of the devices, not variables under control. Simulation studies of VBTS optics [9] and learning-based designs [10] treat the gel as a fixed input. What is known is a set of directional tendencies, each established on a different sensor and rarely with the others held fixed.

### B. Image Reduction and Task-Specific Performance

[II-B1] Several groups have asked how much image a tactile task needs. Minsight [7] reported that three-axis force and contact-position estimation saturated at 82 × 60 pixels (about 1.7 px/mm) for one gel; Shepherd et al. [8] found that texture classification with a TacTip saturated at 25 % of the original image; learning-based force estimators [11] and self-supervised tactile representations [12] resize inputs to 224 × 224 by convention rather than by measurement. Large reductions are evidently possible, but each result is one sensor, one gel, and one task, so the reader cannot tell whether the saturation would move with the gel.

### C. Question Addressed Here

[II-C1] We combine the two lines: with the gel varied systematically on three configurations, we ask how thickness and hardness appear in the physical contact response and, on the same specimens, how much pixel density each estimation task requires, so that the gel dependence of the sampling requirement is observed directly rather than inferred across papers.

---

## III. METHODS

### A. Sensor Hardware

[III-A1] Two imaging principles were implemented in two sensor bodies, each with a replaceable gel module (Fig. 2). The depth-referenced body follows 9DTact [3]: white light enters from below, and a translucent layer under a black opaque skin transmits more light where it is compressed, so brightness increases with local indentation depth. The photometric body follows DIGIT [2]: three colour LEDs illuminate a white reflective skin from the sides, and the shading of the deformed surface encodes its gradient, which is integrated to a height map. The marker variant uses the photometric body and optics unchanged. Within a family every unit is the same body with only the gel exchanged, so a within-family comparison is a gel comparison.

**Fig. 2.** Exploded views of the two sensor bodies. (a) Depth-referenced (9DTact-type): A1 black skin (0.5 mm), A2 translucent sensing layer (1, 2, or 3 mm — the varied layer), A3 transparent silicone base (4.5 mm), A4 acrylic window (2 mm), A5 gel frame, A6 camera, A7 illumination board, A8 housing. (b) Photometric (DIGIT-type): B1 white reflective skin, B2 transparent gel (the varied layer), B3 acrylic window (3 mm) and frame, B4 camera, B5 illumination board, B6 housing. "Thickness" refers to the varied layer only, and the marker variant is body (b) with a dot grid 0.5 mm below the reflective layer.

[III-A2] Layer stacks, from the camera outward, were: depth-referenced, 2 mm acrylic window, 4.5 mm transparent silicone (Smooth-On Solaris), the translucent sensing layer whose thickness was varied (1, 2, or 3 mm), and a 0.5 mm black skin; photometric, 3 mm acrylic window, the transparent gel whose thickness was varied, and a sprayed white reflective skin. "Thickness" throughout this paper refers to the varied layer only. The depth-referenced stack has a compliant base under that layer, whereas the photometric gel rests directly on acrylic, which matters for the saturation results of Section IV-B.

[III-A3] The same camera module (Sincerefirst SF-YL0320-V1, D140 lens) was used in both bodies, streaming 1920 × 1080 uncompressed YUYV frames at a measured 4.9 fps. Exposure, white balance, and gamma were fixed manually and held constant within each family (205 ms depth-referenced, 60 ms photometric; 4600 K), which brought the frame-to-frame brightness scatter from 20.4 to 0.09 grey levels. Field of view was measured per unit; medians were 21.9 × 13.4 mm and 18.5 × 10.5 mm, giving full-frame densities of about 7.8 × 10^3, 1.04 × 10^4, and 1.29 × 10^4 px/mm^2 for the three configurations. Gel thickness changes the camera-to-surface distance and hence the magnification (pixels per millimetre correlated with thickness at ρ = −0.81 to −0.94), so the mechanical and optical effects of thickness are not separated by this design; densities are computed per unit.

### B. Elastomer Specimens

[III-B1] Gel modules were cast for a full factorial of 3 configurations × 3 hardness levels × 3 thicknesses, 27 units, one per condition (Table I). Hardness was set by formulation and measured on the cured material in Shore OO. The two families do not share a hardness scale: the depth-referenced gels span OO-30 to OO-70 across two product lines, the photometric gels one Solaris formulation at three plasticiser ratios, OO-51 to OO-57. The 40-point range of the first is 6.7 times the 6-point range of the second, so every hardness result below must be read within a family. Marker gels use the photometric formulations but were measurably stiffer under a sphere (Hertz stiffness ratio 1.64, higher in 12 of 13 matched pairs), so the marker variant is a different gel as well as a different image.

**TABLE I. Formulations of the sensing layer and measured Shore OO hardness.**

| Configuration | Shore OO | Formulation |
|---|---|---|
| Depth-referenced | 30 | Ecoflex 00-30, A : B = 1 : 1 |
| | 50 | Ecoflex 00-50, A : B = 1 : 1 |
| | 70 | Dragon Skin 20 : Dragon Skin 30 = 1 : 0.8 (each A : B = 1 : 1) |
| Photometric | 51 | Solaris A : B : Slacker = 1 : 1 : 4 |
| | 54 | Solaris A : B : Slacker = 1 : 1 : 2 |
| | 57 | Solaris A : B : Slacker = 1 : 1 : 1 |

Skins: depth-referenced black skin, Ecoflex 00-10 with black pigment, 0.5 mm; photometric white skin, Ecoflex 00-10 with white pigment and NOVOCS Matte, airbrushed. Marker gels carry a dot grid (dot diameter 1.0 mm, pitch 2.5 mm, both measured on the part) printed on water-transfer paper and placed 0.5 mm below the reflective layer.

[III-B4] Not every measurement was made on every configuration. Image saturation is reported for the two configurations indented with the ⌀8 mm sphere; two-contact separation was not measured on the marker configuration; and shape reconstruction was not attempted on it, because the dots occlude the shading the photometric method depends on. The learned force estimator used the representation native to each configuration: three channels (reference, brightening, darkening) as in [3], the raw colour frame, and the colour frame with the dots removed by inpainting. The marker comparison of Section V-A is therefore between the marked sensor processed by inpainting and the unmarked one, not a test of the information carried by the dots.

### C. Apparatus, Probes, and Protocol

[III-C1] Indentation was performed by a FAIRINO FR5 six-axis arm (Fig. 3) carrying the probe on an ATI Mini45 six-axis force/torque sensor read through a National Instruments PCIe-6343 at 2 kHz and logged as 20 ms averages. F/T noise at zero load was 0.015 N in Fz and 0.002 N laterally; zero drift over a ten-minute run (up to 0.17 N) exceeded it and was removed by interpolating between three tare checks per run. Robot positioning was verified rather than taken from a datasheet: the alignment gate before contact required ≤ 0.05 mm radial and ≤ 0.10° tilt error (achieved 0.005–0.023 mm and 0.002–0.022°), return to the contact origin repeated to ±0.007 mm, and the fitted gel surface to 0.029 mm. Remounting the same gel shifted the contact by 0.09 mm laterally and 0.07 mm in height, which is the floor for all unit-to-unit comparisons.

**Fig. 3.** Indentation rig. (a) FAIRINO FR5, (b) probe, (c) VBTS, (d) mount, (e) ATI Mini45 F/T sensor. The probe is carried by the FR5 flange through the F/T sensor; the gel module is clamped to the optical table.

[III-C2] Four probe geometries were used: a ⌀8 mm sphere, a ⌀4 mm flat-ended cylinder, a 4 mm cube pressed on a face, and two-post probes of two ⌀1.0 mm cylinders at centre spacings of 1.10 to 2.50 mm. Each probe was fitted once and carried across all sensors before the next was fitted, because re-fitting introduces a contact asymmetry (0.09 mm) comparable to the effects under study. The gel plane and zero surface were re-measured after every gel change, and the probe was aligned to each unit's measured gel normal.

[III-C3] For every probe and unit the gel surface was found by approaching in 0.02 mm steps to 0.30 mm and fitting a contact law to the force–depth record (Hertz for spheres, linear for flat tips); the fitted zero, precise to ±0.003 mm for flat tips and ±0.014 mm for spheres, is that unit's depth reference. Shape data were collected on a depth ladder from 0.1 to 0.6 mm in 0.1 mm steps, three passes; two-post data from 0.1 to 0.9 mm, or 0.6 mm for the 1 mm gels. Force data were collected with the sphere in a continuous run of 1000 frames per unit, half in normal cycles from 0 to 2.0 N at about 0.15 N/s and half in shear glides along the four sensor axes under a 1.2 N preload. The saturation ramp of Section IV-B was always the last measurement on a unit, because it can damage the gel.

[III-C4] Camera frames were paired with the F/T stream by driver timestamp, and a frame's label is the mean of the F/T samples inside its exposure window; an ablation showed that this exposure-matched window gave the lowest error, and that an instantaneous sample raised the normal-force error of the depth-referenced sensor by 1.48× (p = 0.007). The force moves during the exposure, and that motion, not F/T noise, sets the label floor: the second-difference label noise in Fz is 0.028 N and the best learned Fz error is 1.8 times that, so absolute accuracies in Section V are bounded by the labels and only comparisons between units are meaningful.

---

## IV. CONTACT RESPONSE

### A. Paired-Contact Separation

[IV-B1] Two-contact separation was evaluated with the two-post probes on the depth ladder. From each difference image the brightness profile was taken along the major axis of the imprint pair, averaged over a 0.8 mm strip and binned at 0.02 mm, and scored as Dip = (P − T)/P, where P is the height of the *weaker* of the two peaks above background and T the trough, so that an unequal pair is not credited with a dip it does not have. A rung was *resolved* only if it passed three gates: signal (P ≥ 2.5 grey levels, about two standard deviations of the depth-zero uncertainty expressed in brightness), noise (Dip ≥ 3 × the propagated dip noise), and Rayleigh (Dip ≥ 0.265). A unit resolves a spacing if any rung passes all three; the depth range over which it passes is reported alongside.

**TABLE II. Finest resolved centre spacing (mm) and resolved depth range (mm) at full resolution, depth-referenced configuration. All nine photometric specimens resolved the narrowest spacing tested (1.10 mm); 1 mm photometric gels resolved it to 0.6 mm depth and 2–3 mm gels to 0.9 mm.**

| Shore OO | 1 mm | 2 mm | 3 mm |
|---|---|---|---|
| 30 | 1.50 (0.2–0.6) | 1.75 (0.1–0.9) | 2.00 (0.3–0.3) |
| 50 | 1.10 (0.1–0.6) | 1.10 (0.1–0.9) | 2.50 (0.5–0.9) |
| 70 | 1.25 (0.1–0.6) | 1.25 (0.1–0.9) | 2.50 (0.4–0.9) |

[IV-B2] In the depth-referenced configuration the finest resolved spacing ranged from 1.10 to 2.50 mm and followed thickness (Table II, Fig. 4d): ρ = +0.75 (p = 0.021) for the finest spacing, −0.71 (p = 0.031) for the number of spacings resolved, and −0.74 (p = 0.023) for the best dip, with 3 mm gels resolving only the widest pairs. Hardness was associated with none of the three (|ρ| ≤ 0.32, p ≥ 0.41). Every photometric specimen resolved the 1.10 mm pair at full resolution, so there the measurement is an upper bound rather than a value and no gel dependence can be claimed; the only distinction among photometric gels was the depth range, and the 1 mm gels were limited there by the ladder.

**Fig. 4.** Two-contact separation, depth-referenced configuration. (a), (b) the same hard gel under the same two-post probe (2.00 mm centre spacing) at 0.30 mm indentation, differing only in thickness (1 and 3 mm), both |contact − reference| on the same display range. (c) a cut through those two imprints; dashed line, the 2.5 grey-level decision floor of Section IV-A. (d) finest centre spacing resolved at full resolution against thickness, nine specimens, one per cell, coloured by measured Shore OO; all nine photometric specimens resolved the narrowest probe we could make, so that family is not plotted. (e) the same decision on down-scaled frames, 2.00 mm pair at 0.30 mm, one specimen; dashed line, the Rayleigh threshold Dip = 0.265; × marks a rung where the contact was not detected at all, a different failure from a trough too shallow to pass. One specimen per cell, so there are no error bars.

[IV-B3] Three qualifications apply. First, separation has an optimal depth: for spacings up to 2.00 mm every resolved rung lay at 0.1 to 0.3 mm indentation, and deeper rungs darkened further while the trough between the posts disappeared — no lower threshold recovered it without also declaring "two contacts" on a single-post control. Only at 2.50 mm did separation persist through 0.9 mm, so two-point resolution should be quoted with the depth at which it holds. Second, the verdict is sensitive to the gates: of the 120 rungs whose dip exceeded the Rayleigh value, 38 were rejected by the signal gate, and lowering that gate from 2.5 to 2.0 grey levels raised the specimens resolving 1.25 mm from four of nine to five. Third, the posts did not load equally — the weaker reached a median 0.76 of the stronger one's darkening, mostly from residual gel tilt — and seating was best on the 2 mm units, which also resolved best, so the thickness trend is entangled with seating in this dataset.

[IV-B4] Repeating the decision on frames area-averaged to the twelve widths of Section V (Fig. 4e) separates three outcomes that must be kept apart: resolved; contact detected but not separated; and contact not detected at all. For the 2.00 mm pair the resolved count peaked at 19 of 27 rungs between R ≈ 390 and 1600 px/mm^2, fell to 11 at R ≈ 14, and dropped to 12 at full resolution, where per-pixel noise was five times higher and the median imprint fell below the signal gate. Below R ≈ 200 a growing share of the failures are contacts the detector never found, so values there bound the failure rather than measure it. We do not convert the peak into a requirement comparable to the 10 % plateau of Section V; what the sweep shows is that this decision uses pixels one to two orders of magnitude above the force and shape plateaus of the same camera, and that full resolution is not its best operating point.

### B. Image-Response Saturation

[IV-C1] The maximum force a sensor can report is not the force the gel survives but the force at which the image stops changing. Each unit was driven in depth steps with the ⌀8 mm sphere while force and a frame were recorded at every step. The response is the slope of the mean absolute image change per newton over a three-step window, the maximum response the median of the three highest windows, and saturation is declared when the response falls below 15 % of that maximum for two consecutive steps, the ceiling being the force at the first of the two.

**TABLE III. Image-response ceiling (N) and the indentation depth at saturation, ⌀8 mm sphere.**

| Configuration | Shore OO | 1 mm | 2 mm | 3 mm | Depth at saturation |
|---|---|---|---|---|---|
| Depth-referenced | 30 | 27.8 | 30.2 | 31.0 | 4.3 – 6.8 mm |
| | 50 | 31.0 | 30.2 | 38.5 | (2.0 – 4.7 × thickness) |
| | 70 | 27.5 | 43.3 | 63.2 | |
| Photometric | 51 | 22.4 | 17.7 | 11.8 | 1.1 – 2.1 mm |
| | 54 | 18.2 | 14.1 | 14.4 | (0.6 – 1.3 × thickness) |
| | 57 | 19.5 | 22.4 | 11.8 | |

[IV-C2] Two observations are robust across Table III and Fig. 5. First, the depth at which the image saturates followed thickness in both configurations (ρ = +0.95 and +0.95; p ≤ 0.001) and not hardness (|ρ| ≤ 0.05). Second, the force at that depth moved with thickness in opposite directions in the two families: the ceiling rose in the depth-referenced configuration (ρ = +0.63, p = 0.068; hard 27.5 → 43.3 → 63.2 N) and fell in the photometric one (ρ = −0.90, p = 0.001). Hardness was not associated with the ceiling in either (ρ = +0.37 and +0.05; p ≥ 0.33), but in the depth-referenced family the hard-to-soft ratio grew with thickness, 0.99 → 1.43 → 2.04, so hardness and thickness act multiplicatively rather than additively there.

**Fig. 5.** Image-response ceiling against gel thickness, ⌀8 mm sphere. (a) depth-referenced, (b) photometric; one line per hardness, labelled by measured Shore OO, one marker per specimen, nine per panel. The ceiling is defined in Section IV-B. The vertical scales differ by about a factor of three and must not be compared: the criterion is relative to each unit's own peak response, so ceilings are read within a configuration only.

[IV-C3] These are descriptive trends and we do not fit a mechanism to them. One reading consistent with the depths in Table III is that the two designs saturate in different regimes: the depth-referenced probe reaches 2 to 4.7 times the layer thickness, with a local force–depth exponent of 2.1 to 2.5 against Hertz's 1.5, so it has passed through the varied layer into the compliant base and the whole stack enters the ceiling, whereas the photometric probe saturates at 0.6 to 1.3 times the thickness, still within its own layer against a rigid window, where the optics saturate first. Two things follow. Shore hardness, a static test on a thick block, does not describe the indentation stiffness of a thin layer on a support, which rises with the ratio of contact radius to thickness [13], [14]; and the depth-referenced ceiling can be adjusted by gel choice (27.5 to 63.2 N), whereas the photometric one cannot be ordered by hardness in the range tested. We predict, untested, that a depth-referenced gel supported directly on acrylic would show the photometric trend.

[IV-C4] The criterion is relative to each unit's own peak response, which makes the ceilings of weakly responding units come out higher; with a fixed absolute threshold the gap between the two families widens from 1.8× to 4.3–6.6×. We therefore use these values within a configuration only.

---

## V. ESTIMATION PERFORMANCE VERSUS PIXEL DENSITY

[V-0] We compared trends of estimation error with thickness and hardness, and then asked at what pixel density the error of each task reaches a plateau. Pixel density R is defined per unit as the pixels at a ladder rung divided by the area of gel surface that unit's camera sees, R = (s·k)^2 with s the full-frame pixels per millimetre and k the down-scaling factor; it is the quantity comparable across units and configurations, whereas pixel width alone is not. Fig. 6 shows what a reduction of the input looks like and what it costs. On accuracy, 9 of 40 uncorrected Spearman tests were significant at p < 0.05, all nine on thickness, but none survived Benjamini–Hochberg correction [15] (smallest q = 0.185), and the direction differed between configurations. On the plateau density, none of 26 tests approached significance (smallest q = 0.53). The two families of tests are separate and are not pooled.

**Fig. 6.** What pixel density costs, on the depth-referenced configuration. (a)–(c) one contact frame (hard 2 mm gel, ⌀8 mm sphere) area-averaged to R = 220, 13.8, and 0.55 px/mm^2, all three on the same display range. (d) Fz MAE against pixel density, median of the nine depth-referenced specimens, on the ladder and the plateau rule of Section V-A. The per-specimen curves of all three configurations are in Fig. 7.

### A. Force Estimation

[V-A1] Protocol and data are as in Section III-C: one ⌀8 mm sphere at the centre of the gel, 1000 frames per unit, normal cycles to 2.0 N and shear glides under a 1.2 N preload. Frames with Fz above 2 N were excluded, so the evaluated range is 0 to 2.1 N. The data were split by loading cycle, not by frame, so that neighbouring frames of one cycle never appear on both sides of the split (0.70 / 0.15 / 0.15, in chronological order). Splitting the same data by random frames instead lowers the reported error by about 20 % on both channels, which measures the leakage a random split would hide.

[V-A2] A ResNet-18 [16] pretrained on ImageNet with a six-output head was trained per unit and per resolution with an L1 loss, Adam at 5 × 10^−4 with weight decay 10^−4 and linear decay, an effective batch of 64, and 30 epochs with the epoch chosen on the validation set. Three seeds were run for widths up to 854 px and their median reported; the two highest rungs used one seed. Input frames were area-averaged to twelve widths from 1920 to 8 px at 16 : 9, spanning R ≈ 7.8 × 10^3 to 0.14, 1.04 × 10^4 to 0.18, and 1.29 × 10^4 to 0.22 px/mm^2 for the three configurations. Area averaging was chosen because Fz is, to first order, an integral of the image, which the operation preserves; it also means the sphere cannot by itself reveal a gel-dependent Fz saturation, because the sphere rather than the gel sets the imprint shape. A constant-mean predictor scores about 0.28, 0.32, and 0.44 N in Fz.

[V-A3] The plateau density of a unit is the lowest rung whose error lies within (1 + τ) of that unit's own minimum over the ladder. We use τ = 10 % as the reference, because the argmin itself jumps between rungs on the flat part of the curve under seed noise, and report τ = 20 % alongside. The summary statistic is the median over units of the per-unit plateau density; the plateau of the median curve is a different number (13.6, 18.3, and 361 px/mm^2) and the two must not be mixed. Table IV reports the error a user reads, the resultant ‖F̂ − F‖, rather than the three axes separately. Per axis, the same units give minimum MAEs of 0.042, 0.055, and 0.077 N in Fz and 0.023, 0.027, and 0.031 N in shear, with τ = 10 % plateaus at R = 17.3, 13.3, and 23.0 px/mm^2 (Fz) and 5.9, 6.3, and 71.7 px/mm^2 (shear).

**TABLE IV. Force estimation on a resultant basis (n = 9 per configuration). The error is ‖F̂ − F‖, obtained from the per-axis MAE by Jensen's inequality and therefore a lower bound; a later retrain of the same units that stored the per-frame vector error put this bound at 0.88 to 0.92 of the measured value (Section V-A5). Min. error is the median over units of each unit's best rung; R (px/mm^2) is the density at which error enters the plateau, as the median of the per-unit values, with the pixel width of the median rung in brackets. The last column is the per-unit spread at τ = 10 %.**

| Configuration | Min. error (N) | R at τ = 10 % | R at τ = 20 % | Per-unit range |
|---|---|---|---|---|
| Depth-referenced | 0.057 | 13.6 [80] | 13.6 [80] | 1.7 – 464 |
| Photometric | 0.073 | 6.7 [48] | 3.4 [32] | 2.2 – 293 |
| Photometric + marker | 0.094 | 23.0 [80] | 8.1 [48] | 2.8 – 455 |

[V-A4] Fig. 7 shows the error curves, split once by thickness and once by hardness. Three points stand out. (i) At τ = 10 % the markerless configurations plateau at R ≈ 7 to 14 px/mm^2 for the resultant force, and per axis at R ≈ 13 to 17 for Fz and ≈ 6 for shear; at full resolution their median error is 20 to 35 % above the plateau minimum, i.e. the highest rungs over-fit. (ii) In neither split do the three group medians separate from the spread of the individual specimens: the plateau density is not associated with thickness or hardness in any force row, taken as the resultant or per axis (|ρ| ≤ 0.58, q ≥ 0.53). (iii) Per-unit plateau densities spread over two to three orders of magnitude within a configuration (Table IV, range column), far wider than any separation between the groups, and the requirement also depends on the tolerance: loosening τ to 20 % moves rows by up to threefold. A gel effect smaller than that spread could not have been detected with nine specimens per configuration; the null result is a statement about detection power, not a demonstration of independence.

**Fig. 7.** Force-estimation error against pixel density R. Rows: depth-referenced (a, b), photometric (c, d), photometric with markers (e, f); left column split by thickness, right column split by hardness over the same nine specimens, so the thin lines are identical between columns. Thin line, one specimen (median over seeds); thick line, the median of a group; triangle, the τ = 10 % plateau density. Normal force only. The vertical scale differs between rows and must not be compared across them: the three configurations were trained on different input representations. One specimen per cell, no error bars; the null result is a limit of detection (Section VI).

[V-A5] Two things qualify the resultant values of Table IV. First, they are a bound: the sweep stored per-axis MAE and discarded the per-frame predictions, so by Jensen's inequality L = (MAE_x^2 + MAE_y^2 + MAE_z^2)^1/2 is a lower bound on E‖F̂ − F‖, with equality only if the three axes err together on every frame, which indentation of a single sphere makes close to the case. A later retrain of the same 27 units that stored the per-frame vector error put the bound at 0.88, 0.88, and 0.92 of the measured error, so it locates the plateau correctly and understates the magnitude by about 10 %; read the floors as 0.06 to 0.10 N against an evaluated range of 0 to 2.1 N, i.e. 3 to 5 % of range. Second, the resultant is close to Fz alone, which carries 63, 66, and 79 % of the sum of squares and does not move with density, so lowering the floor is a question about Fz, not about pixels.

[V-A6] The marker variant, processed by inpainting, had the highest Fz floor (0.077 N against 0.042 and 0.055) and needed the most pixels for shear (71.7 px/mm^2 at τ = 10 %), consistent with a smaller image response per newton: inside the contact the brightness change at 2 N was 0.20 to 0.56 times that of the depth-referenced sensor, and the dots occlude 9 to 14 % of the contact. Its shear curve also has a different shape — 7 of the 9 marker specimens had lower shear error at 1920 px than at 80 px, against 1 of 9 and 0 of 9 elsewhere — though the effect is small (median −0.0015 N, below the seed spread of a single specimen), so it is the contrast between configurations, not the size, that is the finding. Because the input representations differ, this comparison cannot separate the markers from the preprocessing.

### B. Shape Reconstruction

[V-B1] Shape data come from the depth ladder of Section III-C with the ⌀4 mm cylinder and the 4 mm cube at the gel centre (18 and 6 frames per unit); a sphere of known radius pressed on the same ladder calibrates the two pipelines and is not scored. The reference is the known probe geometry at the robot's fitted indentation depth, not an independent surface scan, so the elastic sink-in around a flat punch counts as error for every method equally.

[V-B2] The depth-referenced sensor uses a per-unit brightness-to-depth lookup table calibrated on the sphere ladder and applied pixelwise as in [3]. The photometric sensor needed a pipeline built for this study: the sphere geometry gives the per-pixel true surface gradient, a small network maps (colour difference, pixel position) to that gradient, and the field is integrated by a Poisson solve. The scored quantity is the imprint depth against the robot depth, averaged over rungs; the depth-referenced sensor also reports the equivalent diameter of the half-depth contour. One caveat applies to the photometric family: within a unit the reconstructed depth tracked the true depth with correlation +0.98, but the slope varied from 0.16 to 0.92 between units, because the visible contact cap is shallower than the probe travel, so photometric absolute depths are unit-specific and only the curve shape is compared across units.

**TABLE V. Shape reconstruction: depth MAE on the plateau (median over units, range of the three thickness medians) and the pixel density at which error enters the 10 % plateau (median of per-unit values; brackets give the median rung width). Fig. 9 shows the same plateau densities against the gel.**

| Configuration | Probe | Plateau MAE (mm) | R at τ = 10 % (px/mm^2) | Per-unit range |
|---|---|---|---|---|
| Depth-referenced | ⌀4 mm cylinder | 0.064 – 0.072 | 5.5 [48] | 1.7 – 1,550 |
| | 4 mm cube | 0.062 – 0.124 | 4.9 [48] | 2.2 – 7,830 |
| Photometric | ⌀4 mm cylinder | 0.042 – 0.084 | 2.2 [32] | 0.2 – 1,110 |
| | 4 mm cube | 0.030 – 0.096 | 83.2 [160] | 0.2 – 1,200 |

[V-B3] Depth error is flat over a wide range of density (Fig. 8a and 8b, Table V). The photometric cylinder MAE stayed within 0.043 to 0.058 mm from the full frame down to 32 × 18 px (R ≈ 2.9) and only then rose (0.079 mm at 16 × 9, 0.130 mm at 8 × 5); the depth-referenced cylinder was flat at 0.061 to 0.072 mm from R ≈ 4.9 to R ≈ 900, rose to 0.117 mm at the full frame, and collapsed below R ≈ 2. Three of the four task rows plateau between 2 and 6 px/mm^2; the photometric cube is the exception at 83 px/mm^2, and that spread of nearly forty times between two probes on one sensor is the strongest evidence in this study that the task, not the gel, sets the requirement. As in Section V-A, no shape row shows an association of plateau density with thickness or hardness (|ρ| ≤ 0.58, q ≥ 0.53; Fig. 9), and the unit-to-unit spread of the plateau MAE (2.6× and 3.8×) exceeds the change produced by six rungs of down-scaling (1.9× and 1.1×). The depth-referenced lookup table degrades at the highest densities because it loses grey levels rather than pixels: correcting for that brings the full-frame error to 0.048 mm.

**Fig. 8.** Shape reconstruction against pixel density R. Top row, depth error; bottom row, error of the recovered lateral size; (a, c) depth-referenced, (b, d) photometric. Solid blue, ⌀4 mm cylinder; dashed red, 4 mm cube. Line, median of the nine specimens; band, their interquartile range, which is between-specimen scatter, not a measurement uncertainty; triangles, the τ = 10 % plateau density. The scales of (a) and (b) differ and must not be compared; (c) and (d) share a scale and zero is the true 4 mm, with the sign not folded — reading large and reading small are different failures. × marks a rung at which not all nine specimens returned a reconstruction.

**Fig. 9.** Plateau density against the gel: (a, b) resultant force, (c, d) depth of the ⌀4 mm cylinder; left column split by thickness, right column by measured Shore OO hardness, over the same specimens, one row per configuration. Grey bar and grey dots, the range and the individual values of the nine per-unit plateau densities at τ = 10 %; coloured dots, the median of a group. In every panel the group medians fall inside a small part of the grey bar: the spread between nominally identical builds is wider than any separation between the groups, so a gel effect of that size was not detected by this design (Section VI). The two tasks are drawn apart because they are scored in different units and by different pipelines.

[V-B4] The plateau density depends on the processing scale as much as on the sensor. Both pipelines originally applied filters of fixed pixel size (a 7 × 7 Gaussian in the depth-referenced pipeline, a 3 × 3 morphological opening in the photometric contact mask), which grow relative to the imprint as the input shrinks: at 16 × 9 px the opening removed an 18-pixel imprint entirely and 74 % of frames predicted exactly zero depth. Scaling the kernels with the down-scaling factor changed nothing at 1920 px but moved the depth-referenced cylinder MAE at 48 px from 0.155 to 0.072 mm and its median plateau density from R ≈ 55 to R ≈ 5.5, a factor of ten. A pixel-density requirement is therefore a statement about a pipeline, including its preprocessing scale, and not about the sensor alone.

[V-B5] Lateral size does not plateau the way depth does (Fig. 8c). In the depth-referenced sensor the recovered cylinder diameter stayed within ±0.1 mm of the true 4 mm from 32 px to the full frame and failed below 16 px, where the half-depth contour fills the frame, while the cube read large throughout (4.3 to 4.8 mm): the half-depth contour of a flat punch stands outside the true edge, and its shrinkage at low density is blur pulling that contour inward, two errors partly cancelling rather than a better measurement. Recovered size also grew with thickness (cylinder +0.08, +0.27, +0.72 mm at 1, 2, 3 mm), which is the thicker gel spreading contact laterally.

---

## VI. LIMITATIONS AND FUTURE WORK

[VI-1] Each cell of the design holds a single gel, so variation between nominally identical builds cannot be separated from the design factors: the spread between the nine specimens of one configuration covers two to three orders of magnitude in plateau density, wider than any difference between the thickness or hardness groups, so the plateau-density nulls are limits of detection, not evidence of independence, and only the trends that clear that spread — thickness in two-contact separation and in saturation depth — are reported as findings. Three confounds remain. The families differ in support as well as in imaging principle, the depth-referenced gel resting on a compliant base and the photometric gel on acrylic, so the opposite thickness trends of the ceiling (Section IV-B) may be a support effect. Every photometric specimen resolved the narrowest pair we could make, so that family's separation limit is an upper bound, and the depth-referenced trend is entangled with seating symmetry. And hardness spans 40 Shore OO points in one family against 6 in the other, where a flat-punch check did not order the grades consistently, so the photometric hardness nulls are indistinguishable from a range limitation. What we report is in the end a property of a pipeline rather than of a sensor: area-averaging a frame is not a low-resolution camera, and the plateau density moved tenfold when the preprocessing scale was corrected (Section V-B).

[VI-2] The cheapest next experiment is to cast the depth-referenced gel on acrylic and repeat the saturation ramp, which tests the support confound with one family re-made; then, in order of cost, three or more specimens per condition, an absolute saturation criterion so that ceilings compare across families, and narrower two-post probes to find the photometric separation floor. For sensor builders, seating tilt and the scale of preprocessing filters moved the numbers by as much as the design variables did; we suggest reporting the two-contact dip at a stated depth alongside the formulation, which takes one probe and a few minutes.

---

## VII. CONCLUSION

[VII-1] We evaluated three vision-based tactile sensor configurations, each with gels at three hardness levels and three thicknesses, at twelve pixel densities from the full 1920 × 1080 frame down to 8 × 5 pixels, with one robot and one protocol. Thickness changed how a contact appears: two-contact separation followed thickness in the depth-referenced design, whose photometric counterpart resolved every pair we could make, and the depth at which the image saturates followed thickness in both, while the force at that depth rose with thickness in one design and fell in the other. Hardness appeared where it was varied widely: in the depth-referenced design it scaled the saturation ceiling multiplicatively with thickness. Estimation accuracy and the pixel density at which estimation error plateaus showed no thickness or hardness association that survived correction, but the plateau density differed by task by more than an order of magnitude. For design, then, a gel should be chosen against the contact regime and the force range the application needs, and pixel density against the target task and the tolerance one is prepared to accept, with a check that the preprocessing scales with the image (Fig. 1). The numbers reported here are statements about our criteria and our pipeline: we have shown which quantities move and by how much, and a designer should measure them on their own sensor rather than adopt ours.

---

## ACKNOWLEDGMENT

[ACK] *(funding and acknowledgments to be supplied by the authors)*

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

*[17]–[19] of the previous draft (TacTip family; the two [TO VERIFY] entries) are not cited in this text and are dropped.*

### For pasting into the template (no numbers)

The template's reference list numbers itself, so paste these sixteen lines into it in order and let it number them. Journal, proceedings and book titles are italicised in IEEE style; the italics are not marked here, and the [TO VERIFY] notes of the list above are left off.

```
W. Yuan, S. Dong, and E. H. Adelson, "GelSight: High-resolution robot tactile sensors for estimating geometry and force," Sensors, vol. 17, no. 12, p. 2762, 2017.
M. Lambeta et al., "DIGIT: A novel design for a low-cost compact high-resolution tactile sensor with application to in-hand manipulation," IEEE Robot. Autom. Lett., vol. 5, no. 3, pp. 3838–3845, 2020.
C. Lin, H. Zhang, J. Xu, L. Wu, and H. Xu, "9DTact: A compact vision-based tactile sensor for accurate 3D shape reconstruction and generalizable 6D force estimation," IEEE Robot. Autom. Lett., vol. 9, no. 2, pp. 923–930, 2024.
E. Donlon, S. Dong, M. Liu, J. Li, E. Adelson, and A. Rodriguez, "GelSlim: A high-resolution, compact, robust, and calibrated tactile-sensing finger," in Proc. IEEE/RSJ Int. Conf. Intell. Robots Syst. (IROS), 2018, pp. 1927–1934.
M. Halwani et al., "Enhancing sensitivity and measurement range by multi-layered vision-based tactile sensor (ML-VBTS): A parametric study and comparative benchmarking," Measurement, 2025.
Q. Cong et al., "TacEva: A performance evaluation framework for vision-based tactile sensors," Adv. Intell. Syst., 2026.
I. Andrussow, H. Sun, K. J. Kuchenbecker, and G. Martius, "Minsight: A fingertip-sized vision-based tactile sensor for robotic manipulation," Adv. Intell. Syst., vol. 5, no. 8, p. 2300042, 2023.
D. R. Shepherd et al., "Texture and friction classification: Optical TacTip vs. vibrational piezoelectric and accelerometer tactile sensors," Sensors, 2025.
A. Agarwal, T. Man, and W. Yuan, "Simulation of vision-based tactile sensors using physics based rendering," in Proc. IEEE Int. Conf. Robot. Autom. (ICRA), 2021, pp. 1–7.
V. Kakani, X. Cui, M. Ma, and H. Kim, "Vision-based tactile sensor mechanism for the estimation of contact position and force distribution using deep learning," Sensors, vol. 21, no. 5, p. 1920, 2021.
A. Shahidzadeh et al., "FeelAnyForce: Estimating contact force feedback from tactile sensation for vision-based tactile sensors," in Proc. IEEE Int. Conf. Robot. Autom. (ICRA), 2025.
C. Higuera et al., "Sparsh: Self-supervised touch representations for vision-based tactile sensing," in Proc. Conf. Robot Learning (CoRL), 2024.
K. L. Johnson, Contact Mechanics. Cambridge, U.K.: Cambridge Univ. Press, 1985.
E. K. Dimitriadis, F. Horkay, J. Maresca, B. Chadwick, and R. S. Chadwick, "Determination of elastic moduli of thin layers of soft material using the atomic force microscope," Biophys. J., vol. 82, no. 5, pp. 2798–2810, 2002.
Y. Benjamini and Y. Hochberg, "Controlling the false discovery rate: A practical and powerful approach to multiple testing," J. R. Stat. Soc. B, vol. 57, no. 1, pp. 289–300, 1995.
K. He, X. Zhang, S. Ren, and J. Sun, "Deep residual learning for image recognition," in Proc. IEEE Conf. Comput. Vis. Pattern Recognit. (CVPR), 2016, pp. 770–778.
```

---

## OPEN ITEMS / TO RESOLVE

*State as of the shortening pass of 2026-09-15. The body above is meant to be pasted into the manuscript as it stands, so nothing below belongs in the paper.*

### A. Author checks, moved out of the body

These were inline `[AUTHOR CHECK: …]` notes in the previous draft. Nothing about them is settled; they are listed here so that the body can be pasted without editing.

1. **Authors (title block).** The first author carries no superscript in the manuscript, and the affiliation footnote and corresponding-author mark need to be confirmed.
2. **Layer stacks and skins (III-A2, III-B).** Thicknesses, skin materials, NOVOCS Matte, and the water-transfer marker paper come from the authors' design record, not from the repository; the depth safety backstop in the software assumes the black skin adds about 1.0 mm, not 0.5 mm. Fig. 2's part list is the same record and should be checked against it once.
3. **Camera and exposure (III-A3).** Module name (Sincerefirst SF-YL0320-V1 / D140 in the outline, YJX-YL0320-2740 in the configs) and the photometric exposure (60 ms in `camera_digit.yaml`; one analysis note lists 205 ms for all units).
4. **Constant-mean baseline and Fz column (V-A2).** Outline 0.288 / 0.305 / 0.443 N against 0.281 / 0.325 / 0.437 N recomputed from the per-unit CSVs; and whether the Fz column of the axis-wise sweep is over all test frames or the normal block only.
5. **Calibration sphere (V-B1).** Its diameter is not stated; restore it if the Methods section must be reproducible.
6. **Photometric depth scale (V-B2).** The per-unit slope of predicted against true depth (0.16 to 0.92) is stated in the text; the panel that showed it is not in the current shape figure. Either restore the panel or leave the claim to the text.
7. **Resultant bound (V-A5, Table IV).** The bound and the 0.88–0.92 ratio come from two different training runs of the same specimens; the ratio is quoted as a calibration of the bound, not as a pair of comparable absolute values.

### B. Decisions taken in this shortening pass

8. **Section IV-A (imprint growth and optical response) is removed** at the authors' request, with its figure. Everything it carried is gone from the abstract, [I-3], [I-5], [III-B4], [VI-B2] and [VII-2] as well. What is lost with it: the equal-depth against equal-force distinction (1.33× and 1.34× diameter spread at equal depth; 1.01× and 1.91× at equal force), and the 3× unit-to-unit spread of the imprint-diameter slope that [VI-B2] used to rest on. [VI-B2] now recommends only the two-contact dip, and its factor list keeps only the two factors still evidenced in the paper (seating tilt, preprocessing scale).
9. **Section VI is two paragraphs with no A/B split, and Section VII is one paragraph:** `[VI-A1]`–`[VI-A6]` became `[VI-1]` and `[VI-B1]`–`[VI-B2]` became `[VI-2]`, and the three conclusion paragraphs became one, `[VII-1]`. Elsewhere, **section letters moved but paragraph tags did not.** Section IV-A is now Paired-Contact Separation and carries the `[IV-B*]` tags; IV-B is Image-Response Saturation and carries the `[IV-C*]` tags. This keeps the pairing with `paper_draft_kr.md`, which is otherwise now out of date for every paragraph below.
10. **Figures are nine, numbered in document order:** 1 design overview, 2 exploded views, 3 rig, 4 two-contact separation, 5 saturation ceiling, 6 what pixel density costs, 7 force estimation, 8 shape reconstruction, 9 plateau density against the gel. The design-flow chart of the previous draft was dropped as saying the same thing as Fig. 1. In-text references follow this numbering.
11. **Tables are the five in the manuscript**, not the draft's own set: Table IV is the five-column force table (its median-curve plateaus, 13.6 / 18.3 / 361 px/mm^2, are now a clause in [V-A3], and the Fz share is in [V-A5]), and Table V is the shape summary. The gel-effect Spearman table of the previous draft is not here; its result is quoted as |ρ| ≤ 0.58, q ≥ 0.53 in [V-0], [V-A4], [V-B3] and shown in Fig. 9.
12. **The τ = 5 % figures are out of the abstract and [V-A4]**, matching the upstream retraction (item 19) and the τ = 5 % column already dropped from Table IV. The tolerance claim now rests on 10 % against 20 % only, which Table IV supports. Restore the 5 % numbers only if the retraction is reversed.
13. **References are [1]–[16]**; the TacTip entry and the two unresolved ones are dropped as uncited.
14. **Length.** The body is about 5,700 words against about 7,100 before the cut, and the captions about 880 against about 1,650; the captions are now placed in the body rather than listed at the end. See item 20 for what is still over budget.

### C. Carried over, still unresolved

15. **Force protocol numbers.** The text uses the registry values (normal 0–2 N, commanded shear 0.5 N, 1.2 N preload); `docs/methods.md` §5.2 still carries the earlier 0.1–5.0 N ladder and 1.0 N shear target. Confirm and retire the stale text.
16. **Aggregation order.** Every plateau density in the text and in Tables IV and V is a median of per-unit values. Keep that convention everywhere, including the abstract; it differs most from the plateau of the median curve on the marker configuration (23.0 against 361 px/mm^2).
17. **Outline vs. data (V).** The outline's "resultant-force plateau 6.4–13.6 px/mm^2" and "shape plateau 2.9–6.3 px/mm^2" do not match the CSVs (13.6 / 6.7 / 23.0 and 5.5 / 4.9 / 2.2 / 83.2). The tables and captions use the CSV values.
18. **Robot positioning repeatability** is quoted as measured on the rig; add the FR5 datasheet value if required.
19. **The 5 % tolerance result is retracted upstream:** between two training runs of the same nine specimens the 5 % plateau moves by up to 3× and the ordering of the configurations reverses. Only the 10 % plateau may be cited.
20. **Page budget.** Body about 5,700 words, captions about 880, plus five tables, sixteen references, and nine figures. At roughly 950 words per two-column page and about 21 column-inches of figure, that is about 8.5 to 9 pages against a limit of 8. The remaining levers, in order of how much they buy: drop Fig. 1 (two-column, about 0.3 page — its message survives in [I-1] and [VII-3]); fold Fig. 6 into Fig. 7 (about 0.15 page); cut the three longest captions (Figs. 4, 7, 9) to about 60 words each; and, only then, further prose. Do not cut [IV-B3]'s optimal-depth finding or [V-B4]'s preprocessing-scale finding — they are the two results a reader cannot reconstruct from anywhere else.
21. **Figure sources.** Four of the nine are built in `fin_figures/` (Fig. 4 `fig_separation`, Fig. 5 `fig_ceiling`, Fig. 9 `fig_plateau_gel`, and Fig. 6 `fig_input_resolution`, which is F1 of `figure_plan.md`); Figs. 7 and 8 are still the older `paper/figures/` versions; Figs. 1, 2 and 3 are a drawing, a drawing and a photograph. `fig_growth` is no longer used. Also, `paper_style.py` defines markers per hardness but no built script uses them, so the hardness groups are separated by colour alone — against `CLAUDE.md` §2, though commit 57432904 records that the driver asked for the markers to come out.
