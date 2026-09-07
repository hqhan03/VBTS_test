# Data recording — what is written, when, and where

Everything for one run lives in
`data/<principle>/<date>_<pass>_<probe>/<sensor_id>/`, e.g.
`data/9DTact/20260907_passB_ball8/9DTact_hard_3mm_r1/`. Three levels: the
sensor PRINCIPLE (9DTact, DIGIT, DIGIT_Marker), then one folder per pass and
probe, then one per sensor. No timestamps in folder names — the run's start
time is `run_timestamp` in `meta.yaml`, and every record below carries its own
time.

**One run per (pass, sensor).** A re-measurement is written to `<sensor_id>__2`
while it is being made, never into the existing folder. Once it is clear which
run is the one to analyse, the others are moved to
`data/_discarded/<principle>/<dataset>/<run>/` and the survivor's suffix is
stripped, so the tree carries exactly one folder per (pass, sensor) with a
uniform name. Which attempt a kept run was is recorded in its own `state.json`
as `run_dir_was`. **Nothing is deleted.**

`_discarded` sits one directory DEEPER than the dataset tree on purpose. Every
scan in the analysis code globs `data/*/*/state.json` and
`data/*/*/*/state.json`; a discarded run at
`data/_discarded/<principle>/<dataset>/<run>/state.json` is four levels down
and matches neither, so filing a run away removes it from run selection. The
one place that must still see it is the image-scale scan, which reads both
trees deliberately — an analysis result must not change because unused data was
tidied into a different folder, and on 2026-09-07 it did: moving four runs that
carried trusted scales shifted the median scale 4.9 % and moved the dip of
every unit that has no scale of its own. See `_discarded/README.md`.

```
<sensor_id>/
  meta.yaml            written at `newrun`: sensor id, run_timestamp, camera and
                       F/T config as loaded, the sensor→base transform used
  state.json           the run's live state, rewritten after every change
  reference.png        `reference`: unloaded gel, nothing touching
  touchcheck.png       `touchcheck`: first confirmed contact
  characterize/        `characterize`: one frame per step (NN.png) and steps.csv
                       (depth, force, image change, slope, region area/radius)
  contactmap/          `contactmap`: at_depth.png / at_force.png with _diff and
                       _mask images, and contactmap.yaml
  frames/NNNN.png      anchor samples (settled, one per rung) — see below
  stream/              `collect`: every frame, labelled — see below
  samples.csv          `summary`: the anchor table with derived columns
  summary.yaml         `summary`: fits and counts
```

## state.json

| key | written by | content |
|---|---|---|
| `tare` | `tare` | the software zero: wrench and gauge volts |
| `reference` | `reference` | file, wrench, image quality, stability, camera controls as read back |
| `samples[]` | `collect` (and the hand-driven phases) | one dict per **anchor** sample |
| `zero_checks[]` | `collect`, `zerocheck` | drift wrench at each off-gel check, with time |
| `stream` | `collect` | frame counts, cycles, rates, camera mode, speeds, policy |
| `contact_map` | `contactmap` | region size at 0.5 mm and at 0.5 N (also on the registry entry) |
| `step_timings_s`, `total_s` | `run_one_sensor` | seconds per step and the run total |
| `run_dir_was` | housekeeping | the folder name this run had before its attempt number was stripped |

## Registry fields written per sensor (`config/sensor_registry.yaml`)

`gel_model` (Hertz a, exponent, surface), `safe_force_N` / `safe_depth_mm`,
`stopped_on`, `image_response` (`max_measurable_force_N`, `reached`, peak
slope, the note when not reached), `contact_map` (`at_depth`, `at_force`: the
depth/force actually achieved, whether a limit bound it, and the region's
`area_px`, `radius_px`, `enclosing_radius_px`, `centroid_px`, mean |diff|),
`run`. Earlier characterisations of the same unit are appended to `history`.

An anchor sample records, at one settled moment: `image` (its file in
`frames/`), `image_time`, `wrench` (ATI sensor frame, tared), `tcp_mm` /
`tcp_rpy_deg` (robot base), `phase` (`force_series` / `force_shear`),
`force_target_N` or `shear_axis` + `shear_target_N`, `force_reached`,
`stop_reason`, `travel_used_mm`, `depth_mm`, `cycle`, and `stream_index` — the
index of the last stream frame saved before it, which ties the anchor to its
place in the continuous record.

## stream/ — the training data

Written by `collect`. The recorder saves every frame the camera delivers while
it is armed, up to the run's budget, then labels them all at the end.

```
stream/
  000001.png …         every frame (or .jpg = the camera's own bitstream in MJPG mode)
  frames.csv           one row per frame, the labels
  ft.csv               the raw F/T record, 50 Hz, whole phase
  pose.csv             the raw TCP pose record, ~50 Hz, whole phase
  zero_checks.csv      the off-gel zeros the drift correction interpolates between
```

### frames.csv columns

| column | meaning |
|---|---|
| `index`, `file` | frame number and file name |
| `missing` | true if the writer fell behind and the file is not on disk (never seen so far; counted, never renumbered) |
| `t_img` | wall time the frame was retrieved |
| `t_exposure_start` | `t_img` − exposure (205 ms in YUYV mode) |
| `segment` | `normal_load`, `normal_unload`, `dwell`, `shear_+X_out`, `shear_+X_back`, … |
| `cycle`, `axis`, `target_N` | which loading cycle, which shear axis, the force the ramp was heading for at that moment |
| `Fx_s … Tz_s` | **force label**: mean of the 20 ms F/T chunks whose midpoints fall in `[t_exposure_start, t_img]` — the force integrated over the same interval the camera integrated light. ATI sensor frame, tared at the start of `collect` |
| `Fx_s_corr … Tz_s_corr` | the same, minus the zero drift interpolated in time between `zero_checks.csv` rows |
| `Fx_base, Fy_base, Fz_base` | uncorrected force rotated into the robot base |
| `ft_chunks` | how many F/T chunks the label averaged (10 at 205 ms exposure). 0 means none fell inside the window and the nearest chunk was used |
| `tcp_x … rz` | TCP pose interpolated to `t_img` from the 20004 state stream (position linear, orientation nearest) |
| `pose_gap_s` | time to the nearest logged pose (under 20 ms) |
| `height_above_plane_mm`, `depth_mm` | tip height along the sensor normal, and `surface − height` (negative in air) |

Sign convention is the ATI sensor frame throughout: pressing on the gel gives
negative `Fz_s`; the anchors use the same frame, so `-Fz_s` is the normal load.

### What the labels are not

- They are not drift-free by construction: the zero is measured off the gel at
  the start, between the two blocks and at the end, and `_corr` interpolates
  linearly between those. Anything faster than that is in the label.
- Force and image are aligned by host wall-clock time. The F/T chunk timestamp
  is the host time its DAQ read returned (hardware-timed 2 kHz samples; ~1 ms
  latency); the frame time is the host time the read returned (USB latency of
  a few tens of ms, not measured). The residual misalignment is under one
  chunk at the motion speeds used.
- `depth_mm` is geometric, from the robot pose and the surface height the gel
  model recorded; it does not know the gel has crept.

## Budget and fairness

`capture_policy.frames_per_sensor` frames per run, split
`normal_fraction` : rest between the normal and shear blocks. The recorder caps
each block at its share, so the split is exact and the count is the same on
every sensor. `campaign.py --status` shows the count per sensor as `F`.

## Timing (measured 2026-09-04, soft 1 mm, YUYV 5 fps)

300 frames in 96 s of `collect`: 3 normal cycles of ~50 frames, one shear
cycle of ~150. Overall 3.1 frames/s including zero checks and the unrecorded
cycle tails. A 3000-frame run is therefore ~16 min of `collect`.
