#!/usr/bin/env python3
"""
Indentation run: one synchronised sample per invocation.

Each sample records, at the same moment, the VBTS image, the contact wrench,
and where the robot says the indenter tip is. The robot is never commanded --
the operator jogs it and this reads back.

    run_indentation.py --new  --note "0.5 mm depth series"   # open a run
    run_indentation.py --phase tare                          # zero, no contact
    run_indentation.py --phase reference                     # unloaded gel image
    run_indentation.py --phase sample                        # one sample, in contact
    run_indentation.py --phase zerocheck                     # between samples
    run_indentation.py --phase summary                       # curve and table

WHY A REFERENCE IMAGE
---------------------
A VBTS image means nothing on its own: what carries the contact is the
DIFFERENCE from the unloaded gel. The reference is captured with the same
locked camera settings in the same run, so subtracting it removes the
illumination pattern, the vignetting and the fixed-pattern noise together.
A reference borrowed from another run does not, because the settings and the
gel's rest state both move.

DEPTH
-----
Indentation depth is measured along the sensor's own normal, which the frame
transform gives in base coordinates, not along base -Z. The two differ by 1
degree here, so it barely matters for depth, but it matters for deciding
whether a sample was pressed straight in or dragged sideways.

Depth is reported relative to the contact origin. Finding that origin is not
"the first sample that touched": on soft gel the force rises gradually out of
the noise, so the first detectable contact is already indented. The origin is
found instead by fitting the force-depth curve and extrapolating to zero force.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import importlib.util


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cal = _load("cal", ROOT / "scripts" / "prepare_tcp_calibration.py")
chk = _load("chk", ROOT / "scripts" / "robot_readonly_check.py")
xf = _load("xf", ROOT / "scripts" / "measure_sensor_base_transform.py")
mv = _load("mv", ROOT / "scripts" / "move_probe.py")

from vbts_platform.ft_interface import FTInterface  # noqa: E402
from vbts_platform.camera_interface import Camera  # noqa: E402

# Runs are filed under the sensor they measured, not the minute they started.
# A timestamp in the folder name is redundant -- it is already in meta.yaml and
# in every sample -- and it makes the one thing you actually search by, which
# sensor this is, invisible from the listing.
# Named for the indenter, because the tip geometry is the experimental
# condition a tactile dataset is least able to recover from its own contents:
# a 4 mm ball and a flat punch at the same force produce different images and
# nothing in the frames says which was used.
DATASET = "20260905_passA"
OUT = ROOT / "data"
ACTIVE = OUT / "_active_run.txt"
TRANSFORMS = ROOT / "data" / "frame_transform"


def latest_transform() -> tuple[dict, Path]:
    runs = sorted(p for p in TRANSFORMS.glob("*/transform.yaml"))
    if not runs:
        raise SystemExit("no sensor->base transform; run measure_sensor_base_transform.py")
    return yaml.safe_load(open(runs[-1])), runs[-1]


def run_sensor_id(run: Path) -> str | None:
    """Which sensor this run belongs to, taken from its own meta."""
    try:
        return (yaml.safe_load(open(run / "meta.yaml")) or {}).get("sensor_id")
    except Exception:
        return None


def active_run() -> Path:
    if not ACTIVE.is_file():
        raise SystemExit("no active run; start one with --new")
    p = OUT / ACTIVE.read_text().strip()
    if not p.is_dir():
        raise SystemExit(f"active run {p} is missing; start one with --new")
    return p


def state_path(run: Path) -> Path:
    return run / "state.json"


def load_state(run: Path) -> dict:
    p = state_path(run)
    return json.loads(p.read_text()) if p.is_file() else {
        "tare": None, "reference": None, "samples": [], "zero_checks": []}


def save_state(run: Path, s: dict) -> None:
    state_path(run).write_text(json.dumps(s, indent=2))


def read_tared(ft: FTInterface, s: dict, duration_s: float) -> np.ndarray:
    w = ft.read_wrench_mean(duration_s=duration_s, tared=False)
    if not s.get("tare"):
        raise RuntimeError("no zero stored; --phase tare first")
    return w - np.array(s["tare"]["tare_wrench"], dtype=float)


def robot_state(ip: str) -> dict:
    from vbts_platform.robot_interface import RobotInterface
    r = RobotInterface(ip=ip, dry_run=False, allow_real_motion=False)
    r.connect(read_only=True)
    try:
        time.sleep(1.5)
        st = r.get_robot_state()
    finally:
        r.disconnect()
    return {"robot_state": st.robot_state, "robot_mode": st.robot_mode,
            "main_code": st.main_code, "sub_code": st.sub_code,
            "emergency_stop": st.emergency_stop, "collision_state": st.collision_state,
            "safety_stop0": st.safety_stop0, "safety_stop1": st.safety_stop1}


def robot_pose(ip: str) -> dict:
    q = chk.ReadOnlyProxy(ip)
    tool = q("GetActualTCPNum", 0)
    tcp = q("GetActualTCPPose", 0)
    coord = q("GetToolCoordWithID", tool[1]) if isinstance(tool, list) else None
    return {"active_tool": tool, "tcp_pose": tcp, "tool_coord": coord}


def probe_tilt_deg(tcp_rpy: list, sensor_normal: np.ndarray) -> float:
    """Angle between the indenter axis and the sensor normal.

    A spherical tip contacts the gel the same way whatever the shaft angle, so
    tilt does not spoil the contact itself. What it spoils is depth: a tilted
    36 mm printed shaft carries a lateral component of the press load and bends,
    moving the tip away from where the robot reports it. At 10 N and 10 degrees
    that component is 1.8 N, and the resulting deflection is the same size as
    the 0.1 mm depth steps being measured.
    """
    z_tool = cal.rpy_to_matrix(tcp_rpy[0], tcp_rpy[1], tcp_rpy[2])[:, 2]
    c = abs(float(z_tool @ sensor_normal)) / (np.linalg.norm(sensor_normal) or 1.0)
    return float(np.degrees(np.arccos(np.clip(c, -1, 1))))


def check_indenter_tool(p: dict) -> tuple[bool, str]:
    t = p["active_tool"]
    if not (isinstance(t, list) and len(t) > 1 and t[0] == 0):
        return False, f"could not read the active tool: {t}"
    if t[1] == 0:
        return False, ("active tool is 0, so the pose is the FLANGE, not the tip. "
                       "Select tool 1.")
    c = p["tool_coord"]
    if not (isinstance(c, list) and len(c) >= 4 and abs(c[3]) > 1.0):
        return False, f"tool {t[1]} does not look like the indenter: {c}"
    return True, f"tool {t[1]}, z offset {c[3]:.3f} mm"


def diff_level_for(ref_bgr, rel: float, floor: int) -> int:
    """Grey-level threshold for "this pixel deformed", scaled to the sensor.

    A fixed 6 levels meant 3.4 % of a 3 mm sensor reading 179 but 7.6 % of a
    1 mm one reading 79 -- and on that one the whole 0.5 mm contact fell under
    it and measured as zero area. Thresholding at a fraction of the reference
    brightness makes the region definition the same across sensors; the floor
    keeps it well above the ~0.4 level noise left after the blur.
    """
    g = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY)
    h, w = g.shape
    c = g[h // 4:3 * h // 4, w // 4:3 * w // 4]
    return int(max(floor, round(rel * float(c.mean()))))


def diff_level_for_sensor(ref_bgr, a, sensor: str | None) -> int:
    """`diff_level_for`, with the floor this principle's noise actually needs.

    The threshold is a fraction of the reference brightness, which on a DIGIT
    comes out at 4 levels -- far under its floor. A DIGIT is measured by the
    largest PER-CHANNEL deviation rather than a grey difference (see
    `contact_region`), and that reduction takes the worst of three noisy
    channels instead of averaging them, so its background sits higher: measured
    2026-09-08 on DIGIT_hard_3mm_r1 with the probe 2 mm above the gel and NOT
    touching, the blurred per-channel deviation had a median of 4.6, a sigma of
    1.8 and a 99.9th percentile of 12.9. A threshold of 10 found 813 px of
    "contact" on that empty frame; 12 found none. The floor is read from the
    registry so it stays with the data.
    """
    lvl = diff_level_for(ref_bgr, a.diff_rel, a.diff_min)
    reg, _ent = (load_sensor(sensor) if sensor else (None, None))
    pol = ((reg or {}).get("capture_policy") or {}).get("per_principle") or {}
    floor = (pol.get(principle_of(sensor) or "", {}) or {}).get("diff_level_min")
    return max(lvl, int(floor)) if floor else lvl


def contact_region(frame_bgr, ref_bgr, level: int = 6, blur: int = 5,
                   centre_frac: float = 0.5, border_frac: float = 0.05,
                   min_area: int = 200, colour: bool = False) -> dict:
    """Where, and how much, an image differs from the unloaded reference.

    The difference image is blurred (5 px Gaussian) so single-pixel noise does
    not count as contact, thresholded at `level` grey levels, and the largest
    connected blob is taken as the deformed region. Its area and equivalent
    radius are in PIXELS: no mm-per-pixel scale has been calibrated for this
    camera, and inventing one from the indenter geometry would make the
    number circular. `mean_abs_diff_centre` -- the mean |difference| over the
    central half of the frame -- is the single "how much did the image change"
    figure the saturation test tracks against force.
    """
    signed = None
    if colour:
        # A DIGIT encodes shape in the BALANCE of three coloured LEDs, so its
        # imprint is a colour change and grey throws it away: measured
        # 2026-09-08 on DIGIT_hard_3mm_r1, the channels move in OPPOSITE
        # directions under the probe (B -27.6, G -6.8, R +0.9 at 0.28 mm), the
        # per-channel peak grows 25 -> 53 levels down the ladder, and the
        # greyscale peak sits flat at 23 the whole way. Reduce by the largest
        # per-channel deviation instead.
        #
        # The per-channel MEAN is removed first because the probe shadows the
        # gel: the same unit darkened 2.7 levels with the probe 20 mm above the
        # gel, 5.2 at 5 mm and 7.2 in contact, WITHOUT touching, and then held
        # at 7.2-7.5 while the force went 0.02 -> 0.63 N. That pedestal is a
        # standoff effect, not a load, and it is bigger than the imprint under
        # it. A 9DTact lights its gel from inside a light guide, so nothing
        # outside can shadow it and neither correction applies there.
        f = frame_bgr.astype(np.float32) - ref_bgr.astype(np.float32)
        f -= f.mean(axis=(0, 1), keepdims=True)
        k = np.abs(f).argmax(axis=2)
        signed = np.take_along_axis(f, k[:, :, None], axis=2)[:, :, 0]
        d = np.abs(signed)
    else:
        g = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        r = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        d = np.abs(g - r)
    if blur and blur > 1:
        d = cv2.GaussianBlur(d, (blur | 1, blur | 1), 0)
    h, w = d.shape
    c0, c1 = int(h * (1 - centre_frac) / 2), int(h * (1 + centre_frac) / 2)
    k0, k1 = int(w * (1 - centre_frac) / 2), int(w * (1 + centre_frac) / 2)
    centre = d[c0:c1, k0:k1]
    mask = (d > level).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
    n, lab, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    # Blobs touching the frame border are vignetting flicker, not gel: with the
    # real contact under threshold at 0.25 N, the "largest blob" was 59 px at
    # x = 1908 of 1920. Contact happens under the probe, away from the edges,
    # and a region smaller than `min_area` is not a region.
    margin_x, margin_y = int(w * border_frac), int(h * border_frac)
    keep = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if x < margin_x or y < margin_y or x + bw > w - margin_x or y + bh > h - margin_y:
            continue
        if area < min_area:
            continue
        keep.append(i)
    out = {"level": level, "blur_px": blur,
           "mean_abs_diff_centre": float(centre.mean()),
           "max_diff": float(d.max()),
           "changed_fraction": float(mask.mean()),
           "area_px": 0, "radius_px": 0.0, "centroid_px": None, "bbox_px": None,
           "enclosing_radius_px": 0.0, "mean_abs_diff_in_region": 0.0,
           "n_blobs": len(keep), "min_area_px": min_area, "border_frac": border_frac}
    if keep:
        i = max(keep, key=lambda j: stats[j, cv2.CC_STAT_AREA])
        area = int(stats[i, cv2.CC_STAT_AREA])
        blob = (lab == i)
        pts = np.column_stack(np.nonzero(blob))[:, ::-1].astype(np.float32)
        (_cx, _cy), rad = cv2.minEnclosingCircle(pts)
        out.update({
            "area_px": area,
            "radius_px": float(np.sqrt(area / np.pi)),
            "enclosing_radius_px": float(rad),
            "centroid_px": [float(cents[i][0]), float(cents[i][1])],
            "bbox_px": [int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP]),
                        int(stats[i, cv2.CC_STAT_WIDTH]), int(stats[i, cv2.CC_STAT_HEIGHT])],
            "mean_abs_diff_in_region": float(d[blob].mean()),
        })
    # The 9DTact response is a dark core (gel pressed onto the membrane) with a
    # bright ring around it (gel bulging up). Past ~1.9 N on a 1 mm gel the two
    # touched and the "largest blob" doubled overnight while its mean |diff|
    # fell from 17 to 5 levels -- a merged region, not a bigger contact. The
    # signed halves are measured separately so the core radius stays a core.
    # The 9DTact split is on the grey difference; for a DIGIT it is on the
    # channel that moved most, which is the same quantity `d` was reduced from.
    sd = (g - r) if signed is None else signed
    if blur and blur > 1:
        sd = cv2.GaussianBlur(sd, (blur | 1, blur | 1), 0)
    for name, m in (("dark", sd < -level), ("bright", sd > level)):
        mm = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        nn, ll, ss, cc = cv2.connectedComponentsWithStats(mm, 8)
        ok = [i for i in range(1, nn)
              if ss[i, cv2.CC_STAT_AREA] >= min_area
              and ss[i, cv2.CC_STAT_LEFT] >= margin_x and ss[i, cv2.CC_STAT_TOP] >= margin_y
              and ss[i, cv2.CC_STAT_LEFT] + ss[i, cv2.CC_STAT_WIDTH] <= w - margin_x
              and ss[i, cv2.CC_STAT_TOP] + ss[i, cv2.CC_STAT_HEIGHT] <= h - margin_y]
        if ok:
            i = max(ok, key=lambda j: ss[j, cv2.CC_STAT_AREA])
            area = int(ss[i, cv2.CC_STAT_AREA])
            out[f"{name}_area_px"] = area
            out[f"{name}_radius_px"] = float(np.sqrt(area / np.pi))
            out[f"{name}_centroid_px"] = [float(cc[i][0]), float(cc[i][1])]
            out[f"{name}_mean_diff"] = float(sd[ll == i].mean())
        else:
            out[f"{name}_area_px"] = 0
            out[f"{name}_radius_px"] = 0.0
            out[f"{name}_centroid_px"] = None
            out[f"{name}_mean_diff"] = 0.0
    out["_diff"] = d
    out["_mask"] = mask * 255
    return out


def _region_public(r: dict) -> dict:
    return {k: v for k, v in r.items() if not k.startswith("_")}


def _mm_per_px() -> float | None:
    cfg = yaml.safe_load(open(ROOT / "config" / "camera_config.yaml")) or {}
    v = (cfg.get("calibration") or {}).get("mm_per_px")
    return float(v) if v else None


def shadows_the_gel(sensor: str | None) -> bool:
    """Does an approaching probe darken this principle's whole frame?

    True for the DIGIT family, whose three LEDs light the gel from the side so
    anything above it casts a shadow, and false for the 9DTact, whose light
    guide is inside the sensor. See `contact_region(drop_global=...)` for the
    measurement behind it.
    """
    pr = principle_of(sensor) or ""
    return pr.startswith("DIGIT")


def camera_config_for(sensor: str | None):
    """The camera file this unit's principle needs, or None for the default.

    The board is the same on every principle, so nothing stops a DIGIT run from
    opening `camera_config.yaml` and getting the 9DTact's 205 ms exposure --
    which on 2026-09-08 put 15 % of a DIGIT frame at 254-255 and blew the whole
    centre white. A DIGIT reads shape from the COLOUR of three LEDs, so a
    clipped channel is a lost normal, not a bright picture. Pick the file from
    the registry's `principle` and let it fail loudly if it is missing, rather
    than fall back to settings that quietly ruin the data.
    """
    if not sensor:
        # Not every phase is given --sensor: `run_one_sensor` calls the
        # reference phase with only --dataset, and on 2026-09-08 that opened
        # the first DIGIT with the 9DTact's 205 ms exposure and wrote a
        # reference whose centre was 41 % clipped. Recover the unit from the
        # run the phase is about to write into, so the config follows the DATA
        # rather than the argument list.
        try:
            sensor = (yaml.safe_load((active_run() / "meta.yaml").read_text())
                      or {}).get("sensor_id")
        except Exception:
            sensor = None
    pr = principle_of(sensor)
    if not pr or pr == "9DTact":
        return None
    f = ROOT / "config" / f"camera_{pr.lower()}.yaml"
    if f.exists():
        return f
    # DIGIT_Marker shares the DIGIT optics; only the gel carries markers.
    if pr.startswith("DIGIT"):
        f = ROOT / "config" / "camera_digit.yaml"
        if f.exists():
            return f
    raise SystemExit(f"no camera config for principle {pr!r} "
                     f"(expected config/camera_{pr.lower()}.yaml). Refusing to "
                     f"open a {pr} with another principle's exposure.")


def principle_of(sensor: str | None) -> str | None:
    """Which sensing principle a unit belongs to, from the registry.

    Datasets live at data/<principle>/<date>_passA_<probe>/<sensor>/ so the
    three families never share a directory. The principle is read from the
    registry rather than parsed off the id: "DIGIT_Marker_..." and "DIGIT_..."
    would need a prefix rule that the registry already answers correctly.
    """
    if not sensor:
        return None
    try:
        reg = yaml.safe_load(open(ROOT / "config" / "sensor_registry.yaml"))
    except Exception:
        return None
    for e in reg.get("sensors", []):
        if e["id"] == sensor:
            return e.get("principle")
    return None


def dataset_dir(dataset: str, sensor: str | None) -> Path:
    """data/<principle>/<dataset>, falling back to the old flat layout."""
    pr = principle_of(sensor)
    if pr:
        d = OUT / pr / dataset
        if d.exists() or not (OUT / dataset).exists():
            return d
    return OUT / dataset


def phase_new(a) -> int:
    tr, tr_path = latest_transform()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    name = a.sensor or a.note or stamp
    base_dir = dataset_dir(a.dataset, a.sensor)
    run = base_dir / name
    if run.exists() and any(run.iterdir()):
        # Never merge into an existing run folder. Remeasuring is normal --
        # this sensor was remeasured five times while the protocol was being
        # fixed -- and a stale tare or reference.png left behind by the last
        # attempt is worse than a duplicate folder, because nothing downstream
        # can tell it apart from one taken this morning.
        k = 2
        while (base_dir / f"{name}__{k}").exists():
            k += 1
        run = base_dir / f"{name}__{k}"
        print(f"  {name} already holds a run; this one goes to {run.name}")
    (run / "frames").mkdir(parents=True, exist_ok=True)
    cam_cfg = yaml.safe_load(open(ROOT / "config" / "camera_config.yaml"))
    ft_cfg = yaml.safe_load(open(ROOT / "config" / "ft_config.yaml"))
    (run / "meta.yaml").write_text(yaml.safe_dump({
        "started": datetime.now().isoformat(),
        "run_timestamp": stamp,
        "dataset": a.dataset,
        # Stamped on the run AND on every sample. Fifty-four runs eventually get
        # concatenated into one table, and a row that cannot say which sensor it
        # came from is not recoverable from anything else in the file.
        "sensor_id": a.sensor or (a.note or None),
        "note": a.note,
        "camera_config": cam_cfg,
        "ft_config": ft_cfg,
        "sensor_to_base_transform": {
            "source": str(tr_path),
            "rotation_sensor_to_base": tr["rotation_sensor_to_base"],
            "origin_base_mm": tr["origin_base_mm"],
            "residual_mm": tr["residual_position_equivalent_mm"]["rms"]},
        "frames": {"wrench": "ATI_sensor_frame", "pose": "robot_base",
                   "image": "VBTS internal camera"},
        "robot_commanded": False,
    }, sort_keys=False, allow_unicode=True))
    ACTIVE.parent.mkdir(parents=True, exist_ok=True)
    ACTIVE.write_text(str(run.relative_to(OUT)))
    print(f"  run opened: {run}")
    print(f"  transform from {tr_path}")
    print("\n  next: --phase tare (nothing touching), then --phase reference")
    return 0


def phase_tare(a) -> int:
    run = active_run()
    s = load_state(run)
    print("--- zero the F/T: the indenter must be clear of the gel ---\n")
    ft = FTInterface.from_config()
    ft.connect()
    try:
        w = ft.tare(duration_s=a.seconds)
        tv = ft.tare_volts
        check = ft.read_wrench_mean(duration_s=1.0, tared=True)
    finally:
        ft.disconnect()
    print(f"  residual after taring: |F| {np.linalg.norm(check[:3]):.4f} N  "
          f"|T| {np.linalg.norm(check[3:]):.6f} N*m")
    s["tare"] = {"at": datetime.now().isoformat(), "tare_wrench": w.tolist(),
                 "tare_volts": tv.tolist() if tv is not None else None}
    s["zero_checks"] = []
    save_state(run, s)
    print("\n  The zero drifts by roughly 0.0012 N*m per minute here. Re-run")
    print("  --phase zerocheck between samples so it can be interpolated out.")
    return 0


def phase_zerocheck(a) -> int:
    run = active_run()
    s = load_state(run)
    print("--- zero check: nothing may be touching the gel ---\n")
    ft = FTInterface.from_config()
    ft.connect()
    try:
        w = read_tared(ft, s, a.seconds)
    finally:
        ft.disconnect()
    print(f"  drift |F| {np.linalg.norm(w[:3]):.4f} N   "
          f"|T| {np.linalg.norm(w[3:]):.6f} N*m")
    s.setdefault("zero_checks", []).append(
        {"at": datetime.now().isoformat(), "drift_wrench": w.tolist()})
    save_state(run, s)
    return 0


def phase_reference(a) -> int:
    run = active_run()
    s = load_state(run)
    if not s.get("tare"):
        print("  --phase tare first")
        return 2
    print("--- reference: unloaded gel, nothing touching ---\n")
    # Camera first. Opening it takes about three seconds -- longer since the
    # driver queue was cut to one buffer -- and the DAQ task starts filling its
    # one-second buffer the moment it connects, so connecting first overruns it
    # (-200279) before anything reads.
    cam = Camera.from_config(camera_config_for(a.sensor))
    cam.open()
    ft = FTInterface.from_config()
    ft.connect()
    try:
        w = read_tared(ft, s, a.seconds)
        # The reference is the one frame every later picture is subtracted
        # from, and on DIGIT it was being grabbed too early. All 44 DIGIT runs
        # of 2026-09-08/09 have a reference 8-14 % brighter than every frame
        # after it, multiplicatively -- the sensor still on its previous
        # exposure in the first frames of the run's first open (9DTact, opened
        # with a longer settle, shows none of this). So: grab, sit through the
        # stability window, grab again, and only keep a reference that two
        # grabs 3 s apart agree on to 1 %. Otherwise keep grabbing.
        frame0, _ = cam.grab_settled()
        stab = cam.stability(3.0)
        frame, t_img = cam.grab_settled()
        m0, m1 = float(frame0.mean()), float(frame.mean())
        tries = 0
        while abs(m1 - m0) / max(m1, 1e-6) > 0.01 and tries < 6:
            print(f"  exposure still settling: {m0:.1f} -> {m1:.1f} "
                  f"({100 * (m1 - m0) / max(m0, 1e-6):+.1f} %), grabbing again")
            time.sleep(1.0)
            frame0, m0 = frame, m1
            frame, t_img = cam.grab_settled()
            m1 = float(frame.mean())
            tries += 1
        settle_pct = 100 * (m1 - m0) / max(m0, 1e-6)
        q = cam.quality(frame)
        controls = cam.read_controls()
    finally:
        cam.close()
        ft.disconnect()

    f = float(np.linalg.norm(w[:3]))
    print(f"  residual force {f:.4f} N   "
          + ("(clear)" if f < 0.3 else "<-- something IS touching; not a clean reference"))
    print(f"  image: centre mean {q['centre_mean']:.1f}, "
          f"saturated {q['centre_saturated_pct']:.3f} %, black {q['centre_black_pct']:.3f} %")
    print(f"  stability: frame-to-frame std {stab['frame_to_frame_std']:.4f} "
          f"at {stab['fps']:.1f} fps")
    if f >= 0.3:
        print("\n  NOT saved. Retract fully and re-run.")
        return 1
    if stab["frame_to_frame_std"] > 1.0:
        print("\n  the image brightness is not steady — auto exposure may have")
        print("  re-enabled itself. NOT saved.")
        return 1
    if abs(settle_pct) > 1.0:
        print(f"\n  the exposure did not settle ({settle_pct:+.1f} % between grabs "
              "3 s apart after six tries). NOT saved.")
        return 1
    print(f"  exposure settle check: {settle_pct:+.2f} % between two grabs 3 s apart")

    p = run / "reference.png"
    cv2.imwrite(str(p), frame, [cv2.IMWRITE_PNG_COMPRESSION, 1])
    s["reference"] = {"at": datetime.now().isoformat(), "file": p.name,
                      "wrench": w.tolist(), "quality": q, "stability": stab,
                      "settle_pct": settle_pct,
                      "camera_controls": controls, "image_time": t_img}
    save_state(run, s)
    print(f"\n  saved {p.name}")
    return 0


def phase_sample(a) -> int:
    run = active_run()
    s = load_state(run)
    if not s.get("reference"):
        print("  --phase reference first")
        return 2
    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2

    if a.drop:
        if not s["samples"]:
            print("  nothing to drop")
            return 1
        gone = s["samples"].pop()
        fp = run / "frames" / gone["image"]
        if fp.is_file():
            fp.unlink()
        save_state(run, s)
        print(f"  dropped sample {gone['index']}; {len(s['samples'])} remain")
        return 0

    pose = robot_pose(ip)
    ok, why = check_indenter_tool(pose)
    print(f"  tool check: {why}")
    if not ok:
        return 1
    st = robot_state(ip)
    if st["robot_state"] != 1 or st["main_code"] or st["emergency_stop"]:
        print(f"  robot is not in a settled stop: {st}")
        return 1

    meta = yaml.safe_load(open(run / "meta.yaml"))
    normal = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"])[:, 2]
    tilt = probe_tilt_deg(pose["tcp_pose"][4:7], normal)
    print(f"  probe tilt from the sensor normal: {tilt:.2f} deg")
    if tilt > a.max_tilt:
        print(f"\n  that exceeds {a.max_tilt} deg. A tilted shaft bends under load, so")
        print(f"  the tip is not where the robot says: at 10 N this tilt puts")
        print(f"  {10*np.sin(np.radians(tilt)):.2f} N sideways on the shaft.")
        print("  Straighten it (ry near 0) and re-run. NOT saved.")
        return 1

    # Camera first. Opening it takes about three seconds -- longer since the
    # driver queue was cut to one buffer -- and the DAQ task starts filling its
    # one-second buffer the moment it connects, so connecting first overruns it
    # (-200279) before anything reads.
    cam = Camera.from_config(camera_config_for(a.sensor))
    cam.open()
    ft = FTInterface.from_config()
    ft.connect()
    try:
        w1 = read_tared(ft, s, a.seconds)
        frame, t_img = cam.grab_settled()
        t_pose = time.time()
        pose2 = robot_pose(ip)
        w2 = read_tared(ft, s, a.seconds)
        q = cam.quality(frame)
    finally:
        cam.close()
        ft.disconnect()

    drift = float(np.linalg.norm(w2[:3] - w1[:3]))
    w = (w1 + w2) / 2.0
    F = w[:3]
    mag = float(np.linalg.norm(F))

    print(f"  F {np.round(F, 3)} N   |F| {mag:.3f} N")
    print(f"  T {np.round(w[3:], 5)} N*m")
    print(f"  force drift across the sample: {drift:.3f} N")
    print(f"  image centre mean {q['centre_mean']:.1f}, "
          f"saturated {q['centre_saturated_pct']:.3f} %")

    if mag < a.min_force:
        print(f"\n  {mag:.2f} N is below the {a.min_force} N contact threshold. NOT saved.")
        return 1
    if mag > a.max_force:
        print(f"\n  {mag:.2f} N exceeds the {a.max_force} N limit set for this run. NOT saved.")
        return 1
    if drift > a.max_drift:
        print(f"\n  the force moved {drift:.2f} N while sampling — still settling or")
        print("  the gel is relaxing. Hold longer and re-run. NOT saved.")
        return 1
    if q["centre_saturated_pct"] > 0.5:
        print(f"\n  {q['centre_saturated_pct']:.2f} % of the centre is saturated; the")
        print("  contact region is clipped and cannot be read. NOT saved.")
        return 1

    idx = len(s["samples"]) + 1
    name = f"{idx:04d}.png"
    cv2.imwrite(str(run / "frames" / name), frame,
                [cv2.IMWRITE_PNG_COMPRESSION, 1])
    tcp = pose2["tcp_pose"][1:]
    s["samples"].append({
        "index": idx, "sensor_id": run_sensor_id(run),
        "at": datetime.now().isoformat(),
        "image": name, "image_time": t_img, "pose_time": t_pose,
        "wrench": w.tolist(), "wrench_first": w1.tolist(), "wrench_second": w2.tolist(),
        "force_drift_N": drift,
        "tcp_mm": tcp[:3], "tcp_rpy_deg": tcp[3:],
        "active_tool": pose2["active_tool"],
        "image_quality": q, "label": a.label,
        "probe_tilt_deg": tilt,
    })
    save_state(run, s)
    print(f"\n  sample {idx} saved ({name})")
    print(f"    tip in base : {np.round(tcp[:3], 3)} mm")
    return 0


def phase_series(a) -> int:
    """Drive a depth series: step down, record a full sample at each depth.

    Starts by retracting clear of the gel, then descends. The retraction is the
    point: the search stops once it has felt a contact, which on soft gel means
    it is already indented -- here by 0.27 mm. Recording from there would give a
    curve with no shallow end, and the contact origin is found by extrapolating
    the shallow end to zero force. Backing off first buys those points.

    Retracting also means the series is a clean loading curve from rest rather
    than a continuation of the search's own loading.
    """
    from vbts_platform.ft_stream import ForceReader

    run = active_run()
    s = load_state(run)
    if not s.get("reference"):
        print("  --phase reference first")
        return 2
    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2
    st = mv.read_state(ip)
    ok, why = mv.ready_to_move(st)
    if not ok:
        print(f"  not moving: {why}")
        return 2

    q = chk.ReadOnlyProxy(ip)
    pose0 = q("GetActualTCPPose", 0)[1:]
    ok, why = check_indenter_tool(robot_pose(ip))
    print(f"  tool check: {why}")
    if not ok:
        return 1
    meta = yaml.safe_load(open(run / "meta.yaml"))
    normal = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"])[:, 2]
    tilt = probe_tilt_deg(pose0[3:6], normal)
    print(f"  probe tilt {tilt:.2f} deg")
    if tilt > a.max_tilt:
        print(f"  exceeds {a.max_tilt} deg; straighten the probe first.")
        return 1

    # Camera first. Opening it takes about three seconds -- longer since the
    # driver queue was cut to one buffer -- and the DAQ task starts filling its
    # one-second buffer the moment it connects, so connecting first overruns it
    # (-200279) before anything reads.
    cam = Camera.from_config(camera_config_for(a.sensor))
    cam.open()
    ft = FTInterface.from_config()
    ft.connect()
    reader = None
    try:
        tare = np.array(s["tare"]["tare_wrench"], dtype=float)
        reader = ForceReader(ft, tare).start()

        print(f"\n--- retracting {a.retract} mm to start above the gel ---")
        rv = _move_along_normal(ip, +a.retract, a, a.approach_joint_step, vel=a.vel_free)
        if rv != 0:
            return rv
        time.sleep(a.settle)
        w, err = reader.read_fresh()
        resid = float(np.linalg.norm(w[:3]))
        print(f"  force after retracting: {resid:.3f} N")
        if resid > 0.15:
            print("  still loaded — the retraction did not clear the gel. Stopping")
            print("  rather than zeroing against a contact.")
            return 1

        # Re-zero here, clear of the gel and immediately before descending.
        # The stored zero is minutes old by now -- searching and aligning take
        # time -- and this F/T drifts about 0.0012 N*m per minute. On a curve
        # whose full scale is under a newton, a stale zero is a large fraction
        # of the signal.
        print("\n--- re-zeroing, clear of the gel ---")
        reader.stop()
        fresh = ft.tare(duration_s=2.0)
        chk_w = ft.read_wrench_mean(duration_s=1.0, tared=True)
        print(f"  residual |F| {np.linalg.norm(chk_w[:3]):.4f} N")
        s["tare_at_series"] = {"at": datetime.now().isoformat(),
                               "tare_wrench": fresh.tolist(),
                               "replaces": s["tare"]["at"]}
        save_state(run, s)
        reader = ForceReader(ft, fresh).start()

        n_steps = int(round((a.retract + a.max_depth) / a.depth_step))
        print(f"\n--- {n_steps} steps of {a.depth_step} mm ---")
        print(f"  {'#':>3} {'height':>8} {'Fz':>8} {'|F|':>8} {'img centre':>11}")
        for k in range(n_steps):
            rv = _move_along_normal(ip, -a.depth_step, a)
            if rv != 0:
                return rv
            time.sleep(a.settle)
            w, err = reader.read_fresh()
            if err:
                print(f"\n  F/T failed: {err}")
                return 1
            F = w[:3]
            mag = float(np.linalg.norm(F))
            if mag > a.max_force:
                print(f"\n  ABORT: {mag:.2f} N over the {a.max_force} N limit.")
                break
            frame, t_img = cam.grab_settled()
            qual = cam.quality(frame)
            pose = q("GetActualTCPPose", 0)[1:]
            t0v, nv = mv.sensor_axis()
            h = float((np.array(pose[:3]) - t0v) @ nv)
            idx = len(s["samples"]) + 1
            name = f"{idx:04d}.png"
            cv2.imwrite(str(run / "frames" / name), frame,
                        [cv2.IMWRITE_PNG_COMPRESSION, 1])
            s["samples"].append({
                "index": idx, "sensor_id": run_sensor_id(run), "at": datetime.now().isoformat(),
                "image": name, "image_time": t_img, "pose_time": time.time(),
                "wrench": w.tolist(), "wrench_first": w.tolist(),
                "wrench_second": w.tolist(), "force_drift_N": 0.0,
                "tcp_mm": pose[:3], "tcp_rpy_deg": pose[3:],
                "active_tool": q("GetActualTCPNum", 0),
                "image_quality": qual, "label": a.label or f"step{k+1}",
                "probe_tilt_deg": tilt,
                "height_above_plane_mm": h, "commanded": True,
            })
            save_state(run, s)
            print(f"  {idx:>3} {h:>8.3f} {F[2]:>8.3f} {mag:>8.3f} "
                  f"{qual['centre_mean']:>11.1f}"
                  + ("   SATURATED" if qual["centre_saturated_pct"] > 0.5 else ""))
    finally:
        if reader is not None:
            reader.stop()
        cam.close()
        ft.disconnect()
    print(f"\n  {len(s['samples'])} sample(s) in the run.")
    print("  retract, then --phase zerocheck, then --phase summary")
    return 0


# Speed (%) for any move that travels AWAY from the gel. The descent keeps
# whatever the caller asked for, because that is where contact happens.
UP_VEL = 100.0


def _move_along_normal(ip: str, mm: float, a, ceiling: float | None = None,
                       vel: float | None = None) -> int:
    """One commanded move along the sensor normal. Positive is away from the gel.

    `ceiling` is the joint-change limit. It exists to catch an inverse-kinematics
    solution that reconfigures the arm rather than stepping it -- measured on this
    robot, a wrong branch moves a joint by over 200 degrees. The limit therefore
    has to scale with how far the move actually travels: 0.1 mm turns the largest
    joint by 0.0135 degrees, but the 8 mm approach to the working depth turns it
    by about 1.1, which is a perfectly ordinary move and not a reconfiguration.
    Probe steps keep the tight default; positioning moves pass their own.
    """
    q = chk.ReadOnlyProxy(ip)
    pose = q("GetActualTCPPose", 0)[1:]
    _, n = mv.sensor_axis()
    p = np.array(pose[:3]) + mm * n
    target = [float(p[0]), float(p[1]), float(p[2])] + [float(v) for v in pose[3:]]
    pl = mv.plan(ip, target, ceiling if ceiling is not None else a.max_joint_step)
    if not pl.get("ok"):
        print(f"  refusing the move: {pl.get('why')}")
        return 2
    tool = pl["active_tool"][1] if isinstance(pl["active_tool"], list) else 1
    _v = vel if vel is not None else a.vel
    if mm > 0:
        # Away from the gel: nothing is measured on the way up and there is
        # nothing to run into, so it goes at UP_VEL instead of the velocity the
        # descent needs (operator, 2026-09-10). Only mm > 0 takes this branch,
        # so contact velocity is untouched.
        _v = max(_v, UP_VEL)
    rv = mv.send_movel(ip, pl["target_joints"], pl["target_pose"], tool,
                       _v, a.ovl)
    if rv != 0:
        print(f"  MoveL returned {rv}")
        return 1
    return 0


def phase_shear(a) -> int:
    """Indent to a depth, then shear laterally in four directions.

    Each direction is walked out in small steps rather than jumped, because the
    interesting thing is the shape of the curve, not its endpoint. A contact
    that grips gives force rising with displacement; one that slips gives a
    plateau. A single measurement at 0.3 mm cannot tell those apart, and on this
    gel slip is likely: at 0.5 mm depth the normal force is only 0.62 N, so the
    friction limit is a few tenths of a newton — about what 0.3 mm of shear
    produces.

    Shear runs along the SENSOR's own axes, not the base frame's. The sensor is
    rotated about 30 degrees about vertical, so shearing along base X would
    split the force across Fx and Fy for no reason. Along sensor X the signal
    lands in Fx alone.

    The order is +X, -X, -Y, +Y, and the centre is re-measured between each.
    Gel creeps, so a straight +X, -X, +Y, -Y order would let elapsed time
    masquerade as a direction difference; alternating the second pair puts the
    time trend across the directions instead of along them. The centre
    measurements record that trend, and they also say whether the contact came
    back — if the force does not return to its normal-only value, the gel took a
    set or the tip slipped.
    """
    from vbts_platform.ft_stream import ForceReader

    run = active_run()
    st_run = load_state(run)
    if not st_run.get("reference"):
        print("  --phase reference first")
        return 2
    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2
    st = mv.read_state(ip)
    ok, why = mv.ready_to_move(st)
    if not ok:
        print(f"  not moving: {why}")
        return 2

    # Where the gel surface is, from the depth series that already ran.
    surf = a.surface
    if surf is None:
        prev = sorted(list((ROOT / "data").glob("*/*/summary.yaml"))
                      + list((ROOT / "data").glob("*/*/*/summary.yaml")))
        for f in reversed(prev):
            y = yaml.safe_load(open(f))
            fit = (y or {}).get("force_depth_fit") or {}
            if fit.get("gel_surface_height_mm"):
                surf = float(fit["gel_surface_height_mm"])
                print(f"  gel surface {surf:.3f} mm, from {f.parent.name}")
                break
    if surf is None:
        print("  no gel surface known. Run a depth series first, or pass --surface.")
        return 2

    meta = yaml.safe_load(open(run / "meta.yaml"))
    R = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"])
    n = R[:, 2]
    axes = {"+X": R[:, 0], "-X": -R[:, 0], "+Y": R[:, 1], "-Y": -R[:, 1]}
    q = chk.ReadOnlyProxy(ip)
    t_sensor, _ = mv.sensor_axis()

    def height() -> float:
        p = np.array(q("GetActualTCPPose", 0)[1:][:3])
        return float((p - t_sensor) @ n)

    okt, whyt = check_indenter_tool(robot_pose(ip))
    print(f"  tool check: {whyt}")
    if not okt:
        return 1
    tilt = probe_tilt_deg(q("GetActualTCPPose", 0)[1:][3:6], n)
    print(f"  probe tilt {tilt:.2f} deg")
    if tilt > a.max_tilt:
        return 1

    # The F/T task is opened AFTER the move that clears the gel. It acquires
    # continuously once open, and a blocking MoveL takes seconds during which
    # nothing would be draining it -- long enough to overrun the buffer and have
    # the driver kill the task. Nothing needs a force reading until the gel is
    # cleared, so the task simply does not exist until then.
    h_now = height()
    clearance = surf + a.retract - h_now
    if clearance > 0:
        print(f"\n--- rising {clearance:.3f} mm to clear the gel ---")
        if _move_along_normal(ip, clearance, a, a.approach_joint_step, vel=a.vel_free):
            return 2
    else:
        print(f"\n--- already {h_now - surf:.3f} mm above the surface ---")

    # Camera first. Opening it takes about three seconds -- longer since the
    # driver queue was cut to one buffer -- and the DAQ task starts filling its
    # one-second buffer the moment it connects, so connecting first overruns it
    # (-200279) before anything reads.
    cam = Camera.from_config(camera_config_for(a.sensor))
    cam.open()
    ft = FTInterface.from_config()
    ft.connect()
    reader = None
    try:
        time.sleep(a.settle)
        print("--- re-zeroing, clear of the gel ---")
        tare = ft.tare(duration_s=2.0)
        chkw = ft.read_wrench_mean(duration_s=1.0, tared=True)
        print(f"  residual |F| {np.linalg.norm(chkw[:3]):.4f} N")
        if np.linalg.norm(chkw[:3]) > 0.15:
            print("  not clear of the gel; refusing to zero against a contact.")
            return 1
        reader = ForceReader(ft, tare).start()

        target_h = surf - a.depth
        drop = height() - target_h
        print(f"\n--- descending {drop:.3f} mm to {a.depth} mm depth ---")
        if _move_along_normal(ip, -drop, a, a.approach_joint_step):
            return 2
        time.sleep(a.settle)
        w, _ = reader.read_fresh()
        fz = -float(w[2])
        print(f"  normal force {fz:.3f} N at height {height():.3f} mm")
        if a.expect_n and abs(fz - a.expect_n) > max(0.3, 0.5 * a.expect_n):
            print(f"  expected about {a.expect_n:.2f} N. The gel surface may have")
            print("  moved since the depth series. Stopping rather than guessing.")
            return 1

        centre = q("GetActualTCPPose", 0)[1:]

        def grab(label: str, lat_mm: float, axis: str) -> bool:
            time.sleep(a.settle)
            w, err = reader.read_fresh()
            if err:
                print(f"  F/T failed: {err}")
                return False
            # The ATI calibration already reports in the sensor frame, so this
            # is the shear resolved on the axes being commanded. Multiplying by
            # R.T here would rotate an already-sensor-frame vector by the
            # sensor's azimuth a second time.
            fs = w[:3]
            lat = float(np.linalg.norm(fs[:2]))
            if abs(fs[2]) > a.max_force or lat > a.max_shear:
                print(f"  ABORT: normal {abs(fs[2]):.2f} N / shear {lat:.2f} N "
                      "over limit")
                return False
            frame, t_img = cam.grab_settled()
            qual = cam.quality(frame)
            pose = q("GetActualTCPPose", 0)[1:]
            idx = len(st_run["samples"]) + 1
            name = f"{idx:04d}.png"
            cv2.imwrite(str(run / "frames" / name), frame,
                        [cv2.IMWRITE_PNG_COMPRESSION, 1])
            st_run["samples"].append({
                "index": idx, "sensor_id": run_sensor_id(run), "at": datetime.now().isoformat(), "image": name,
                "image_time": t_img, "pose_time": time.time(),
                "wrench": w.tolist(), "wrench_first": w.tolist(),
                "wrench_second": w.tolist(), "force_drift_N": 0.0,
                "tcp_mm": pose[:3], "tcp_rpy_deg": pose[3:],
                "active_tool": q("GetActualTCPNum", 0),
                "image_quality": qual, "label": label,
                "probe_tilt_deg": tilt, "commanded": True,
                "phase": "shear", "shear_axis": axis,
                "shear_command_mm": lat_mm, "depth_mm": a.depth,
                "height_above_plane_mm": height(),
                "force_sensor_axes": fs.tolist(),
            })
            save_state(run, st_run)
            print(f"  {idx:>3} {label:<12} {lat_mm:>+7.3f} "
                  f"Fx {fs[0]:>+7.3f} Fy {fs[1]:>+7.3f} Fz {fs[2]:>+7.3f} "
                  f"|shear| {lat:>6.3f}")
            return True

        def slipped(hist: list, k0: float) -> bool:
            """Has the contact stopped gripping?

            A gripping contact's force tracks displacement. Once static friction
            is exceeded the tip slides and the force flattens: displacement
            keeps going, force does not.

            The test is on the LOCAL slope, not on the force itself. Comparing
            the force against what the initial slope predicts only trips once
            the prediction has grown past the plateau, which on a contact that
            let go at 0.5 mm takes until 0.9 mm — 0.4 mm of dragging after the
            answer was already available. The local slope collapses at the
            moment of slip instead.

            Measured over a four-step window, and required twice running, so the
            per-step noise (about 0.02 N against increments of 0.03) cannot fire
            it on its own.

            Stopping here is the point. The friction limit is the quantity worth
            having; dragging a sphere further across the gel adds no measurement
            and does wear the surface.
            """
            win = a.slip_window
            if k0 <= 0 or len(hist) < a.slip_after + win + 1:
                return False
            slopes = []
            for end in (len(hist), len(hist) - 1):
                seg = hist[end - win - 1:end]
                dd = seg[-1][0] - seg[0][0]
                slopes.append((seg[-1][1] - seg[0][1]) / dd if dd > 0 else 0.0)
            return all(sl < a.slip_ratio * k0 for sl in slopes)

        print(f"\n  {'#':>3} {'label':<12} {'cmd mm':>7} "
              f"{'Fx':>10} {'Fy':>10} {'Fz':>10} {'|shear|':>7}")
        if not grab("centre-0", 0.0, "none"):
            return 1

        for k, axis in enumerate(a.order.split(","), 1):
            axis = axis.strip()
            if axis not in axes:
                print(f"  unknown axis {axis}")
                return 2
            v = axes[axis]
            uax = np.array([np.cos(np.radians({"+X": 0.0, "-X": 180.0,
                                               "+Y": 90.0, "-Y": -90.0}[axis])),
                            np.sin(np.radians({"+X": 0.0, "-X": 180.0,
                                               "+Y": 90.0, "-Y": -90.0}[axis]))])
            hist: list = []
            k0 = 0.0
            slip_at = None
            for j in range(a.shear_steps):
                p = np.array(q("GetActualTCPPose", 0)[1:][:3]) + a.shear_step * v
                pose = q("GetActualTCPPose", 0)[1:]
                tgt = [float(p[0]), float(p[1]), float(p[2])] + \
                      [float(x) for x in pose[3:]]
                pl = mv.plan(ip, tgt, a.max_joint_step)
                if not pl.get("ok"):
                    print(f"  refusing the step: {pl.get('why')}")
                    return 2
                tool = pl["active_tool"][1] if isinstance(pl["active_tool"], list) else 1
                if mv.send_movel(ip, pl["target_joints"], pl["target_pose"], tool,
                                 a.vel, a.ovl) != 0:
                    return 1
                if not grab(f"{axis}", a.shear_step * (j + 1), axis):
                    return 1
                last = st_run["samples"][-1]
                d_cmd = a.shear_step * (j + 1)
                f_ax = float(np.array(last["wrench"][:2]) @ uax)
                hist.append((d_cmd, f_ax))
                if len(hist) == a.slip_after:
                    dd = np.array([h[0] for h in hist])
                    ff = np.array([h[1] for h in hist])
                    # Fit WITH an intercept. Each direction starts from whatever
                    # shear the previous one left behind -- 0.18 N here -- and a
                    # through-origin fit charges that offset to the slope. On +Y
                    # that inflated k0 from 0.71 to 1.94 N/mm, and the healthy
                    # slope that followed then read as a collapse. The offset is
                    # a starting condition, not stiffness.
                    A = np.vstack([dd, np.ones(dd.size)]).T
                    k0, off = np.linalg.lstsq(A, ff, rcond=None)[0]
                    k0 = float(k0)
                    print(f"      initial slope {k0:.3f} N/mm "
                          f"(offset {off:+.3f} N) — slip watch armed")
                if a.stop_on_slip and slipped(hist, k0):
                    slip_at = d_cmd
                    print(f"      SLIP at {d_cmd:.2f} mm: force {f_ax:.3f} N is below "
                          f"{a.slip_ratio:.0%} of the {k0*d_cmd:.3f} N the initial")
                    print(f"      slope predicts. Stopping this direction — the "
                          "friction limit is the measurement.")
                    last["slip_detected"] = True
                    last["slip_at_mm"] = d_cmd
                    save_state(run, st_run)
                    break

            # Straight back to the pose the shear started from.
            pl = mv.plan(ip, centre, a.max_joint_step)
            if not pl.get("ok"):
                print(f"  refusing the return: {pl.get('why')}")
                return 2
            tool = pl["active_tool"][1] if isinstance(pl["active_tool"], list) else 1
            if mv.send_movel(ip, pl["target_joints"], pl["target_pose"], tool,
                             a.vel, a.ovl) != 0:
                return 1
            if not grab(f"centre-{k}", 0.0, "none"):
                return 1
    finally:
        if reader is not None:
            reader.stop()
        cam.close()
        ft.disconnect()
    print(f"\n  {len(st_run['samples'])} sample(s) in the run.")
    print("  retract, then --phase zerocheck, then --phase shear-summary")
    return 0


def _force_targets(fmin: float, fmax: float, step: float) -> list:
    """Force levels to visit, at a fixed spacing in force.

    Even spacing in DISPLACEMENT is the wrong grid for a force-estimation
    dataset. The contact is Hertzian, F proportional to delta^1.5, so equal
    depth steps crowd samples into the low-force end and leave the high end
    sparse -- the 1 mm run put eleven of its samples under 2.4 N with the last
    four spanning nearly a newton each. Spacing the TARGETS in force and solving
    for the depth that reaches each one inverts that.
    """
    n = int(round((fmax - fmin) / step)) + 1
    return [round(fmin + step * i, 4) for i in range(n) if fmin + step * i <= fmax + 1e-9]


def _seek_force(ip, a, reader, axis_vec, target, measure, model_step,
                travel_used, travel_limit, force_cap, tag,
                travel_origin=None, hold=None) -> tuple:
    """Move along `axis_vec` until the measured force reaches `target`.

    Open-loop from a model, then corrected: the model predicts a step, the step
    is taken, the force is measured, and the remaining error drives the next
    step. The model only has to be roughly right -- it sets the first guess and
    keeps the correction from overshooting.

    Returns (reached, force, travel_used, why). `why` says which limit stopped
    it, because with a soft gel the travel limit and the force target routinely
    disagree about which comes first, and a dataset that silently stopped short
    of its stated maximum is worse than one that says so.
    """
    q = chk.ReadOnlyProxy(ip)
    # Travel is measured against where this seek started, projected on the axis
    # it is moving along. Accumulating the commanded steps instead let the real
    # displacement drift away from the number the limit is checked against --
    # 0.217 mm over 39 steps elsewhere in this file. A limit applied to a
    # quantity that is not the one being limited is not a limit.
    # The origin has to be the start of the whole ladder, not of this one seek.
    # Measuring from a fresh origin each time reset the count to zero at every
    # target, so the limit was applied to a single target's movement while the
    # accumulated depth walked past it -- 0.747 mm against a 0.70 mm ceiling.
    origin = (np.array(travel_origin) if travel_origin is not None
              else np.array(q("GetActualTCPPose", 0)[1:][:3]))
    # `hold` closes a second loop, on the NORMAL force, while this one works
    # the lateral force. Shearing lifts the contact and the gel creeps, so a
    # depth fixed at the start sags: 12-13 % of the load on 3 mm gels and
    # 29-40 % on 1 mm ones across four axes. Re-seating between axes corrects
    # that after the fact; pushing in as it happens means it never happens, and
    # it costs no extra moves -- the correction rides on the step already being
    # sent.
    hold_offset = 0.0
    hold_vec = (np.asarray(hold["vec"], dtype=float) if hold is not None
                else np.zeros(3))
    # Orientation is anchored for the same reason position is: handing each
    # move the LAST achieved RPY chains the servo's angular error, and the
    # probe tilt reached 2.04 degrees over one collect -- under the 3 degree
    # gate, so nothing complained, while a tilted 36 mm shaft bends and puts
    # the tip somewhere other than where the robot reports.
    rpy0 = [float(v) for v in q("GetActualTCPPose", 0)[1:][3:]]

    def measured_travel() -> float:
        p_now = np.array(q("GetActualTCPPose", 0)[1:][:3])
        return float((p_now - origin) @ axis_vec)

    travel_used = measured_travel()
    last = None                      # (travel, force) of the previous step
    for _ in range(a.seek_iters):
        f = measure()
        err = target - f
        if abs(err) <= a.force_tol:
            return True, f, travel_used, "reached"
        # The cap means "do not push in past this", not "stop doing anything".
        # It used to return on force alone, so once a contact was over the cap
        # every mechanism that could have pulled it back gave up -- including
        # the re-seat that starts each shear cycle. Measured 2026-09-08 on
        # DIGIT_Marker_soft_2mm_r1 (ball8, 1.20 N hold, 2.0 N cap): the shear
        # block started each cycle wherever the last one ended, and the depth
        # walked 0.485 -> 0.788 mm over twelve cycles while the normal force
        # went 2.9 -> 6.5 N, four times the hold, with the re-seat returning
        # "force cap" every time and never once retracting. Retracting is
        # always safe; only the inward direction is capped.
        if f >= force_cap and err > 0:
            return False, f, travel_used, f"force cap {force_cap} N"
        step = model_step(f, target)

        # Bound the step by how much FORCE it can add, not just by distance.
        # The distance cap alone is calibrated against one gel. A thinner or
        # harder elastomer sits closer to its rigid backing and stiffens
        # sharply, so the same 0.25 mm that adds 0.6 N here could add several
        # newtons there -- past the cap in a single move, with the check only
        # happening afterwards. Measuring the local stiffness from the step just
        # taken and sizing the next one to add at most `seek_max_dforce` keeps
        # the overshoot bounded on a gel whose model is wrong or unknown.
        if last is not None:
            dt = travel_used - last[0]
            if abs(dt) > 1e-4:
                k_local = abs((f - last[1]) / dt)
                if k_local > 1e-6:
                    step = float(np.clip(step, -a.seek_max_dforce / k_local,
                                         a.seek_max_dforce / k_local))
        elif step > a.seek_first_step:
            # No previous step means no stiffness estimate, and the model is
            # the only guide -- which is exactly the situation where it may be
            # badly wrong. The first move into an unknown elastomer is a
            # deliberate small probe: it costs one iteration and it is what
            # makes the force-based bound above possible at all.
            step = a.seek_first_step
        last = (travel_used, f)
        step = float(np.clip(step, -a.seek_max_step, a.seek_max_step))
        if abs(step) < 1e-4:
            return False, f, travel_used, "step underflow"
        # Aim short of the limit, not at it. Clamping the step so it lands
        # exactly on the limit puts the tip past it by whatever the servo
        # misses by -- under load that ran to 27 um, so a 1.000 mm ceiling
        # was recorded as 1.027 mm on four shear rungs.
        stop_at = travel_limit - a.travel_margin
        if travel_used + step > stop_at:
            step = stop_at - travel_used
            if step <= 1e-4:
                return False, f, travel_used, f"travel limit {travel_limit} mm"
        pose = q("GetActualTCPPose", 0)[1:]
        # Target from the ORIGIN plus the travel wanted, not from wherever the
        # last move happened to land. Chaining "read the pose, add a step"
        # accumulates MoveL's own Cartesian bias: about 3 um a move, invisible
        # over the 150 moves the old ladder took, but 6.1 mm of drift across
        # the 2000+ moves a 10-cycle collect makes -- the contact walked right
        # across the gel while every force reading still looked correct.
        if hold is not None:
            fz_now = hold["measure"]()
            if abs(hold["target"] - fz_now) > a.force_tol:
                d_now = max(hold["depth"](), 0.0)
                d_want = (max(hold["target"], 0.0) / hold["a_h"]) ** (2.0 / 3.0)
                dz = float(np.clip(d_want - d_now, -hold["max_step"],
                                   hold["max_step"]))
                if 0.0 <= d_now + dz <= hold["depth_cap"]:
                    hold_offset += dz
        p = origin + (travel_used + step) * axis_vec + hold_offset * hold_vec
        tgt = [float(p[0]), float(p[1]), float(p[2])] + rpy0
        pl = mv.plan(ip, tgt, a.max_joint_step)
        if not pl.get("ok"):
            return False, f, travel_used, f"refused: {pl.get('why')}"
        tool = pl["active_tool"][1] if isinstance(pl["active_tool"], list) else 1
        if mv.send_movel(ip, pl["target_joints"], pl["target_pose"], tool,
                         a.vel, a.ovl) != 0:
            return False, f, travel_used, "MoveL failed"
        time.sleep(a.settle)
        travel_used = measured_travel()
    return False, measure(), travel_used, f"{a.seek_iters} iterations"


def _hold_spec(n, target, measure_n, a_h, depth_fn, depth_cap, max_step=0.04):
    """Arguments for `_seek_force`'s normal-force loop."""
    return {"vec": -np.asarray(n, dtype=float), "target": float(target),
            "measure": measure_n, "a_h": float(a_h), "depth": depth_fn,
            "depth_cap": float(depth_cap), "max_step": float(max_step)}


def phase_force_series(a) -> int:
    """Normal-force ramp: visit a list of force levels, recording at each."""
    from vbts_platform.ft_stream import ForceReader

    run = active_run()
    st_run = load_state(run)
    if not st_run.get("reference"):
        print("  --phase reference first")
        return 2
    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2
    ok, why = mv.ready_to_move(mv.read_state(ip))
    if not ok:
        print(f"  not moving: {why}")
        return 2

    surf, a_h = _gel_model(a)
    if surf is None:
        return 2
    depth_cap, force_cap, _reg, ent = sensor_limits(a)
    if ent:
        print(f"  sensor {ent['id']}: {ent['thickness_mm']} mm {ent['hardness']}")
        print(f"    depth backstop {depth_cap:.1f} mm (no per-thickness limit), "
              f"characterised ceiling {ent['safe_force_N']:.2f} N")
    meta = yaml.safe_load(open(run / "meta.yaml"))
    R = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"])
    n = R[:, 2]
    q = chk.ReadOnlyProxy(ip)
    t_sensor, _ = mv.sensor_axis()

    reach = (force_cap / a_h) ** (2.0 / 3.0)
    print(f"\n  gel model  F = {a_h:.3f} * depth^1.5,  surface {surf:.3f} mm")
    print(f"  binding limits: {depth_cap:.2f} mm depth, {force_cap:.2f} N force")
    print(f"  {force_cap:.2f} N needs {reach:.2f} mm")
    if reach > depth_cap:
        print(f"  -> the DEPTH limit binds first. Expect to stop near "
              f"{a_h * depth_cap ** 1.5:.2f} N.")

    def height():
        return float((np.array(q("GetActualTCPPose", 0)[1:][:3]) - t_sensor) @ n)

    okt, whyt = check_indenter_tool(robot_pose(ip))
    print(f"  tool check: {whyt}")
    if not okt:
        return 1
    tilt = probe_tilt_deg(q("GetActualTCPPose", 0)[1:][3:6], n)
    if tilt > a.max_tilt:
        print(f"  probe tilt {tilt:.2f} deg exceeds {a.max_tilt}")
        return 1

    clearance = surf + a.retract - height()
    if clearance > 0:
        print(f"\n--- rising {clearance:.3f} mm to clear the gel ---")
        if _move_along_normal(ip, clearance, a, a.approach_joint_step, vel=a.vel_free):
            return 2

    # Camera first. Opening it takes about three seconds -- longer since the
    # driver queue was cut to one buffer -- and the DAQ task starts filling its
    # one-second buffer the moment it connects, so connecting first overruns it
    # (-200279) before anything reads.
    cam = Camera.from_config(camera_config_for(a.sensor))
    cam.open()
    ft = FTInterface.from_config()
    ft.connect()
    reader = None
    try:
        time.sleep(a.settle)
        print("--- zeroing, clear of the gel ---")
        tare = ft.tare(duration_s=2.0)
        res = ft.read_wrench_mean(duration_s=1.0, tared=True)
        print(f"  residual |F| {np.linalg.norm(res[:3]):.4f} N")
        if np.linalg.norm(res[:3]) > 0.15:
            print("  not clear of the gel.")
            return 1
        reader = ForceReader(ft, tare).start()

        # Down to the surface, so travel is counted from first contact.
        drop = height() - surf
        print(f"\n--- descending {drop:.3f} mm to the gel surface ---")
        if _move_along_normal(ip, -drop, a, a.approach_joint_step):
            return 2
        time.sleep(a.settle)

        def measure_n():
            w, err = reader.read_fresh()
            if err:
                raise RuntimeError(err)
            return -float(w[2])

        def model_step(f_now, f_want):
            d_now = max((max(f_now, 0.0) / a_h) ** (2.0 / 3.0), 0.0)
            d_want = (f_want / a_h) ** (2.0 / 3.0)
            return d_want - d_now

        targets = _force_targets(a.force_min, force_cap, a.force_step)
        print(f"\n--- {len(targets)} force levels, {a.force_step} N apart: "
              f"{targets[0]:.2f} to {targets[-1]:.2f} N ---")
        print(f"  {'#':>3} {'target':>7} {'actual':>8} {'depth':>7} {'travel':>7}  note")
        used = 0.0
        ladder_origin = np.array(q("GetActualTCPPose", 0)[1:][:3])
        for t in targets:
            reached, f, used, why = _seek_force(
                ip, a, reader, -n, t, measure_n, model_step, used,
                depth_cap, force_cap + a.force_tol, "normal",
                travel_origin=ladder_origin)
            frame, t_img = cam.grab_settled()
            qual = cam.quality(frame)
            pose = q("GetActualTCPPose", 0)[1:]
            w, _ = reader.read_fresh()
            idx = len(st_run["samples"]) + 1
            name = f"{idx:04d}.png"
            cv2.imwrite(str(run / "frames" / name), frame,
                        [cv2.IMWRITE_PNG_COMPRESSION, 1])
            h = height()
            st_run["samples"].append({
                "index": idx, "sensor_id": run_sensor_id(run), "at": datetime.now().isoformat(), "image": name,
                "image_time": t_img, "pose_time": time.time(),
                "wrench": w.tolist(), "wrench_first": w.tolist(),
                "wrench_second": w.tolist(), "force_drift_N": 0.0,
                "tcp_mm": pose[:3], "tcp_rpy_deg": pose[3:],
                "active_tool": q("GetActualTCPNum", 0),
                "image_quality": qual, "label": f"N{t:.2f}",
                "probe_tilt_deg": tilt, "commanded": True,
                "phase": "force_series", "force_target_N": t,
                "force_reached": reached, "stop_reason": why,
                "travel_used_mm": used, "height_above_plane_mm": h,
                "depth_mm": surf - h,
            })
            save_state(run, st_run)
            print(f"  {idx:>3} {t:>7.2f} {f:>8.3f} {surf-h:>7.3f} {used:>7.3f}  "
                  + ("" if reached else why))
            # Reaching a travel limit while the force is still at the noise
            # floor does not mean the sensor is stiff -- it means the probe
            # never arrived. Distinguishing the two is the difference between a
            # short dataset and a fabricated one.
            if not reached and abs(f) < a.contact_floor:
                print(f"\n  ABORT: travelled {used:.3f} mm and the force is still "
                      f"{f:.3f} N, below the {a.contact_floor} N that counts as "
                      "touching. The probe is not on the gel — the surface height "
                      "is wrong for this sensor.")
                return 1
            if not reached and why.startswith(("travel", "force cap")):
                print(f"\n  stopping the ramp: {why}")
                break
    finally:
        if reader is not None:
            reader.stop()
        cam.close()
        ft.disconnect()
    print(f"\n  {len(st_run['samples'])} sample(s) in the run.")
    return 0


def phase_force_shear(a) -> int:
    """Shear-force ramp at a held normal load, four directions.

    Shear is capped by friction, not by the operator: the contact can only carry
    mu times the normal load before it slides. With mu known only to be above
    0.59, a 1 N shear target needs at least 1.7 N pressing down, so at light
    normal loads the target is unreachable by physics and the run will slip
    instead of getting there. Both outcomes are recorded; which one happened is
    written into every sample.
    """
    from vbts_platform.ft_stream import ForceReader

    run = active_run()
    st_run = load_state(run)
    if not st_run.get("reference"):
        print("  --phase reference first")
        return 2
    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2
    ok, why = mv.ready_to_move(mv.read_state(ip))
    if not ok:
        print(f"  not moving: {why}")
        return 2

    surf, a_h = _gel_model(a)
    if surf is None:
        return 2
    depth_cap, force_cap, _reg, ent = sensor_limits(a)
    if ent:
        print(f"  sensor {ent['id']}: depth ceiling {depth_cap:.2f} mm, "
              f"force ceiling {force_cap:.2f} N")
    if a.normal_hold > force_cap:
        print(f"\n  REFUSING: holding {a.normal_hold} N is above this sensor's "
              f"measured ceiling of {force_cap:.2f} N.")
        return 2
    meta = yaml.safe_load(open(run / "meta.yaml"))
    R = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"])
    n = R[:, 2]
    axes = {"+X": R[:, 0], "-X": -R[:, 0], "+Y": R[:, 1], "-Y": -R[:, 1]}
    uvec = {"+X": np.array([1.0, 0]), "-X": np.array([-1.0, 0]),
            "+Y": np.array([0, 1.0]), "-Y": np.array([0, -1.0])}
    q = chk.ReadOnlyProxy(ip)
    t_sensor, _ = mv.sensor_axis()

    def height():
        return float((np.array(q("GetActualTCPPose", 0)[1:][:3]) - t_sensor) @ n)

    okt, whyt = check_indenter_tool(robot_pose(ip))
    print(f"  tool check: {whyt}")
    if not okt:
        return 1
    tilt = probe_tilt_deg(q("GetActualTCPPose", 0)[1:][3:6], n)
    if tilt > a.max_tilt:
        print(f"  probe tilt {tilt:.2f} deg exceeds {a.max_tilt}")
        return 1

    depth = (a.normal_hold / a_h) ** (2.0 / 3.0)
    if depth > depth_cap:
        print(f"\n  REFUSING: {a.normal_hold} N needs {depth:.2f} mm on this gel, "
              f"past the {depth_cap:.2f} mm ceiling.")
        return 2
    friction_floor = a.mu_floor * a.normal_hold
    print(f"\n  holding {a.normal_hold} N normal, which is {depth:.2f} mm deep")
    print(f"  friction can carry at least {friction_floor:.2f} N "
          f"(mu > {a.mu_floor}); shear target is {a.max_shear_force} N")
    if friction_floor < a.max_shear_force:
        print(f"  -> the target may be beyond what friction holds here. Slip is "
              "the expected outcome, and is recorded as one.")

    clearance = surf + a.retract - height()
    if clearance > 0:
        print(f"\n--- rising {clearance:.3f} mm to clear the gel ---")
        if _move_along_normal(ip, clearance, a, a.approach_joint_step, vel=a.vel_free):
            return 2

    # Camera first. Opening it takes about three seconds -- longer since the
    # driver queue was cut to one buffer -- and the DAQ task starts filling its
    # one-second buffer the moment it connects, so connecting first overruns it
    # (-200279) before anything reads.
    cam = Camera.from_config(camera_config_for(a.sensor))
    cam.open()
    ft = FTInterface.from_config()
    ft.connect()
    reader = None
    try:
        time.sleep(a.settle)
        print("--- zeroing, clear of the gel ---")
        tare = ft.tare(duration_s=2.0)
        res = ft.read_wrench_mean(duration_s=1.0, tared=True)
        print(f"  residual |F| {np.linalg.norm(res[:3]):.4f} N")
        if np.linalg.norm(res[:3]) > 0.15:
            return 1
        reader = ForceReader(ft, tare).start()

        drop = height() - (surf - depth)
        print(f"\n--- descending {drop:.3f} mm to {depth:.2f} mm depth ---")
        if _move_along_normal(ip, -drop, a, a.approach_joint_step):
            return 2
        time.sleep(a.settle)
        w, _ = reader.read_fresh()
        fz_now = -float(w[2])
        print(f"  normal force {fz_now:.3f} N (target {a.normal_hold})")
        if fz_now < max(a.contact_floor, 0.4 * a.normal_hold):
            print(f"\n  ABORT: the probe is not carrying the load it was sent to "
                  f"hold. Shearing from here would drag the tip through air and "
                  "record it as data.")
            return 1
        centre = q("GetActualTCPPose", 0)[1:]

        # A contact cannot carry more shear than friction holds, and that is
        # mu times the normal load. On a 1 mm gel held at 0.3 N the limit is
        # under 0.2 N, so a fixed 1 N ladder spends eight of its ten rungs
        # chasing forces the physics forbids -- each one dragging the tip to the
        # travel limit across a gel it is also wearing. The ladder stops where
        # friction does.
        friction_cap = a.mu_floor * a.normal_hold
        shear_cap = min(a.max_shear_force, friction_cap)
        # Rungs as FRACTIONS of what this contact can carry, not a fixed 0.1 N
        # grid. On a 1 mm gel friction holds 0.18 N, so a 0.1 N grid starting at
        # 0.1 N leaves exactly one rung -- a single point per direction, which
        # gives no slope and no way to see whether the contact was gripping.
        # Fractions give the same number of points on every sensor, and the
        # points sit where that sensor can actually reach.
        fracs = [float(x) for x in a.shear_fractions.split(",")]
        targets = [round(shear_cap * f, 4) for f in fracs
                   if shear_cap * f >= a.shear_abs_min]
        print(f"  shear ceiling {shear_cap:.3f} N "
              + (f"(friction: {a.mu_floor} x {a.normal_hold} N)"
                 if friction_cap < a.max_shear_force else "(requested limit)"))
        if not targets:
            print(f"\n  even the largest rung would be under the {a.shear_abs_min} N "
                  "floor where the F/T can resolve it. Press deeper first.")
            return 1
        print(f"  {len(targets)} rungs: " + ", ".join(f"{t:.3f}" for t in targets) + " N")
        print(f"\n  {'#':>3} {'axis':>4} {'target':>7} {'actual':>8} "
              f"{'travel':>7} {'Fz':>7}  note")
        for axis in a.order.split(","):
            axis = axis.strip()
            u = uvec[axis]

            def measure_s():
                w, err = reader.read_fresh()
                if err:
                    raise RuntimeError(err)
                return float(np.array(w[:2]) @ u)

            k_guess = [a.shear_k]

            def model_step(f_now, f_want):
                return (f_want - f_now) / max(k_guess[0], 0.05)

            used = 0.0
            axis_origin = np.array(q("GetActualTCPPose", 0)[1:][:3])
            for t in targets:
                reached, f, used, why = _seek_force(
                    ip, a, reader, axes[axis], t, measure_s, model_step, used,
                    a.max_travel_shear, shear_cap + a.force_tol, axis,
                    travel_origin=axis_origin)
                if used > 0.05:
                    k_guess[0] = max(f / used, 0.05)   # learn the real stiffness
                frame, t_img = cam.grab_settled()
                qual = cam.quality(frame)
                pose = q("GetActualTCPPose", 0)[1:]
                w, _ = reader.read_fresh()
                idx = len(st_run["samples"]) + 1
                name = f"{idx:04d}.png"
                cv2.imwrite(str(run / "frames" / name), frame,
                            [cv2.IMWRITE_PNG_COMPRESSION, 1])
                st_run["samples"].append({
                    "index": idx, "sensor_id": run_sensor_id(run), "at": datetime.now().isoformat(), "image": name,
                    "image_time": t_img, "pose_time": time.time(),
                    "wrench": w.tolist(), "wrench_first": w.tolist(),
                    "wrench_second": w.tolist(), "force_drift_N": 0.0,
                    "tcp_mm": pose[:3], "tcp_rpy_deg": pose[3:],
                    "active_tool": q("GetActualTCPNum", 0),
                    "image_quality": qual, "label": f"{axis}S{t:.2f}",
                    "probe_tilt_deg": tilt, "commanded": True,
                    "phase": "force_shear", "shear_axis": axis,
                    "shear_target_N": t, "force_reached": reached,
                    "stop_reason": why, "travel_used_mm": used,
                    "normal_hold_N": a.normal_hold,
                    "height_above_plane_mm": height(),
                })
                save_state(run, st_run)
                print(f"  {idx:>3} {axis:>4} {t:>7.2f} {f:>8.3f} {used:>7.3f} "
                      f"{w[2]:>7.3f}  " + ("" if reached else why))
                if not reached and why.startswith(("travel", "force cap",
                                                   "step underflow")):
                    print(f"       {axis} stops here: {why}")
                    break
            pl = mv.plan(ip, centre, a.approach_joint_step)
            if not pl.get("ok"):
                print(f"  refusing the return: {pl.get('why')}")
                return 2
            tool = pl["active_tool"][1] if isinstance(pl["active_tool"], list) else 1
            if mv.send_movel(ip, pl["target_joints"], pl["target_pose"], tool,
                             a.vel, a.ovl) != 0:
                return 1
            time.sleep(a.settle)
    finally:
        if reader is not None:
            reader.stop()
        cam.close()
        ft.disconnect()
    print(f"\n  {len(st_run['samples'])} sample(s) in the run.")
    return 0


def capture_policy(a) -> dict:
    """Frame budget and ramp parameters: registry first, command line over it."""
    reg = yaml.safe_load(open(REGISTRY))
    pol = dict(reg.get("capture_policy") or {})
    out = {
        "frames": int(a.frames or pol.get("frames_per_sensor", 3000)),
        "normal_fraction": float(a.normal_fraction
                                 if a.normal_fraction is not None
                                 else pol.get("normal_fraction", 0.5)),
        "ramp_step": float(a.ramp_step or pol.get("ramp_step_N", 0.05)),
        "ramp_settle": float(a.ramp_settle if a.ramp_settle is not None
                             else pol.get("ramp_settle_s", 0.15)),
        "anchor_every": float(a.anchor_every or pol.get("anchor_every_N", 0.1)),
    }
    return out


class ForceBinner:
    """Accept a frame only if its wrench is new, and only until its bin is full.

    Two rules, both taken from the literature and both aimed at what a force
    regressor actually needs:

    Separation -- FeelAnyForce's problem in reverse. At 5 fps the median gap
    between neighbouring frames is 0.012 N, below the F/T's own 0.02 N noise,
    so consecutive frames carry the same label to within its uncertainty. A
    frame is rejected unless its wrench differs from every frame already kept
    in its bin by `min_sep`. 9DTact does the same thing with a scaled L1
    distance over the whole wrench (`collect_data.py`), though their threshold
    -- a quarter of a 12 N range -- is far coarser than ours.

    Quota -- FeelAnyForce is the only paper that deliberately flattens the
    force histogram, and it is the right thing to do when the metric is MAE
    across a range. Left to itself the protocol spends 55 % of its frames at
    the shear hold and 8 % above 4 N, which is exactly where the model is
    worst. Each force bin takes a fixed share of the budget and then stops
    accepting, so the cycles keep running until the whole range is covered.

    If the budget cannot be filled that way -- some bins are unreachable, or
    the gel stops giving new states -- `relax()` widens the quota and loosens
    the separation, so every sensor still ends with the same frame count. Every
    relaxation is recorded, because a run that needed three of them did not
    collect the same kind of data as one that needed none.
    """

    def __init__(self, budget: int, normal_fraction: float, force_cap: float,
                 shear_cap: float, bin_normal: float, bin_shear: float,
                 min_sep: float):
        self.n_budget = int(round(budget * normal_fraction))
        self.s_budget = budget - self.n_budget
        self.bin_normal = bin_normal
        self.bin_shear = bin_shear
        self.min_sep = min_sep
        self.force_cap = float(force_cap)
        self.shear_cap = float(shear_cap)
        self.n_rejected_range = 0
        n_bins = max(1, int(np.ceil(force_cap / bin_normal)))
        s_bins = max(1, int(np.ceil(shear_cap / bin_shear))) * 4
        self.quota = {"normal": max(1, int(np.ceil(self.n_budget / n_bins))),
                      "shear": max(1, int(np.ceil(self.s_budget / s_bins)))}
        self.kept: dict = {}
        # Separation is judged WITHIN one pass, not against the whole run.
        # 9DTact does exactly this -- `collect_data.py` clears its saved-wrench
        # buffer on release, so two presses may repeat the same wrench. That is
        # right: the force repeats but the image does not, because the gel has
        # crept and the loading history differs, and a regressor has to survive
        # that. Judging globally instead made a 234-move cycle yield ten frames
        # and put the run on course for 90 minutes.
        self.pass_seen: dict = {}
        self.n_offered = 0
        self.n_rejected_bin = 0
        self.n_rejected_sep = 0
        self.relaxations: list = []

    def key(self, w, tag):
        seg = str(tag.get("segment", ""))
        if seg.startswith("shear"):
            f = float(np.hypot(w[0], w[1]))
            return ("shear", tag.get("axis", "?"), int(f / self.bin_shear)), f
        f = -float(w[2])
        return ("normal", int(max(f, 0.0) / self.bin_normal)), f

    def in_range(self, k, scalar) -> bool:
        """Is this frame inside the FIXED collection range?

        key() floors the force into a bin with no upper bound, so a frame past
        the cap simply lands in a bin above the last one the quota was sized
        for -- a new bin, created on demand, handed the full per-bin quota. The
        range is fixed precisely so that every unit is measured over the same
        span, and nothing was holding the saved frames to it.

        Measured 2026-09-08 on the first Pass B DIGIT units: 54 normal bins
        occupied against the 40 that 0-2 N at 0.05 N allows, and 5.7-16.7 % of
        saved frames above 2 N (2.15 N and 1.3 % across the seventeen 9DTact
        units, whose softer gels overshoot far less). A sixth of a unit's
        frames outside the common span is not a rounding error -- it is the
        comparison the fixed range exists to make.

        The ramp still overshoots; that is a control problem and it costs
        motion, not data. This is what keeps the overshoot out of the dataset.
        """
        if k[0] == "shear":
            # NOT capped. Shear is set by friction, not by command -- the
            # block asks for min(range_shear, mu x hold) and the gel gives
            # what it gives, up to 0.85 N on a DIGIT 2 mm marker gel and
            # 0.91 N on 9DTact_hard_3mm_r2 against the same 0.5 N ask.
            # Rejecting the excess was tried on 2026-09-08 and starved the
            # shear bins: the outward glide crosses 0-0.5 N quickly and spends
            # the rest of its travel above it, so the block ran 54 cycles and
            # relaxed TWENTY times, which drives min_sep from 0.020 N to
            # 1.6e-5 N and lets near-duplicate frames in. A collapsed
            # separation rule is worse than a wide range. The normal channel
            # has no such problem -- its cap is what the ramp is servoing to.
            return True
        return scalar <= self.force_cap + 1e-9

    def offer(self, w, tag) -> bool:
        self.n_offered += 1
        k, scalar = self.key(w, tag)
        if not self.in_range(k, scalar):
            self.n_rejected_range += 1
            return False
        block = k[0]
        seen = self.kept.setdefault(k, [])
        if len(seen) >= self.quota[block]:
            self.n_rejected_bin += 1
            return False
        this_pass = self.pass_seen.setdefault(k, [])
        if this_pass and min(abs(scalar - v) for v in this_pass) < self.min_sep:
            self.n_rejected_sep += 1
            return False
        seen.append(scalar)
        this_pass.append(scalar)
        return True

    def new_pass(self) -> None:
        """A new loading pass: forget what this pass has seen, keep the quotas."""
        self.pass_seen = {}

    def relax(self, why: str) -> None:
        self.quota = {k: int(np.ceil(v * 1.5)) for k, v in self.quota.items()}
        self.min_sep *= 0.7
        self.relaxations.append({"at": datetime.now().isoformat(), "why": why,
                                 "quota": dict(self.quota),
                                 "min_sep_N": round(self.min_sep, 5)})

    def report(self) -> dict:
        occ = {k: len(v) for k, v in self.kept.items() if v}
        nb = [len(v) for k, v in self.kept.items() if k[0] == "normal" and v]
        sb = [len(v) for k, v in self.kept.items() if k[0] == "shear" and v]
        return {"bin_normal_N": self.bin_normal, "bin_shear_N": self.bin_shear,
                "min_sep_N": round(self.min_sep, 5), "quota": dict(self.quota),
                "offered": self.n_offered,
                "rejected_bin_full": self.n_rejected_bin,
                "rejected_too_close": self.n_rejected_sep,
                "rejected_out_of_range": self.n_rejected_range,
                "force_cap_N": self.force_cap, "shear_cap_N": self.shear_cap,
                "bins_occupied_normal": len(nb), "bins_occupied_shear": len(sb),
                "frames_per_bin_normal": {"min": min(nb) if nb else 0,
                                          "max": max(nb) if nb else 0},
                "frames_per_bin_shear": {"min": min(sb) if sb else 0,
                                         "max": max(sb) if sb else 0},
                "relaxations": self.relaxations}


def phase_collect(a) -> int:
    """Continuous capture: loading cycles and shear cycles until the frame
    budget is spent, every frame labelled.

    WHY CYCLES AND A BUDGET
    -----------------------
    The ladder phases took one settled image per rung, so a sensor's dataset
    size was set by how many rungs its gel could carry: 69 images for a hard
    3 mm gel, 21 for a soft 1 mm one. A force estimator trained on each would
    then be compared on data quantity as much as on the sensor. Here the camera
    is read at its own rate for the whole of every commanded motion, and the
    probe loads and unloads the gel -- and shears it in four directions -- over
    and over until exactly `frames_per_sensor` frames are on disk. The 1 mm gel
    sees more cycles; both sensors give the same number of frames.

    WHAT EACH FRAME IS LABELLED WITH
    --------------------------------
    The F/T is read in 20 ms chunks on its own thread and every chunk is
    timestamped, so a frame's force label is the mean over the interval the
    camera was integrating light for that frame, not a reading taken after it.
    The TCP pose comes from the 20004 state stream at ~96 Hz and is interpolated
    to the frame time. The zero is re-measured off the gel between the two
    blocks and at the end, and both raw and drift-corrected wrenches are written.

    The settled anchor samples the ladder phases produced are still taken --
    at every `anchor_every` newtons on the way up and at every shear rung -- so
    the per-rung tables, the Hertz fit in `summary` and the campaign status keep
    working unchanged.
    """
    from vbts_platform.ft_stream import ForceReader
    from vbts_platform.camera_interface import FrameRecorder
    from vbts_platform.pose_stream import PoseLogger

    run = active_run()
    st_run = load_state(run)
    if not st_run.get("reference"):
        print("  --phase reference first")
        return 2
    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2
    ok, why = mv.ready_to_move(mv.read_state(ip))
    if not ok:
        print(f"  not moving: {why}")
        return 2

    surf, a_h = _gel_model(a)
    if surf is None:
        return 2
    depth_cap, force_cap, _reg, ent = sensor_limits(a)
    pol = capture_policy(a)
    budget = pol["frames"]
    n_budget = int(round(budget * pol["normal_fraction"]))
    hold = a.normal_hold
    if hold > force_cap:
        print(f"\n  REFUSING: holding {hold} N is above this sensor's ceiling of "
              f"{force_cap:.2f} N.")
        return 2
    hold_depth = (hold / a_h) ** (2.0 / 3.0)
    if hold_depth > depth_cap:
        print(f"\n  REFUSING: {hold} N needs {hold_depth:.2f} mm here, past the "
              f"{depth_cap:.2f} mm ceiling.")
        return 2

    meta = yaml.safe_load(open(run / "meta.yaml"))
    R = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"])
    n = R[:, 2]
    axes = {"+X": R[:, 0], "-X": -R[:, 0], "+Y": R[:, 1], "-Y": -R[:, 1]}
    uvec = {"+X": np.array([1.0, 0]), "-X": np.array([-1.0, 0]),
            "+Y": np.array([0, 1.0]), "-Y": np.array([0, -1.0])}
    q = chk.ReadOnlyProxy(ip)
    t_sensor, _ = mv.sensor_axis()

    def height(p=None) -> float:
        if p is None:
            p = q("GetActualTCPPose", 0)[1:][:3]
        return float((np.array(p[:3]) - t_sensor) @ n)

    def radial() -> float:
        """Distance from the sensor axis. Watched every cycle: a run whose
        contact walks across the gel reports perfectly normal forces the whole
        way, so nothing else notices."""
        d = np.array(q("GetActualTCPPose", 0)[1:][:3]) - t_sensor
        return float(np.linalg.norm(d - (d @ n) * n))

    okt, whyt = check_indenter_tool(robot_pose(ip))
    print(f"  tool check: {whyt}")
    if not okt:
        return 1
    tilt = probe_tilt_deg(q("GetActualTCPPose", 0)[1:][3:6], n)
    if tilt > a.max_tilt:
        print(f"  probe tilt {tilt:.2f} deg exceeds {a.max_tilt}")
        return 1

    if ent:
        print(f"  sensor {ent['id']}: {ent['thickness_mm']} mm {ent['hardness']}")
    print(f"\n  gel model  F = {a_h:.3f} * depth^1.5,  surface {surf:.3f} mm")
    print(f"  limits: {depth_cap:.2f} mm depth, {force_cap:.2f} N force; shear "
          f"held at {hold:.2f} N ({hold_depth:.2f} mm)")
    print(f"  budget {budget} frames: {n_budget} in normal cycles, "
          f"{budget - n_budget} in shear cycles")
    print(f"  ramp {pol['ramp_step']:.2f} N per step, {pol['ramp_settle']:.2f} s "
          f"settle; anchors every {pol['anchor_every']:.2f} N")
    print(f"  speeds: contact {a.vel_contact:.0f} %, free {a.vel_free:.0f} %")

    # ramp steps take one model/feedback step per target and do not wait to
    # converge -- the frames are the data, the rung is only a waypoint
    ar = argparse.Namespace(**vars(a))
    ar.seek_iters = 1
    ar.settle = pol["ramp_settle"]

    clearance = surf + a.retract - height()
    if clearance > 0:
        print(f"\n--- rising {clearance:.3f} mm to clear the gel ---")
        if _move_along_normal(ip, clearance, a, a.approach_joint_step, vel=a.vel_free):
            return 2

    # Camera and pose stream first, F/T last. The DAQ task starts filling its
    # buffer the moment it connects, and the camera takes about three seconds to
    # open and settle -- long enough to overrun the buffer before the first
    # read, which is exactly what happened on the first attempt (-200279).
    stream_dir = run / "stream"
    if stream_dir.exists() and any(stream_dir.iterdir()):
        # A rerun after a crash. The previous attempt's frames are kept aside,
        # and the anchor samples it wrote are dropped, so the new stream and
        # the per-rung table describe the same pass over the gel.
        k = 1
        while (run / f"stream__{k}").exists():
            k += 1
        stream_dir.rename(run / f"stream__{k}")
        print(f"  previous stream moved to stream__{k}")
        keep = [x for x in st_run["samples"]
                if x.get("phase") not in ("force_series", "force_shear")]
        for x in st_run["samples"]:
            if x not in keep:
                fp = run / "frames" / x["image"]
                if fp.is_file():
                    fp.unlink()
        st_run["samples"] = keep
        save_state(run, st_run)
    base, base_why = saturation_base(ent)
    shear_target = a.range_shear
    a.max_shear_force = shear_target
    print(f"\n  fixed collection range (same for every sensor):")
    print(f"    normal  0 - {force_cap:.2f} N")
    print(f"    shear   0 - {shear_target:.2f} N, held at {hold:.2f} N normal "
          f"(friction carries {a.mu_floor * hold:.2f} N)")
    print(f"  this sensor's own measured ceiling: {base:.2f} N from {base_why} "
          "(recorded, not used to set the range)")
    shear_cap_guess = min(shear_target, a.mu_floor * hold)
    binner = ForceBinner(budget, pol["normal_fraction"], force_cap,
                         shear_cap_guess, a.bin_normal, a.bin_shear, a.min_sep)
    print(f"  distribution: {a.bin_normal:.2f} N normal bins "
          f"(quota {binner.quota['normal']}/bin), {a.bin_shear:.2f} N shear bins "
          f"per axis (quota {binner.quota['shear']}/bin), "
          f"frames closer than {a.min_sep:.3f} N to a kept frame are dropped")
    cam = Camera.from_config(camera_config_for(a.sensor))
    # Four driver buffers, not the usual one. This is the only phase that reads
    # the camera flat out, and with a single buffer the driver drops every
    # second frame: measured 2026-09-07, 2.48 fps against the exposure's own
    # 4.89 fps ceiling, with 58 of 59 gaps exactly two frame periods. The two
    # collect runs on record grabbed 2.44 and 2.46 fps for the same reason, so
    # every one of their 1000 frames cost twice the wall time it needed to.
    # The backlog a deeper queue can build is handled by timestamping from the
    # driver rather than from the clock -- see Camera.capture_time.
    cam.open(buffersize=4)

    def gate(tag):
        w, err = reader.read() if reader is not None else (None, "no reader")
        if w is None or err:
            return False
        return binner.offer(w, tag)

    rec = FrameRecorder(cam, stream_dir, budget, gate=gate).start()
    poses = PoseLogger(ip).start()
    time.sleep(a.settle)
    ft = FTInterface.from_config()
    ft.connect()
    reader = None
    zero_checks: list[dict] = []
    t_start = time.time()
    normal_cycles = shear_cycles = 0
    rv = 1
    try:
        print("--- zeroing, clear of the gel ---")
        tare = ft.tare(duration_s=2.0)
        res = ft.read_wrench_mean(duration_s=1.0, tared=True)
        print(f"  residual |F| {np.linalg.norm(res[:3]):.4f} N")
        if np.linalg.norm(res[:3]) > 0.15:
            print("  not clear of the gel.")
            return 1
        reader = ForceReader(ft, tare).start()
        zero_checks.append({"at": datetime.now().isoformat(), "t": time.time(),
                            "drift_wrench": [0.0] * 6, "where": "tare"})

        def measure_n():
            w, err = reader.read_fresh()
            if err:
                raise RuntimeError(err)
            return -float(w[2])

        def model_n(f_now, f_want):
            d_now = max((max(f_now, 0.0) / a_h) ** (2.0 / 3.0), 0.0)
            d_want = (max(f_want, 0.0) / a_h) ** (2.0 / 3.0)
            return d_want - d_now

        def anchor(phase: str, label: str, **extra) -> dict:
            frame, t_img = rec.wait_fresh()
            qual = cam.quality(frame)
            pose = q("GetActualTCPPose", 0)[1:]
            w, _ = reader.read_fresh()
            idx = len(st_run["samples"]) + 1
            name = f"{idx:04d}.png"
            cv2.imwrite(str(run / "frames" / name), frame,
                        [cv2.IMWRITE_PNG_COMPRESSION, 1])
            h = height(pose)
            smp = {"index": idx, "sensor_id": run_sensor_id(run),
                   "at": datetime.now().isoformat(), "image": name,
                   "image_time": t_img, "pose_time": time.time(),
                   "wrench": w.tolist(), "wrench_first": w.tolist(),
                   "wrench_second": w.tolist(), "force_drift_N": 0.0,
                   "tcp_mm": pose[:3], "tcp_rpy_deg": pose[3:],
                   "active_tool": q("GetActualTCPNum", 0),
                   "image_quality": qual, "label": label,
                   "probe_tilt_deg": tilt, "commanded": True, "phase": phase,
                   "height_above_plane_mm": h, "depth_mm": surf - h,
                   "stream_index": rec.saved, **extra}
            st_run["samples"].append(smp)
            save_state(run, st_run)
            return smp

        def descend_to(target_h: float) -> int:
            """Free speed to `approach_clear` above the surface, contact speed
            from there. The surface estimate can be 0.1-0.3 mm off, and a 30 %
            move that lands in the gel is the overshoot this guards against."""
            h = height()
            stop_free = surf + a.approach_clear
            if h > stop_free + 1e-3 and target_h < stop_free:
                if _move_along_normal(ip, -(h - stop_free), a,
                                      a.approach_joint_step, vel=a.vel_free):
                    return 2
                h = height()
            if h - target_h > 1e-3:
                if _move_along_normal(ip, -(h - target_h), a,
                                      a.approach_joint_step):
                    return 2
            return 0

        def zero_check(where: str) -> None:
            time.sleep(a.settle)
            w, _ = reader.read_fresh()
            zero_checks.append({"at": datetime.now().isoformat(), "t": time.time(),
                                "drift_wrench": w.tolist(), "where": where})
            st_run.setdefault("zero_checks", []).append(
                {"at": zero_checks[-1]["at"], "drift_wrench": w.tolist()})
            save_state(run, st_run)
            print(f"  zero drift |F| {np.linalg.norm(w[:3]):.4f} N   "
                  f"|T| {np.linalg.norm(w[3:]):.6f} N*m   ({where})")

        # ---------------- continuous ramp (2026-09-07) ----------------
        # The stepped ramp paused 0.15 s at every 0.1 N rung, and the frames
        # that fill the force bins were the ones captured while it paused --
        # so 30 % of grabbed frames were kept and the rest were duplicates of
        # a force already on record (measured on the first eleven units:
        # "too close" 29-39 %, "bin full" 25-33 %, 0.7 s per saved frame).
        # A slow, continuous glide never repeats a force: every camera frame
        # is at a new one. The glide is cut into short segments so the force
        # is read between them and the same guards apply -- force cap, depth
        # backstop, no-contact abort, load collapse on shear. Labels are still
        # the F/T mean over each frame's own exposure window. Nothing about
        # the budget, the bins, the separation rule or the range changes; the
        # gel's loading history does (no pauses), which the operator accepted.
        continuous = a.ramp_mode == "continuous"

        # HOW FAST THE GLIDE HAS TO BE, and why it is not a fixed percentage.
        # A frame is kept only if its force differs from one already kept in
        # its bin by --min-sep (0.02 N). Frames arrive every 1/4.86 s, so the
        # force has to move at least 0.02 N in 0.206 s -- about 0.1 N/s -- or
        # most frames are duplicates and get dropped. The first continuous
        # attempt used a fixed 0.5 %, which on 9DTact_hard_1mm_r1 gave 8.5 s
        # per 0.10 mm segment: 0.035 N/s, 0.007 N per frame, and the same 31 %
        # acceptance the stepped ramp had. Removing the pauses is not enough;
        # the glide has to be paced.
        #
        # The pace that matters is dF/dt, and the same speed gives a different
        # dF/dt on every gel, so the velocity is computed per segment from the
        # stiffness just measured: aim each segment at RAMP_DF newtons and at
        # RAMP_DF/RAMP_DFDT seconds. The robot's millimetres per second at
        # 100 % is not assumed -- it is measured from each glide's own elapsed
        # time and carried forward, so the loop calibrates itself on the first
        # couple of segments whatever the arm is set to.
        RAMP_DF = 0.25            # newtons a segment should add
        RAMP_DFDT = 0.15          # newtons per second while gliding
        MOVEL_OVERHEAD = 0.40     # s of plan + round trip, measured 2026-09-07
        pace = {"mm_per_s_100": 2.5}

        def _pace(k_local, step_mm):
            """Velocity percentage for a segment of `step_mm` at stiffness `k_local`."""
            want_s = max(RAMP_DF / max(RAMP_DFDT, 1e-3), 0.6)
            motion_s = max(want_s - MOVEL_OVERHEAD, 0.25)
            v_mm_s = step_mm / motion_s
            return float(np.clip(v_mm_s / max(pace["mm_per_s_100"], 0.05) * 100.0,
                                 0.2, 20.0))

        # STEP_MIN was 0.05 mm, which is a floor on the FORCE a segment adds,
        # not on its length: 0.05 mm on a gel of stiffness k adds 0.05k
        # newtons whatever RAMP_DF asks for. On 9DTact's gels k is small enough
        # that the floor never binds. On a DIGIT 1 mm gel under ball8, k is
        # about 12.8 N/mm, so one floor-length step adds 0.64 N against the
        # 0.25 N target, and the ramp sails past the fixed 2 N range before it
        # can be stopped: measured 2026-09-08, Fz reaching 3.11 N (55 % over)
        # with 16.7 % of the saved frames above 2 N, against 2.15 N and 1.3 %
        # across the seventeen 9DTact units. The whole reason the range is
        # fixed is that the units have to be compared over the same span, so
        # a sixth of a unit's frames sitting outside it is not a rounding
        # error. 0.02 mm is the step the zero phase already uses, so its
        # accuracy at that length is established.
        #
        # `head` is the force still available before the cap. Near the top of
        # the ramp the segment is sized to land ON the cap rather than to add
        # a full RAMP_DF past it.
        STEP_MIN = 0.02
        def _step_for(k_local, head=None):
            want = RAMP_DF if head is None else max(min(RAMP_DF, float(head)), 0.02)
            return float(np.clip(want / max(k_local, 1e-3), STEP_MIN, 0.40))

        def _return_to_origin(origin, vel):
            """Absolute MoveL back to `origin`, wiping the accumulated drift.

            _glide chains every target off the pose just achieved, so MoveL's
            few-micron Cartesian bias accumulates -- the same leak descend_from()
            and _seek_force were written to avoid, and the reason run_one_sensor
            re-centres before collect. The stepped ramp did not care because it
            went through _seek_force, which is origin-anchored; the continuous
            glide added 2026-09-07 does not, and nothing noticed until a run
            needed enough cycles to matter.

            Measured 2026-09-08 on DIGIT_Marker_soft_1mm_r2 (ball8): 0.0216 mm
            of lateral walk per load/unload cycle, monotone and along the gel's
            own tilt, so 9 cycles reached the 0.3 mm abort. It is not a DIGIT
            fault -- 9DTact_hard_1mm_r1 walked 0.0355 mm per cycle in Pass B --
            it is that 9DTact filled its 1000-frame budget in 5-10 cycles and
            never got far enough for the limit to bite. The walk grows with gel
            stiffness (0.02-0.036 mm/cycle on the hard 1 mm units against
            0.001-0.004 on the soft 3 mm ones), which is what a lateral load on
            a tilted surface deflecting the arm looks like.

            Called at the end of each unload, where the force is back to about
            zero and the tip is at the surface it started from, so this is a
            few tens of microns of motion against no load.
            """
            pose_ = q("GetActualTCPPose", 0)[1:]
            tgt_ = [float(v) for v in origin] + [float(v) for v in pose_[3:]]
            pl_ = mv.plan(ip, tgt_, a.approach_joint_step)
            if not pl_.get("ok"):
                print(f"  refusing the re-centre: {pl_.get('why')}")
                return 2
            tool_ = pl_["active_tool"][1] if isinstance(pl_["active_tool"], list) else 1
            if mv.send_movel(ip, pl_["target_joints"], pl_["target_pose"], tool_,
                             float(vel), a.ovl) != 0:
                print("  MoveL failed returning to the ladder origin")
                return 1
            return 0

        def _recentre_lateral(ref, vel):
            """Remove the PERPENDICULAR offset from the axis through `ref`.

            The shear block cannot use _return_to_origin: its height is held by
            the force servo at every cycle, so a full 3-D return would fight it.
            What has to be undone is only the radial part -- the component of
            (here - ref) perpendicular to the gel normal.

            Measured 2026-09-08 on DIGIT_Marker_soft_2mm_r1: anchoring the four
            axes of ONE cycle to a shared point took the block from 4 cycles to
            14, but the anchor was re-read inside the cycle loop, so it still
            followed the walk from cycle to cycle and the run aborted at
            0.306 mm with 797 of 1000 frames. `shear_origin` is captured once,
            before the loop, and is the reference that does not move.
            """
            p_ = np.array(q("GetActualTCPPose", 0)[1:][:3])
            pose_ = q("GetActualTCPPose", 0)[1:]
            d_ = p_ - np.asarray(ref, dtype=float)
            perp = d_ - (d_ @ n) * n
            if float(np.linalg.norm(perp)) < 5e-4:
                return 0
            return _return_to_origin(p_ - perp, vel)

        def _glide(vec, mm, vel):
            """One MoveL of `mm` along unit `vec` at `vel` %, frames saved throughout.

            Returns (rc, seconds). The elapsed time updates the speed model.
            """
            pose_ = q("GetActualTCPPose", 0)[1:]
            p_ = np.array(pose_[:3]) + float(mm) * np.asarray(vec, dtype=float)
            tgt_ = [float(v) for v in p_] + [float(v) for v in pose_[3:]]
            pl_ = mv.plan(ip, tgt_, a.approach_joint_step)
            if not pl_.get("ok"):
                print(f"  refusing the glide: {pl_.get('why')}")
                return 2, 0.0
            tool_ = pl_["active_tool"][1] if isinstance(pl_["active_tool"], list) else 1
            t_ = time.time()
            if mv.send_movel(ip, pl_["target_joints"], pl_["target_pose"], tool_,
                             float(vel), a.ovl) != 0:
                print("  MoveL failed during the glide")
                return 1, 0.0
            dt_ = time.time() - t_
            moving = dt_ - MOVEL_OVERHEAD
            if moving > 0.15 and abs(mm) > 1e-3:
                seen = abs(mm) / moving / max(vel, 1e-6) * 100.0
                pace["mm_per_s_100"] = 0.7 * pace["mm_per_s_100"] + 0.3 * seen
            return 0, dt_

        # ---------------- normal block ----------------
        print(f"\n--- descending to the gel surface ---")
        if descend_to(surf):
            return 2
        time.sleep(a.settle)
        ladder_origin = np.array(q("GetActualTCPPose", 0)[1:][:3])
        anchor_grid = pol["anchor_every"]
        rec.set_cap(n_budget)
        print(f"\n--- normal cycles until {n_budget} frames ---")
        print(f"  {'cyc':>3} {'dir':>6} {'steps':>5} {'peak N':>7} {'peak mm':>7} "
              f"{'frames':>6}  note")
        dead = 0
        saved_before = 0
        if continuous:
            print(f"  continuous ramp: paced to {RAMP_DF:.2f} N and "
                  f"{RAMP_DF/RAMP_DFDT:.1f} s per segment ({RAMP_DFDT:.2f} N/s), "
                  f"velocity from the measured stiffness each segment")
        while continuous and normal_cycles < a.max_cycles:
            normal_cycles += 1
            binner.new_pass()
            rec.arm(segment="normal_load", cycle=normal_cycles, axis="",
                    target_N=float(force_cap))
            d_goal = min((force_cap / a_h) ** (2.0 / 3.0), depth_cap - a.travel_margin)
            used, peak_f, peak_d, why, nseg = 0.0, 0.0, 0.0, "", 0
            f = measure_n()
            k_local = max(1.5 * a_h * max(d_goal, 0.05) ** 0.5, 0.2)   # Hertz slope, refined below
            while True:
                room = depth_cap - a.travel_margin - used
                head_N = max(force_cap - abs(measure_n()), 0.0)
                step = min(_step_for(k_local, head_N), room)
                if step <= 1e-4:
                    why = f"depth cap {depth_cap:.2f} mm"
                    break
                f_before, d_before = f, used
                rv, _dt = _glide(-n, step, _pace(k_local, step))
                if rv:
                    return rv
                nseg += 1
                used = surf - height()             # measured, not summed
                f = measure_n()
                moved = used - d_before
                if moved > 1e-3:
                    k_local = 0.5 * k_local + 0.5 * max((f - f_before) / moved, 0.05)
                peak_f, peak_d = max(peak_f, f), max(peak_d, used)
                if f < a.contact_floor and used > a.no_contact_mm:
                    print(f"\n  ABORT: {used:.3f} mm in and the force is still "
                          f"{f:.3f} N. The probe is not on the gel.")
                    return 1
                if f >= force_cap - a.force_tol:
                    why = "force cap"
                    break
                if used >= d_goal - 1e-4 and f >= force_cap - 3 * a.force_tol:
                    why = "reached"
                    break
                if nseg > 400:
                    why = "segment count"
                    break
            anchor("force_series", f"N{f:.2f}", force_target_N=float(force_cap),
                   force_reached=bool(f >= force_cap - a.force_tol),
                   stop_reason=why, travel_used_mm=used, cycle=normal_cycles)
            print(f"  {normal_cycles:>3} {'load':>6} {nseg:>5} {peak_f:>7.3f} "
                  f"{peak_d:>7.3f} {rec.saved:>6}  {'' if why.startswith(('reached', 'force')) else why}")
            if peak_f < a.cycle_min_frac * force_cap:
                dead += 1
                print(f"      cycle {normal_cycles} carried only {peak_f:.3f} N "
                      f"({dead}/{a.max_dead_cycles}); re-finding the surface")
                if dead >= a.max_dead_cycles:
                    print("\n  ABORT: the ramp cannot load the gel. The surface "
                          "height or the F/T zero is wrong.")
                    return 1
                rec.disarm()
                for _ in range(40):
                    if measure_n() >= a.contact_floor:
                        break
                    if _move_along_normal(ip, -0.05, a, a.max_joint_step):
                        return 2
                    time.sleep(pol["ramp_settle"])
                surf = height()
                print(f"      contact re-established at {surf:.3f} mm, {measure_n():.3f} N")
                continue
            dead = 0
            # unload: one continuous glide back to the surface, recorded
            binner.new_pass()
            rec.retag(segment="normal_unload", target_N=0.0)
            # Unload in segments too, at the same pace: a single slow glide
            # spends a minute producing frames a few thousandths of a newton
            # apart, which the separation rule then throws away.
            nback = 0
            while nback < 200:
                back = surf - height()
                if back <= 1e-3:
                    break
                f_before, h_before = measure_n(), height()
                step = min(_step_for(k_local), back)
                rv, _dt = _glide(+n, step, _pace(k_local, step))
                if rv:
                    return rv
                nback += 1
                moved = height() - h_before
                if moved > 1e-3:
                    k_local = 0.5 * k_local + 0.5 * max((f_before - measure_n()) / moved, 0.05)
            rec.retag(segment="dwell", target_N=0.0)
            # Wipe the per-cycle drift here, at zero force, rather than let it
            # accumulate into the 0.3 mm abort. See _return_to_origin.
            _rc_o = _return_to_origin(ladder_origin, max(_pace(k_local, 0.10), 1.0))
            if _rc_o:
                return _rc_o
            time.sleep(a.cycle_dwell)
            print(f"  {normal_cycles:>3} {'unload':>6} {nback:>5} {'':>7} {'':>7} {rec.saved:>6}"
                  f"  r={radial():.3f}")
            if rec.capped:
                break
            if rec.error:
                print(f"  recorder: {rec.error}")
                return 1
            r_now = radial()
            if r_now > a.max_radial_drift:
                print(f"\n  ABORT: the contact is {r_now:.3f} mm off the sensor axis, "
                      f"past the {a.max_radial_drift} mm limit.")
                return 1
            gained = rec.saved - saved_before
            if gained < a.cycle_min_gain:
                binner.relax(f"normal cycle {normal_cycles} added {gained} frames")
                print(f"      only {gained} new frames; quota -> "
                      f"{binner.quota['normal']}/bin, separation -> "
                      f"{binner.min_sep:.3f} N")
            saved_before = rec.saved
        while (not continuous) and normal_cycles < a.max_cycles:
            normal_cycles += 1
            # -- load
            binner.new_pass()
            rec.arm(segment="normal_load", cycle=normal_cycles, axis="",
                    target_N=0.0)
            used, steps, peak_f, peak_d, why = 0.0, 0, 0.0, 0.0, ""
            next_anchor = anchor_grid
            f = measure_n()
            while True:
                # Target from the force actually being carried, floored at zero.
                # Taking it from a drifted or negative reading made the target
                # 0.00 N, which the Hertz model turns into a zero-length step:
                # 39 of 42 cycles on one sensor "ran" without moving, recording
                # 410 frames of a probe resting on the surface as loading data.
                t = min(max(f, 0.0) + pol["ramp_step"], force_cap)
                rec.retag(target_N=float(t))
                reached, f, used, why = _seek_force(
                    ip, ar, reader, -n, t, measure_n, model_n, used,
                    depth_cap, force_cap + a.force_tol, "normal",
                    travel_origin=ladder_origin)
                steps += 1
                d = surf - height()
                peak_f, peak_d = max(peak_f, f), max(peak_d, d)
                if f + 1e-9 >= next_anchor - a.force_tol:
                    anchor("force_series", f"N{next_anchor:.2f}",
                           force_target_N=float(next_anchor),
                           force_reached=bool(abs(f - next_anchor) <= a.force_tol),
                           stop_reason=why, travel_used_mm=used,
                           cycle=normal_cycles)
                    next_anchor = round(next_anchor + anchor_grid, 4)
                # The no-contact abort guards against a wrong surface height,
                # not against a gel that is still recovering. After the first
                # unload a soft 1 mm gel sat 0.15 mm lower for a few seconds
                # and the second cycle's first three steps read 0.010 N -- the
                # gel was there, just not yet back at its rest height. So the
                # test is travel-based: well past half the depth budget with
                # nothing pressing back is a probe in air.
                # Absolute, not a fraction of the depth cap. The cap is now a
                # 20 mm runaway guard, and 60 % of that would let a probe that
                # missed the gel travel 12 mm before anything objected.
                if f < a.contact_floor and used > a.no_contact_mm:
                    print(f"\n  ABORT: {used:.3f} mm in and the force is still "
                          f"{f:.3f} N. The probe is not on the gel.")
                    return 1
                if f >= force_cap - a.force_tol or why.startswith(
                        ("travel", "force cap", "step underflow", "refused",
                         "MoveL")):
                    break
                if steps > 400:
                    why = "step count"
                    break
            n_saved = rec.saved
            print(f"  {normal_cycles:>3} {'load':>6} {steps:>5} {peak_f:>7.3f} "
                  f"{peak_d:>7.3f} {n_saved:>6}  {why if not why.startswith('reached') else ''}")
            if why.startswith(("refused", "MoveL")):
                return 1
            # A cycle that never loaded the gel is not a cycle. It costs frames
            # that look like loading data and are not, so contact is re-found
            # before trying again, and repeated failure stops the run rather
            # than filling the budget with a probe sitting still.
            if peak_f < a.cycle_min_frac * force_cap:
                dead += 1
                print(f"      cycle {normal_cycles} carried only {peak_f:.3f} N "
                      f"({dead}/{a.max_dead_cycles}); re-finding the surface")
                if dead >= a.max_dead_cycles:
                    print("\n  ABORT: the ramp cannot load the gel. The surface "
                          "height or the F/T zero is wrong.")
                    return 1
                rec.disarm()
                for _ in range(40):
                    if measure_n() >= a.contact_floor:
                        break
                    if _move_along_normal(ip, -0.05, a, a.max_joint_step):
                        return 2
                    time.sleep(pol["ramp_settle"])
                ladder_origin = np.array(q("GetActualTCPPose", 0)[1:][:3])
                surf = height()          # the gel settled; this is its surface now
                print(f"      contact re-established at {surf:.3f} mm, "
                      f"{measure_n():.3f} N")
                rec.arm(segment="normal_load", cycle=normal_cycles, axis="",
                        target_N=0.0)
                continue
            dead = 0
            # -- unload: back out in the same force increments until clear
            binner.new_pass()
            rec.retag(segment="normal_unload")
            steps = 0
            while True:
                f = measure_n()
                if f < a.contact_floor or used <= 0.02:
                    break
                t = max(f - pol["ramp_step"], 0.0)
                rec.retag(target_N=float(t))
                reached, f, used, why = _seek_force(
                    ip, ar, reader, -n, t, measure_n, model_n, used,
                    depth_cap, force_cap + a.force_tol, "normal",
                    travel_origin=ladder_origin)
                steps += 1
                if why.startswith(("refused", "MoveL")):
                    return 1
                if steps > 400:
                    break
            # land exactly on the surface so every cycle starts from the same
            # height; the frames of this move are the zero-force end of the curve
            if _move_along_normal(ip, surf - height(), a, a.max_joint_step):
                return 2
            # Dwell at the surface with the camera running: the gel's recovery
            # after unloading is part of what a force estimator has to read
            # through, and the pause also gives the next cycle a partly
            # recovered surface instead of a sunken one.
            rec.retag(segment="dwell", target_N=0.0)
            time.sleep(a.cycle_dwell)
            used = 0.0
            print(f"  {normal_cycles:>3} {'unload':>6} {steps:>5} {'':>7} {'':>7} "
                  f"{rec.saved:>6}")
            if rec.capped:
                break
            if rec.error:
                print(f"  recorder: {rec.error}")
                return 1
            r_now = radial()
            if r_now > a.max_radial_drift:
                print(f"\n  ABORT: the contact is {r_now:.3f} mm off the sensor "
                      f"axis, past the {a.max_radial_drift} mm limit. The gel is "
                      "not being pressed where it was characterised.")
                print("     This is an ABSOLUTE position check, not a drift "
                      "check: it fails just as readily on a run that started "
                      "off-centre and never moved. Compare the radial at the "
                      "first and last frame of stream/frames.csv before looking "
                      "for something that moved -- on 2026-09-07 it was constant "
                      "to 0.010 mm across the whole cycle and the offset was "
                      "inherited from the phases before collect.")
                return 1
            gained = rec.saved - saved_before
            if gained < a.cycle_min_gain:
                binner.relax(f"normal cycle {normal_cycles} added {gained} frames")
                print(f"      only {gained} new frames; quota -> "
                      f"{binner.quota['normal']}/bin, separation -> "
                      f"{binner.min_sep:.3f} N")
            saved_before = rec.saved
        rec.disarm()
        rec.set_cap(budget)

        # ---------------- mid zero check, off the gel ----------------
        print(f"\n--- lifting {a.retract:.1f} mm for the mid-run zero check ---")
        if _move_along_normal(ip, a.retract, a, a.approach_joint_step, vel=a.vel_free):
            return 2
        zero_check("between normal and shear blocks")

        # ---------------- shear block ----------------
        print(f"\n--- descending to {hold_depth:.2f} mm depth for {hold:.2f} N ---")
        if descend_to(surf - hold_depth):
            return 2
        time.sleep(a.settle)
        shear_origin = np.array(q("GetActualTCPPose", 0)[1:][:3])
        fracs = [float(x) for x in a.shear_fractions.split(",")]
        print(f"\n--- shear cycles until {budget} frames ---")
        print(f"  {'cyc':>3} {'axis':>4} {'hold N':>7} {'cap N':>6} {'rungs':>5} "
              f"{'peak N':>7} {'travel':>7} {'frames':>6}  note")
        saved_before = rec.saved
        while continuous and not rec.done and shear_cycles < a.max_cycles:
            shear_cycles += 1
            reached, fz, _u, whyn = _seek_force(
                ip, a, reader, -n, hold, measure_n, model_n, 0.0,
                depth_cap, force_cap + a.force_tol, "normal",
                travel_origin=shear_origin)
            if whyn.startswith(("refused", "MoveL")):
                return 1
            if measure_n() < max(a.contact_floor, 0.4 * hold):
                print(f"\n  ABORT: carrying {measure_n():.3f} N against a {hold} N "
                      "hold. Shearing from here would drag through air.")
                return 1
            # ONE origin for the whole shear block. `centre` used to be re-read
            # from the actual pose at the top of every axis, so it FOLLOWED the
            # drift instead of removing it: each axis started wherever the last
            # one left off, the per-axis return converged on that moved point,
            # and the block walked. Measured 2026-09-08 on
            # DIGIT_Marker_soft_2mm_r1: the normal block ended on-axis to
            # 0.079 mm and the shear block added 0.22 mm in four cycles, past
            # the 0.3 mm abort with 563 of 1000 frames saved. Anchoring every
            # axis to the same point makes the existing return an absolute one.
            # Back onto the axis through shear_origin -- the point captured
            # before this loop, so the correction cannot drift with it.
            if _recentre_lateral(shear_origin,
                                 max(a.release_mm_s / 2.5 * 100.0, 1.0)):
                return 1
            shear_block_origin = np.array(q("GetActualTCPPose", 0)[1:][:3])
            for axis in a.order.split(","):
                axis = axis.strip()
                u = uvec[axis]
                # LATERAL ONLY. A full 3-D return here restores the height
                # the cycle started at, and during shear the probe rides UP on
                # the gel -- so putting the height back drives it deeper, four
                # times a cycle, cycle after cycle. Measured 2026-09-08 on
                # DIGIT_Marker_soft_2mm_r1: the normal force during the shear
                # block reached 13.4 N (median 5.7) against a 1.20 N hold, and
                # the depth reached 1.355 mm against a 1.40 mm backstop. The
                # gel survived -- its surface came back to 24.619 mm against
                # 24.597 at the start, no permanent set -- but a thinner or
                # softer one need not have. The height belongs to the force
                # servo; only the radial walk is ours to undo.
                _rc_s = _recentre_lateral(shear_block_origin,
                                          max(a.release_mm_s / 2.5 * 100.0, 1.0))
                if _rc_s:
                    return _rc_s
                fz_now = measure_n()
                shear_cap = min(a.max_shear_force, a.mu_floor * fz_now)
                centre = q("GetActualTCPPose", 0)[1:]
                axis_origin = np.array(centre[:3])
                binner.new_pass()
                rec.arm(segment=f"shear_{axis}_out", cycle=shear_cycles,
                        axis=axis, target_N=float(shear_cap))

                def measure_s():
                    w, err = reader.read_fresh()
                    if err:
                        raise RuntimeError(err)
                    return float(np.array(w[:2]) @ u)

                used, peak, why, fs, nseg = 0.0, 0.0, "", 0.0, 0
                limit = a.max_travel_shear - a.travel_margin
                ks = max(a.shear_k, 0.05)
                while used < limit:
                    step = min(_step_for(ks), limit - used)
                    fs_before, u_before = fs, used
                    rv, _dt = _glide(axes[axis], step, _pace(ks, step))
                    if rv:
                        return rv
                    nseg += 1
                    p_now = np.array(q("GetActualTCPPose", 0)[1:][:3])
                    used = abs(float((p_now - axis_origin) @ axes[axis]))
                    fs = measure_s(); fz_here = measure_n()
                    if used - u_before > 1e-3:
                        ks = 0.5 * ks + 0.5 * max((fs - fs_before) / (used - u_before), 0.05)
                    peak = max(peak, fs)
                    if fs >= shear_cap - a.force_tol:
                        why = "reached"
                        break
                    if fz_here < a.slip_off_frac * fz_now:
                        why = "load collapsed"
                        break
                    # The load can run AWAY as well as collapse, and until
                    # 2026-09-08 only the collapse was watched. The normal
                    # servo below corrects at most 0.04 mm per segment, so
                    # anything that drives the probe in faster than that wins:
                    # a full 3-D re-centre inside the shear block put 13.4 N
                    # on a gel held at 1.20 N, eleven times the hold, with
                    # nothing objecting the whole way down. That bug is gone,
                    # but the gel had no guard of its own and now it does.
                    # 4x the hold, not 2.5x. A stiff gel gives large single-
                    # segment force swings even when the hold is stable: with
                    # the runaway fixed, DIGIT_Marker_soft_2mm_r1 sat at a
                    # 1.202 N median against its 1.20 N hold and still touched
                    # 3.21 N (p95 2.27), because 0.04 mm on a 10 N/mm gel is
                    # 0.4 N. The guard is for a load that WALKS -- 6.5 N and
                    # climbing -- not for the peaks of one that holds.
                    _fz_max = max(4.0 * hold, force_cap + 2.0)
                    if fz_here > _fz_max:
                        print(f"\n  ABORT: carrying {fz_here:.2f} N normal against "
                              f"a {hold:.2f} N hold, past the {_fz_max:.2f} N "
                              f"guard. The shear block is driving the probe in.")
                        return 1
                    # hold the normal load: one model step if it has sagged
                    if abs(hold - fz_here) > a.force_tol:
                        d_now = max(surf - height(), 0.0)
                        d_want = (max(hold, 0.0) / a_h) ** (2.0 / 3.0)
                        dz = float(np.clip(d_want - d_now, -0.04, 0.04))
                        if 0.0 <= d_now + dz <= depth_cap and abs(dz) > 1e-4:
                            rv, _dt = _glide(-n, dz, _pace(max(k_local, 0.2), abs(dz)))
                            if rv:
                                return rv
                    if nseg > 400:
                        why = "segment count"
                        break
                if not why:
                    why = f"travel limit {a.max_travel_shear} mm"
                anchor("force_shear", f"{axis}S{fs:.2f}", shear_axis=axis,
                       shear_target_N=float(shear_cap), force_reached=bool(why == "reached"),
                       stop_reason=why, travel_used_mm=used,
                       normal_hold_N=float(hold), cycle=shear_cycles)
                print(f"  {shear_cycles:>3} {axis:>4} {fz_now:>7.3f} {shear_cap:>6.3f} {nseg:>5} "
                      f"{peak:>7.3f} {used:>7.3f} {rec.saved:>6}  {'' if why == 'reached' else why}")
                # back to the centre in one continuous glide, recording the release
                binner.new_pass()
                rec.retag(segment=f"shear_{axis}_back", target_N=0.0)
                p_now = np.array(q("GetActualTCPPose", 0)[1:][:3])
                vec = axis_origin - p_now
                dist = float(np.linalg.norm(vec))
                # The return is a RELEASE, not a ramp: the forces it passes
                # through are ones the outward glide already covered, so it
                # needs no force resolution and gets a brisk fixed pace.
                # Pacing it like the ramp cost 426 s of the 788 s collect on
                # 9DTact_hard_1mm_r1 (2026-09-07) -- 21 s per axis, four axes,
                # five cycles -- against 51 s for the stepped ramp's three
                # fixed steps, and wiped out everything the faster ramp won.
                back_v = float(np.clip(a.release_mm_s / max(pace["mm_per_s_100"], 0.05)
                                       * 100.0, 0.5, 40.0))
                nb = 0
                # The return had no normal-force guard -- the outward loop's
                # guard does not run here -- and on DIGIT_Marker_medium_1mm_r2
                # (2026-09-09, ball8, 1.20 N hold, 1 mm gel) two return frames
                # read 6.08 N at 0.556 mm while the out-glide before them sat
                # at 2.7-3.3 N / 0.43 mm. Transient, and the next axis re-seated
                # to 1.08 N, but 6 N on a 1 mm gel is five times the hold with
                # nothing watching. Same guard as the outward loop; on a hit,
                # back out along the normal one small step and re-check, and
                # only abort if it does not clear.
                _fz_max_b = max(4.0 * hold, force_cap + 2.0)
                while dist > 1e-3 and nb < 12:
                    step = min(max(dist / 3.0, 0.05), dist)
                    rv, _dt = _glide(vec / dist, step, back_v)
                    if rv:
                        return rv
                    nb += 1
                    _fz_b = measure_n()
                    if _fz_b > _fz_max_b:
                        rv, _dt = _glide(+n, 0.05, back_v)      # retract 0.05 mm
                        if rv:
                            return rv
                        _fz_b2 = measure_n()
                        print(f"  return guard: {_fz_b:.2f} N against a {hold:.2f} N "
                              f"hold, retracted 0.05 mm -> {_fz_b2:.2f} N")
                        if _fz_b2 > _fz_max_b:
                            print(f"\n  ABORT: still {_fz_b2:.2f} N after retracting; "
                                  "the return glide is driving the probe in.")
                            return 1
                    p_now = np.array(q("GetActualTCPPose", 0)[1:][:3])
                    vec = axis_origin - p_now
                    dist = float(np.linalg.norm(vec))
                if rec.done:
                    break
            if rec.error:
                print(f"  recorder: {rec.error}")
                return 1
            r_now = float(np.linalg.norm(
                (np.array(centre[:3]) - t_sensor)
                - ((np.array(centre[:3]) - t_sensor) @ n) * n))
            if r_now > a.max_radial_drift:
                print(f"\n  ABORT: the shear centre is {r_now:.3f} mm off the sensor axis.")
                return 1
            gained = rec.saved - saved_before
            if gained < a.cycle_min_gain and not rec.done:
                binner.relax(f"shear cycle {shear_cycles} added {gained} frames")
                print(f"      only {gained} new frames; quota -> "
                      f"{binner.quota['shear']}/bin, separation -> "
                      f"{binner.min_sep:.3f} N")
            saved_before = rec.saved
        while (not continuous) and not rec.done and shear_cycles < a.max_cycles:
            shear_cycles += 1
            # Re-seat the normal load once per cycle, not once per axis.
            # Per-axis was tighter -- without any re-seat the load fell 12-13 %
            # on 3 mm gels and 29-40 % on 1 mm ones across four axes -- but it
            # cost a converging seek four times a cycle. Once a cycle keeps the
            # four axes anchored to a common load while letting the gel creep
            # between them, which broadens the (Fz, Fxy) coverage rather than
            # narrowing it; every frame still carries its own measured Fz.
            reached, fz, _u, whyn = _seek_force(
                ip, a, reader, -n, hold, measure_n, model_n, 0.0,
                depth_cap, force_cap + a.force_tol, "normal",
                travel_origin=shear_origin)
            if whyn.startswith(("refused", "MoveL")):
                return 1
            if measure_n() < max(a.contact_floor, 0.4 * hold):
                print(f"\n  ABORT: carrying {measure_n():.3f} N against a {hold} N "
                      "hold. Shearing from here would drag through air.")
                return 1
            # off, see the continuous branch above
            shear_block_origin = np.array(q("GetActualTCPPose", 0)[1:][:3])
            for axis in a.order.split(","):
                axis = axis.strip()
                u = uvec[axis]
                # off, see the continuous branch above
                fz_now = measure_n()
                shear_cap = min(a.max_shear_force, a.mu_floor * fz_now)
                targets = [round(shear_cap * fr, 4) for fr in fracs
                           if shear_cap * fr >= a.shear_abs_min]
                centre = q("GetActualTCPPose", 0)[1:]
                axis_origin = np.array(centre[:3])
                binner.new_pass()
                rec.arm(segment=f"shear_{axis}_out", cycle=shear_cycles,
                        axis=axis, target_N=0.0)

                def measure_s():
                    w, err = reader.read_fresh()
                    if err:
                        raise RuntimeError(err)
                    return float(np.array(w[:2]) @ u)

                k_guess = [a.shear_k]

                def model_s(f_now, f_want):
                    return (f_want - f_now) / max(k_guess[0], 0.05)

                used, peak, why = 0.0, 0.0, ""
                for t in targets:
                    rec.retag(target_N=float(t))
                    reached, f, used, why = _seek_force(
                        ip, a, reader, axes[axis], t, measure_s, model_s, used,
                        a.max_travel_shear, shear_cap + a.force_tol, axis,
                        travel_origin=axis_origin,
                        hold=_hold_spec(n, hold, measure_n, a_h,
                                        lambda: surf - height(), depth_cap))
                    if used > 0.05:
                        k_guess[0] = max(f / used, 0.05)
                    peak = max(peak, f)
                    w_now, _ = reader.read_fresh()
                    # With 10 mm of lateral allowance the tip can travel far
                    # enough to slide off the contact patch entirely. Nothing in
                    # the shear seek watches the normal load, and a contact that
                    # has left the gel still reports a plausible shear force
                    # from the shaft dragging. The load collapsing is the signal.
                    # Judged against what THIS axis started with, not the
                    # cycle's nominal hold. The load creeps down across a cycle
                    # by design now, and a fixed fraction of the nominal would
                    # read that ordinary creep as the contact leaving the gel --
                    # truncating the third and fourth axes on thin gels.
                    fz_here = -float(w_now[2])
                    if fz_here < a.slip_off_frac * fz_now:
                        print(f"       {axis} stops here: normal load fell to "
                              f"{fz_here:.2f} N from {fz_now:.2f} N at the start "
                              "of this axis — the contact is sliding off")
                        why = "load collapsed"
                    anchor("force_shear", f"{axis}S{t:.2f}", shear_axis=axis,
                           shear_target_N=float(t), force_reached=bool(reached),
                           stop_reason=why, travel_used_mm=used,
                           normal_hold_N=float(hold), cycle=shear_cycles)
                    if why.startswith(("refused", "MoveL")):
                        return 1
                    if not reached and why.startswith(("travel", "force cap",
                                                       "step underflow",
                                                       "load collapsed")):
                        break
                print(f"  {shear_cycles:>3} {axis:>4} {fz_now:>7.3f} {shear_cap:>6.3f} "
                      f"{len(targets):>5} {peak:>7.3f} {used:>7.3f} {rec.saved:>6}  "
                      f"{'' if why.startswith('reached') else why}")
                # back to centre in three steps, recording the release
                binner.new_pass()
                rec.retag(segment=f"shear_{axis}_back", target_N=0.0)
                p_now = np.array(q("GetActualTCPPose", 0)[1:][:3])
                for k in (1, 2, 3):
                    pt = p_now + (axis_origin - p_now) * (k / 3.0)
                    tgt = [float(v) for v in pt] + [float(v) for v in centre[3:]]
                    pl = mv.plan(ip, tgt, a.approach_joint_step)
                    if not pl.get("ok"):
                        print(f"  refusing the return: {pl.get('why')}")
                        return 2
                    tool = (pl["active_tool"][1]
                            if isinstance(pl["active_tool"], list) else 1)
                    if mv.send_movel(ip, pl["target_joints"], pl["target_pose"],
                                     tool, a.vel, a.ovl) != 0:
                        return 1
                    time.sleep(pol["ramp_settle"])
                if rec.done:
                    break
            if rec.error:
                print(f"  recorder: {rec.error}")
                return 1
            # The shear block moves sideways on purpose, so it is judged
            # against the centre it returns to, not the instantaneous position.
            # Judged on the centre the sweep returns to, which is on the axis
            # by construction -- so the allowance is the drift limit itself,
            # not the drift limit plus the lateral travel. Adding the travel
            # made the threshold 10.3 mm once the shear allowance went to 10,
            # which is no guard at all.
            r_now = float(np.linalg.norm(
                (np.array(centre[:3]) - t_sensor)
                - ((np.array(centre[:3]) - t_sensor) @ n) * n))
            if r_now > a.max_radial_drift:
                print(f"\n  ABORT: the shear centre has wandered {r_now:.3f} mm "
                      "off the sensor axis.")
                return 1
            gained = rec.saved - saved_before
            if gained < a.cycle_min_gain and not rec.done:
                binner.relax(f"shear cycle {shear_cycles} added {gained} frames")
                print(f"      only {gained} new frames; quota -> "
                      f"{binner.quota['shear']}/bin, separation -> "
                      f"{binner.min_sep:.3f} N")
            saved_before = rec.saved
        rec.disarm()

        # ---------------- unload and final zero ----------------
        print(f"\n--- unloading to the surface, then {a.retract:.1f} mm clear ---")
        if _move_along_normal(ip, surf - height(), a, a.approach_joint_step):
            return 2
        if _move_along_normal(ip, a.retract, a, a.approach_joint_step, vel=a.vel_free):
            return 2
        zero_check("end of collect")
        rv = 0
    finally:
        rec.stop()
        if reader is not None:
            reader.stop()
        poses.stop()
        cam.close()
        ft.disconnect()

        # ---------------- label every frame ----------------
        t_ft, W = reader.history() if reader is not None else (np.zeros(0), np.zeros((0, 6)))
        t_p, P = poses.history()
        zc_t = np.array([z["t"] for z in zero_checks])
        zc_w = np.array([z["drift_wrench"] for z in zero_checks])

        def drift_at(t: float) -> np.ndarray:
            if zc_t.size == 0:
                return np.zeros(6)
            if zc_t.size == 1 or t <= zc_t[0]:
                return zc_w[0]
            if t >= zc_t[-1]:
                return zc_w[-1]
            return np.array([np.interp(t, zc_t, zc_w[:, k]) for k in range(6)])

        rows = []
        n_interp = 0
        for r in rec.records:
            w, nch = reader.window(r["t_exposure_start"], r["t_img"]) \
                if reader is not None else (np.zeros(6), 0)
            if nch == 0:
                n_interp += 1
            pose, gap = poses.at(r["t_img"])
            h = height(pose) if np.isfinite(pose[0]) else float("nan")
            wc = w - drift_at(r["t_img"])
            F_b = R @ w[:3]
            rows.append([r["index"], r["file"], r.get("missing", False),
                         f"{r['t_img']:.6f}", f"{r['t_exposure_start']:.6f}",
                         r.get("segment", ""), r.get("cycle", ""),
                         r.get("axis", ""), r.get("target_N", ""),
                         *np.round(w, 5), *np.round(wc, 5), *np.round(F_b, 5),
                         nch, *np.round(pose, 4), round(gap, 4),
                         round(h, 4), round(surf - h, 4)])
        stream_dir.mkdir(exist_ok=True)
        with open(stream_dir / "frames.csv", "w", newline="") as fh:
            wcsv = csv.writer(fh)
            wcsv.writerow(["index", "file", "missing", "t_img", "t_exposure_start",
                           "segment", "cycle", "axis", "target_N",
                           "Fx_s", "Fy_s", "Fz_s", "Tx_s", "Ty_s", "Tz_s",
                           "Fx_s_corr", "Fy_s_corr", "Fz_s_corr",
                           "Tx_s_corr", "Ty_s_corr", "Tz_s_corr",
                           "Fx_base", "Fy_base", "Fz_base", "ft_chunks",
                           "tcp_x", "tcp_y", "tcp_z", "rx", "ry", "rz", "pose_gap_s",
                           "height_above_plane_mm", "depth_mm"])
            wcsv.writerows(rows)
        with open(stream_dir / "ft.csv", "w", newline="") as fh:
            wcsv = csv.writer(fh)
            wcsv.writerow(["t", "Fx", "Fy", "Fz", "Tx", "Ty", "Tz"])
            for t, w in zip(t_ft, W):
                wcsv.writerow([f"{t:.6f}", *np.round(w, 5)])
        with open(stream_dir / "pose.csv", "w", newline="") as fh:
            wcsv = csv.writer(fh)
            wcsv.writerow(["t", "x", "y", "z", "rx", "ry", "rz"])
            for t, pp in zip(t_p, P):
                wcsv.writerow([f"{t:.6f}", *np.round(pp, 4)])
        with open(stream_dir / "zero_checks.csv", "w", newline="") as fh:
            wcsv = csv.writer(fh)
            wcsv.writerow(["t", "at", "where", "Fx", "Fy", "Fz", "Tx", "Ty", "Tz"])
            for z in zero_checks:
                wcsv.writerow([f"{z['t']:.6f}", z["at"], z["where"],
                               *np.round(z["drift_wrench"], 5)])
        elapsed = time.time() - t_start
        armed_t = 0.0
        if rec.records:
            armed_t = rec.records[-1]["t_img"] - rec.records[0]["t_img"]
        st_run["stream"] = {
            "saved": rec.saved, "budget": budget, "grabbed": rec.grabbed,
            "dropped": rec.dropped, "normal_cycles": normal_cycles,
            "shear_cycles": shear_cycles, "normal_budget": n_budget,
            "fps": (rec.saved / armed_t) if armed_t > 0 else 0.0,
            "ft_rate_hz": (t_ft.size / (t_ft[-1] - t_ft[0])) if t_ft.size > 1 else 0.0,
            "pose_rate_hz": (t_p.size / (t_p[-1] - t_p[0])) if t_p.size > 1 else 0.0,
            "frames_with_interpolated_force": n_interp,
            "camera": {"fourcc": cam.fourcc, "exposure_s": cam.exposure_s,
                       "raw_jpeg": cam.raw_jpeg},
            "speeds_pct": {"contact": a.vel_contact, "free": a.vel_free},
            "policy": pol, "elapsed_s": elapsed,
            "distribution": binner.report(),
            "files": ["stream/frames.csv", "stream/ft.csv", "stream/pose.csv",
                      "stream/zero_checks.csv"],
        }
        save_state(run, st_run)
        br = binner.report()
        print(f"\n  distribution: {br['bins_occupied_normal']} normal bins and "
              f"{br['bins_occupied_shear']} shear bins occupied; "
              f"{br['rejected_bin_full']} frames dropped as a full bin, "
              f"{br['rejected_too_close']} as too close; "
              f"{len(br['relaxations'])} relaxation(s)")
        print(f"\n  stream: {rec.saved} of {budget} frames saved "
              f"({rec.grabbed} grabbed, {rec.dropped} missing), "
              f"{normal_cycles} normal + {shear_cycles} shear cycles, "
              f"{elapsed/60:.1f} min")
        print(f"  {len(st_run['samples'])} anchor sample(s); labels in "
              f"{stream_dir.relative_to(run)}/frames.csv")
    return rv


def phase_contactmap(a) -> int:
    """Deformed-region size at a fixed depth and at a fixed force.

    Two probes every sensor gets identically: 0.5 mm in, and 0.5 N on. The
    image is compared with the unloaded reference and the largest region that
    differs by more than `qc_diff_level` grey levels is measured -- area,
    equivalent radius, enclosing radius, centroid -- in pixels. Depth is
    geometric (from the surface the gel model recorded), force is sought with
    the F/T. A sensor whose limits do not reach a target gets measured at its
    limit instead and the record says so.
    """
    from vbts_platform.ft_stream import ForceReader

    run = active_run()
    st_run = load_state(run)
    if not st_run.get("reference"):
        print("  --phase reference first")
        return 2
    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2
    ok, why = mv.ready_to_move(mv.read_state(ip))
    if not ok:
        print(f"  not moving: {why}")
        return 2
    surf, a_h = _gel_model(a)
    if surf is None:
        return 2
    depth_cap, force_cap, reg, ent = sensor_limits(a)
    meta = yaml.safe_load(open(run / "meta.yaml"))
    R = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"])
    n = R[:, 2]
    q = chk.ReadOnlyProxy(ip)
    t_sensor, _ = mv.sensor_axis()

    def height():
        return float((np.array(q("GetActualTCPPose", 0)[1:][:3]) - t_sensor) @ n)

    okt, whyt = check_indenter_tool(robot_pose(ip))
    if not okt:
        print(f"  {whyt}")
        return 1
    ref_img = cv2.imread(str(run / "reference.png"))
    _shadow = shadows_the_gel(getattr(a, "sensor", None))
    if ref_img is None:
        print("  no reference.png")
        return 2
    out_dir = run / "contactmap"
    out_dir.mkdir(exist_ok=True)
    scale = _mm_per_px()
    diff_level = diff_level_for_sensor(ref_img, a, getattr(a, "sensor", None))

    d_target = min(a.map_depth, depth_cap)
    f_target = min(a.map_force, force_cap)
    print(f"\n  targets: {a.map_depth:.2f} mm" + (f" (limited to {d_target:.2f})" if d_target < a.map_depth else "")
          + f", {a.map_force:.2f} N" + (f" (limited to {f_target:.2f})" if f_target < a.map_force else ""))
    print(f"  region = |frame - reference| > {diff_level} levels "
          f"({a.diff_rel:.0%} of the reference brightness, floor {a.diff_min}) "
          f"after a 5 px blur; sizes in px" + (f" and mm ({scale} mm/px)" if scale else
                                      " (no mm/px calibration on file)"))

    clearance = surf + a.retract - height()
    if clearance > 0:
        if _move_along_normal(ip, clearance, a, a.approach_joint_step, vel=a.vel_free):
            return 2
    cam = Camera.from_config(camera_config_for(a.sensor))
    cam.open()
    ft = FTInterface.from_config()
    ft.connect()
    reader = None
    results = {}
    try:
        tare = ft.tare(duration_s=2.0)
        res = ft.read_wrench_mean(duration_s=1.0, tared=True)
        if np.linalg.norm(res[:3]) > 0.15:
            print("  not clear of the gel.")
            return 1
        reader = ForceReader(ft, tare).start()

        def measure_n():
            w, err = reader.read_fresh()
            if err:
                raise RuntimeError(err)
            return -float(w[2])

        def model_n(f_now, f_want):
            d_now = max((max(f_now, 0.0) / a_h) ** (2.0 / 3.0), 0.0)
            return (max(f_want, 0.0) / a_h) ** (2.0 / 3.0) - d_now

        def to_surface():
            h = height()
            stop_free = surf + a.approach_clear
            if h > stop_free + 1e-3:
                if _move_along_normal(ip, -(h - stop_free), a,
                                      a.approach_joint_step, vel=a.vel_free):
                    return 2
            if _move_along_normal(ip, -(height() - surf), a, a.approach_joint_step):
                return 2
            return 0

        def capture(tag: str, target: dict) -> dict:
            t_moved = time.time()
            time.sleep(a.map_settle)
            frame, t_img = cam.grab_after(t_moved + a.map_settle)
            w, _ = reader.read_fresh()
            h = height()
            r = contact_region(frame, ref_img, diff_level,
                               colour=_shadow)
            cv2.imwrite(str(out_dir / f"{tag}.png"), frame, [cv2.IMWRITE_PNG_COMPRESSION, 1])
            cv2.imwrite(str(out_dir / f"{tag}_diff.png"),
                        np.clip(r["_diff"] * 4, 0, 255).astype(np.uint8))
            cv2.imwrite(str(out_dir / f"{tag}_mask.png"), r["_mask"])
            # An untouched gel differs from its own reference by ~1.45 levels
            # of temporal noise (mean |diff| after the blur). Contact the F/T
            # can feel but the image cannot is either a stale frame or a real
            # finding, and either way it must not pass silently.
            if -float(w[2]) > 0.15 and r["mean_abs_diff_centre"] < a.image_floor:
                print(f"  !! {tag}: the F/T reads {-w[2]:.2f} N but the image is at the "
                      "noise floor -- a stale frame, or a sensor whose image does not "
                      "respond at this load. Recorded as measured.")
            rec = {**target, "at": datetime.now().isoformat(), "image": f"{tag}.png",
                   "image_time": t_img, "depth_mm": surf - h,
                   "height_above_plane_mm": h,
                   "normal_force_N": -float(w[2]), "wrench": w.tolist(),
                   "region": _region_public(r)}
            if scale:
                rec["region"]["area_mm2"] = r["area_px"] * scale * scale
                rec["region"]["radius_mm"] = r["radius_px"] * scale
                rec["region"]["enclosing_radius_mm"] = r["enclosing_radius_px"] * scale
            print(f"  {tag:<8} depth {surf - h:6.3f} mm  force {-w[2]:6.3f} N  "
                  f"area {r['area_px']:>7d} px  r_eq {r['radius_px']:6.1f} px  "
                  f"r_enc {r['enclosing_radius_px']:6.1f} px  "
                  f"dark core r {r['dark_radius_px']:5.1f} px  bright ring r "
                  f"{r['bright_radius_px']:5.1f} px  mean|diff| centre "
                  f"{r['mean_abs_diff_centre']:.2f}")
            return rec

        # -- at fixed depth
        if to_surface():
            return 2
        time.sleep(a.settle)
        if _move_along_normal(ip, -d_target, a, a.max_joint_step):
            return 2
        results["at_depth"] = capture("at_depth", {
            "target_depth_mm": a.map_depth, "target_used_mm": d_target,
            "limited_by_depth_cap": d_target < a.map_depth})
        # back off and let the gel recover before the force probe
        if _move_along_normal(ip, surf - height(), a, a.max_joint_step):
            return 2
        time.sleep(a.map_recover)

        # -- at fixed force
        origin = np.array(q("GetActualTCPPose", 0)[1:][:3])
        reached, f, used, why = _seek_force(
            ip, a, reader, -n, f_target, measure_n, model_n, 0.0,
            depth_cap, force_cap + a.force_tol, "normal", travel_origin=origin)
        results["at_force"] = capture("at_force", {
            "target_force_N": a.map_force, "target_used_N": f_target,
            "limited_by_force_cap": f_target < a.map_force,
            "force_reached": bool(reached), "stop_reason": why})

        if _move_along_normal(ip, surf - height(), a, a.max_joint_step):
            return 2
        if _move_along_normal(ip, a.retract, a, a.approach_joint_step, vel=a.vel_free):
            return 2
    finally:
        if reader is not None:
            reader.stop()
        ft.disconnect()
        cam.close()

    results["mm_per_px"] = scale
    results["diff_level"] = diff_level
    results["diff_level_rule"] = f"max({a.diff_min}, {a.diff_rel} x reference centre mean)"
    (out_dir / "contactmap.yaml").write_text(yaml.safe_dump(
        json.loads(json.dumps(results, default=str)), sort_keys=False))
    st_run["contact_map"] = json.loads(json.dumps(results, default=str))
    save_state(run, st_run)
    if ent is not None:
        keep = {}
        for k in ("at_depth", "at_force"):
            r = results[k]
            keep[k] = {kk: r[kk] for kk in r if kk not in ("wrench", "image_time")}
            keep[k]["region"] = {kk: vv for kk, vv in r["region"].items()
                                 if kk not in ("bbox_px", "n_blobs", "level", "blur_px",
                                               "min_area_px", "border_frac")}
        ent["contact_map"] = keep
        save_sensor(reg, ent)
        print(f"\n  registry updated: {ent['id']} contact_map")
    print(f"  written: {out_dir.relative_to(run)}/contactmap.yaml")
    return 0


REGISTRY = ROOT / "config" / "sensor_registry.yaml"


def load_sensor(sid: str) -> tuple:
    reg = yaml.safe_load(open(REGISTRY))
    for e in reg["sensors"]:
        if e["id"] == sid:
            return reg, e
    raise SystemExit(f"sensor {sid} is not in the registry")


def save_sensor(reg: dict, entry: dict) -> None:
    """Write ONE entry back, re-reading the file first.

    The `reg` a phase holds was loaded when that phase started, and phases run
    for minutes. Writing it back wholesale republishes that stale snapshot over
    everything changed since -- which silently reverted an edit made while a
    contactmap was running, and the next run then read the old value and
    collected to the wrong ceiling. Only the entry this call owns is replaced.
    """
    live = yaml.safe_load(open(REGISTRY))
    for i, e in enumerate(live["sensors"]):
        if e["id"] == entry["id"]:
            live["sensors"][i] = entry
            break
    else:
        live["sensors"].append(entry)
    REGISTRY.write_text(yaml.safe_dump(live, sort_keys=False, allow_unicode=True))


def phase_characterize(a) -> int:
    """Find one sensor's own safe envelope before loading it properly.

    Every elastomer here is a different thickness and hardness, and a 1 mm layer
    on a rigid backing is not the elastic half space Hertz assumes. As the
    contact approaches the backing the force stops following delta^1.5 and
    climbs faster, so the model fitted at the surface under-predicts what the
    next step will do -- the exact way to overshoot a force limit on a sensor
    nobody has measured yet.

    So the ceiling is found rather than assumed. The probe descends in small
    steps, and after each one the LOCAL exponent is measured. While the contact
    behaves like a half space that exponent sits near 1.5; when the backing
    starts carrying load it rises. Crossing the threshold ends the
    characterisation and sets the ceiling there. The fixed per-thickness depth
    limit stays as a backstop for the case where stiffening is gradual enough
    to not trip the test.
    """
    from vbts_platform.ft_stream import ForceReader

    reg, ent = load_sensor(a.sensor)
    run = active_run()
    st_run = load_state(run)
    if not st_run.get("reference"):
        print("  --phase reference first")
        return 2
    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2
    ok, why = mv.ready_to_move(mv.read_state(ip))
    if not ok:
        print(f"  not moving: {why}")
        return 2

    # The registry limit is per-sensor and reasoned; --max-travel-normal is a
    # blanket override. Applying the tighter of the two silently let a default
    # meant for another phase truncate a characterisation to less than half its
    # range, while the printout still carried the registry's justification next
    # to the overriding number. Both limits are named, and so is the one that
    # actually binds.
    reg_cap = depth_backstop(reg, ent)
    if a.force_depth_cap is not None:
        # An explicit operator override, upward included. Exists for probing a
        # sensor past its registry limit on purpose -- e.g. driving a 1 mm gel
        # to 1 N to see where its image stops responding -- and is only honest
        # together with --no-registry, so the ceiling the dataset was collected
        # under is not silently replaced by the probe's.
        depth_cap, cap_src = float(a.force_depth_cap), "OPERATOR OVERRIDE (--force-depth-cap)"
    elif a.max_travel_normal is None:
        depth_cap, cap_src = reg_cap, "backstop only — the per-thickness depth limit was removed 2026-09-04"
    else:
        depth_cap = min(reg_cap, a.max_travel_normal)
        cap_src = ("--max-travel-normal override"
                   if a.max_travel_normal < reg_cap else "backstop only")
    print(f"\n  sensor {ent['id']}")
    print(f"    {ent['principle']}, {ent['hardness']}, {ent['thickness_mm']} mm")
    print(f"    depth backstop {reg_cap:.2f} mm (no per-thickness limit)")
    if a.max_travel_normal is not None:
        print(f"    command-line limit   {a.max_travel_normal:.2f} mm")
    print(f"    binding depth cap    {depth_cap:.2f} mm  ({cap_src})")
    print(f"    force cap {a.max_force} N, exponent alarm at {a.exp_alarm}")

    surf = a.surface
    if surf is None:
        print("    --surface is required: run move_probe.py --search first")
        return 2

    meta = yaml.safe_load(open(run / "meta.yaml"))
    R = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"])
    n = R[:, 2]
    q = chk.ReadOnlyProxy(ip)
    t_sensor, _ = mv.sensor_axis()

    def height():
        return float((np.array(q("GetActualTCPPose", 0)[1:][:3]) - t_sensor) @ n)

    okt, whyt = check_indenter_tool(robot_pose(ip))
    if not okt:
        print(f"  {whyt}")
        return 1

    clearance = surf + a.retract - height()
    if clearance > 0:
        if _move_along_normal(ip, clearance, a, a.approach_joint_step, vel=a.vel_free):
            return 2

    # Ramp at the sensor's CENTRE, wherever the previous phase left the probe.
    # This phase takes its lateral position from the current pose, and running
    # it straight after calibgrid put it on the grid's last point -- 8.20 mm
    # off centre on DIGIT_hard_2mm_r2, out at the lattice corner. Two things
    # went wrong there and both are silent (2026-09-10): the contact sat
    # OUTSIDE the central half of the frame that `mean_abs_diff_centre` covers,
    # so the image metric barely moved (1.08 levels over the whole ramp against
    # 13.12 for the same unit's replicate) and the saturation test could never
    # fire; and the gel is far stiffer near its shell, so the ramp reached
    # 19.24 N at 1.85 mm where the centre of the replicate saturated at 9.04 N
    # and 1.66 mm. The ceiling that came out was not this unit's ceiling.
    pose_now = q("GetActualTCPPose", 0)[1:]
    p_now = np.array([float(v) for v in pose_now[:3]])
    o_base = np.array(
        meta["sensor_to_base_transform"]["origin_base_mm"])
    dx0 = float((p_now - o_base) @ R[:, 0])
    dy0 = float((p_now - o_base) @ R[:, 1])
    if max(abs(dx0), abs(dy0)) > 0.5:
        tilt = _grid_gel_tilt(a.sensor)
        sx, sy = tilt if tilt else (0.0, 0.0)
        print(f"  the probe is {dx0:+.2f} / {dy0:+.2f} mm off the sensor centre; "
              "moving back before the ramp")
        target = (p_now - dx0 * R[:, 0] - dy0 * R[:, 1]
                  - (dx0 * sx + dy0 * sy) * n)
        if _move_to_point(ip, target, [float(v) for v in pose_now[3:]], a,
                          a.approach_joint_step, vel=a.vel_free):
            return 2

    # The image is part of the envelope. A gel can keep carrying force after
    # its picture has stopped changing -- the layer is against its backing and
    # the optics see the same thing at 3 N as at 2 -- and past that point the
    # force is not measurable from the image, which is the only thing a VBTS
    # measures with. So every step also takes a frame, and the ramp stops when
    # the brightness change per newton falls under `sat_frac` of its peak.
    ref_img = cv2.imread(str(run / "reference.png"))
    _shadow = shadows_the_gel(getattr(a, "sensor", None))
    if ref_img is None:
        print("  no reference.png; --phase reference first")
        return 2
    char_dir = run / ("characterize" if not a.char_tag else f"characterize_{a.char_tag}")
    char_dir.mkdir(exist_ok=True)
    diff_level = diff_level_for_sensor(ref_img, a, getattr(a, "sensor", None))
    cam = Camera.from_config(camera_config_for(a.sensor))
    cam.open()                      # before the DAQ task: it must not sit unread
    ft = FTInterface.from_config()
    ft.connect()
    reader = None
    img_rows = []
    sat = {"max_measurable_force_N": None, "max_measurable_depth_mm": None,
           "reached": False,
           "metric": "mean |frame - reference| over the central half, grey levels",
           "threshold_frac_of_peak_slope": a.sat_frac,
           "min_force_N": a.sat_min_force, "consecutive": a.sat_hits}
    try:
        tare = ft.tare(duration_s=2.0)
        res = ft.read_wrench_mean(duration_s=1.0, tared=True)
        print(f"\n  zero residual |F| {np.linalg.norm(res[:3]):.4f} N")
        if np.linalg.norm(res[:3]) > 0.15:
            print("  not clear of the gel.")
            return 1
        reader = ForceReader(ft, tare).start()
        if _move_along_normal(ip, -(height() - surf), a, a.approach_joint_step):
            return 2
        time.sleep(a.settle)

        # Depth is READ BACK from the robot, not accumulated from the commands
        # that were sent. Summing commanded steps drifted 0.217 mm over 39 of
        # them here, which is 11 % of the range: forces then appear at depths
        # shallower than where they were actually measured and the gel looks
        # 16 % stiffer than it is. That single bookkeeping choice produced a
        # discrepancy convincing enough to be blamed on viscoelastic
        # relaxation, on loading history and on contact location in turn.
        base_h = height()
        print(f"\n  reference height {base_h:.3f} mm; depth is measured, not counted")
        print(f"\n  {'depth':>7} {'cmd':>7} {'force':>8} {'local exp':>10} "
              f"{'img':>6} {'lvl/N':>7}  note")
        d_hist, f_hist, s_hist = [], [], []
        stop = "depth backstop"
        depth = 0.0
        commanded = 0.0
        exp_hits = 0
        exp_first_over_mm = None
        sat_force = None                 # force at which the picture gave up
        sat_hits = 0
        peak_slope = 0.0
        slopes_seen: list = []
        # Every unit is pressed to --min-force whatever else says stop, because
        # a ceiling only means something against a common yardstick: the first
        # two units saturated at 7.37 and 9.03 N, and a ramp that stops at the
        # depth backstop on one and at saturation on another cannot be compared
        # across thickness at all. So while the force is under it, the depth
        # backstop, saturation and the exponent alarm are all overridden.
        # A last line remains: `hard_cap`. The one gel ever destroyed gave out
        # at 3.1 x its own thickness (6.19 mm on a 2 mm layer), so twice the
        # thickness is the furthest this will go, and if the force is still
        # short of the target there, it stops and says so.
        floor_f = float(a.char_floor_n)
        hard_cap = max(depth_cap, a.char_floor_depth_mult * ent["thickness_mm"])
        if floor_f > 0:
            print(f"  pressing to at least {floor_f:.1f} N even past the "
                  f"{depth_cap:.2f} mm backstop, and no further than "
                  f"{hard_cap:.2f} mm")
        f_now = 0.0
        while True:
            limit = hard_cap if f_now < floor_f else depth_cap
            if depth >= limit - 1e-6:
                break
            step = min(a.char_step, limit - depth)
            if step < 0.01:
                # The measured depth trails the commanded one by a few tens of
                # microns under load; chasing the last 5 um of the cap took six
                # near-zero steps and six noisy slope samples for nothing.
                break
            if _move_along_normal(ip, -step, a, a.max_joint_step):
                return 2
            commanded += step
            time.sleep(a.settle)
            depth = base_h - height()
            w, err = reader.read_fresh()
            if err:
                print(f"  F/T failed: {err}")
                return 1
            f = -float(w[2])
            frame, _t = cam.grab_settled()
            reg_img = contact_region(frame, ref_img, diff_level,
                               colour=_shadow)
            S = reg_img["mean_abs_diff_centre"]
            k = len(d_hist) + 1
            cv2.imwrite(str(char_dir / f"{k:02d}.png"), frame,
                        [cv2.IMWRITE_PNG_COMPRESSION, 1])
            d_hist.append(depth)
            f_hist.append(f)
            s_hist.append(S)
            # Brightness change per newton, as a least-squares slope over the
            # last `sat_window` steps spanning at least `sat_min_df` newtons.
            # A single-step slope divided 0.1 level of image scatter by a
            # 0.03 N force step and came out at -2.6 lvl/N on a gel that was
            # plainly still responding.
            slope = float("nan")
            if len(f_hist) >= a.sat_window:
                ff = np.array(f_hist[-a.sat_window:])
                ss = np.array(s_hist[-a.sat_window:])
                if ff.max() - ff.min() >= a.sat_min_df:
                    slope = float(np.polyfit(ff, ss, 1)[0])
                    if f > a.fit_floor:
                        slopes_seen.append(slope)
                        # The reference is the median of the three largest
                        # window slopes, not the single largest: one noisy
                        # window read 4.65 lvl/N on a curve whose real early
                        # slope was 2.76, and against that "peak" the 15 %
                        # test fired at what was really 25 % of the response.
                        top = sorted(slopes_seen, reverse=True)[:3]
                        peak_slope = float(np.median(top))
            img_rows.append({"step": k, "depth_mm": depth, "commanded_mm": commanded,
                             "force_N": f, "img_mean_abs_diff": S,
                             "slope_levels_per_N": slope,
                             "area_px": reg_img["area_px"],
                             "radius_px": reg_img["radius_px"],
                             "region_mean_diff": reg_img["mean_abs_diff_in_region"],
                             "dark_area_px": reg_img["dark_area_px"],
                             "dark_radius_px": reg_img["dark_radius_px"],
                             "dark_mean_diff": reg_img["dark_mean_diff"],
                             "bright_area_px": reg_img["bright_area_px"],
                             "bright_radius_px": reg_img["bright_radius_px"]})
            # A log-log slope is only as good as the smallest force in its
            # window. At 0.06 N against a 0.02 N noise floor the logarithm is
            # mostly noise, and the exponent it returns says nothing: the same
            # depth on this gel read 1.66 one run and 2.19 the next. Three gates
            # have to agree before the alarm is believed.
            exp = float("nan")
            window_ok = (len(d_hist) >= a.exp_window + 1
                         and min(f_hist[-a.exp_window - 1:]) > a.exp_min_force)
            if window_ok:
                dd = np.array(d_hist[-a.exp_window - 1:])
                ff = np.array(f_hist[-a.exp_window - 1:])
                exp = float(np.polyfit(np.log(dd), np.log(ff), 1)[0])
            # The backing cannot carry load until the indentation is a real
            # fraction of the layer. Below that the alarm is physically
            # impossible and any trigger is noise by definition.
            deep_enough = depth >= a.exp_min_depth_frac * ent["thickness_mm"]
            armed = window_ok and deep_enough
            note = ""
            sat_armed = (f >= a.sat_min_force and peak_slope > 0
                         and np.isfinite(slope))
            if f >= a.max_force:
                stop, note = "force cap", "force cap"
            elif sat_armed and slope < a.sat_frac * peak_slope:
                sat_hits += 1
                if sat_hits >= a.sat_hits and sat_force is None:
                    note = (f"image change {slope:.2f} lvl/N is under "
                            f"{a.sat_frac:.0%} of its peak {peak_slope:.2f}")
                    sat["reached"] = True
                    # the force where the response first fell under threshold
                    sat_force = float(f_hist[-sat_hits])
                    sat["max_measurable_force_N"] = sat_force
                    sat["max_measurable_depth_mm"] = float(d_hist[-sat_hits])
                    if a.past_saturation_n > 0:
                        # Carry on a little past the ceiling rather than
                        # stopping on it. Saturation is declared from a slope
                        # measured over a window, so the steps just past it are
                        # what show whether the picture has really stopped
                        # answering or only paused -- and they cost nothing:
                        # this unit's ceiling was 9.04 N where the one gel ever
                        # damaged held 19 N with its imprint still intact.
                        note += (f"; pressing on to "
                                 f"{sat_force + a.past_saturation_n:.2f} N")
                    else:
                        stop = "image saturation"
                elif sat_hits >= a.sat_hits:
                    note = f"past saturation, {f - sat_force:+.2f} N beyond it"
                    if f >= sat_force + a.past_saturation_n:
                        stop = "image saturation (+ margin)"
                else:
                    note = f"image change low ({sat_hits}/{a.sat_hits})"
            elif armed and np.isfinite(exp) and exp > a.exp_alarm:
                exp_hits += 1
                if exp_hits >= a.exp_hits:
                    # Record where the backing starts to carry load, but do
                    # not stop for it unless asked. The alarm was the safe
                    # envelope while there was no depth limit; the (thickness
                    # + 1) x 0.9 backstop is the safety now, and stopping here
                    # only truncated the range. On 9DTact_soft_1mm_r2
                    # (2026-09-07, ball8) it fired at 1.32 mm / 1.76 N -- the
                    # exponent really was 2.45, a soft top layer over a stiff
                    # floor -- while the same unit had carried 9.09 N at
                    # 4.12 mm with no permanent set, and the image was still
                    # answering at 1.71 lvl/N. A 4 mm sphere feels the floor
                    # at 1.3 mm because its contact is already 3 mm wide.
                    if exp_first_over_mm is None:
                        exp_first_over_mm = float(depth)
                    if a.exp_alarm_stops:
                        stop, note = "substrate stiffening", f"exponent {exp:.2f}"
                    else:
                        note = f"exponent {exp:.2f} (backing loaded; noted, not stopping)"
                else:
                    note = f"exponent {exp:.2f} ({exp_hits}/{a.exp_hits})"
            else:
                exp_hits = 0
                if not (sat_armed and slope < a.sat_frac * peak_slope):
                    sat_hits = 0
            print(f"  {depth:>7.3f} {commanded:>7.3f} {f:>8.3f} "
                  + (f"{exp:>10.2f}" if np.isfinite(exp) else f"{'—':>10}")
                  + f" {S:>6.2f} "
                  + (f"{slope:>7.2f}" if np.isfinite(slope) else f"{'—':>7}")
                  + f"  {note}")
            f_now = float(f)
            if f_now < floor_f and depth < hard_cap - 1e-6:
                # Short of the common yardstick. Whatever the step decided --
                # saturation, the exponent, the depth backstop -- it is
                # recorded and the ramp carries on; only the STOP is held.
                continue
            if note and not (note.startswith(("exponent", "image change low",
                                              "past saturation"))
                             or "pressing on to" in note):
                break
            if stop.startswith("image saturation ("):
                break
            if (note.startswith("exponent") and exp_hits >= a.exp_hits
                    and a.exp_alarm_stops):
                break

        d = np.array(d_hist)
        f = np.array(f_hist)
        # Fit only where the force is real. A 0.05 N floor let two points at
        # 0.050 and 0.051 N -- two and a half times the noise, and identical to
        # each other across a doubling of depth -- into a log-log fit, which
        # dragged the exponent to 1.04 and the coefficient 25 % away from what a
        # repeat measured. Those points were the probe not yet touching.
        m = f > a.fit_floor
        if m.sum() < 3:
            print(f"  only {int(m.sum())} points above the {a.fit_floor} N fit "
                  "floor; the model from this run is not trustworthy")
        exp_all = (float(np.polyfit(np.log(d[m]), np.log(f[m]), 1)[0])
                   if m.sum() >= 3 else None)

        # The depth axis is anchored to a surface height that came from the
        # search's contact point plus a guessed margin, and that guess has been
        # wrong by up to 0.25 mm -- this run's two shallowest samples read
        # NEGATIVE force, so the probe was still in air where the axis said it
        # was 0.2 mm in. Fitting the offset alongside the coefficient lets the
        # data place its own zero, which is the same thing the depth-series
        # summary does and for the same reason.
        surf_off, a_h, fit_rms, n_fit = None, None, None, 0
        best = None
        for d0 in np.arange(-0.10, 0.45, 0.002):
            dep = d - d0
            mm = (dep > 1e-3) & (f > a.fit_floor * 0.3)
            if mm.sum() < 3:
                continue
            aa = float(np.sum(dep[mm] ** 1.5 * f[mm]) / np.sum(dep[mm] ** 3))
            rr = float(np.sqrt(np.mean((aa * dep[mm] ** 1.5 - f[mm]) ** 2)))
            if best is None or rr < best[0]:
                best = (rr, float(d0), aa, int(mm.sum()))
        if best:
            fit_rms, surf_off, a_h, n_fit = best
            print(f"  fitted on {n_fit} points, surface {surf_off:+.3f} mm from "
                  f"where it was assumed, rms {fit_rms:.4f} N")
        elif m.sum() >= 3:
            a_h = float(np.sum(d[m] ** 1.5 * f[m]) / np.sum(d[m] ** 3))
            print(f"  fitted on {int(m.sum())} points with the surface held fixed")
        safe_depth = float(d[-1])
        safe_force = float(f[-1])
        # The envelope of a VBTS ends where its PICTURE ends, not where the gel
        # is still willing to carry load. Taking the last step made the two
        # disagree as soon as the ramp was allowed past saturation:
        # DIGIT_hard_2mm_r2 saturated at 9.03 N and was recorded as 14.18 N,
        # which would have told the collecting phases to drive a sensor half
        # again past the force it can still read. Where saturation was found,
        # that is the envelope.
        if sat["reached"] and sat.get("max_measurable_depth_mm") is not None:
            print(f"  ramp ended at {safe_depth:.3f} mm / {safe_force:.3f} N, "
                  "but the envelope is where the image stopped answering")
            safe_depth = float(sat["max_measurable_depth_mm"])
            safe_force = float(sat["max_measurable_force_N"])
        drift = float(commanded - safe_depth)
        print(f"\n  commanded {commanded:.3f} mm, measured {safe_depth:.3f} mm, "
              f"difference {drift:+.3f} mm")
        if floor_f > 0 and float(f[-1]) < floor_f:
            stop = f"{hard_cap:.2f} mm hard cap, still under the floor"
        print(f"  stopped on: {stop}")
        if floor_f > 0:
            print(f"  reached {float(f[-1]):.2f} N against a {floor_f:.1f} N floor"
                  + ("" if float(f[-1]) >= floor_f else "  <-- SHORT"))
        print(f"  safe envelope: {safe_depth:.3f} mm, {safe_force:.3f} N")
        if a_h:
            print(f"  gel model F = {a_h:.3f} * depth^1.5   "
                  f"(free exponent {exp_all:.3f})")
        ladder = reg["force_policy"]["target_ladder_N"]
        usable = [t for t in ladder if t <= safe_force]
        print(f"  reaches {len(usable)} of {len(ladder)} ladder rungs "
              f"(up to {usable[-1] if usable else 0} N)")
        if not sat["reached"]:
            last_slope = next((r["slope_levels_per_N"] for r in reversed(img_rows)
                               if np.isfinite(r["slope_levels_per_N"])), float("nan"))
            sat["note"] = (f"not reached within the limits: stopped on {stop} at "
                           f"{f_hist[-1]:.2f} N with the image still changing at "
                           f"{last_slope:.2f} lvl/N ({(last_slope / peak_slope) if peak_slope else float('nan'):.0%} of peak)")
        sat["peak_slope_levels_per_N"] = float(peak_slope)
        sat["image_change_at_stop"] = float(s_hist[-1]) if s_hist else None
        print(f"\n  image response: " + (
            f"saturates at {sat['max_measurable_force_N']:.2f} N -> that is the "
            "maximum force this sensor can measure from its image"
            if sat["reached"] else sat["note"]))
    finally:
        if reader is not None:
            reader.stop()
        ft.disconnect()
        cam.close()
        if img_rows:
            with open(char_dir / "steps.csv", "w", newline="") as fh:
                wcsv = csv.DictWriter(fh, fieldnames=list(img_rows[0].keys()))
                wcsv.writeheader()
                wcsv.writerows(img_rows)

    if a.no_registry:
        (char_dir / "result.yaml").write_text(yaml.safe_dump(json.loads(json.dumps({
            "sensor": ent["id"], "at": datetime.now().isoformat(),
            "depth_cap_used_mm": depth_cap, "force_cap_used_N": a.max_force,
            "exp_alarm": a.exp_alarm, "exp_alarm_stops": bool(a.exp_alarm_stops),
            "exponent_first_over_mm": exp_first_over_mm, "stopped_on": stop,
            "reached_depth_mm": safe_depth, "reached_force_N": safe_force,
            "hertz_a": a_h, "free_exponent": exp_all, "image_response": sat,
            "registry_written": False}, default=str)), sort_keys=False))
        print(f"\n  --no-registry: result kept in {char_dir.relative_to(run)}/result.yaml; "
              "the registry entry is untouched")
        return 0

    # Characterising the same sensor again is a measurement, not a correction:
    # the coefficient moved 16 % between two runs on this one unit and which
    # number is right depends on loading history. Overwriting would destroy the
    # comparison that question needs, so each result is appended.
    prev = {k: ent.get(k) for k in ("characterised_at", "gel_model",
                                    "safe_depth_mm", "safe_force_N", "stopped_on",
                                    "ladder_rungs_reached", "depth_cap_used_mm",
                                    "image_response", "run")}
    if prev.get("characterised_at"):
        hist = ent.setdefault("history", [])
        key = (prev["characterised_at"], (prev.get("gel_model") or {}).get("hertz_a"))
        if key not in [(h.get("characterised_at"),
                        (h.get("gel_model") or {}).get("hertz_a")) for h in hist]:
            hist.append(prev)
    ent.update({"status": "characterised",
                "gel_model": {"hertz_a": a_h, "free_exponent": exp_all,
                              "surface_mm": float(surf if surf_off is None
                                                  else surf - surf_off)},
                "safe_depth_mm": safe_depth, "safe_force_N": safe_force,
                "commanded_depth_mm": float(commanded),
                "command_vs_measured_mm": drift,
                "stopped_on": stop,
                "ladder_rungs_reached": len(usable),
                "image_response": sat,
                "characterised_at": datetime.now().isoformat(),
                # store the path from the repo root, not the folder name --
                # under the sensor-named layout the name alone no longer says
                # which dataset the run belongs to
                "run": str(run.relative_to(ROOT))})
    save_sensor(reg, ent)
    print(f"\n  registry updated: {ent['id']}")
    return 0


def sensor_limits(a) -> tuple:
    """Depth and force ceilings for the sensor being run, from the registry.

    characterize measures each elastomer's own safe envelope and writes it here.
    Until this was wired in, the phases that actually collect the data ignored
    it: force-series would descend to its blanket 1.0 mm default on a 1 mm layer
    whose registry limit is 0.5 mm, and climb to 5 N whatever characterize had
    found the sensor could take. The measurement that exists to set the limit
    has to be the thing that sets it.
    """
    if not a.sensor:
        return (a.max_travel_normal, a.max_force, None, None)
    reg, ent = load_sensor(a.sensor)
    # 'ladder_only' is a WEAKER provenance than 'characterised' and is named
    # so on every run. It exists because collect and characterize want each
    # other first: collect refuses without a measured ceiling, and characterize
    # is the test that damages gels, so it is deliberately last. A DIGIT unit's
    # ceiling here comes from its ball4 shape ladder -- a Hertz fit over 6 rungs
    # that stop at 0.6 mm -- extrapolated to the depth backstop. That is an
    # extrapolation 1.2-3.5x past the fitted depth and the gel stiffens near its
    # backing, so it is a FLOOR on what the unit can take, not a prediction of
    # where it fails. It is sound for the one question this gate asks -- can
    # this unit reach the fixed 2 N range inside its backstop -- and it is not
    # sound for anything else. characterize overwrites it.
    _prov = ent.get("status")
    if _prov not in ("characterised", "ladder_only") or not ent.get("safe_force_N"):
        raise SystemExit(
            f"{a.sensor} has not been characterised. Run --phase characterize "
            "first; without it there is no measured ceiling to hold to.")
    if _prov == "ladder_only":
        print(f"  !! {a.sensor}'s ceiling is 'ladder_only', NOT characterised: "
              f"{ent['safe_force_N']:.2f} N extrapolated from the ball4 ladder "
              f"(fitted to {ent.get('gel_model',{}).get('fitted_depth_max_mm','?')} mm, "
              f"backstop {ent.get('safe_depth_mm',float('nan')):.2f} mm). "
              f"The 2 N range and the depth backstop are what actually bind.")
    # The per-thickness depth limit was removed on 2026-09-04 (operator
    # decision) after a 1 mm soft gel was driven to 5 N -- 3 mm of TCP travel
    # -- four times with no permanent set, no image clipping and a Hertz
    # exponent that never left 1.6-1.7. Depth is no longer what ends a ramp;
    # the force ceiling and the image response are. What remains is a
    # backstop against a probe that never finds the gel at all.
    depth = float(depth_backstop(reg, ent))
    # The ceiling is a fraction of the force at which THIS sensor's image stops
    # responding, because past that the force cannot be read from the picture,
    # which is the only thing a VBTS reads. Measured per sensor: 9.0 N on a soft
    # 1 mm gel, still not reached at 15.9 N on a hard 3 mm one -- a spread of
    # 1.8x that no single number covers. If the ramp stopped for another reason
    # (substrate stiffening, the depth backstop) that stopping force is the base
    # instead, so the rule always has an input.
    # FIXED collection range, not a per-sensor one. Comparing 54 sensors on
    # force-estimation resolution needs them measured over the same span: the
    # same model on the same sensor scored 9-10 % relative error over 0-2 N and
    # 0.8-2.6 % over 14-17 N, so a per-sensor ceiling would have made the MAEs
    # incomparable by construction. What characterize measures -- the saturation
    # force, the substrate limit -- is still recorded per sensor; it just does
    # not set this. The measured ceiling only ever lowers the range, never
    # raises it, so a sensor that cannot safely take 5 N is collected over what
    # it can and the shortfall is on record.
    ir = ent.get("image_response") or {}
    base = (float(ir["max_measurable_force_N"]) if ir.get("reached")
            else float(ent["safe_force_N"]))
    force = min(a.range_normal, a.ceiling_frac * base)
    if force < a.range_normal - 1e-9:
        # A short run is not a cheaper run, it is a useless one. The whole
        # point of a FIXED range is that the units are compared over the same
        # span; a unit collected to 1.7 N cannot be put beside one collected to
        # 2 N, so spending ten minutes and a thousand frames on it buys
        # nothing. Operator's instruction, 2026-09-07: stop and say so.
        #
        # This is a REFUSAL, not a warning, because the previous behaviour was
        # to print exactly this and carry on, and nobody reads a NOTE in the
        # middle of a 10-minute log.
        print(f"\n  REFUSING: this unit's measured ceiling is "
              f"{a.ceiling_frac * base:.2f} N ({a.ceiling_frac:.0%} of the "
              f"{base:.2f} N that characterize reached), below the fixed "
              f"{a.range_normal:.1f} N range.")
        print(f"     Collecting it would give {force:.2f} N of span, which is "
              f"not comparable with the other units and is why the range is "
              f"fixed in the first place.")
        print(f"     What is actually stopping it: characterize stopped on "
              f"'{ent.get('stopped_on','?')}' at {ent.get('safe_depth_mm', float('nan')):.2f} mm, "
              f"against a {depth_backstop(_reg_for(ent), ent):.2f} mm backstop.")
        print(f"     To collect it anyway, pass --allow-short-range.")
        if not getattr(a, "allow_short_range", False):
            raise SystemExit(3)
    if a.max_travel_normal is not None:
        depth = min(depth, a.max_travel_normal)
    force = min(force, a.max_force)
    return (depth, force, reg, ent)


def _reg_for(ent):
    """The registry dict, for a helper that only has the sensor's entry."""
    return yaml.safe_load(open(REGISTRY))


def saturation_base(ent) -> tuple:
    """The force the collection limits are derived from, and where it came from."""
    ir = ent.get("image_response") or {}
    if ir.get("reached"):
        return float(ir["max_measurable_force_N"]), "image saturation"
    return float(ent["safe_force_N"]), f"ramp stop ({ent.get('stopped_on','?')})"


def depth_backstop(reg: dict | None = None, ent: dict | None = None) -> float:
    """Hard depth limit: (thickness + offset) x depth_frac from the gel surface.

    Reinstated 2026-09-04 after 9DTact_medium_2mm_r1 was permanently deformed.
    Its surface dropped 26.234 -> 26.074 -> 25.964 mm across two deep probes --
    0.27 mm that never came back, against a run-to-run repeatability of 0.03 mm
    -- and the gel was visibly damaged afterwards. The probes had reached
    5.5-6.6 mm on a 2 mm layer.

    WHY THE OFFSET (operator, 2026-09-07)
    -------------------------------------
    `thickness_mm` names the TRANSLUCENT gel -- the 3, 2 or 1 mm layer the
    sensors are sorted by. On a 9DTact that layer is not the whole compliant
    stack: a black gel is cast over it, so what the probe presses into is about
    a millimetre thicker than the number the unit is called by. Taking the
    label as the whole stack made the limit tighter than intended by that
    millimetre, and on the 1 mm units that was most of their range: 0.90 mm of
    allowance, about 1 N, against a 3 N collection range.

    This binds in EVERY phase, and it still binds before force does on the
    softer designs -- a soft 2 mm unit reaches roughly 1.9 N at its 2.70 mm
    limit. That is the deliberate trade: the sensors have to survive the
    campaign, and a range that is short is recorded as short rather than
    bought with a damaged gel.
    """
    reg = reg or yaml.safe_load(open(REGISTRY))
    pol = reg.get("capture_policy") or {}
    # The policy above is the 9DTact's. Its +1 mm offset is a fact about that
    # sensor's construction -- a black gel cast over the translucent layer the
    # unit is named by -- and carries no meaning on a principle built
    # differently. The operator confirmed on 2026-09-08 that a DIGIT gel has no
    # such extra layer, so the label IS the whole compliant stack there, and
    # asked for a deliberately tight 0.7 to start with, to be raised once the
    # ladders show where the substrate actually begins.
    #
    # Getting this wrong is not recoverable: 9DTact_medium_2mm_r1 was
    # permanently deformed and left the campaign.
    per = (pol.get("per_principle") or {}).get(principle_of(
        (ent or {}).get("id")) or "", {})
    frac = float(per.get("depth_frac", pol.get("depth_frac", 0.9)))
    off = float(per.get("depth_offset_mm", pol.get("depth_offset_mm", 1.0)))
    if ent is not None and ent.get("thickness_mm"):
        return (float(ent["thickness_mm"]) + off) * frac
    return float(pol.get("depth_backstop_mm", 0.9))


def _gel_model(a):
    """Hertz coefficient and surface height for the sensor being run.

    When a sensor is named, this comes from ITS registry entry, written by
    characterize. Falling back to whatever summary.yaml was written last is how
    a 1 mm elastomer was driven using the surface height of the 3 mm one before
    it -- 2 mm too high, so the probe descended, hit its travel limit, and
    recorded a whole force ladder without ever touching the gel. The
    measurements were of empty air and nothing in the chain objected.
    """
    if a.surface is not None and a.hertz_a is not None:
        return a.surface, a.hertz_a
    # THIS RUN'S OWN zero, when it was measured with the probe now fitted, beats
    # anything stored. The registry's gel_model carries whatever probe wrote it,
    # and a surface is not probe-independent: the same gel on the same mount
    # read 23.636 mm through ball4 and 23.854 mm through ball8 -- 0.218 mm of
    # tip-endpoint difference. Depth is (surface - height), so mixing one
    # probe's surface with another's height subtracts that difference straight
    # out of every depth: the first Pass B collect (DIGIT_Marker_soft_1mm_r2,
    # 2026-09-08) recorded 0.148 mm at 2.6 N where its own ball4 ladder needs
    # 0.45 mm, and the depth backstop was reading half the indentation it was
    # meant to be guarding. zero also fits the Hertz coefficient with that same
    # probe, so both numbers come from one self-consistent measurement taken
    # minutes earlier on this mount.
    try:
        _run = active_run()
        _z = (load_state(_run) or {}).get("zero") or {}
        if (_z.get("probe") and getattr(a, "probe", None) == _z["probe"]
                and _z.get("surface_mm")):
            _fits = [f for f in (_z.get("fits") or []) if f.get("ok") and f.get("a")]
            # The BEST fit, not the first. zero can approach more than once,
            # and on DIGIT_Marker_hard_1mm_r2 (2026-09-09) approach 1 fitted
            # a = 1.25 (r2 0.67, sigma_d0 0.35 mm) while approach 2 fitted
            # a = 13.9 (r2 0.99, sigma 0.006). zero chose its surface from
            # approach 2; this took a from approach 1, sized the 1.2 N hold
            # at 0.97 mm on a 1 mm gel, and collect refused.
            _fits.sort(key=lambda f: float(f.get("sigma_d0_mm", 1e9)))
            _a = float(_fits[0]["a"]) if _fits else None
            if _a:
                print(f"  gel model from THIS run's zero ({_z['probe']}): "
                      f"surface {float(_z['surface_mm']):.3f} mm, a {_a:.3f}")
                return float(_z["surface_mm"]), _a
    except Exception as _e:
        print(f"  (could not read this run's zero: {_e})")
    if getattr(a, "sensor", None):
        _reg, ent = load_sensor(a.sensor)
        gm = ent.get("gel_model") or {}
        if not (gm.get("hertz_a") and gm.get("surface_mm")):
            print(f"  {a.sensor} has no measured gel model. Run --phase "
                  "characterize first; guessing one from another sensor is how "
                  "a run ends up probing thin air.")
            return None, None
        print(f"  gel model from the registry entry for {a.sensor}")
        return (a.surface if a.surface is not None else float(gm["surface_mm"]),
                a.hertz_a if a.hertz_a is not None else float(gm["hertz_a"]))
    for f in sorted(list((ROOT / "data").glob("*/*/summary.yaml"))
                    + list((ROOT / "data").glob("*/*/*/summary.yaml")),
                    reverse=True):
        y = yaml.safe_load(open(f)) or {}
        fit = y.get("force_depth_fit") or {}
        hz = (fit.get("hertz") or {}).get("a_N_per_mm1p5")
        surf = fit.get("gel_surface_height_mm")
        if hz and surf:
            print(f"  gel model from {f.parent.name} (no --sensor given)")
            return (a.surface if a.surface is not None else float(surf),
                    a.hertz_a if a.hertz_a is not None else float(hz))
    print("  no gel model available; run a depth series or pass --surface/--hertz-a")
    return None, None


def phase_summary(a) -> int:
    run = active_run()
    s = load_state(run)
    samples = s["samples"]
    if not samples:
        print("  no samples yet")
        return 2
    st_all = list(samples)
    meta = yaml.safe_load(open(run / "meta.yaml"))
    tr = meta["sensor_to_base_transform"]
    R = np.array(tr["rotation_sensor_to_base"])
    t0 = np.array(tr["origin_base_mm"])
    normal = R[:, 2]              # sensor z axis, in base coordinates

    # Drift interpolation, same idea as the transform measurement.
    def drift_at(when: str) -> np.ndarray:
        checks = s.get("zero_checks") or []
        if not checks:
            return np.zeros(6)
        base = datetime.fromisoformat(s["tare"]["at"])
        pts = [(0.0, np.zeros(6))] + [
            ((datetime.fromisoformat(c["at"]) - base).total_seconds(),
             np.array(c["drift_wrench"])) for c in checks]
        pts.sort(key=lambda kv: kv[0])
        x = (datetime.fromisoformat(when) - base).total_seconds()
        if x <= pts[0][0]:
            return pts[0][1]
        if x >= pts[-1][0]:
            return pts[-1][1]
        for (xa, va), (xb, vb) in zip(pts, pts[1:]):
            if xa <= x <= xb:
                f = 0.0 if xb == xa else (x - xa) / (xb - xa)
                return va + f * (vb - va)
        return pts[-1][1]

    # The force-depth fit describes indentation, so it may only see indentation
    # samples. Shear samples sit at one held depth with a large sideways
    # component, and including them put four points of constant depth into a fit
    # that reads slope from depth -- dragging the coefficient from 0.97 to 0.80.
    normal_phases = {None, "force_series", "series", "sample"}
    samples = [q for q in samples if q.get("phase") in normal_phases]
    if not samples:
        print("  no indentation samples in this run (shear only)")
        return 2
    rows = []
    for q in samples:
        w = np.array(q["wrench"]) - drift_at(q["at"])
        p = np.array(q["tcp_mm"])
        F_s = w[:3]
        T_s = w[3:]
        F_b = R @ F_s
        # Contact point on the gel, in sensor coordinates, straight from torque.
        fz = F_s[2]
        r_xy = (np.array([T_s[1], -T_s[0]]) / -fz * 1000.0
                if abs(fz) > 1e-6 else np.array([np.nan, np.nan]))
        rows.append({"index": q["index"], "at": q["at"], "image": q["image"],
                     "label": q.get("label"),
                     "F_sensor": F_s, "T_sensor": T_s, "F_base": F_b,
                     "Fmag": float(np.linalg.norm(F_s)),
                     "tcp": p, "along_normal": float((p - t0) @ normal),
                     "contact_xy_sensor": r_xy,
                     "tilt_deg": q.get("probe_tilt_deg"),
                     "lateral_fraction": float(np.linalg.norm(F_s[:2])
                                               / max(np.linalg.norm(F_s), 1e-9))})

    # --- contact detection -------------------------------------------------
    # The pre-contact samples are noise, and everything below has to exclude
    # them. A "smallest force" reference picks whichever noise sample happened
    # to sit lowest, and a straight-line fit through flat-then-rising data
    # returns a slope that belongs to neither part.
    Fz = np.array([-r["F_sensor"][2] for r in rows])       # pressing is positive
    z = np.array([r["along_normal"] for r in rows])
    pre = Fz[Fz < 0.1]
    noise = float(pre.std()) if pre.size >= 3 else 0.02
    thresh = max(5.0 * noise, 0.05)
    contact = Fz > thresh
    descent = -(z - z[0])
    for r, dd in zip(rows, descent):
        r["descent_mm"] = float(dd)

    fit = None
    if contact.sum() >= 3:
        d_c, F_c = descent[contact], Fz[contact]
        A = np.vstack([d_c, np.ones(d_c.size)]).T
        (k, c), *_ = np.linalg.lstsq(A, F_c, rcond=None)
        lin_rms = float(np.sqrt(np.mean((A @ [k, c] - F_c) ** 2)))
        d0_lin = float(-c / k) if abs(k) > 1e-9 else float("nan")

        # A sphere on an elastic half space is Hertzian, F = a*delta^1.5, not
        # linear. Fitting the right shape also gives a better contact origin,
        # because a straight line through a curve places its own zero crossing
        # too deep.
        best = None
        for dd in np.arange(d0_lin - 0.3, d0_lin + 0.3, 0.002):
            dep = d_c - dd
            if dep.min() <= 1e-6:
                continue
            aa = float(np.sum(dep ** 1.5 * F_c) / np.sum(dep ** 3))
            rr = float(np.sqrt(np.mean((aa * dep ** 1.5 - F_c) ** 2)))
            if best is None or rr < best[0]:
                best = (rr, float(dd), aa)
        hz_rms, d0_hz, a_hz = best if best else (float("nan"),) * 3
        hertz_better = bool(best and hz_rms < lin_rms)
        d0 = d0_hz if hertz_better else d0_lin
        fit = {"n_contact_samples": int(contact.sum()),
               "noise_sigma_N": noise, "contact_threshold_N": thresh,
               "linear": {"stiffness_N_per_mm": float(k), "rms_N": lin_rms,
                          "contact_origin_descent_mm": d0_lin},
               "hertz": {"a_N_per_mm1p5": a_hz, "rms_N": hz_rms,
                         "contact_origin_descent_mm": d0_hz},
               "model_used": "hertz" if hertz_better else "linear",
               "contact_origin_descent_mm": float(d0),
               "gel_surface_height_mm": float(z[0] - d0)}
        for r in rows:
            r["depth_corrected_mm"] = r["descent_mm"] - d0

    print(f"\n--- contact detection ---")
    print(f"  pre-contact noise sigma {noise:.4f} N, threshold {thresh:.3f} N")
    print(f"  {int(contact.sum())} of {len(rows)} samples are in contact")

    print(f"\n{'#':>3} {'|F| N':>8} {'Fz_s N':>8} {'descent':>8} {'depth':>8} "
          f"{'lat%':>6} {'contact x':>10} {'y':>8}  image")
    for r, c_on in zip(rows, contact):
        # Contact location is torque divided by force. Below the contact
        # threshold that is noise over noise, and it prints as hundreds of
        # millimetres. Blank is the honest answer there.
        loc = (f"{r['contact_xy_sensor'][0]:>10.2f} {r['contact_xy_sensor'][1]:>8.2f}"
               if c_on else f"{'—':>10} {'—':>8}")
        lat = f"{100*r['lateral_fraction']:>5.1f}%" if c_on else f"{'—':>6}"
        dep = (f"{r['depth_corrected_mm']:>8.3f}" if "depth_corrected_mm" in r
               else f"{'—':>8}")
        print(f"{r['index']:>3} {r['Fmag']:>8.3f} {r['F_sensor'][2]:>8.3f} "
              f"{r['descent_mm']:>8.3f} {dep} {lat} {loc}  {r['image']}")

    if fit:
        print(f"\n--- force vs depth, contact samples only ---")
        print(f"  linear : {fit['linear']['stiffness_N_per_mm']:.3f} N/mm, "
              f"rms {fit['linear']['rms_N']:.4f} N")
        print(f"  hertz  : F = {fit['hertz']['a_N_per_mm1p5']:.3f} * depth^1.5, "
              f"rms {fit['hertz']['rms_N']:.4f} N")
        print(f"  using the {fit['model_used']} fit — a sphere on soft gel is "
              "Hertzian, and here it also fits better")
        print(f"  gel surface at {fit['gel_surface_height_mm']:.3f} mm above the "
              "sensor plane")
        if fit["model_used"] == "hertz":
            a_ = fit["hertz"]["a_N_per_mm1p5"]
            print(f"\n  force at depth:  "
                  + "   ".join(f"{d:.1f}mm {a_*d**1.5:.2f}N"
                               for d in (0.1, 0.2, 0.5, 1.0)))
            print(f"  10 N would need {(10/a_)**(1/1.5):.2f} mm of indentation")

    sid = run_sensor_id(run) or ""
    with open(run / "samples.csv", "w", newline="") as fh:
        wcsv = csv.writer(fh)
        wcsv.writerow(["sensor_id", "index", "at", "image", "label",
                       "Fx_s", "Fy_s", "Fz_s", "Tx_s", "Ty_s", "Tz_s",
                       "Fx_base", "Fy_base", "Fz_base", "Fmag",
                       "tcp_x", "tcp_y", "tcp_z", "descent_mm", "depth_corrected_mm",
                       "contact_x_sensor_mm", "contact_y_sensor_mm",
                       "lateral_fraction", "probe_tilt_deg"])
        for r in rows:
            wcsv.writerow([sid, r["index"], r["at"], r["image"], r["label"] or "",
                           *np.round(r["F_sensor"], 5), *np.round(r["T_sensor"], 6),
                           *np.round(r["F_base"], 5), round(r["Fmag"], 5),
                           *np.round(r["tcp"], 4), round(r["descent_mm"], 4),
                           round(r.get("depth_corrected_mm", float("nan")), 4),
                           round(r["contact_xy_sensor"][0], 3),
                           round(r["contact_xy_sensor"][1], 3),
                           round(r["lateral_fraction"], 4),
                           round(r["tilt_deg"], 3) if r["tilt_deg"] is not None else ""])
    (run / "summary.yaml").write_text(yaml.safe_dump(json.loads(json.dumps({
        "run": run.name, "sensor_id": sid, "note": meta.get("note"),
        "n_samples": len(rows), "n_zero_checks": len(s.get("zero_checks") or []),
        "sensor_normal_in_base": normal.tolist(),
        "force_depth_fit": fit,
        "depth_reference": ("contact origin from extrapolating the contact-region "
                            "fit to zero force; pre-contact samples are excluded"),
        "drift_correction": "interpolated between zero checks",
        "robot_commanded": False,
    }, default=str)), sort_keys=False, allow_unicode=True))
    stream = s.get("stream")
    if stream:
        print(f"\n--- continuous capture ---")
        print(f"  {stream['saved']} frames saved of a {stream['budget']} budget "
              f"({stream.get('fps', 0):.1f} fps), {stream['normal_cycles']} normal "
              f"cycles, {stream['shear_cycles']} shear cycles, "
              f"{stream.get('dropped', 0)} frames missing on disk")
        print(f"  labels in stream/frames.csv; raw F/T at "
              f"{stream.get('ft_rate_hz', 0):.0f} Hz in stream/ft.csv; pose in "
              "stream/pose.csv")
    print(f"\n  written: {run}/samples.csv and summary.yaml")
    return 0


# ----------------------------------------------------------------- probes ---

def _write_rows(path: Path, rows: list) -> None:
    if not rows:
        return
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def load_probe(pid: str) -> tuple[dict, dict]:
    cfg = yaml.safe_load(open(ROOT / "config" / "probes.yaml"))
    for p in cfg["probes"]:
        if p["id"] == pid:
            return cfg, p
    ids = ", ".join(p["id"] for p in cfg["probes"])
    raise SystemExit(f"  unknown probe {pid!r}. known: {ids}")


def fit_zero(depth, force, law: str, fmax: float) -> dict:
    """Where the gel surface really is, extrapolated from a fine approach.

    The searched surface is not it. `move_probe --search` stops at the first
    reading over 0.11 N, but that threshold is crossed by a transient during
    the step: re-approaching the SAME height afterwards reads 0.01-0.08 N on
    every run measured so far. So the recorded surface sits somewhere near the
    real one with an error nobody had quantified.

    Measured 2026-09-05, seven repeats on 9DTact_soft_1mm_r2, same day, no
    remount: this fit locates the zero to +-0.014 mm within one approach and
    the zero itself scatters 0.029 mm (1 sigma) between approaches. Detecting
    contact from the IMAGE instead -- first frame whose changed area leaves
    zero -- scattered 0.026 mm over the same seven, so the limit is physical
    repeatability, not the detector. Both are recorded; only this one is used.

    The absolute value is model-dependent and the fit window is therefore
    pinned, not chosen per run. Fitting the same seven approaches over F < 0.2,
    0.3, 0.5, 1.0, 2.0 and 3.0 N moved the mean zero from -0.104 mm to
    +0.060 mm, because these gels run a free exponent of 1.25-1.6 and a fixed
    1.5 makes d0 absorb the mismatch. F < 1.0 N had the lowest scatter of the
    six and is what `zero_policy.fit_max_force_N` holds.
    """
    from scipy.optimize import curve_fit
    d = np.asarray(depth, dtype=float)
    f = np.asarray(force, dtype=float)
    p = 1.5 if law == "hertz" else 1.0
    m = (f < fmax) & (f > -0.05)
    if int(m.sum()) < 5:
        # A stiff gel can cross the whole fit window in three fine steps:
        # DIGIT_medium_1mm_r1 under ball8 (2026-09-09) went 0.835 -> 0.909 ->
        # 1.200 N in 0.02 mm steps and left four points under 1.0 N, and the
        # zero phase failed outright. The window exists to keep the fit in the
        # Hertz regime, not to starve it; the ball4 ladders fit d^1.5 cleanly
        # to 3 N on these gels. Widen it to the smallest force that admits six
        # points, and say so in fit_max_force_N.
        fin = np.sort(f[f > -0.05])
        if len(fin) >= 6:
            fmax = float(fin[5]) + 1e-6
            m = (f < fmax) & (f > -0.05)
        if int(m.sum()) < 5:
            return {"ok": False, "why": f"only {int(m.sum())} points under {fmax:.2f} N"}

    def model(x, aa, d0):
        return aa * np.clip(x - d0, 0.0, None) ** p

    span = max(float(d[m].max() - d[m].min()), 1e-6)
    try:
        po, pc = curve_fit(model, d[m], f[m], maxfev=40000,
                           p0=[max(float(f[m].max()), 1e-3) / span ** p,
                               float(d[m].min()) - 0.05])
    except Exception as e:                       # noqa: BLE001
        return {"ok": False, "why": f"fit failed: {e}"}
    r = f[m] - model(d[m], *po)
    denom = float(((f[m] - f[m].mean()) ** 2).sum())
    r2 = float(1 - (r ** 2).sum() / denom) if denom > 0 else float("nan")
    sig = float(np.sqrt(np.diag(pc))[1])
    # curve_fit "succeeding" is not a fit being any good. On
    # DIGIT_Marker_hard_1mm_r1 (2026-09-09) an approach converged to
    # d0 = -14163 mm, a = 8e-9, sigma_d0 = 4e8 mm, r2 = -3e-6 -- the model
    # pinned to zero force everywhere -- and came back ok: True. The zero
    # phase's own vote survived it, but anything that averaged the ok fits
    # did not (see check_surface_plausible). A fit is ok when it explains
    # the data and locates the surface to better than a millimetre.
    # r2 > 0.8 and sigma_d0 < 0.2 mm: a 0.67 / 0.35 mm fit (approach 1 above)
    # is not a surface, it is a guess, and the zero phase's own vote already
    # discards such approaches.
    # r2 asks how well a Hertz curve F = a*d^n describes the approach, which is
    # the wrong question for a FLAT PUNCH: its force rises almost linearly from
    # first contact, so a punch that seated perfectly still scores badly. On the
    # marker 1 mm gels cyl4 was rejected three times with r2 0.31-0.45 while the
    # three independent approaches agreed on the surface to 0.035 mm and each
    # reported its own uncertainty as 0.07-0.15 mm -- the estimate was fine and
    # the gate was measuring the model, not the measurement. For a punch the
    # gate is therefore sigma_d0, which is the uncertainty in the surface, and
    # r2 only has to show the fit is not noise. Spheres keep the old gate.
    r2_min = 0.2 if str(law).lower().startswith("punch") else 0.8
    ok = bool(np.isfinite(r2) and r2 > r2_min and np.isfinite(sig) and sig < 0.2
              and abs(float(po[1])) < 50.0)
    out = {"ok": ok,
           "d0_mm": float(po[1]),
           "a": float(po[0]),
           "sigma_d0_mm": sig,
           "r2": r2,
           "exponent": p, "law": law, "n": int(m.sum()),
           "fit_max_force_N": float(fmax)}
    if not ok:
        out["why"] = (f"degenerate fit: r2 {r2:.3g} (needs > {r2_min}), "
                      f"sigma_d0 {sig:.3g} mm, d0 {float(po[1]):.3g} mm")
    return out


def _steady_fz(reader, seconds: float) -> tuple:
    """A patient reading of Fz, for the offsets the whole zero rests on.

    `read_fresh` averages 0.1 s, which carries the rig's documented 0.02 N
    scatter. That is fine for a stop condition and much too coarse for the
    per-approach offset: a force error eps shifts a flat-punch fit's zero by
    eps/a, so 0.02 N on a 2.1 N/mm gel is 0.010 mm -- the whole of the
    approach-to-approach scatter seen on 9DTact_medium_1mm_r1. Averaging for a
    second instead cuts it by the root of ten, for two seconds per approach.
    """
    vals, t0 = [], time.time()
    while time.time() - t0 < seconds:
        w, err = reader.read_fresh()
        if err:
            return float("nan"), err
        vals.append(-float(w[2]))
    if not vals:
        w, err = reader.read_fresh()
        return (float("nan"), err) if err else (-float(w[2]), None)
    return float(np.mean(vals)), None


def phase_zero(a) -> int:
    """Locate the gel surface finely enough that a 0.1 mm ladder means something.

    Test 2 presses to 0.1 ... 0.6 mm in 0.1 mm steps and compares the pictures
    across 54 sensors. That comparison is only as good as the depth zero, and
    the searched surface is not good enough on its own: it repeats to about
    0.03 mm between approaches, a third of one ladder step. This phase spends
    a couple of minutes buying that back -- 0.02 mm approach steps instead of
    0.05, and `--zero-repeats` independent approaches averaged, which puts the
    mean at roughly 0.017 mm.

    Nothing here presses deeper than `--zero-stop-force`, well under a newton,
    so it carries no damage risk and can be repeated freely.
    """
    from vbts_platform.ft_stream import ForceReader

    reg, ent = load_sensor(a.sensor)
    pcfg, probe = load_probe(a.probe)
    pol = pcfg["zero_policy"]
    step = a.zero_step if a.zero_step is not None else float(pol["step_mm"])
    reps = a.zero_repeats if a.zero_repeats is not None else int(pol["repeats"])
    fmax = float(pol["fit_max_force_N"])

    run = active_run()
    st_run = load_state(run)
    if not st_run.get("reference"):
        print("  --phase reference first")
        return 2
    surf = a.surface
    if surf is None:
        print("  --surface is required: run move_probe.py --search first")
        return 2

    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2
    ok, why = mv.ready_to_move(mv.read_state(ip))
    if not ok:
        print(f"  not moving: {why}")
        return 2
    okt, whyt = check_indenter_tool(robot_pose(ip))
    if not okt:
        print(f"  {whyt}")
        return 1

    meta = yaml.safe_load(open(run / "meta.yaml"))
    R = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"])
    n = R[:, 2]
    q = chk.ReadOnlyProxy(ip)
    t_sensor, _ = mv.sensor_axis()

    def height():
        return float((np.array(q("GetActualTCPPose", 0)[1:][:3]) - t_sensor) @ n)

    print(f"\n  sensor {ent['id']}  ({ent['principle']}, {ent['hardness']}, "
          f"{ent['thickness_mm']} mm)")
    print(f"  probe  {probe['id']}  ({probe['tip']}, contact law "
          f"{probe['contact_law']})")
    print(f"  {reps} approaches at {step:.3f} mm, fit over F < {fmax} N, "
          f"stop at {a.zero_stop_force} N")

    ref_img = cv2.imread(str(run / "reference.png"))
    _shadow = shadows_the_gel(getattr(a, "sensor", None))
    if ref_img is None:
        print("  no reference.png; --phase reference first")
        return 2
    diff_level = diff_level_for_sensor(ref_img, a, getattr(a, "sensor", None))
    zdir = run / "zero"
    zdir.mkdir(exist_ok=True)

    # Clear of the gel BEFORE the F/T is zeroed, exactly as characterize does
    # it. Entering this phase with --from zero after a previous run had left
    # the tip pressed into the gel put the contact load INTO the tare: every
    # reading afterwards carried a -1.5 N offset, the residual check passed
    # because it is taken at the same pose an instant later, and the whole
    # approach was measured against a zero that was 1.5 N wrong.
    clearance = surf + a.retract - height()
    if clearance > 0:
        print(f"\n  lifting {clearance:.3f} mm clear before zeroing the F/T")
        if _move_along_normal(ip, clearance, a, a.approach_joint_step,
                              vel=a.vel_free):
            return 2

    cam = Camera.from_config(camera_config_for(a.sensor))
    cam.open()                      # before the DAQ task: it must not sit unread
    ft = FTInterface.from_config()
    ft.connect()
    reader = None
    rows, fits = [], []
    try:
        tare = ft.tare(duration_s=2.0)
        res = ft.read_wrench_mean(duration_s=1.0, tared=True)
        print(f"\n  zero residual |F| {np.linalg.norm(res[:3]):.4f} N")
        if np.linalg.norm(res[:3]) > 0.15:
            print("  not clear of the gel.")
            return 1
        reader = ForceReader(ft, tare, duration_s=a.zero_read_s).start()
        if a.zero_read_s > 0.11:
            print(f"  averaging {a.zero_read_s:.2f} s per reading "
                  f"(noise ~{0.02 * (0.1 / a.zero_read_s) ** 0.5:.4f} N)")

        # Two approaches, and a third only if the first two disagree. How
        # repeatable a gel is turns out to be a property of the unit, not of
        # the rig: 9DTact_hard_1mm_r1 scattered 0.0062 mm and held its fitted
        # stiffness to 2 %, while 9DTact_medium_1mm_r1 scattered 0.011-0.013 mm
        # and 5 % on the same day with the same probe and negligible F/T drift.
        # A fixed count either wastes a minute on the good units or under-
        # measures the poor ones, so the run decides from what it just saw.
        rep = 0
        # Bound the ATTEMPTS, not just the accepted approaches. The gates below
        # count only fits that pass the quality bar, so a gel that failed every
        # one would loop forever; +3 leaves room to retry a few bad approaches
        # without ever becoming unbounded.
        while rep < a.zero_max_repeats + 1:
            rep += 1
            # Start clear of the gel every time. Approaching from a height the
            # last approach left it at would carry that approach's residual
            # deformation into this one, and the whole point is that these are
            # independent samples of the same quantity.
            back = surf + a.zero_margin - height()
            if abs(back) > 1e-4:
                if _move_along_normal(ip, back, a, a.approach_joint_step,
                                      vel=a.vel_free):
                    return 2
            time.sleep(a.zero_recover_s)
            base_h = height()
            f0, err0 = _steady_fz(reader, a.zero_offset_s)
            if err0:
                print(f"  F/T failed: {err0}")
                return 1
            # A non-zero reading where nothing is touching is either the F/T
            # zero having drifted since the tare -- measured 2026-09-05: 0.08 N
            # between two approaches a couple of minutes apart, four times the
            # noise floor -- or the probe actually touching, which would mean
            # the standoff is too small. Those need opposite responses, so they
            # are told apart by moving: lift a little further and read again.
            # Drift does not care about height; contact does.
            if _move_along_normal(ip, a.zero_lift_check, a, a.max_joint_step,
                                  vel=a.vel_free):
                return 2
            time.sleep(a.settle)
            f1, err1 = _steady_fz(reader, a.zero_offset_s)
            if err1:
                print(f"  F/T failed: {err1}")
                return 1
            if _move_along_normal(ip, -a.zero_lift_check, a, a.max_joint_step,
                                  vel=a.vel_free):
                return 2
            time.sleep(a.settle)
            base_h = height()
            if abs(f0 - f1) > a.zero_start_tol:
                print(f"\n  {f0:+.3f} N at {base_h:.3f} mm but {f1:+.3f} N "
                      f"{a.zero_lift_check:.2f} mm higher: the probe is "
                      f"TOUCHING at the start of the approach. Raise "
                      f"--zero-margin.")
                return 1
            # It is drift, so re-zero this approach against it rather than
            # carrying one phase-level tare across all three.
            f_off = 0.5 * (f0 + f1)
            t_off0 = time.time()
            print(f"\n  approach {rep}/{reps}  from {base_h:.3f} mm "
                  f"(offset {f_off:+.4f} N removed; {f0:+.4f} / {f1:+.4f} N "
                  f"over {a.zero_lift_check:.2f} mm, so it is drift not contact)")
            print(f"    {'depth':>7} {'force':>8} {'area px':>9}")
            d_h, f_h, t_h = [], [], []
            onset = None
            travelled = 0.0
            # Coarse until the gel answers, fine from there. The standoff has
            # to be large enough to clear the worst tip (0.5 mm), but only the
            # points around contact carry the zero, so crossing the empty part
            # at the fine step would spend 25 moves measuring air.
            fine = False
            # Travel at which the gel first answered. The stop condition below
            # counts from HERE, not from the assumed surface: on
            # 9DTact_soft_3mm_r1 with pair100 (2026-09-07) the assumed surface
            # was 0.92 mm low -- that probe's tip reaches further than the 4 mm
            # ones -- so "0.30 mm below the surface" put a pair of 1 mm posts
            # 1.19 mm into the gel at 0.47 N, four times the depth they are
            # allowed. Counting from real contact makes the limit mean what it
            # says however wrong the starting guess is.
            contact_travel = None
            # Once contact has been noticed the budget is contact-relative:
            # first contact plus --zero-stop-depth, even if that lies past
            # the fixed budget. On 9DTact_soft_3mm_r1 (2026-09-07, ball8,
            # search skipped) the height on record was 0.4 mm too high, the
            # 0.37 mm coarse steps met the gel 1.48 mm below the start, and
            # the absolute cap (margin + stop = 1.3 mm) ended the approach on
            # the very step that found contact -- three times, four points
            # each, no fit. The retry with the search then found the same gel
            # without difficulty. The fixed budget still bounds a probe that
            # never meets anything.
            while travelled < (a.zero_max_travel if contact_travel is None
                               else max(a.zero_max_travel,
                                        contact_travel + a.zero_stop_depth + 0.05)):
                this = step if fine else a.zero_coarse_step
                if _move_along_normal(ip, -this, a, a.max_joint_step):
                    return 2
                travelled += this
                time.sleep(a.settle)
                depth = base_h - height()
                w, err = reader.read_fresh()
                if err:
                    print(f"  F/T failed: {err}")
                    return 1
                f_raw = -float(w[2])
                f = f_raw - f_off
                # grab(), not grab_settled(). grab_settled discards two frames to
                # clear the buffer and the one exposed mid-motion, which costs
                # 1.20 s against 0.41 s (measured 2026-09-07) -- half of this
                # loop's 2.5 s per point, 31 s of a 65 s phase. It buys nothing
                # HERE: the order is move, settle, read force, then grab, so by
                # this line the probe has been stationary for about 1.3 s, more
                # than three frame periods at 2.7 fps, and whatever sits in the
                # one-deep queue was exposed after the move ended.
                frame, _t = cam.grab()
                area = contact_region(frame, ref_img, diff_level,
                               colour=_shadow)["area_px"]
                if onset is None and area > 0:
                    onset = depth
                d_h.append(depth)
                f_h.append(f_raw)
                t_h.append(time.time())
                rows.append({"approach": rep, "depth_mm": depth,
                             "force_N": f, "force_N_raw": f_raw,
                             "area_px": area, "base_height_mm": base_h,
                             "step_mm": this, "fine": fine})
                print(f"    {depth:>7.3f} {f:>8.4f} {area:>9d}"
                      + ("  fine" if fine else "      ")
                      + ("   <- image onset" if onset == depth else ""))
                if f >= a.zero_notice_force and contact_travel is None:
                    contact_travel = travelled
                if not fine and f >= a.zero_notice_force:
                    fine = True
                    print(f"    ({f:.3f} N noticed — {step:.3f} mm steps from here)")
                    # A coarse step can cross the whole fit range in one go.
                    # 9DTact_hard_3mm_r1 with cube4 (2026-09-06) went
                    # -0.00 N -> +1.29 N on a single 0.40 mm step: the gel is
                    # ~6.8 N/mm under a flat 4 mm face, so 1.0 N lives inside
                    # 0.15 mm and NO fixed coarse step can resolve it -- 0.20 mm
                    # overshoots it too. Every approach ended with two points
                    # under the fit ceiling and the run died with "no usable
                    # fit". Switching to fine steps from here is too late; the
                    # points that carry the zero are already behind us. So back
                    # out by the step just taken and come down again finely.
                    if f >= fmax and travelled > this:
                        if _move_along_normal(ip, +this, a,
                                              a.approach_joint_step,
                                              vel=a.vel_contact):
                            return 2
                        travelled -= this
                        contact_travel = None      # backed out of contact
                        time.sleep(a.settle)
                        w, err = reader.read_fresh()
                        if err:
                            print(f"  F/T failed: {err}")
                            return 1
                        f = -float(w[2]) - f_off
                        d_h.pop(); f_h.pop(); t_h.pop(); rows.pop()
                        print(f"    stepped back {this:.3f} mm to {f:.3f} N — "
                              f"the fit range was crossed in one step")
                        continue
                # Depth, not force, is what ends the approach. A stop force
                # picked from ball data (1.2 N) put the flat cyl4 tip 0.73 mm
                # into the gel -- DEEPER than the 0.6 mm ladder this phase
                # exists to support -- and doing that three times made the
                # fitted zero walk 0.039 mm per approach in one direction
                # (measured 2026-09-05: 0.1366, 0.1772, 0.2147 mm, against a
                # +-0.003 mm fit error). Averaging those does not sharpen the
                # zero, it averages a drift. A depth cap bounds the disturbance
                # identically for a stiff flat punch and a soft sphere; the
                # force cap stays as a safety limit only.
                # depth is measured from base_h, which sits --zero-margin
                # above the searched contact, so the cap has to include that
                # standoff or the approach stops before it ever touches.
                if ((contact_travel is not None
                     and travelled - contact_travel >= a.zero_stop_depth)
                        or (contact_travel is None
                            and depth >= a.zero_margin + a.zero_stop_depth + 1.0)
                        or f >= a.zero_stop_force):
                    break
            else:
                print(f"    travel limit {a.zero_max_travel} mm with no contact")
                return 1
            # The offset was measured ONCE, before the approach. When the
            # zero is moving fast that is not enough: on
            # 9DTact_medium_1mm_r1 it swung 0.078 N in a minute, and the
            # approach it happened during fitted a stiffness 9 % lower with
            # R2 0.9923 against 0.9987 -- a linear fit absorbing a time ramp
            # into its slope and intercept. So it is measured again at the
            # end, clear of the gel, and taken out as a straight line in
            # time. This is what `collect` already does for the stream, with
            # its off-gel zero checks.
            if _move_along_normal(ip, base_h + a.zero_lift_check - height(),
                                  a, a.approach_joint_step, vel=a.vel_free):
                return 2
            time.sleep(a.settle)
            f_off_end, err2 = _steady_fz(reader, a.zero_offset_s)
            if err2:
                print(f"  F/T failed: {err2}")
                return 1
            t_off1 = time.time()
            span = max(t_off1 - t_off0, 1e-6)
            ramp = (f_off_end - f_off) / span
            f_corr = [fr - (f_off + ramp * (tt - t_off0))
                      for fr, tt in zip(f_h, t_h)]
            if abs(f_off_end - f_off) > a.zero_start_tol:
                print(f"    zero moved {f_off_end - f_off:+.4f} N during the "
                      f"approach ({ramp * 60:+.3f} N/min); the ramp is removed")
            # the saved rows carry the ramp-corrected force; the raw reading
            # stays alongside it so the correction can always be undone
            for rr, fc in zip([r for r in rows if r["approach"] == rep], f_corr):
                rr["force_N"] = float(fc)
            fit = fit_zero(d_h, f_corr, probe["contact_law"], fmax)
            fit["zero_drift_N"] = float(f_off_end - f_off)
            fit["zero_drift_N_per_min"] = float(ramp * 60)
            fit.update({"approach": rep, "base_height_mm": base_h,
                        "image_onset_depth_mm": onset})
            fits.append(fit)
            if fit["ok"]:
                print(f"    fit d0 {fit['d0_mm']:+.4f} +-{fit['sigma_d0_mm']:.4f} mm"
                      f"   a {fit['a']:.3f}   R2 {fit['r2']:.4f}"
                      + (f"   image onset {onset:.3f} mm" if onset else ""))
            else:
                print(f"    fit failed: {fit['why']}")
            # Judge the gates on fits that are actually measurements. A fit
            # that fails the quality bar is not evidence of scatter, so it must
            # neither inflate the sem (which would buy an approach to cure a
            # problem more approaches cannot cure) nor count toward `reps`
            # (a rejected approach should be retried, not tallied).
            done = [f for f in fits if f["ok"]
                    and f["r2"] >= a.zero_min_r2
                    and f["sigma_d0_mm"] <= a.zero_max_sigma]
            if len(done) >= reps:
                if len(done) < 2:
                    # Nothing to compare, so the fit's own sigma has to stand in
                    # for the scatter -- and it must actually be CHECKED. When
                    # repeats fell to 1 this branch broke out unexamined and a
                    # +-0.0448 mm zero on 9DTact_hard_3mm_r1/ball4 passed
                    # silently, 45% of the ladder's first 0.1 mm rung. A sphere
                    # cannot pin the zero as well as a flat punch (measured
                    # medians 0.0258 vs 0.0089 mm over 66 fits) because F ~ d^1.5
                    # flattens at contact, so the one probe that needs the check
                    # is the one that was running without it.
                    if (done[0]["sigma_d0_mm"] > a.zero_sigma_gate
                            and len(done) < a.zero_max_repeats):
                        print(f"  single fit +-{done[0]['sigma_d0_mm']:.4f} mm, over the "
                              f"{a.zero_sigma_gate:.4f} mm gate -- adding an approach")
                        continue
                    break
                sp = np.array([f["base_height_mm"] - f["d0_mm"] for f in done])
                # Gate on the standard error of the MEAN, which is the number
                # the ladder is measured from, not on the spread. The spread is
                # a property of the gel and does not shrink with more
                # approaches: 9DTact_soft_2mm_r1 held 0.009-0.017 mm however
                # many were taken, so a spread gate just ran to the cap for
                # nothing. sigma/sqrt(n) is what extra approaches actually buy.
                sem = float(sp.std(ddof=1) / np.sqrt(len(sp)))
                if sem <= a.zero_sem_gate or len(done) >= a.zero_max_repeats:
                    if sem > a.zero_sem_gate:
                        print(f"  mean still +-{sem:.4f} mm after "
                              f"{len(done)} approaches, over the "
                              f"{a.zero_sem_gate:.4f} mm gate; taking it")
                    break
                print(f"  mean +-{sem:.4f} mm, over the "
                      f"{a.zero_sem_gate:.4f} mm gate — adding an approach")

        good = [f for f in fits if f["ok"]]
        # "ok" only means the fit converged, and a converged fit can still be
        # worthless. On 9DTact_soft_3mm_r1/ball4 (2026-09-06) four approaches
        # gave d0 1.064, 1.010, 0.132, 1.265 mm: the third had R2 0.65 and its
        # own sigma 0.212 mm, an order of magnitude past the others, and it was
        # averaged in like the rest -- dragging the surface 0.25 mm and taking
        # the whole shape ladder with it. Averaging cannot defend itself against
        # a member that is not a measurement, so reject on each fit's OWN stated
        # quality before combining, never on how far it sits from its peers
        # (that would reject the honest outlier on a gel that really does
        # scatter). Only if every fit fails does the run fall back to all of
        # them, so a systematically hard gel still yields a surface.
        clean = [f for f in good
                 if f["r2"] >= a.zero_min_r2 and f["sigma_d0_mm"] <= a.zero_max_sigma]
        if good and len(clean) < len(good):
            for f in good:
                if f not in clean:
                    print(f"  rejecting approach {f['approach']}: R2 {f['r2']:.4f}"
                          f", sigma {f['sigma_d0_mm']:.4f} mm"
                          f"  (need R2 >= {a.zero_min_r2:.2f} and sigma <= "
                          f"{a.zero_max_sigma:.3f} mm)")
            if clean:
                good = clean
            else:
                print("  every approach failed the quality gate; using them all")
        if not good:
            print("\n  no usable fit.")
            return 1
        # The surface each approach found, in the robot's own height units, is
        # base_h - d0: heights are what the next phase commands, and each
        # approach has its own base_h because the retract does not land in
        # exactly the same place twice.
        surfaces = np.array([f["base_height_mm"] - f["d0_mm"] for f in good])
        onsets = np.array([f["base_height_mm"] - f["image_onset_depth_mm"]
                           for f in good if f["image_onset_depth_mm"] is not None])
        s_mean = float(surfaces.mean())
        s_std = float(surfaces.std(ddof=1)) if len(surfaces) > 1 else float("nan")
        # float(), not the numpy scalar np.sqrt returns: yaml.safe_dump has no
        # representer for numpy types and raised RepresenterError here, which
        # failed the phase AFTER all three approaches had been measured.
        s_sem = float(s_std / np.sqrt(len(surfaces))) if len(surfaces) > 1 else float("nan")
        # A monotone walk and random scatter have the same standard deviation
        # and mean completely different things: the first says the gel is still
        # moving and the mean of three is the mean of a drift, the second says
        # averaging helps. Both numbers are printed so they cannot be confused.
        drift = float(surfaces[-1] - surfaces[0]) if len(surfaces) > 1 else 0.0
        per_approach = drift / (len(surfaces) - 1) if len(surfaces) > 1 else 0.0
        monotone = bool(len(surfaces) > 2 and (
            np.all(np.diff(surfaces) > 0) or np.all(np.diff(surfaces) < 0)))
        print(f"\n  {'surface (force fit)':<26}{s_mean:.4f} mm")
        if len(surfaces) > 1:
            print(f"  {'scatter over approaches':<26}{s_std:.4f} mm (1 sigma), "
                  f"mean +-{s_sem:.4f}")
            print(f"  {'first -> last':<26}{drift:+.4f} mm "
                  f"({per_approach:+.4f} per approach)"
                  + ("   MONOTONE — this is drift, not scatter, and the mean "
                     "of three is the mean of a moving quantity"
                     if monotone and abs(drift) > 3 * s_sem else ""))
            print(f"  {'first approach only':<26}{float(surfaces[0]):.4f} mm"
                  "   (the only one on an undisturbed gel)")
        if len(onsets):
            print(f"  {'surface (image onset)':<26}{onsets.mean():.4f} mm"
                  f"   disagreement {onsets.mean() - s_mean:+.4f} mm")
        print(f"  {'searched surface was':<26}{surf:.4f} mm"
              f"   correction {s_mean - surf:+.4f} mm")

        _write_rows(zdir / "approaches.csv", rows)
        zero = {"probe": probe["id"], "contact_law": probe["contact_law"],
                "searched_surface_mm": float(surf),
                "surface_mm": s_mean,
                "sigma_mm": s_std, "sem_mm": s_sem,
                "first_surface_mm": float(surfaces[0]),
                "drift_first_to_last_mm": drift,
                "drift_per_approach_mm": per_approach,
                "monotone": monotone,
                "n_approaches": int(len(surfaces)),
                "image_onset_surface_mm": (float(onsets.mean()) if len(onsets)
                                           else None),
                "step_mm": step, "fit_max_force_N": fmax,
                "stop_force_N": a.zero_stop_force,
                "fits": fits, "at": datetime.now().isoformat()}
        st_run["zero"] = zero
        save_state(run, st_run)
        with open(zdir / "zero.yaml", "w") as fh:
            yaml.safe_dump(zero, fh, sort_keys=False)
        # Clear of the gel before anything else runs.
        back = surf + a.retract - height()
        if back > 0:
            _move_along_normal(ip, back, a, a.approach_joint_step, vel=a.vel_free)
        return 0
    finally:
        if reader is not None:
            reader.stop()
        ft.disconnect()
        cam.close()


# Fraction of a gel's safe force at which the depth ladder stops descending.
# 0.7 leaves room for the next rung to be much stiffer than the last, which is
# what a thin gel on a rigid backing does (4.6 N at 0.58 mm where 0.47 mm gave
# 2.3 N).
SHAPE_FORCE_FRAC = 0.7


def phase_shape(a) -> int:
    """The depth ladder: press to fixed indentations and photograph each one.

    Serves test 2 (shape reconstruction, one frame per shape per depth) and
    test 3 (spatial resolution, the same ladder with the paired-cylinder tips),
    because resolvability is a function of depth -- a pair that merges at
    0.5 mm may separate at 0.1 -- and running one ladder answers both.

    Depth is measured back from the robot, never counted from the commands,
    and it is measured from the fitted surface in `state["zero"]`, not from the
    searched one. Each rung is approached from clear air rather than by walking
    down the ladder, so rung k does not carry k-1 rungs of accumulated creep.
    """
    from vbts_platform.ft_stream import ForceReader

    reg, ent = load_sensor(a.sensor)
    pcfg, probe = load_probe(a.probe)
    run = active_run()
    st_run = load_state(run)
    zero = st_run.get("zero")
    if not zero:
        print("  --phase zero first: the ladder is measured from its surface")
        return 2
    if zero["probe"] != probe["id"]:
        print(f"  the zero on file was found with probe {zero['probe']!r}, "
              f"not {probe['id']!r}. Re-run --phase zero.")
        return 2
    depths = [float(x) for x in a.depths.split(",")]
    cap = depth_backstop(reg, ent)
    if max(depths) > cap:
        print(f"  deepest rung {max(depths)} mm exceeds the {cap:.2f} mm "
              f"backstop for a {ent['thickness_mm']} mm gel")
        return 2
    # The depth backstop is the only limit this phase had, and depth is not what
    # breaks a gel -- force is. A flat punch has eight times the paired
    # cylinders' area, so on 2026-09-10 the cyl4 ladder on DIGIT_hard_1mm_r2
    # reached 4.60 N at 0.578 mm against that unit's 4.95 N ceiling, on the rung
    # before last, with nothing in the code watching. Stop descending once a
    # rung passes this fraction of the registry's safe force; the rung that
    # triggers it is kept (it is already measured and was under the ceiling).
    f_stop = SHAPE_FORCE_FRAC * float(sensor_limits(a)[1])

    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2
    ok, why = mv.ready_to_move(mv.read_state(ip))
    if not ok:
        print(f"  not moving: {why}")
        return 2
    okt, whyt = check_indenter_tool(robot_pose(ip))
    if not okt:
        print(f"  {whyt}")
        return 1

    meta = yaml.safe_load(open(run / "meta.yaml"))
    R = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"])
    n = R[:, 2]
    q = chk.ReadOnlyProxy(ip)
    t_sensor, _ = mv.sensor_axis()

    def height():
        return float((np.array(q("GetActualTCPPose", 0)[1:][:3]) - t_sensor) @ n)

    surf = float(zero["surface_mm"])
    ref_img = cv2.imread(str(run / "reference.png"))
    _shadow = shadows_the_gel(getattr(a, "sensor", None))
    if ref_img is None:
        print("  no reference.png; --phase reference first")
        return 2
    diff_level = diff_level_for_sensor(ref_img, a, getattr(a, "sensor", None))
    out = run / f"shape_{probe['id']}"
    out.mkdir(exist_ok=True)

    print(f"\n  sensor {ent['id']}  probe {probe['id']} ({probe['tip']})")
    print(f"  surface {surf:.4f} mm (fitted, +-{zero.get('sem_mm', float('nan')):.4f})")
    print(f"  rungs {depths} mm x {a.shape_repeats}, backstop {cap:.2f} mm")

    clearance = surf + a.retract - height()
    if clearance > 0:
        print(f"\n  lifting {clearance:.3f} mm clear before zeroing the F/T")
        if _move_along_normal(ip, clearance, a, a.approach_joint_step,
                              vel=a.vel_free):
            return 2

    cam = Camera.from_config(camera_config_for(a.sensor))
    cam.open()                      # before the DAQ task: it must not sit unread
    ft = FTInterface.from_config()
    ft.connect()
    reader = None
    rows = []
    try:
        tare = ft.tare(duration_s=2.0)
        res = ft.read_wrench_mean(duration_s=1.0, tared=True)
        print(f"\n  zero residual |F| {np.linalg.norm(res[:3]):.4f} N")
        if np.linalg.norm(res[:3]) > 0.15:
            print("  not clear of the gel.")
            return 1
        reader = ForceReader(ft, tare).start()

        print(f"\n  {'rep':>4} {'target':>8} {'reached':>8} {'force':>8} "
              f"{'area px':>9} {'radius px':>10}")
        for rep in range(1, a.shape_repeats + 1):
            for dtgt in depths:
                back = surf + a.zero_margin - height()
                if abs(back) > 1e-4:
                    if _move_along_normal(ip, back, a, a.approach_joint_step,
                                          vel=a.vel_free):
                        return 2
                time.sleep(a.zero_recover_s)
                down = height() - (surf - dtgt)
                if _move_along_normal(ip, -down, a, a.max_joint_step):
                    return 2
                time.sleep(a.shape_dwell)
                reached = surf - height()
                w, err = reader.read_fresh()
                if err:
                    print(f"  F/T failed: {err}")
                    return 1
                f = -float(w[2])
                t_moved = time.time()
                frame, t_img = cam.grab_after(t_moved)
                rg = contact_region(frame, ref_img, diff_level,
                               colour=_shadow)
                name = f"{probe['id']}_d{dtgt:.2f}_r{rep}.png"
                cv2.imwrite(str(out / name), frame,
                            [cv2.IMWRITE_PNG_COMPRESSION, 1])
                pose = q("GetActualTCPPose", 0)[1:]
                rows.append({"probe": probe["id"], "repeat": rep,
                             "target_depth_mm": dtgt, "depth_mm": reached,
                             "force_N": f, "file": name, "t_img": t_img,
                             "Fx": float(w[0]), "Fy": float(w[1]),
                             "Fz": float(w[2]), "Tx": float(w[3]),
                             "Ty": float(w[4]), "Tz": float(w[5]),
                             "tcp_x": pose[0], "tcp_y": pose[1], "tcp_z": pose[2],
                             "area_px": rg["area_px"], "radius_px": rg["radius_px"],
                             "enclosing_radius_px": rg["enclosing_radius_px"],
                             "centroid_px": str(rg["centroid_px"]),
                             "mean_abs_diff_in_region": rg["mean_abs_diff_in_region"],
                             "dark_area_px": rg["dark_area_px"],
                             "bright_area_px": rg["bright_area_px"],
                             "diff_level": diff_level})
                print(f"  {rep:>4} {dtgt:>8.2f} {reached:>8.3f} {f:>8.3f} "
                      f"{rg['area_px']:>9d} {rg['radius_px']:>10.1f}")
                if f >= f_stop:
                    print(f"  stopping the ladder here: {f:.3f} N is past "
                          f"{SHAPE_FORCE_FRAC:.0%} of the {f_stop/SHAPE_FORCE_FRAC:.2f} N "
                          f"ceiling this phase runs under (the fixed collection "
                          f"range, or the gel's own limit where that is lower). "
                          f"Deeper rungs skipped.")
                    break

        _write_rows(out / "ladder.csv", rows)
        st_run.setdefault("shape", {})[probe["id"]] = {
            "n_frames": len(rows), "depths_mm": depths,
            "repeats": a.shape_repeats, "surface_mm": surf,
            "dir": out.name, "at": datetime.now().isoformat()}
        save_state(run, st_run)
        print(f"\n  {len(rows)} frames -> {out}")
        back = surf + a.retract - height()
        if back > 0:
            _move_along_normal(ip, back, a, a.approach_joint_step, vel=a.vel_free)
        return 0
    finally:
        if reader is not None:
            reader.stop()
        ft.disconnect()
        cam.close()


def _move_to_point(ip: str, p, rpy, a, ceiling: float | None = None,
                   vel: float | None = None) -> int:
    """One commanded move to an ABSOLUTE point, orientation held.

    Every target here is built from a fixed origin rather than from the pose
    the last move achieved. Chaining moves off the achieved pose accumulated
    MoveL's few-micron Cartesian bias into 6.1 mm of lateral drift and 2.04
    degrees of tilt over a long run once already.
    """
    target = [float(p[0]), float(p[1]), float(p[2])] + [float(v) for v in rpy]
    pl = mv.plan(ip, target, ceiling if ceiling is not None else a.max_joint_step)
    if not pl.get("ok"):
        print(f"  refusing the move: {pl.get('why')}")
        return 2
    tool = pl["active_tool"][1] if isinstance(pl["active_tool"], list) else 1
    rv = mv.send_movel(ip, pl["target_joints"], pl["target_pose"], tool,
                       vel if vel is not None else a.vel, a.ovl)
    if rv != 0:
        print(f"  MoveL returned {rv}")
        return 1
    return 0


def diff_centroid(frame_bgr, ref_bgr, floor: int, blur: int = 9):
    """Intensity-weighted centroid of the change, with no threshold contour.

    A thresholded region's centroid is the wrong tool here. On a 9DTact gel a
    flat 4 mm tip leaves no edge at all -- the deformation is a smooth dip that
    spreads well past the tip (measured 2026-09-05: 0.94x the tip radius at
    0.3 mm depth, 1.50x at 0.6 mm), so the outline is a contour of the
    threshold, not of anything physical, and it moves as the threshold or the
    illumination changes. The first moment of |frame - reference| needs no
    outline: it is where the change is, weighted by how much changed. The floor
    keeps sensor noise across 2 megapixels from dragging it toward frame
    centre.
    """
    g = cv2.GaussianBlur(cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY),
                         (blur, blur), 0).astype(np.float32)
    r = cv2.GaussianBlur(cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY),
                         (blur, blur), 0).astype(np.float32)
    d = np.abs(g - r) - float(floor)
    np.clip(d, 0.0, None, out=d)
    tot = float(d.sum())
    if tot <= 0.0:
        return None
    yy, xx = np.mgrid[0:d.shape[0], 0:d.shape[1]]
    return (float((d * xx).sum() / tot), float((d * yy).sum() / tot), tot)


def matrix_to_rpy(M) -> list:
    """Rotation matrix -> FAIRINO pose angles, inverse of cal.rpy_to_matrix.

    Same extrinsic XYZ convention: R = Rz @ Ry @ Rx.
    """
    ry = np.arcsin(-np.clip(M[2, 0], -1.0, 1.0))
    rz = np.arctan2(M[1, 0], M[0, 0])
    rx = np.arctan2(M[2, 1], M[2, 2])
    return [float(np.degrees(v)) for v in (rx, ry, rz)]


def rot_about(axis, deg: float):
    """Rodrigues rotation about a unit axis."""
    a = np.asarray(axis, dtype=float)
    a = a / np.linalg.norm(a)
    t = np.radians(deg)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * (K @ K)


def _window_for(shape, cx, cy, half: int, srch: int, min_half: int = 60):
    """Template and search half-sizes for a contact at (cx, cy).

    The contact is not in the middle of the picture. It sits where the sensor's
    optics put it, and on 9DTact_medium_1mm_r2 the imprint sits at y = 370 in a
    1080-tall frame, where a 460 px margin does not fit on both sides.

    Only the TEMPLATE has to lie inside the frame -- it is the picture of the
    imprint, and cutting it discards the very thing being tracked. The SEARCH
    region does not: `_ncc_shift` pads it with zeros, which is what a
    difference image is outside the sensor anyway, so the search margin costs
    nothing at the edges and is never traded away.

    That order was backwards until 2026-09-08. On 9DTact_soft_1mm_r1 the
    contact sits at y = 674, the template was cut from 260 to 204 to protect a
    search margin that did not need protecting, and the x row's residual went
    from 4.46 px to 8.84 px. Returns (0, 0) if even `min_half` of template will
    not fit, and the caller reports that rather than a NaN.
    """
    h, w = shape[:2]
    room = min(cx, w - cx, cy, h - cy) - 2
    if room < min_half:
        return 0, 0
    return int(min(half, room)), int(srch)


def _ncc_shift(img, tmpl, cx, cy, half: int, srch: int):
    """Where `img` sits relative to `tmpl`, in pixels, to a fraction of one.

    Normalised cross-correlation with a parabolic peak fit. NOT phase
    correlation: that whitens the spectrum, and the only high-frequency content
    here is stationary sensor noise, which correlates at zero shift and buries
    the smooth low-frequency blob that actually moved. Measured 2026-09-05,
    every phase-correlation slope came back under 0.05 px/mm on displacements
    of 250 px.
    """
    T = tmpl[cy - half:cy + half, cx - half:cx + half]
    # The search region may hang off the frame; pad it with zeros rather than
    # letting a negative slice index silently wrap and put the origin in the
    # wrong place. A difference image is zero outside the sensor, so the padding
    # is the honest continuation and only ever meets the template at shifts far
    # larger than the sweep being measured.
    y0, x0 = cy - half - srch, cx - half - srch
    side = 2 * (half + srch)
    h, w = img.shape[:2]
    top, left = max(0, -y0), max(0, -x0)
    bot, right = max(0, y0 + side - h), max(0, x0 + side - w)
    if top or left or bot or right:
        img = cv2.copyMakeBorder(img, top, bot, left, right,
                                 cv2.BORDER_CONSTANT, value=0)
        y0, x0 = y0 + top, x0 + left
    S = img[y0:y0 + side, x0:x0 + side]
    if T.size == 0 or S.shape[0] <= T.shape[0] or S.shape[1] <= T.shape[1]:
        return float("nan"), float("nan"), 0.0
    r = cv2.matchTemplate(S, T, cv2.TM_CCOEFF_NORMED)
    _, peak, _, ml = cv2.minMaxLoc(r)
    px, py = ml

    def sub(v0, vm, vp):
        den = vm - 2 * v0 + vp
        return 0.0 if abs(den) < 1e-9 else 0.5 * (vm - vp) / den

    ddx = sub(r[py, px], r[py, px - 1], r[py, px + 1]) if 0 < px < r.shape[1] - 1 else 0.0
    ddy = sub(r[py, px], r[py - 1, px], r[py + 1, px]) if 0 < py < r.shape[0] - 1 else 0.0
    return float(px + ddx - srch), float(py + ddy - srch), float(peak)


def _scale_jacobian(result, theta_tol: float, max_rms: float):
    """J = scale x rotation from the four fitted rows, with both self-checks.

    Split out of `phase_scale` on 2026-09-08 so that a run's frames can be
    re-fitted offline by `scripts/refit_scale.py` through exactly this code
    rather than a second copy of it.
    """
    jx = np.array([result.get("px_per_mm_xx", np.nan),
                   result.get("px_per_mm_xy", np.nan)])
    jy = np.array([result.get("px_per_mm_yx", np.nan),
                   result.get("px_per_mm_yy", np.nan)])
    if np.all(np.isfinite(np.r_[jx, jy])):
        J = np.array([[jx[0], jy[0]], [jx[1], jy[1]]])
        # J = S @ Rot(theta): anisotropic pixel scale times a rotation
        th1 = np.degrees(np.arctan2(-J[0, 1], J[0, 0]))
        th2 = np.degrees(np.arctan2(J[1, 0], J[1, 1]))
        kx = float(np.hypot(J[0, 0], J[0, 1]))
        ky = float(np.hypot(J[1, 0], J[1, 1]))
        result.update({"theta_from_row1_deg": float(th1),
                       "theta_from_row2_deg": float(th2),
                       "px_per_mm_image_x": kx, "px_per_mm_image_y": ky})
        print(f"\n  fitting J = scale x rotation:")
        print(f"    rotation from row 1 {th1:7.2f} deg, from row 2 {th2:7.2f} deg"
              f"   (agreement is the test of the model)")
        print(f"    image x {kx:8.2f} px/mm = {1000/kx:6.3f} um/px"
              f"  -> FOV width  {1920/kx:6.2f} mm")
        print(f"    image y {ky:8.2f} px/mm = {1000/ky:6.3f} um/px"
              f"  -> FOV height {1080/ky:6.2f} mm")
        print(f"    anisotropy kx/ky = {kx/ky:.3f}  "
              f"(1.000 = square pixels, design implies 1.199)")
        # The two rows give theta independently. If the model J = scale x
        # rotation holds they must agree, so their disagreement is a
        # self-check that costs nothing and needs no reference. Measured
        # 2026-09-05: 0.8 deg on a run whose four residuals were 0.6-1.6 px,
        # 8.4 deg on one whose y row was 3.6 px. The anisotropy rests
        # entirely on the second row, so a bad row makes kx/ky meaningless
        # while leaving kx itself (which came out 10.41 and 10.46 um/px on
        # two different sensors) perfectly good.
        dth = abs(th1 - th2)
        result["theta_disagreement_deg"] = float(dth)
        # The row agreement tests the MODEL; the residuals test the FIT,
        # and a run can pass the first with 30 px of the second. Measured
        # 2026-09-08 over every scale run on file: entries that passed the
        # angle gate alone spanned 0.8-30.1 px of residual and implied a
        # 19.2-31.0 mm field of view for one sensor design. Both gates now.
        rms_worst = max(result.get("rms_px_xx", 0.0), result.get("rms_px_yy", 0.0))
        result["rms_px_worst"] = float(rms_worst)
        result["scale_trusted"] = bool(dth <= theta_tol
                                       and rms_worst <= max_rms)
        if dth <= theta_tol and rms_worst > max_rms:
            print(f"\n  ** the rows agree ({dth:.1f} deg) but the fit does not: "
                  f"worst residual {rms_worst:.1f} px, over the "
                  f"{max_rms:.1f} px gate. NOT trusted.")
        if dth > theta_tol:
            print(f"\n  ** the two rows disagree by {dth:.1f} deg, over the "
                  f"{theta_tol:.1f} deg gate. The rotation and the "
                  f"anisotropy from this run are NOT trustworthy; image x "
                  f"({1000/kx:.3f} um/px) rests on the better row and "
                  f"still is. Worst residual "
                  f"{max(result.get(f'rms_px_{t}', 0) for t in ('xx','xy','yx','yy')):.2f} px.")
    return result


SCALE_COLLAPSE_PX = 0.5


def _track_series(imgs, cx, cy, half: int, srch: int, log=None):
    """Where each frame of a sweep sits, in pixels, relative to the middle one.

    Every frame is correlated against the middle frame, as before. What is new
    is that a correlation is allowed to FAIL, and is repaired instead of being
    fitted.

    The failure is specific and was diagnosed on 9DTact_medium_1mm_r2 on
    2026-09-08 by measuring all ten pairs of a five-frame sweep instead of only
    the five that share the middle frame. Seventeen of the twenty pair
    displacements agreed with a straight line to 1-3 px. The other three came
    back as EXACTLY zero -- (+0.03, +0.01) for a pair whose frames are 28 px
    apart. They are not noisy measurements; the correlation peak of the imprint
    has been swallowed by the zero-shift peak of the stationary background
    (fixed pattern noise, dust, the illumination texture), which is what
    matchTemplate finds when the imprint's own contrast is weak. All three
    failures were at the smallest separation in the sweep, 0.5 mm, where the
    true peak sits closest to the origin. That is why a different row collapsed
    on every re-run of this unit, and why pressing harder, re-aligning, and
    changing the sweep width all failed to help: none of them touches the
    background, and the unit was never far from the edge.

    A commanded move of half a millimetre cannot produce half a pixel when its
    neighbours produce forty, so a shift under `SCALE_COLLAPSE_PX` is treated as
    no measurement at all. The point is then re-measured against a frame that
    did track -- the pair with the strongest correlation -- and its position is
    that frame's position plus the pair displacement. Chaining is exact here:
    these are rigid translations of the same imprint, so positions add.

    Measured over every scale run on file: eleven runs that already passed both
    gates are unchanged to the last digit, because nothing collapses in them.
    Of the runs that failed, medium_1mm_r2 went from 13.85 px residual and
    6.7 deg of row disagreement to 2.44 px and 2.2 deg, and medium_3mm_r1 from
    18.66 px to 3.26 px, from the frames already on disk.
    """
    n = len(imgs)
    mid = n // 2
    s = [_ncc_shift(imgs[i], imgs[mid], cx, cy, half, srch) for i in range(n)]
    p = np.array([[z[0], z[1]] for z in s], dtype=float)

    def dead(v):
        return (not np.isfinite(v[0])) or (abs(v[0]) < SCALE_COLLAPSE_PX
                                           and abs(v[1]) < SCALE_COLLAPSE_PX)

    bad = [i for i in range(n) if i != mid and dead(p[i])]
    for i in bad:
        best = None
        for k in range(n):
            if k == i or k in bad:
                continue
            dx, dy, q = _ncc_shift(imgs[i], imgs[k], cx, cy, half, srch)
            if dead((dx, dy)):
                continue
            if best is None or q > best[2]:
                best = (dx, dy, q, k)
        if best is None:
            p[i] = np.nan
            if log is not None:
                log(f"    frame {i}: correlation collapsed to zero shift and no "
                    f"other frame tracks it either -- dropped from the fit")
        else:
            dx, dy, q, k = best
            p[i] = p[k] + np.array([dx, dy])
            if log is not None:
                log(f"    frame {i}: correlation against the middle frame "
                    f"collapsed to zero shift; relayed through frame {k} "
                    f"(peak {q:.3f}) -> ({p[i, 0]:+.1f}, {p[i, 1]:+.1f}) px")
    return p


def _diff_f32(frame_bgr, ref_bgr, colour: bool = False):
    """The picture the scale tracker correlates.

    `colour` reduces by the largest per-channel deviation after removing each
    channel's mean, for the reasons `contact_region` does: an approaching probe
    shadows a side-lit gel, and the imprint is a shift in the balance of three
    LEDs that grey averages away. Measured 2026-09-08 on DIGIT_hard_3mm_r1,
    down one depth ladder the per-channel peak grew 25 -> 53 levels while the
    greyscale peak stayed at 23.
    """
    if colour:
        f = frame_bgr.astype(np.float32) - ref_bgr.astype(np.float32)
        f -= f.mean(axis=(0, 1), keepdims=True)
        return np.abs(f).max(axis=2)
    g = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    r = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return np.abs(g - r)


def _grid_gel_tilt(sensor: str):
    """Mean gel plane slope (sx, sy) for this unit, from any pass that fitted
    one in its scale phase. Same source run_one_sensor uses to square the probe."""
    import glob, json
    sx, sy = [], []
    for p in (glob.glob(str(ROOT / "data" / "*" / "*" / "state.json"))
              + glob.glob(str(ROOT / "data" / "*" / "*" / "*" / "state.json"))):
        name = re.sub(r"__\w+$", "", Path(p).parent.name)
        if name != sensor:
            continue
        try:
            sc = json.loads(Path(p).read_text()).get("scale") or {}
        except Exception:
            continue
        for v in sc.values():
            if isinstance(v, dict) and v.get("plane_slope_y") is not None:
                sx.append(float(v["plane_slope_x"]))
                sy.append(float(v["plane_slope_y"]))
    return (sum(sx) / len(sx), sum(sy) / len(sy)) if sx else None


def phase_calibgrid(a) -> int:
    """Photometric-stereo calibration: a known sphere pressed over a grid.

    9DTact reads depth from one number per pixel -- how dark the pigment layer
    went -- so its calibration is one curve. DIGIT lights the gel from the side
    with three coloured LEDs and reads the SLOPE of the surface from the colour,
    then integrates it; that map from (R, G, B) to (dz/dx, dz/dy) is what has to
    be calibrated, and it is not one curve because the lighting is not uniform.
    Measured on this rig (cross_principle.md 1.1): moving the same contact
    1.5 mm sideways changes the green channel by 72 counts and can flip its
    sign. A single central calibration therefore cannot be used off-centre,
    which is why the cube4 and star10 frames collected so far have no
    reconstruction to be scored against.

    So: press a sphere of KNOWN radius at a grid of positions across the field,
    at several depths each. At every contact point the true surface slope is
    analytic -- for a sphere of radius R indented by d, the contact patch has
    radius sqrt(2Rd - d^2) and the slope at distance r from the centre is
    r / sqrt(R^2 - r^2) -- so each frame gives (position, colour) -> slope for
    a whole disc of slopes at once, and the grid covers the field.

    Depth-controlled, not force-controlled: the slope field is set by the
    geometry of the indentation, so the depth is the quantity that has to be
    held, and the force is recorded and used only as the safety guard.

    Writes calibgrid_<probe>/grid.csv and one PNG per (position, depth).
    """
    from vbts_platform.ft_stream import ForceReader

    reg, ent = load_sensor(a.sensor)
    pcfg, probe = load_probe(a.probe)
    if probe.get("tip") != "sphere":
        print(f"  {probe['id']} is a {probe.get('tip')}. The calibration needs a "
              "SPHERE: its slope field is the thing that is known.")
        return 2
    run = active_run()
    st_run = load_state(run)
    zero = st_run.get("zero")
    if not zero:
        print("  --phase zero first: the grid is measured from its surface")
        return 2
    if zero["probe"] != probe["id"]:
        print(f"  the zero on file used {zero['probe']!r}, not {probe['id']!r}.")
        return 2
    depths = [float(x) for x in a.grid_depths.split(",")]
    cap = depth_backstop(reg, ent)
    if max(depths) > cap:
        print(f"  deepest rung {max(depths)} mm exceeds the {cap:.2f} mm backstop")
        return 2
    nx, ny = (int(v) for v in a.grid_n.split(","))
    # The gel plane is NOT perpendicular to the sensor axis: it is tilted about
    # 2 deg per unit (rig-geometry note, 2026-09-05), and the align step squares
    # the PROBE to it without changing the axis this phase steps along. So a
    # lateral move of 4 mm along the sensor x climbs or drops ~0.14 mm relative
    # to the gel -- as much as the whole indentation. Measured on the first grid
    # (DIGIT_medium_2mm_r1): at 0.15 mm the x = -4 mm column left almost no
    # imprint while x = +4 mm left twice the central one. The surface height at
    # each grid point therefore gets the plane's own correction.
    tilt = _grid_gel_tilt(a.sensor)
    if tilt is None:
        print("  no measured gel plane for this unit; the grid will run flat "
              "and the outer columns may not touch")
        sx = sy = 0.0
    else:
        sx, sy = tilt
        print(f"  gel plane slope ({sx:+.5f}, {sy:+.5f}) -> correcting the "
              f"surface by {sx * a.grid_x:+.3f} / {sy * a.grid_y:+.3f} mm at the edges")

    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2
    ok, why = mv.ready_to_move(mv.read_state(ip))
    if not ok:
        print(f"  not moving: {why}")
        return 2
    okt, whyt = check_indenter_tool(robot_pose(ip))
    if not okt:
        print(f"  {whyt}")
        return 1

    meta = yaml.safe_load(open(run / "meta.yaml"))
    R = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"])
    n = R[:, 2]
    q = chk.ReadOnlyProxy(ip)
    t_sensor, _ = mv.sensor_axis()

    def height():
        return float((np.array(q("GetActualTCPPose", 0)[1:][:3]) - t_sensor) @ n)

    surf = float(zero["surface_mm"])
    pose0 = q("GetActualTCPPose", 0)[1:]
    rpy0 = [float(v) for v in pose0[3:]]
    p_now = np.array(pose0[:3])
    p_surf = p_now - (height() - surf) * n          # the surface point, on axis
    # ...but on WHICH axis. Taking the origin from wherever the TCP happens to
    # be starts the grid at the end of whatever ran last: two of the first six
    # units began 4.02 / 2.52 mm off centre -- exactly the last grid point of a
    # previous calibgrid attempt -- which pushed a third of their frames off the
    # bottom of the image and made their response maps uncomparable to the rest
    # (2026-09-10). Anchor on the sensor centre instead, and correct the surface
    # height for the gel plane over the distance moved to get there.
    o_base = np.array(yaml.safe_load(
        open(run / "meta.yaml"))["sensor_to_base_transform"]["origin_base_mm"])
    dx0 = float((p_now - o_base) @ R[:, 0])
    dy0 = float((p_now - o_base) @ R[:, 1])
    if max(abs(dx0), abs(dy0)) > 0.5:
        print(f"  zero sat {dx0:+.2f} / {dy0:+.2f} mm off the sensor centre; "
              "the grid is anchored on the centre, not on it")
    p_surf = (p_surf - dx0 * R[:, 0] - dy0 * R[:, 1]
              - (dx0 * sx + dy0 * sy) * n)

    ref_img = cv2.imread(str(run / "reference.png"))
    if ref_img is None:
        print("  no reference.png; --phase reference first")
        return 2
    diff_level = diff_level_for_sensor(ref_img, a, getattr(a, "sensor", None))
    out = run / f"calibgrid_{probe['id']}"
    out.mkdir(exist_ok=True)
    f_stop = SHAPE_FORCE_FRAC * float(sensor_limits(a)[1])

    print(f"\n  sensor {ent['id']}  probe {probe['id']} (R = "
          f"{float(probe.get('element_diameter_mm', 4.0)) / 2:.1f} mm sphere)")
    print(f"  surface {surf:.4f} mm, backstop {cap:.2f} mm, force stop {f_stop:.2f} N")
    print(f"  grid {nx} x {ny} over +-{a.grid_x:.1f} x +-{a.grid_y:.1f} mm, "
          f"depths {depths} mm -> {nx * ny * len(depths)} frames")

    # Get clear BEFORE the DAQ task exists. A commanded move takes seconds, and
    # the task is a running acquisition -- leaving it unread that long overran
    # the buffer and the phase died with "the application is not able to keep up
    # with the hardware acquisition" (2026-09-10).
    if _move_to_point(ip, p_surf + a.retract * n, rpy0, a,
                      a.approach_joint_step, vel=a.vel_free):
        return 2
    cam = Camera.from_config(camera_config_for(a.sensor))
    cam.open()
    ft = FTInterface.from_config()
    ft.connect()
    reader = None
    rows = []
    try:
        tare = ft.tare(duration_s=2.0)
        res = ft.read_wrench_mean(duration_s=1.0, tared=True)
        print(f"  zero residual |F| {np.linalg.norm(res[:3]):.4f} N")
        if np.linalg.norm(res[:3]) > 0.15:
            print("  not clear of the gel.")
            return 1
        reader = ForceReader(ft, tare).start()
        _cal_ref = {"done": (run / "reference_calibgrid.png").exists()}

        # NOT reference.png. Every DIGIT reference.png is 8-14 % brighter than
        # the frames that follow it -- the probe is clear of the gel when it is
        # taken, so nothing shadows the translucent side-lit gel (note of
        # 2026-09-09). On this unit it is 77.0 against 68.1 for the working
        # reference and 69.0 for the frames. Differenced against it a whole
        # quadrant of the picture clears any threshold: the first autoframe run
        # picked a 240349 px blob for one of the three presses -- an eighth of
        # the frame -- put its centroid 200 px from the real imprint, and the
        # affine that came out read 111 px/mm along one axis and 45 along the
        # other, so the lattice collapsed to 24 % of the field.
        # Resolved on FIRST USE, not here: the best reference for this phase is
        # the one the first press writes a moment from now, so reading the
        # directory before that would always miss it.
        _ref_af = {}

        def ref_for_diff():
            if "img" not in _ref_af:
                for nm in ("reference_calibgrid.png", "reference_working.png",
                           "reference_collect.png", "reference.png"):
                    if (run / nm).exists():
                        _ref_af["img"] = cv2.imread(str(run / nm)).astype(np.float32)
                        print(f"  imprints are differenced against {nm} "
                              f"(mean {_ref_af['img'].mean():.1f})")
                        break
            return _ref_af.get("img")

        def imprint_centre(frame):
            """Centroid and area of the largest blob that moved, in pixels.

            contact_region's level threshold is tuned for the ladder phases and
            is not stable enough to solve a coordinate frame from: on the first
            six grids it returned 0 px for two frames of thirty and 346 px right
            beside 69179 on consecutive rungs of one point. This takes the
            largest connected component of the blurred absolute difference at a
            threshold relative to that frame's own peak, which on the same
            thirty frames varied by 1.9x instead of 200x.
            """
            rf = ref_for_diff()
            if rf is None:
                return None, 0
            d = cv2.GaussianBlur(
                np.abs(frame.astype(np.float32) - rf).max(2), (0, 0), 7)
            m = (d > max(5.0, 0.5 * float(d.max()))).astype(np.uint8)
            nb, _, st, cen = cv2.connectedComponentsWithStats(m, 8)
            if nb < 2:
                return None, 0
            i = 1 + int(np.argmax(st[1:, 4]))
            return np.array(cen[i], float), int(st[i, 4])

        def press(dx, dy, dtgt, name):
            """One indentation at a grid offset, gel-plane corrected."""
            base = (p_surf + dx * R[:, 0] + dy * R[:, 1]
                    + (dx * sx + dy * sy) * n)
            if _move_to_point(ip, base + a.zero_margin * n, rpy0, a,
                              a.approach_joint_step, vel=a.vel_free):
                return None
            time.sleep(a.zero_recover_s)
            # The phase's own working reference, taken from right here: clear
            # of the gel but still a millimetre off it, so the probe's shadow
            # is in the frame the way it is in every measured frame. It exists
            # because reference.png does NOT have that shadow -- on a DIGIT it
            # runs 8-14 % brighter than everything that follows -- and
            # differencing against it is what made the first autoframe pick a
            # 240349 px blob. run_one_sensor writes reference_working.png at
            # its own 0.30 mm standoff inside the touchcheck step, so taking
            # one here is what lets that step be skipped: it costs no move, the
            # probe is already lifted and waiting out zero_recover_s.
            if not _cal_ref["done"]:
                _cal_ref["done"] = True
                try:
                    fr, _ = cam.grab_after(time.time())
                    cv2.imwrite(str(run / "reference_calibgrid.png"), fr,
                                [cv2.IMWRITE_PNG_COMPRESSION, 1])
                    print(f"  reference_calibgrid.png at {a.zero_margin:.2f} mm "
                          f"standoff (mean {float(fr.mean()):.1f})")
                except Exception as e:                       # noqa: BLE001
                    print(f"  (reference_calibgrid.png not saved: {e})")
            if _move_to_point(ip, base - dtgt * n, rpy0, a, a.max_joint_step):
                return None
            time.sleep(a.shape_dwell)
            reached = surf - height()
            w, err = reader.read_fresh()
            if err:
                print(f"  F/T failed: {err}")
                return None
            frame, t_img = cam.grab_after(time.time())
            rg = contact_region(frame, ref_img, diff_level,
                               colour=shadows_the_gel(getattr(a, "sensor", None)))
            cv2.imwrite(str(out / name), frame, [cv2.IMWRITE_PNG_COMPRESSION, 1])
            return dict(frame=frame, rg=rg, force=-float(w[2]), depth=reached,
                        w=w, t_img=t_img)

        # The grid has to be laid out in IMAGE coordinates, not robot ones.
        # What is being calibrated is a map from a place in the PICTURE to a
        # slope, and the picture is not squarely mounted on the robot axes:
        # fitting the first six units' imprint centroids against the commanded
        # offsets gave rotations of 20.8-32.4 deg, scales of 82-109 px/mm (it
        # tracks gel thickness -- a thinner gel sits closer to the lens), and
        # grid centres anywhere from (867, 519) to (1145, 955) in a 1920x1080
        # frame. Two consequences, both measured (2026-09-10):
        #   * the corners of a robot-axis grid ran off the bottom of the frame
        #     on two of the six units, losing 13 of their 60 frames;
        #   * comparing two units' response maps by their COMMANDED (x, y) was
        #     comparing different places in the picture. Correlation between a
        #     pair of units tracked how far apart their grid centres were
        #     (Spearman -0.75, p 0.001) and NOT whether they were replicates:
        #     the seven pairs within 150 px all agreed (median dG +0.56) and
        #     the eight beyond it did not (-0.15), including a different-gel
        #     pair at +0.75 and same-gel replicates at -0.33.
        # So press a few points first, read where their imprints actually
        # land, solve the affine mm -> px by least squares, and invert it to
        # place a lattice that is square to the frame and centred on it.
        #
        # FIVE presses, not three. Three points leave no redundancy: one
        # misread centroid goes straight into the affine, which is how the
        # first attempt came out 111 px/mm along one axis and 45 along the
        # other and collapsed the lattice to 24 % of the field. The imprint's
        # difference is an ANNULUS -- the contact's flat middle barely changes
        # colour, only its sloped rim does -- and the rim is brighter on the
        # downhill side, so a centroid carries a bias of tens of pixels that
        # varies over the field. Symmetric pairs cancel most of it and an
        # over-determined fit shows what is left as a residual.
        #
        # Deeper than the grid's own rungs, too: the gel-plane correction is
        # not exact, so an off-centre press lands shallower than commanded --
        # the first attempt reached 0.164 mm where it asked for 0.30 -- and a
        # faint imprint is exactly what a centroid cannot be trusted on.
        d_fit = max(depths)
        aff = None
        if a.grid_autoframe:
            q_mm = a.grid_probe_mm
            spots = ((0.0, 0.0), (q_mm, 0.0), (-q_mm, 0.0),
                     (0.0, q_mm), (0.0, -q_mm))
            print(f"\n  autoframe: {len(spots)} presses at {d_fit:.2f} mm, "
                  f"+-{q_mm:.1f} mm apart, to find the frame's own axes")
            R_ball = float(probe.get("element_diameter_mm", 4.0)) / 2.0
            a_hi = 4.0 * np.pi * (2.0 * R_ball * d_fit) * 120.0 ** 2
            pts = []
            # Match the FORCE at every autoframe point, not the depth. What
            # the affine needs is centroid DIFFERENCES, so a bias that is the
            # same at all five points cancels -- but the bias is a function of
            # how big the imprint is and which way its annulus leans, so it
            # only stays constant if the contacts are the same size. Commanding
            # a depth does not give that: the gel-plane correction is off by
            # about 0.14 mm at 3.5 mm out, and on DIGIT_hard_1mm_r1 the five
            # points landed at 0.146 to 0.426 mm. The y axis then came out
            # 137 px/mm against a true 110, an over-estimate that pushed the
            # lattice outward until its left column hung off the frame.
            # Hertz gives the step: F goes as depth^1.5, so one correction of
            # (F_target / F)^(2/3) lands within a few percent.
            f_tgt = a.grid_probe_force or 0.5 * f_stop
            print(f"    each press is trimmed to {f_tgt:.2f} N so all five "
                  "contacts are the same size")
            for dx, dy in spots:
                # Converge on the force even when the gel-plane correction is
                # wrong. On DIGIT_hard_1mm_r2 a commanded 0.30 mm gave 0.00 N
                # at (0, +3.5) and 0.43 mm of depth at (0, -3.5): 0.29 mm of
                # residual tilt over 7 mm, the same size as the correction that
                # had just been applied. A 1 mm gel has no room to absorb that,
                # so three attempts with one Hertz step each ended on presses
                # of 0.27-0.41 N against a 0.70 N target and the fit scattered
                # by 194 px. Five attempts, a step clamped so a near-zero
                # reading cannot slam into the depth cap, and a floor under
                # what counts as contact at all.
                dd = d_fit
                f_min = max(0.15, 0.25 * f_tgt)
                best = None
                for attempt in range(5):
                    r = press(dx, dy, dd, f"autoframe_x{dx:+.2f}_y{dy:+.2f}.png")
                    if r is None:
                        return 2
                    c, area = imprint_centre(r["frame"])
                    f_now = max(r["force"], 1e-3)
                    print(f"    ({dx:+.2f}, {dy:+.2f}) at {dd:.2f} mm -> centroid "
                          f"{'-' if c is None else c.round(0)}  area {area} px  "
                          f"{f_now:.2f} N  depth {r['depth']:.3f} mm")
                    if f_now >= f_min and (best is None
                                           or abs(f_now - f_tgt) < abs(best[2] - f_tgt)):
                        best = (c, area, f_now)
                    if 0.75 * f_tgt <= f_now <= 1.3 * f_tgt:
                        break
                    if dd >= cap - 1e-6 and f_now < f_tgt:
                        print("      at the depth cap and still light; taking it")
                        break
                    if f_now < 0.02:
                        nd = dd + 0.15          # not touching: the law says nothing
                    else:
                        nd = dd * (f_tgt / f_now) ** (2.0 / 3.0)
                        nd = float(np.clip(nd, dd * 0.6, dd * 1.8))
                    nd = float(np.clip(nd, 0.05, cap))
                    if abs(nd - dd) < 0.01:
                        break
                    dd = nd
                    print(f"      {f_now:.2f} N against {f_tgt:.2f} N target; "
                          f"pressing {dd:.2f} mm")
                if best is not None:
                    c, area, f_best = best
                else:
                    print(f"    never reached {f_min:.2f} N here; not running")
                    return 2
                # Judge the press that was KEPT, not whichever the loop tried
                # last -- a search that overshoots once and comes back must not
                # be failed on the overshoot.
                if f_best >= f_stop:
                    print(f"    past the {f_stop:.2f} N stop; not running")
                    return 2
                # The contact of a known sphere at a known depth has a known
                # area, so a blob far off it is not the contact. The upper gate
                # matters most when the probe is barely touching: at 0.00 N the
                # detector picked a 394819 px region of noise as the imprint.
                if c is None or area < 400 or area > a_hi:
                    print(f"    blob of {area} px is not a "
                          f"{2.0 * np.sqrt(2.0 * R_ball * d_fit):.2f} mm contact "
                          f"(want 400-{a_hi:.0f} px); not running")
                    return 2
                pts.append((c, dx, dy))
            if len(pts) == len(spots):
                # A SIMILARITY -- one rotation, one scale, one offset -- not
                # a free affine. A camera with square pixels looking at a flat
                # gel cannot produce anything else, so the two extra degrees of
                # freedom an affine carries can only absorb centroid error, and
                # they do: the free fit on DIGIT_hard_1mm_r1 came out with its
                # axes 78 deg apart and scales 16 % different, against 92.5 deg
                # and 1 % from the same unit's 30-point grid. Four parameters
                # from five points, in closed form (Procrustes).
                P = np.array([q[0] for q in pts])
                U = np.array([[q[1], q[2]] for q in pts], float)
                Uc, Pc = U - U.mean(0), P - P.mean(0)
                num = float((Uc[:, 0] * Pc[:, 0] + Uc[:, 1] * Pc[:, 1]).sum())
                den = float((Uc[:, 0] * Pc[:, 1] - Uc[:, 1] * Pc[:, 0]).sum())
                scl = np.hypot(num, den) / max(float((Uc ** 2).sum()), 1e-9)
                th = np.arctan2(den, num)
                M = scl * np.array([[np.cos(th), -np.sin(th)],
                                    [np.sin(th), np.cos(th)]])
                c0 = P.mean(0) - M @ U.mean(0)
                res = np.linalg.norm(U @ M.T + c0 - P, axis=1)
                sxx, syy = float(np.hypot(*M[:, 0])), float(np.hypot(*M[:, 1]))
                ang = float(np.degrees(np.arccos(np.clip(
                    M[:, 0] @ M[:, 1] / (sxx * syy + 1e-9), -1, 1))))
                print(f"    fit residual {res.mean():.0f} px mean, "
                      f"{res.max():.0f} px worst")
                if res.mean() > a.grid_res_max_px:
                    print(f"    that is past the {a.grid_res_max_px:.0f} px "
                          "limit; not running")
                    return 2
                # A camera looking at a flat gel through square pixels maps mm
                # to px as a rotation and a near-uniform scale. The first six
                # units bear that out: 82-109 px/mm along x against 92-110 along
                # y on the same unit, never more than 17 % apart. Further off
                # than that means a centroid was misread, and inverting it sends
                # the lattice somewhere arbitrary.
                if (min(sxx, syy) < 20.0 or abs(ang - 90.0) > 15.0
                        or max(sxx, syy) / max(min(sxx, syy), 1e-9) > 1.35):
                    print(f"    the two axes came out {sxx:.0f} and {syy:.0f} "
                          f"px/mm at {ang:.0f} deg apart -- that is not a "
                          "rotation of the gel plane; not running")
                    return 2
                else:
                    aff = (M, c0)
                    rot = np.degrees(np.arctan2(M[1, 0], M[0, 0]))
                    print(f"    mm -> px: rotation {rot:+.1f} deg, "
                          f"{sxx:.0f} / {syy:.0f} px/mm at {ang:.0f} deg, "
                          f"centre {c0.round(0)}")
        H_img, W_img = ref_img.shape[:2]
        if aff is None:
            # --grid-x / --grid-y are the TRAVEL BACKSTOP for the image-space
            # lattice, not a grid span. Reaching a 1920 x 1080 frame through a
            # 25 deg rotation costs about 9 x 7.5 mm of travel, but the gel is
            # only about 19 x 11 mm across, so walking a grid to those numbers
            # takes the probe off the sensor -- which is what happened on
            # 2026-09-10 when an autoframe failure fell through to here: six of
            # the first twelve points left no imprint at all (area 0 px) and
            # pressed the bezel at up to 1.33 N. The robot-axis grid gets its
            # own span, and it is small.
            xs = np.linspace(-a.grid_span_x, a.grid_span_x, nx)
            ys = np.linspace(-a.grid_span_y, a.grid_span_y, ny)
            print(f"  robot-axis grid over +-{a.grid_span_x:.1f} x "
                  f"+-{a.grid_span_y:.1f} mm")
            pts_rows = [[(float(dx), float(dy), float("nan"), float("nan"))
                         for dx in xs] for dy in ys]
        else:
            M, c0 = aff
            Minv = np.linalg.inv(M)
            ctr = np.array([W_img / 2.0, H_img / 2.0])
            # Hertzian contact radius of a known sphere at a known depth,
            # in pixels -- exact, where a thresholded blob is not: the blob
            # finds the strong core (about 55 px here) while the contact is
            # really 1.05 mm across at 0.30 mm, which is 115 px at this scale.
            R_ball = float(probe.get("element_diameter_mm", 4.0)) / 2.0
            r_mm = float(np.sqrt(max(2.0 * R_ball * d_fit - d_fit ** 2, 1e-9)))
            r_px = r_mm * float(np.hypot(*M[:, 0]))
            marg = r_px + a.grid_margin_px
            print(f"    contact radius {r_mm:.2f} mm = {r_px:.0f} px; keeping "
                  f"{marg:.0f} px clear of the frame edge")
            # Pull the lattice in further than the margin alone asks. The
            # SCALE this fit returns cannot be trusted to better than about a
            # sixth: on DIGIT_hard_1mm_r1 the same sensor read 109 px/mm over a
            # +-4 x +-2.5 mm grid, 127 from the five autoframe points, and 123
            # over a -6.3..+7.1 mm grid -- while the rotation agreed to a degree
            # across all three (29.5 / 30.7 / 30.4). The imprint centroid is
            # simply not a good enough ruler, because where it sits depends on
            # how deep the contact went and where in the field it is. An
            # over-read scale pushes the lattice OUTWARD, and that is what hung
            # its left column off the frame. So size the lattice to survive
            # being wrong by this much rather than trying to be right.
            # Size the lattice by how well the fit actually came out, not by a
            # fixed guess. The residual is a direct measure of how far a placed
            # point may land from where it was asked to: over a baseline of
            # q_mm x scale pixels, a residual of `res` carries roughly
            # res/baseline of relative error into the scale and the angle
            # alike. Good units come in at 8-9 px and get the full lattice;
            # DIGIT_hard_1mm_r2 came in at 85 px -- its imprints vary in size
            # across the field because the ILLUMINATION does, which is the very
            # thing being calibrated, so this is a floor of the method and not
            # a fault to be fixed -- and gets a smaller one.
            baseline_px = max(q_mm * float(np.hypot(*M[:, 0])), 1.0)
            safety = float(np.clip(1.0 - 2.0 * res.mean() / baseline_px,
                                   0.45, a.grid_safety))
            if safety < a.grid_safety:
                print(f"    a {res.mean():.0f} px residual over a "
                      f"{baseline_px:.0f} px baseline pulls the lattice to "
                      f"{safety * 100:.0f} % instead of {a.grid_safety * 100:.0f} %")
            half = (np.array([W_img / 2.0 - marg, H_img / 2.0 - marg]) * safety)
            # If the frame asks for more travel than the caps allow, shrink
            # the lattice as a rectangle -- clipping point by point would put
            # it back out of square with the image, which is the whole point of
            # measuring the affine. Both half-extents are searched rather than
            # scaled together, because the rotation makes the two axes cost
            # different amounts of travel and a uniform scale throws away the
            # cheaper one.
            def reachable(hx, hy):
                for sgx in (-1, 1):
                    for sgy in (-1, 1):
                        v = Minv @ (ctr + np.array([sgx * hx, sgy * hy]) - c0)
                        if abs(v[0]) > a.grid_x or abs(v[1]) > a.grid_y:
                            return False
                return True
            if not reachable(*half):
                want = half.copy()
                best = None
                for fx in np.linspace(0.05, 1.0, 40):
                    for fy in np.linspace(0.05, 1.0, 40):
                        hx, hy = want[0] * fx, want[1] * fy
                        if reachable(hx, hy) and (best is None or hx * hy > best[0] * best[1]):
                            best = (hx, hy)
                if best is None:
                    print(f"    even a single point at the frame centre needs "
                          f"more than {a.grid_x:.1f} x {a.grid_y:.1f} mm of "
                          "travel; not running")
                    return 2
                half = np.array(best)
                print(f"    the frame needs more than the {a.grid_x:.1f} x "
                      f"{a.grid_y:.1f} mm travel allows; lattice covers "
                      f"{half[0] / (W_img / 2) * 100:.0f} % x "
                      f"{half[1] / (H_img / 2) * 100:.0f} % of it")
            pts_rows = []
            for ty in np.linspace(-half[1], half[1], ny):
                row = []
                for tx in np.linspace(-half[0], half[0], nx):
                    v = Minv @ (ctr + np.array([tx, ty]) - c0)
                    row.append((float(v[0]), float(v[1]),
                                float(ctr[0] + tx), float(ctr[1] + ty)))
                pts_rows.append(row)
            sp = [p for row in pts_rows for p in row]
            print(f"    lattice pulled to {safety * 100:.0f} % of the "
                  f"usable frame: +-{half[0]:.0f} x +-{half[1]:.0f} px")
            print(f"    lattice spans {min(p[0] for p in sp):+.2f}..{max(p[0] for p in sp):+.2f} x "
                  f"{min(p[1] for p in sp):+.2f}..{max(p[1] for p in sp):+.2f} mm "
                  f"to cover the frame with {marg:.0f} px to spare")
        # What each rung SHOULD weigh, from this unit's own gel model. The grid
        # is depth-controlled on purpose -- the slope field a photometric
        # calibration reads is set by the geometry of the indentation, so the
        # depth is the quantity to hold -- but the depth that arrives is not
        # the depth commanded: the gel plane correction leaves a residual
        # gradient, and over a lattice that now spans +-9 mm that residual eats
        # the whole rung. Measured over the aligned grids collected so far, the
        # 0.30 mm rung came out at 0.75 N median on the 1 mm units, 0.46 on the
        # 2 mm and 0.20 on the 3 mm, and on BOTH 3 mm units fifteen of thirty
        # points were under 0.10 N -- half the grid barely touching, which is
        # no calibration datum at all. So the force is used to find the LOCAL
        # surface: press, compare against the model, correct the depth, and
        # carry the correction to the next point, where the tilt is nearly the
        # same.
        gm = (ent.get("gel_model") or {})
        k_h = float(gm.get("hertz_a") or 0.0)
        n_h = float(gm.get("free_exponent") or 1.5)
        if k_h > 0:
            print("  rung force from this unit's gel model: "
                  + ", ".join(f"{d:.2f} mm -> {k_h * d ** n_h:.2f} N"
                              for d in sorted(depths)))
        else:
            print("  no gel model for this unit; rungs run at their commanded "
                  "depth with no local-surface correction")
        dz_off = 0.0                 # local surface offset, carried between points
        print(f"\n  {'ix':>3} {'iy':>3} {'x':>6} {'y':>6} {'depth':>7} "
              f"{'force':>8} {'area px':>9}  note")
        for iy, row in enumerate(pts_rows):
            for ix, (dx, dy, tx_px, ty_px) in enumerate(row):
                base = (p_surf + dx * R[:, 0] + dy * R[:, 1]
                        + (dx * sx + dy * sy) * n)
                # Lift and cross to the new position ONCE, then walk the depths
                # downward without coming back up. Each commanded move costs
                # about two seconds of round trip whatever it travels -- the
                # 0.2 mm steps take milliseconds -- so the way to make the grid
                # faster is fewer moves, not faster ones. Going deeper from an
                # existing contact does carry the shallower rung's creep into
                # the deeper one, which for a photometric calibration is
                # harmless: the force is recorded at every rung and the actual
                # depth is taken from it, not from the command.
                if _move_to_point(ip, base + a.zero_margin * n, rpy0, a,
                                  a.approach_joint_step, vel=a.vel_free):
                    return 2
                time.sleep(a.zero_recover_s)
                for dtgt in sorted(depths):
                    f_want = k_h * dtgt ** n_h if k_h > 0 else 0.0
                    note = ""
                    for attempt in range(3):
                        if _move_to_point(ip, base - (dtgt + dz_off) * n, rpy0, a,
                                          a.max_joint_step):
                            return 2
                        time.sleep(a.shape_dwell)
                        reached = surf - height()
                        w, err = reader.read_fresh()
                        if err:
                            print(f"  F/T failed: {err}")
                            return 1
                        f = -float(w[2])
                        if f_want <= 0 or f >= f_stop:
                            break
                        # Hertz again: F goes as depth^n, so the depth this
                        # point is really at is (f/f_want)^(1/n) of what was
                        # asked, and the difference is where its surface sits.
                        if 0.6 * f_want <= f <= 1.6 * f_want:
                            break
                        d_true = dtgt * (max(f, 1e-3) / f_want) ** (1.0 / n_h)
                        corr = float(np.clip(dtgt - d_true, -0.4, 0.4))
                        if abs(corr) < 0.01 or attempt == 2:
                            note = f"{f:.2f} N vs {f_want:.2f} N wanted"
                            break
                        # never past the unit's own depth backstop
                        dz_off = float(np.clip(dz_off + corr, -0.6,
                                               min(0.6, cap - dtgt)))
                        note = f"surface {dz_off:+.3f} mm"
                    frame, t_img = cam.grab_after(time.time())
                    rg = contact_region(frame, ref_img, diff_level,
                                        colour=shadows_the_gel(getattr(a, "sensor", None)))
                    name = f"{probe['id']}_x{dx:+.2f}_y{dy:+.2f}_d{dtgt:.2f}.png"
                    cv2.imwrite(str(out / name), frame,
                                [cv2.IMWRITE_PNG_COMPRESSION, 1])
                    pose = q("GetActualTCPPose", 0)[1:]
                    rows.append({"probe": probe["id"], "ix": ix, "iy": iy,
                                 "x_mm": float(dx), "y_mm": float(dy),
                                 "img_x_px": tx_px, "img_y_px": ty_px,
                                 "target_depth_mm": dtgt, "depth_mm": reached,
                                 "surface_offset_mm": dz_off,
                                 "force_wanted_N": f_want,
                                 "force_N": f, "file": name, "t_img": t_img,
                                 "Fx": float(w[0]), "Fy": float(w[1]),
                                 "Fz": float(w[2]),
                                 "tcp_x": pose[0], "tcp_y": pose[1], "tcp_z": pose[2],
                                 "area_px": rg["area_px"],
                                 "radius_px": rg["radius_px"],
                                 "centroid_px": str(rg["centroid_px"]),
                                 "diff_level": diff_level})
                    print(f"  {ix:>3} {iy:>3} {dx:>6.2f} {dy:>6.2f} {reached:>7.3f} "
                          f"{f:>8.3f} {rg['area_px']:>9d}  {note}")
                    if f >= f_stop:
                        print(f"    {f:.3f} N past the stop; deeper rungs here skipped")
                        break
        _write_rows(out / "grid.csv", rows)
        st_run.setdefault("calibgrid", {})[probe["id"]] = {
            "n_frames": len(rows), "grid_n": [nx, ny], "depths_mm": depths,
            "span_mm": [a.grid_x, a.grid_y], "surface_mm": surf,
            "affine_mm_to_px": (None if aff is None else
                                {"M": aff[0].tolist(), "origin_px": aff[1].tolist(),
                                 "probe_mm": a.grid_probe_mm}),
            "dir": out.name, "at": datetime.now().isoformat()}
        save_state(run, st_run)
        print(f"\n  {len(rows)} frames -> {out}")
    finally:
        if reader is not None:
            reader.stop()
        cam.close()
        ft.disconnect()
        back = surf + a.retract - height()
        if back > 0:
            _move_along_normal(ip, back, a, a.approach_joint_step, vel=a.vel_free)
    return 0


def phase_scale(a) -> int:
    """Millimetres per pixel, the gel's own plane, and the pressure-centre sign.

    Three things the first attempt could not deliver, and why:

    * It pressed to a fixed DEPTH. Along the sensor y that gave 0.813 N at one
      end of the sweep and 1.134 N at the other, so every sample had a
      different contact and the centroid moved for two reasons at once. Force
      control fixes the contact instead, and then the HEIGHT at which the force
      is reached maps the gel surface for free -- which is the plane
      measurement, obtained from the same presses.
    * It located the contact by the intensity-weighted centroid. The
      illumination is not uniform, so the first moment is pulled toward the
      bright part of the frame: even the clean sweep varied 15 % segment to
      segment. Phase correlation measures the translation of the pattern
      itself and does not care about a slowly varying gain.
    * It recorded only Fz. The centre of pressure needs the whole wrench, and
      needs it corrected for shear: the contact sits ~25.7 mm above the ATI
      wrench origin, so 0.01 N of shear makes 0.26 N.mm, the same size as the
      moments being interpreted. With the offsets commanded and known, the
      computed centre of pressure can finally be checked against the truth
      rather than trusted.

    `--scale-rotate 180` re-runs the same presses with the tool turned about
    the sensor normal. A tilt that belongs to the probe reverses with it; a
    tilt that belongs to the gel does not.
    """
    from vbts_platform.ft_stream import ForceReader

    reg, ent = load_sensor(a.sensor)
    pcfg, probe = load_probe(a.probe)
    run = active_run()
    st_run = load_state(run)
    zero = st_run.get("zero")
    if not zero:
        print("  --phase zero first")
        return 2
    if zero["probe"] != probe["id"]:
        print(f"  the zero on file was found with probe {zero['probe']!r}, "
              f"not {probe['id']!r}. Re-run --phase zero.")
        return 2
    offsets = [float(x) for x in a.scale_offsets.split(",")]

    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2
    ok, why = mv.ready_to_move(mv.read_state(ip))
    if not ok:
        print(f"  not moving: {why}")
        return 2
    okt, whyt = check_indenter_tool(robot_pose(ip))
    if not okt:
        print(f"  {whyt}")
        return 1

    meta = yaml.safe_load(open(run / "meta.yaml"))
    R = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"])
    n = R[:, 2]
    q = chk.ReadOnlyProxy(ip)
    t_sensor, _ = mv.sensor_axis()

    def height():
        return float((np.array(q("GetActualTCPPose", 0)[1:][:3]) - t_sensor) @ n)

    surf = float(zero["surface_mm"])
    # What force to seek is not a constant of the rig: it is whatever this gel
    # can give inside the depth the calibration is allowed to use. Asking every
    # sensor for 1.0 N failed all ten points on 9DTact_soft_2mm_r1, which
    # reaches 0.60-0.77 N at the 0.6 mm cap, and spent seven minutes finding
    # that out. The contact only has to be identical at every OFFSET on one
    # sensor; it need not be the same between sensors.
    # WHAT THE IMPRINT HAS TO LOOK LIKE, and why neither a force nor a depth
    # sets it. The tracking needs an imprint with texture: too faint and the
    # correlation has nothing to lock onto, too deep and the contact saturates
    # into a featureless dark disc. Both failures were measured on 2026-09-08,
    # same rig, same hour:
    #
    #   9DTact_hard_3mm_r1  0.99 N -> 0.66 mm = 0.22 x thickness   15.9-31.3 px
    #   9DTact_hard_3mm_r1  2.00 N -> 1.05 mm = 0.35 x thickness    0.59-2.61 px
    #   9DTact_hard_2mm_r1  0.99 N -> 0.78 mm = 0.39 x thickness    1.07 px
    #   9DTact_hard_1mm_r2  0.99 N -> 0.87 mm = 0.87 x thickness    3.80 px
    #   9DTact_medium_1mm_r2 2.00 N -> 1.39 mm = 1.39 x thickness   all NaN
    #
    #   9DTact_medium_1mm_r2 0.40 mm = 0.40 x thickness   0.00 px/mm, nothing
    #
    # ABSOLUTE depth predicts all six; thickness fraction does not. The four
    # that worked sit at 0.78-1.05 mm whatever the gel, and the three that
    # failed are at 0.40, 0.66 and 1.39 mm across fractions of 0.22 to 1.39.
    # That is the right variable physically: what the correlation tracks is the
    # imprint's SIZE, and for a 2 mm ball the contact radius is sqrt(2Rd),
    # set by depth alone. Too small and there is no patch to lock onto; too
    # deep and the contact saturates into a featureless disc.
    #
    # (A thickness-fraction rule was tried first, on 2026-09-08, and asking
    # 9DTact_medium_1mm_r2 for 0.40 x 1 mm found nothing at all. The fraction
    # only looked right because the three units it was fitted to happened to
    # be 2 and 3 mm.)
    #
    # The mechanics were never at fault in any of the failures: all ten offsets
    # reached their force to 2 %, and the centre of pressure tracked the
    # commanded position with slope 0.86-0.99 every time.
    _cap0 = min(a.scale_max_depth, depth_backstop(reg, ent), a.scale_depth_mm)
    _stiff = [f["a"] for f in zero.get("fits", []) if f.get("ok")]
    force_target = float(a.scale_force)
    # The contact law's EXPONENT matters: a sphere gives a*d^1.5, not a*d.
    # Ignoring it asked 9DTact_soft_3mm_r1 for 0.14 N when the gel could give
    # 0.11 N at the cap, and six of the ten offsets never reached it.
    _exp = 1.5 if probe["contact_law"] == "hertz" else 1.0
    # WHICH STIFFNESS. The zero phase fits over the first 0.3 mm, which is a
    # different part of the curve from the 0.9 mm this phase presses to, and on
    # some gels it is badly out: 9DTact_medium_3mm_r1's zero fits gave 0.56-0.61
    # N/mm^1.5 where characterize, fitted over 2.2 mm, gives 1.326. Taking the
    # zero's value asked for 0.36 N when 0.90 mm is worth 1.13 N, so the imprint
    # went in a third of the intended depth, came out at 14-17 grey levels
    # against the 24-27 of units that track cleanly, and the y row failed three
    # times running. The registry's gel model is fitted over the range this
    # phase works in, so it is the one to believe; the zero fits stay as the
    # fallback for a unit that has not been characterised.
    _gm = (ent.get("gel_model") or {})
    _k_reg = float(_gm.get("hertz_a") or 0.0)
    _k = _k_reg if _k_reg > 0 else (float(np.mean(_stiff)) if _stiff else 0.0)
    _src = "registry gel model" if _k_reg > 0 else "zero fits"
    if _stiff and _k_reg > 0:
        _k_zero = float(np.mean(_stiff))
        if abs(_k_zero - _k_reg) > 0.3 * max(_k_reg, 1e-6):
            print(f"\n  note: the zero fits give {_k_zero:.2f} N/mm^{_exp:g} and "
                  f"the registry {_k_reg:.2f}; using the registry, which is "
                  f"fitted over the depth this phase presses to")
    if _k > 0:
        _reach = a.scale_force_frac * _k * _cap0 ** _exp
        if _reach < force_target:
            force_target = float(_reach)
            print(f"\n  {a.scale_force} N is not what this gel needs for a "
                  f"trackable imprint ({_k:.2f} N/mm^{_exp:g} from the {_src} "
                  f"at the {_cap0:.2f} mm depth cap); seeking "
                  f"{force_target:.2f} N instead")
    pose0 = q("GetActualTCPPose", 0)[1:]
    rpy_now = [float(v) for v in pose0[3:]]
    if abs(a.scale_rotate) > 1e-6:
        # About the TOOL's own axis, not the registry's nominal normal. The two
        # are not the same once the tool has been aligned to the gel: this
        # unit's gel sits 2.51 deg off nominal, so turning about the nominal
        # axis sweeps the tool round a cone of that half-angle and its tilt
        # AGAINST THE GEL runs from 0 to 5.02 deg with the rotation. Measured
        # 2026-09-08 on DIGIT_hard_3mm_r1 with pair100, whose two posts are
        # 2 mm apart and therefore 0, 45, 88 and 124 um apart in height at 0,
        # 30, 60 and 90 deg of rotation -- against a contact depth of 50-100 um.
        # The posts' symmetry followed exactly: 0.96, 0.58, 0.36, and then no
        # second post at all. Aligning first did not help, because the
        # alignment was being undone by the rotation itself.
        #
        # A roll about the tool axis leaves the tilt where alignment put it, at
        # every angle. The 180 deg probe-versus-gel test this was written for
        # still works: a tilt belonging to the probe reverses with a tool-axis
        # roll just as it did with a normal-axis one.
        M = cal.rpy_to_matrix(*rpy_now) @ rot_about([0, 0, 1], a.scale_rotate)
        rpy0 = matrix_to_rpy(M)
        tool_n = cal.rpy_to_matrix(*rpy_now)[:, 2]
        print(f"\n  tool rolled {a.scale_rotate:+.0f} deg about its own axis "
              f"(which is {np.degrees(np.arccos(np.clip(abs(tool_n @ n), 0, 1))):.2f} deg "
              f"off the nominal normal): rpy {np.round(rpy_now, 2)} -> "
              f"{np.round(rpy0, 2)}")
    else:
        rpy0 = rpy_now
    p0 = np.array(pose0[:3], dtype=float)
    p_surf = p0 - (height() - surf) * n

    ref_img = cv2.imread(str(run / "reference.png"))
    _shadow = shadows_the_gel(getattr(a, "sensor", None))
    if ref_img is None:
        print("  no reference.png")
        return 2
    tag = "" if abs(a.scale_rotate) < 1e-6 else f"_rot{int(a.scale_rotate)}"
    out = run / f"scale_{probe['id']}{tag}"
    out.mkdir(exist_ok=True)

    print(f"\n  sensor {ent['id']}  probe {probe['id']}")
    print(f"  surface {surf:.4f} mm, seeking {force_target:.2f} N at each offset")
    print(f"  offsets {offsets} mm along the sensor x and y")

    # Reach the working height BEFORE the DAQ task exists, from wherever the
    # probe is. Between ft.connect() and the reader thread starting nothing
    # drains the buffer, and it holds one second at 2 kHz, so any move longer
    # than that overruns it (-200279, "not able to keep up with the hardware
    # acquisition").
    #
    # This guard used to fire only when the probe was BELOW the working height
    # -- written for coming up off the gel after the ladder. On 2026-09-08 the
    # opposite case appeared: pass_a_sensor.sh's `--to shape` now parks at
    # 78 mm before the scale phase runs, so the phase began with a 50 mm
    # DESCENT after connecting, and it overran twice in a row on
    # 9DTact_hard_1mm_r2. The move is needed in both directions; the condition
    # was the bug.
    if abs(surf + a.retract - height()) > 0.05:
        if _move_to_point(ip, p_surf + a.retract * n, rpy_now, a,
                          a.approach_joint_step, vel=a.vel_free):
            return 2

    # EVERY robot move that takes time must happen BEFORE the DAQ task
    # exists. The guard just above already learned that -- the phase used to
    # begin with a 50 mm descent after connecting and overran twice. The
    # reorientation is the same mistake somewhere else: it lifts to a 40 mm
    # standoff, sweeps joint 6 through the whole angle and comes back down,
    # all while an open task fills a buffer nobody is reading, and the tare
    # after it died with -200279 on the first rotated press of
    # DIGIT_hard_3mm_r1 (2026-09-08). Rotate first, connect second.
    if abs(a.scale_rotate) > 1e-6:
        # Turning the tool about its own axis is a WRIST reconfiguration --
        # joint 6 sweeps the full angle -- and the 15 deg step ceiling
        # refuses it, correctly, because it cannot tell a deliberate
        # reorientation from an IK branch flip. So it is its own move, at a
        # standoff far enough that a swinging tool body cannot reach the
        # gel, under a ceiling that has to be asked for by name.
        print(f"\n  reorienting {a.scale_rotate:+.0f} deg at "
              f"{a.rotate_height:.0f} mm standoff, joint ceiling "
              f"{a.rotate_joint_ceiling:.0f} deg")
        if _move_to_point(ip, p_surf + a.rotate_height * n, rpy_now, a,
                          a.approach_joint_step, vel=a.vel_free):
            return 2
        if _move_to_point(ip, p_surf + a.rotate_height * n, rpy0, a,
                          a.rotate_joint_ceiling, vel=a.vel_free):
            return 2
        got = [float(v) for v in q("GetActualTCPPose", 0)[1:][3:]]
        err = float(np.abs(cal.rpy_to_matrix(*got)
                           - cal.rpy_to_matrix(*rpy0)).max())
        print(f"  reached rpy {np.round(got, 2)}, orientation error {err:.2e}")
        if err > 0.02:
            print("  the tool did not reach the requested orientation.")
            return 1
    # already clear, and now at the working orientation
    if _move_to_point(ip, p_surf + a.retract * n, rpy0, a,
                      a.approach_joint_step, vel=a.vel_free):
        return 2

    cam = Camera.from_config(camera_config_for(a.sensor))
    cam.open()                      # before the DAQ task: it must not sit unread
    ft = FTInterface.from_config()
    ft.connect()
    reader = None
    rows = []
    try:
        tare = ft.tare(duration_s=2.0)
        res = ft.read_wrench_mean(duration_s=1.0, tared=True)
        print(f"\n  zero residual |F| {np.linalg.norm(res[:3]):.4f} N")
        if np.linalg.norm(res[:3]) > 0.15:
            print("  not clear of the gel.")
            return 1
        reader = ForceReader(ft, tare).start()

        print(f"\n  {'axis':>5} {'cmd':>7} {'reached':>8} {'force':>8} "
              f"{'height':>9} {'steps':>6} {'CoP x':>8} {'CoP y':>8}")
        if a.plane_only:
            # mm/px is a property of the sensor's own optics and does not move
            # when the unit is re-seated on the fixture, so it is measured once
            # per sensor, in the first probe's pass. The PLANE does move: it is
            # where the gel sits relative to the robot, and re-mounting changed
            # the surface height by 0.45 mm on the one measured. So the passes
            # after the first re-measure the plane and skip the image tracking.
            offsets = [offsets[0], 0.0, offsets[-1]]
            print(f"  plane only: {offsets} mm, no image tracking")
        for axis_name, axis_vec in (("x", R[:, 0]), ("y", R[:, 1])):
            for off in offsets:
                base = p_surf + off * axis_vec
                if _move_to_point(ip, base + a.zero_margin * n, rpy0, a,
                                  a.approach_joint_step, vel=a.vel_free):
                    return 2
                time.sleep(a.zero_recover_s)
                # descend until the target force, then one proportional
                # correction from the stiffness the descent just measured
                travelled, steps, f, prev = 0.0, 0, 0.0, None
                # The cap is the deepest rung of the ladder this calibration
                # has to describe: never press harder for a calibration than
                # for the measurement. `zero_stop_depth` was wrong here -- it
                # bounds how far the SURFACE FIT may disturb the gel, 0.3 mm,
                # and 1.0 N needs 0.44 mm on a gel of 2.25 N/mm.
                depth_cap = min(a.scale_max_depth, depth_backstop(reg, ent))
                fine = False
                # Jump most of the way, then crawl. The stiffness is known --
                # the zero of this same run measured it -- so the depth that
                # reaches the target force is force/k. Crawling 0.02 mm at a
                # time toward a depth arithmetic already knows spent about
                # fifteen moves per offset, and there are ten offsets. The jump
                # stops short of the target so a stiffer patch of gel cannot
                # overshoot the force; the fine steps finish it.
                if _stiff:
                    # `travelled` is measured from the STANDOFF, so the jump has
                    # to cross the standoff as well as the predicted depth.
                    # Sending it only the depth left the tip still in the air
                    # with `fine` already latched, and the 0.02 mm crawl then
                    # covered the remaining air too: 28-32 moves per offset
                    # against the 15-20 it was meant to replace.
                    guess = a.zero_margin + min(
                        a.scale_jump_frac
                        * (force_target / max(_k, 0.05)) ** (1.0 / _exp),
                        depth_cap - 0.05)
                    if guess > a.zero_margin + a.zero_coarse_step:
                        if _move_to_point(ip, base + (a.zero_margin - guess) * n,
                                          rpy0, a, a.approach_joint_step,
                                          vel=a.vel_contact):
                            return 2
                        travelled, steps, fine = guess, 1, True
                        time.sleep(a.settle)
                        w, err = reader.read_fresh()
                        if err:
                            print(f"  F/T failed: {err}")
                            return 1
                        f = -float(w[2])
                while travelled < a.zero_margin + depth_cap:
                    # coarse across the standoff, fine once the gel answers:
                    # 0.02 mm steps through 0.5 mm of air is 25 wasted moves
                    step = a.scale_step if fine else a.zero_coarse_step
                    if _move_to_point(ip, base + (a.zero_margin - travelled
                                                  - step) * n, rpy0, a,
                                      a.max_joint_step, vel=a.vel_contact):
                        return 2
                    travelled += step
                    steps += 1
                    time.sleep(a.settle)
                    w, err = reader.read_fresh()
                    if err:
                        print(f"  F/T failed: {err}")
                        return 1
                    prev, f = f, -float(w[2])
                    if not fine and f >= a.zero_notice_force:
                        fine = True
                    if f >= force_target:
                        break
                else:
                    print(f"  {axis_name:>5} {off:>7.2f}   only {f:.3f} N at the "
                          f"{depth_cap:.2f} mm cap, seeking "
                          f"{force_target:.2f} N")
                    continue
                k = max((f - prev) / a.scale_step, 0.2)
                dz = float(np.clip((f - force_target) / k, -0.1, 0.1))
                if abs(dz) > 0.002:
                    if _move_to_point(ip, base + (a.zero_margin - travelled + dz) * n,
                                      rpy0, a, a.max_joint_step, vel=a.vel_contact):
                        return 2
                    travelled -= dz
                    time.sleep(a.settle)
                    w, err = reader.read_fresh()
                    if err:
                        print(f"  F/T failed: {err}")
                        return 1
                    f = -float(w[2])
                h_at = height()
                # The achieved lateral position, not the commanded one. Two
                # independent checks -- the pressure centre and the imprint
                # radius against the tip's known 2.00 mm -- both came out 0.85
                # of what the commanded offsets implied, and the one quantity
                # that could settle it was the one not written down.
                p_now = np.array(q("GetActualTCPPose", 0)[1:][:3], dtype=float)
                rel = p_now - p_surf
                ach_x = float(rel @ R[:, 0])
                ach_y = float(rel @ R[:, 1])
                frame, t_img = cam.grab_after(time.time())
                name = f"{probe['id']}_{axis_name}{off:+.2f}{tag}.png"
                cv2.imwrite(str(out / name), frame,
                            [cv2.IMWRITE_PNG_COMPRESSION, 1])
                fx, fy, fz = float(w[0]), float(w[1]), float(w[2])
                tx, ty, tz = float(w[3]), float(w[4]), float(w[5])
                sc = 1000.0 if abs(tx) < 0.05 else 1.0     # N.m -> N.mm
                txm, tym = tx * sc, ty * sc
                # contact sits `surf` above the wrench origin, and shear on
                # that lever is the same size as the moment being read
                cop_x = (surf * fx - tym) / fz
                cop_y = (txm + surf * fy) / fz
                rows.append({"axis": axis_name, "offset_mm": off, "force_N": f,
                             "achieved_x_mm": ach_x, "achieved_y_mm": ach_y,
                             "height_mm": h_at, "steps": steps, "file": name,
                             "Fx": fx, "Fy": fy, "Fz": fz,
                             "Tx_Nmm": txm, "Ty_Nmm": tym, "Tz_Nmm": tz * sc,
                             "cop_x_mm": cop_x, "cop_y_mm": cop_y,
                             "rotate_deg": a.scale_rotate})
                ach = ach_x if axis_name == "x" else ach_y
                print(f"  {axis_name:>5} {off:>7.2f} {ach:>8.3f} {f:>8.3f} "
                      f"{h_at:>9.4f} {steps:>6} {cop_x:>8.3f} {cop_y:>8.3f}")

        _write_rows(out / "scale.csv", rows)
        result = {"probe": probe["id"], "force_N": force_target,
                  "offsets_mm": offsets, "rotate_deg": a.scale_rotate,
                  "surface_mm": surf, "at": datetime.now().isoformat()}

        # --- the gel plane, from the heights the target force was reached at --
        print()
        for axis_name in ("x", "y"):
            r = [x for x in rows if x["axis"] == axis_name]
            if len(r) < 3:
                continue
            o = np.array([x[f"achieved_{axis_name}_mm"] for x in r])
            h = np.array([x["height_mm"] for x in r])
            sl = float(np.polyfit(o, h, 1)[0])
            result[f"plane_slope_{axis_name}"] = sl
            print(f"  gel surface along sensor {axis_name}: {sl:+.5f} mm/mm "
                  f"= {np.degrees(np.arctan(abs(sl))):5.2f} deg tilt"
                  f"   ({abs(sl) * 4:.3f} mm across the 4 mm tip)")

        # --- the pressure centre, against offsets that are known -------------
        print()
        for axis_name in ("x", "y"):
            r = [x for x in rows if x["axis"] == axis_name]
            if len(r) < 3:
                continue
            o = np.array([x[f"achieved_{axis_name}_mm"] for x in r])
            for comp in ("cop_x_mm", "cop_y_mm"):
                v = np.array([x[comp] for x in r])
                sl, ic = np.polyfit(o, v, 1)
                result[f"cop_slope_{axis_name}_{comp[4]}"] = float(sl)
                result[f"cop_intercept_{axis_name}_{comp[4]}"] = float(ic)
                print(f"  sensor {axis_name} -> {comp[:5]}{comp[4]}: "
                      f"slope {sl:+.3f} mm/mm, intercept {ic:+.3f} mm")
        print("  a correct sign convention gives slope +1 on the matching axis,")
        print("  0 on the other; the INTERCEPT is the standing tilt offset.")

        # --- millimetres per pixel, by cross-correlation ---------------------
        print()
        if a.plane_only:
            result["plane_only"] = True
            st_run.setdefault("scale", {})[f"plane{int(a.scale_rotate)}"] = result
            save_state(run, st_run)
            with open(out / "plane.yaml", "w") as fh:
                yaml.safe_dump(result, fh, sort_keys=False)
            if _move_to_point(ip, p_surf + a.retract * n, rpy0, a,
                              a.approach_joint_step, vel=a.vel_free):
                return 2
            return 0
        for axis_name in ("x", "y"):
            r = sorted([x for x in rows if x["axis"] == axis_name],
                       key=lambda z: z["offset_mm"])
            if len(r) < 3:
                continue
            imgs = [_diff_f32(cv2.imread(str(out / x["file"])), ref_img, _shadow)
                    for x in r]
            mid = len(r) // 2
            m = (imgs[mid] >= 6).astype(np.uint8)
            m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
            nb, lab, stt, cen = cv2.connectedComponentsWithStats(m, 8)
            if nb < 2:
                print(f"  {axis_name}: no contact region to track")
                continue
            kk = 1 + int(np.argmax(stt[1:, cv2.CC_STAT_AREA]))
            cx, cy = int(cen[kk][0]), int(cen[kk][1])
            half_i, srch_i = _window_for(imgs[mid].shape, cx, cy,
                                         a.scale_template, a.scale_search)
            if half_i == 0:
                print(f"  {axis_name}: the contact sits at ({cx}, {cy}) in a "
                      f"{imgs[mid].shape[1]}x{imgs[mid].shape[0]} frame; no "
                      f"correlation window fits. Not tracked.")
                continue
            if (half_i, srch_i) != (a.scale_template, a.scale_search):
                print(f"  {axis_name}: contact at ({cx}, {cy}) — window "
                      f"trimmed to template {half_i}, search {srch_i} px "
                      f"(asked {a.scale_template}/{a.scale_search})")
            p = _track_series(imgs, cx, cy, half_i, srch_i, log=print)
            o = np.array([x[f"achieved_{axis_name}_mm"]
                          - r[mid][f"achieved_{axis_name}_mm"] for x in r])
            for ci, comp in ((0, "x"), (1, "y")):
                v = p[:, ci]
                g = np.isfinite(v)
                if int(g.sum()) < 3:
                    print(f"  sensor {axis_name} -> image {comp}: only "
                          f"{int(g.sum())} frames tracked, not fitted")
                    continue
                sl, ic = np.polyfit(o[g], v[g], 1)
                resid = v[g] - (sl * o[g] + ic)
                rms = float(np.sqrt((resid ** 2).mean()))
                result[f"px_per_mm_{axis_name}{comp}"] = float(sl)
                result[f"rms_px_{axis_name}{comp}"] = rms
                result[f"n_fit_{axis_name}{comp}"] = int(g.sum())
                print(f"  sensor {axis_name} -> image {comp}: {sl:+9.2f} px/mm "
                      f"  rms {rms:5.2f} px" +
                      ("" if int(g.sum()) == len(o) else
                       f"  ({int(g.sum())}/{len(o)} frames)"))
        _scale_jacobian(result, a.scale_theta_tol, a.scale_max_rms_px)
        st_run.setdefault("scale", {})[f"rot{int(a.scale_rotate)}"] = result
        save_state(run, st_run)
        with open(out / "scale.yaml", "w") as fh:
            yaml.safe_dump(result, fh, sort_keys=False)
        if _move_to_point(ip, p_surf + a.retract * n, rpy0, a,
                          a.approach_joint_step, vel=a.vel_free):
            return 2
        return 0
    finally:
        if reader is not None:
            reader.stop()
        ft.disconnect()
        cam.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--new", action="store_true", help="open a new run")
    ap.add_argument("--dataset", default=DATASET,
                    help="dataset folder under data/ that runs are filed in")
    ap.add_argument("--note", default="", help="what this run is for")
    ap.add_argument("--phase", choices=("tare", "zerocheck", "reference",
                                        "sample", "series", "shear",
                                        "force-series", "force-shear",
                                        "collect", "characterize", "contactmap",
                                        "zero", "shape", "scale", "summary",
                                        "calibgrid"))
    ap.add_argument("--grid-n", default="7,7",
                    help="calibgrid: how many positions across x and y")
    ap.add_argument("--grid-x", type=float, default=9.0,
                    help="calibgrid: half-span along the sensor x, mm")
    ap.add_argument("--grid-y", type=float, default=7.5,
                    help="calibgrid: half-span along the sensor y, mm")
    ap.add_argument("--grid-span-x", type=float, default=4.0,
                    help="half-width of the ROBOT-AXIS grid, used only when "
                         "autoframe is off; --grid-x is a travel backstop, not "
                         "a span, and is far too large to walk a grid to")
    ap.add_argument("--grid-span-y", type=float, default=2.5)
    ap.add_argument("--grid-autoframe", action="store_true", default=True,
                    help="press three points first and lay the grid out square "
                         "to the IMAGE, not to the robot axes (default on)")
    ap.add_argument("--no-grid-autoframe", dest="grid_autoframe",
                    action="store_false")
    ap.add_argument("--grid-probe-force", type=float, default=0.0,
                    help="force each autoframe press is trimmed to, so all five "
                         "contacts come out the same size; 0 means half the "
                         "phase's force stop")
    ap.add_argument("--grid-probe-mm", type=float, default=3.5,
                    help="offset of the two autoframe probe presses")
    ap.add_argument("--grid-res-max-px", type=float, default=150.0,
                    help="refuse to place a lattice when the autoframe fit "
                         "scatters by more than this; below it the lattice is "
                         "shrunk in proportion instead of refused")
    ap.add_argument("--grid-safety", type=float, default=0.8,
                    help="shrink the image-space lattice by this factor, so a "
                         "scale the autoframe fit over-reads still lands every "
                         "imprint inside the frame")
    ap.add_argument("--grid-margin-px", type=float, default=120.0,
                    help="clearance to keep between an imprint and the frame edge")
    ap.add_argument("--grid-depths", default="0.1,0.2,0.3",
                    help="calibgrid: indentation depths at each position")
    ap.add_argument("--probe", default=None,
                    help="probe id from config/probes.yaml. Required by the "
                         "zero and shape phases: the contact law used to "
                         "extrapolate the surface differs between a ball and "
                         "a flat tip, and the dataset has to record which tip "
                         "made it")
    ap.add_argument("--sensor", default=None, help="sensor id from the registry")
    ap.add_argument("--char-step", type=float, default=0.1,
                    help=("descent step while characterising. Measured on this "
                          "robot, a step lands within about 0.012 mm of where it "
                          "was told, which is a quarter of a 0.05 mm step but "
                          "only a tenth of a 0.1 mm one. The depth is read back "
                          "either way, so this only sets how finely the curve is "
                          "sampled -- and 0.1 mm still gives about 0.25 N spacing "
                          "at the top of a 5 N range, finer than the force ladder"))
    ap.add_argument("--exp-window", type=int, default=4,
                    help="steps the local force-depth exponent is fitted over")
    ap.add_argument("--fit-floor", type=float, default=0.10,
                    help="force below which a point is noise and is left out of "
                         "the gel-model fit; five times the 0.02 N scatter")
    ap.add_argument("--exp-min-force", type=float, default=0.5,
                    help="every point in the exponent window must exceed this, "
                         "so the log-log slope is not fitted through noise")
    ap.add_argument("--exp-min-depth-frac", type=float, default=0.25,
                    help="fraction of elastomer thickness below which substrate "
                         "stiffening is physically impossible and the alarm stays "
                         "disarmed")
    ap.add_argument("--exp-hits", type=int, default=2,
                    help="consecutive windows over the threshold before stopping")
    ap.add_argument("--char-floor-n", type=float, default=0.0,
                    help="characterize: press to at least this force whatever "
                         "else would stop the ramp -- the depth backstop, "
                         "image saturation and the exponent alarm are all "
                         "overridden until it is reached, so every unit is "
                         "measured against a common yardstick")
    ap.add_argument("--char-floor-depth-mult", type=float, default=2.0,
                    help="characterize: absolute depth limit while chasing "
                         "--char-floor-n, as a multiple of gel thickness. The one "
                         "gel ever destroyed gave out at 3.1x its thickness")
    ap.add_argument("--past-saturation-n", type=float, default=0.0,
                    help="characterize: after the image stops answering, keep "
                         "pressing until the force is this much past the "
                         "ceiling. 0 stops at the ceiling. The depth and force "
                         "backstops still bind.")
    ap.add_argument("--exp-alarm-stops", action="store_true",
                    help="characterize: END the ramp when the local exponent "
                         "stays above --exp-alarm. Off since 2026-09-07: the "
                         "depth backstop is the safety limit, and the alarm "
                         "was cutting 1 mm units short of the 2 N range. The "
                         "crossing depth is recorded either way")
    ap.add_argument("--exp-alarm", type=float, default=2.0,
                    help="local exponent above which the rigid backing is judged "
                         "to be carrying load; Hertz alone gives 1.5")
    ap.add_argument("--force-min", type=float, default=0.1)
    ap.add_argument("--force-step", type=float, default=0.1,
                    help="spacing of the normal-force ladder")
    ap.add_argument("--max-travel-normal", type=float, default=None,
                    help="depth limit override; without it, --sensor takes the "
                         "registry's per-sensor limit and other phases use 1.0 mm")
    ap.add_argument("--max-travel-shear", type=float, default=10.0,
                    help="lateral travel allowed per shear axis. Raised from "
                         "1.0 on 2026-09-04 so the friction cap, not the "
                         "travel, is what ends a shear ramp")
    ap.add_argument("--max-shear-force", type=float, default=1.0,
                    help="overwritten in collect by --shear-frac of the "
                         "saturation force; the default only serves the "
                         "stand-alone shear phases")
    ap.add_argument("--no-contact-mm", type=float, default=2.0,
                    help="press this far past the surface with no force and the "
                         "probe is judged not to be on the gel")
    ap.add_argument("--range-normal", type=float, default=2.0,
                    help="fixed normal-force range every sensor is collected "
                         "over, so their force-estimation errors are comparable. "
                         "Set to 2 N by the operator 2026-09-07")
    ap.add_argument("--range-shear", type=float, default=0.5,
                    help="fixed shear range: a quarter of the normal range, "
                         "set by the operator 2026-09-07. Friction is not the "
                         "binding constraint at this level -- mu >= 0.59 on a "
                         "1.2 N hold carries 0.71 N")
    ap.add_argument("--allow-short-range", action="store_true",
                    help="collect a unit that cannot reach the fixed normal "
                         "range. Off by default since 2026-09-07: a dataset "
                         "that spans less than the common range is not "
                         "comparable with the others, so it is refused rather "
                         "than collected and noted")
    ap.add_argument("--scale-max-rms-px", type=float, default=5.0,
                    help="scale: worst per-row fit residual a trusted scale may "
                         "have. Set 2026-09-08 from the separation in the data: "
                         "every run under 5 px implies a 19-26 mm field of view, "
                         "every run over 17 px is scattered")
    ap.add_argument("--ceiling-frac", type=float, default=0.9,
                    help="fraction of the saturation force the normal ramp uses")
    ap.add_argument("--shear-frac", type=float, default=0.2,
                    help="fraction of the saturation force the shear ramp targets")
    ap.add_argument("--shear-fractions", default="0.2,0.4,0.6,0.8,1.0",
                    help="shear rungs as fractions of what friction can hold, so "
                         "every sensor gets the same number of points")
    ap.add_argument("--shear-abs-min", type=float, default=0.04,
                    help="rungs below this are dropped: two sigma of the 0.02 N "
                         "noise floor, under which a shear reading is not a "
                         "measurement")
    ap.add_argument("--contact-floor", type=float, default=0.06,
                    help="force below which the probe counts as not touching; "
                         "about three times the 0.02 N scatter")
    ap.add_argument("--force-tol", type=float, default=0.03,
                    help=("how close to a target counts as reached. Must stay "
                          "well under the ladder spacing, or a sample can sit "
                          "nearer its neighbour's target than its own. At 0.1 N "
                          "spacing this is under a third of the gap, and still "
                          "about 1.5 times the 0.02 N noise floor"))
    ap.add_argument("--seek-iters", type=int, default=12)
    ap.add_argument("--seek-max-step", type=float, default=0.25,
                    help="hard distance cap on one seek step")
    ap.add_argument("--seek-first-step", type=float, default=0.05,
                    help="size of the first move of a seek, before any stiffness "
                         "has been measured")
    ap.add_argument("--seek-max-dforce", type=float, default=1.0,
                    help="most force one seek step may add, using the stiffness "
                         "measured from the previous step; this is what protects "
                         "an unknown or stiffer-than-modelled elastomer")
    ap.add_argument("--hertz-a", type=float, default=None)
    ap.add_argument("--shear-min", type=float, default=0.1)
    ap.add_argument("--normal-hold", type=float, default=1.74,
                    help="normal load to hold while shearing")
    ap.add_argument("--shear-k", type=float, default=1.0,
                    help="first guess at shear stiffness, N/mm; corrected as it goes")
    ap.add_argument("--mu-floor", type=float, default=0.59,
                    help="lowest friction coefficient the rig has demonstrated")
    ap.add_argument("--depth", type=float, default=0.5,
                    help="indentation depth to shear at")
    ap.add_argument("--surface", type=float, default=None,
                    help="gel surface height; taken from the last depth series "
                         "if omitted")
    ap.add_argument("--shear-step", type=float, default=0.05)
    ap.add_argument("--shear-steps", type=int, default=6)
    ap.add_argument("--order", default="+X,-X,-Y,+Y")
    ap.add_argument("--max-shear", type=float, default=3.0,
                    help="lateral force limit, to protect the printed probe")
    ap.add_argument("--travel-margin", type=float, default=0.03,
                    help="stop this far short of a travel limit so servo "
                         "tracking error cannot carry the tip past it (mm)")
    ap.add_argument("--stop-on-slip", dest="stop_on_slip", action="store_true",
                    default=True)
    ap.add_argument("--no-stop-on-slip", dest="stop_on_slip", action="store_false")
    ap.add_argument("--slip-after", type=int, default=4,
                    help="steps used to establish the initial slope")
    ap.add_argument("--slip-window", type=int, default=4,
                    help="steps the local slope is measured over")
    ap.add_argument("--slip-ratio", type=float, default=0.45,
                    help="fraction of the initial slope below which the local "
                         "slope counts as slipping")
    ap.add_argument("--expect-n", type=float, default=0.62,
                    help="normal force expected at --depth; a large miss means "
                         "the surface moved")
    ap.add_argument("--depth-step", type=float, default=0.1)
    ap.add_argument("--max-depth", type=float, default=0.5)
    ap.add_argument("--retract", type=float, default=2.0,
                    help="back off this far before starting: it clears the gel "
                         "so the zero can be retaken, and captures the shallow "
                         "end of the curve on the way back down")
    ap.add_argument("--settle", type=float, default=0.15,
                    help="wait after a step before reading. NOTE this is not "
                         "there to flush the buffer -- read_fresh() averages "
                         "only chunks that arrive after it is called, so the "
                         "move's own data is already excluded. It is there to "
                         "let the force physically settle. Measured 2026-09-05 "
                         "on 9DTact_hard_3mm_r1 by sampling the force 0.10-1.20 s "
                         "after each of ten 0.02 mm steps: the mean departure "
                         "from the 1.20 s reading was 0.008 N at 0.10 s and "
                         "0.003 N at 0.50 s, both inside the 0.02 N noise floor, "
                         "and individual steps scattered in sign rather than "
                         "decaying. 0.5 s was two to three times what the gel "
                         "needs")
    # Two speeds, measured 2026-09-04 in free air with the global speed left at
    # 5 %: a 2 mm move took 8.0 s at vel 5, 2.7 s at 15 and 1.4 s at 30, so the
    # per-move vel is what sets the pace. Anything that ends on or in the gel
    # uses the contact speed -- at 30 a 0.05 mm step read back 0.111 mm before
    # the servo settled, which is a probe step's worth of error.
    ap.add_argument("--vel-contact", type=float, default=40.0,
                    help="speed %% for probe steps and any move that ends on "
                         "the gel. Raised from 15 on 2026-09-05: eight 0.05 mm "
                         "steps at 15/25/40/60 %% with the settle actually used "
                         "landed to sigma 0.0161/0.0091/0.0033/0.0054 mm, so "
                         "accuracy does not fall off with speed and was best at "
                         "40. The old limit came from reading a step BEFORE it "
                         "had settled")
    ap.add_argument("--vel-free", type=float, default=60.0,
                    help="speed %% for rises, retracts and other moves clear of the gel")
    ap.add_argument("--vel", type=float, default=None,
                    help="override for --vel-contact (kept for old command lines)")
    ap.add_argument("--ovl", type=float, default=10.0)
    ap.add_argument("--frames", type=int, default=None,
                    help="collect: frame budget for this run; default from the "
                         "registry's capture_policy")
    ap.add_argument("--normal-fraction", type=float, default=None,
                    help="collect: share of the budget spent on normal loading "
                         "cycles, the rest on shear cycles")
    ap.add_argument("--ramp-step", type=float, default=None,
                    help="collect: force increment between ramp steps, N")
    ap.add_argument("--ramp-settle", type=float, default=None,
                    help="collect: pause after each ramp step, s")
    ap.add_argument("--anchor-every", type=float, default=None,
                    help="collect: force spacing of the settled anchor samples "
                         "that keep the per-rung table and the Hertz fit alive")
    ap.add_argument("--ramp-mode", choices=["continuous", "stepped"], default="continuous",
                    help="collect: 'continuous' glides slowly through the range "
                         "with the force read between short segments (default "
                         "since 2026-09-07, 12th unit on); 'stepped' is the "
                         "0.1 N / 0.15 s rung ramp the first eleven units used")
    ap.add_argument("--ramp-vel", type=float, default=0.5,
                    help="collect: MoveL speed percentage for the continuous "
                         "glide. Set from a timed free-air move, see "
                         "capture_policy.ramp_vel_basis")
    ap.add_argument("--release-mm-s", type=float, default=0.60,
                    help="collect: speed of the shear return to centre, mm/s. "
                         "The release retraces forces the outward glide already "
                         "covered, so it is paced for time, not for force "
                         "resolution")
    ap.add_argument("--ramp-segment-mm", type=float, default=0.10,
                    help="collect: glide length between force readings")
    ap.add_argument("--max-cycles", type=int, default=400,
                    help="collect: hard cap on loading cycles per block")
    ap.add_argument("--force-depth-cap", type=float, default=None,
                    help="characterize: operator override of the depth cap, "
                         "upward included; pair with --no-registry")
    ap.add_argument("--no-registry", action="store_true",
                    help="characterize: write the result to the run folder only")
    ap.add_argument("--char-tag", default=None,
                    help="characterize: output folder becomes characterize_<tag>")
    ap.add_argument("--sat-frac", type=float, default=0.15,
                    help="characterize: stop when the image change per newton "
                         "falls under this fraction of its peak")
    ap.add_argument("--sat-window", type=int, default=3,
                    help="characterize: steps the image-change slope is fitted over")
    ap.add_argument("--sat-min-df", type=float, default=0.08,
                    help="characterize: force span a slope window must cover, N")
    ap.add_argument("--diff-rel", type=float, default=0.04,
                    help="deformed-pixel threshold as a fraction of the reference "
                         "centre brightness")
    ap.add_argument("--diff-min", type=int, default=3,
                    help="floor on that threshold, grey levels")
    ap.add_argument("--sat-hits", type=int, default=2,
                    help="characterize: consecutive steps under the threshold")
    ap.add_argument("--sat-min-force", type=float, default=0.3,
                    help="characterize: do not judge saturation below this force")
    ap.add_argument("--qc-diff-level", type=int, default=6,
                    help="grey levels a pixel must differ from the reference by "
                         "to count as deformed")
    ap.add_argument("--map-depth", type=float, default=0.5,
                    help="contactmap: fixed indentation, mm")
    ap.add_argument("--map-force", type=float, default=0.5,
                    help="contactmap: fixed normal force, N")
    ap.add_argument("--image-floor", type=float, default=1.7,
                    help="mean |frame - reference| below which the image is "
                         "considered unchanged (noise floor ~1.45 levels)")
    ap.add_argument("--map-settle", type=float, default=1.0,
                    help="contactmap: dwell before the image is taken, s")
    ap.add_argument("--map-recover", type=float, default=3.0,
                    help="contactmap: pause at the surface between the two probes, s")
    ap.add_argument("--slip-off-frac", type=float, default=0.5,
                    help="fraction of the held normal load below which the "
                         "shear sweep is judged to have slid off the contact")
    ap.add_argument("--max-radial-drift", type=float, default=0.30,
                    help="abort if the contact wanders this far off the sensor "
                         "axis during collect")
    ap.add_argument("--bin-normal", type=float, default=0.05,
                    help="width of the normal-force bins the budget is spread over")
    ap.add_argument("--bin-shear", type=float, default=0.04,
                    help="width of the shear-force bins, per axis")
    ap.add_argument("--min-sep", type=float, default=0.02,
                    help="a frame whose force is closer than this to one already "
                         "kept in its bin is dropped; the F/T's own noise")
    ap.add_argument("--cycle-min-gain", type=int, default=8,
                    help="new frames a cycle must add before the quota and the "
                         "separation are relaxed to keep the budget fillable")
    ap.add_argument("--cycle-min-frac", type=float, default=0.2,
                    help="a loading cycle must reach this fraction of the force "
                         "ceiling to count; below it, contact is re-found")
    ap.add_argument("--max-dead-cycles", type=int, default=3,
                    help="consecutive cycles that fail to load before aborting")
    ap.add_argument("--cycle-dwell", type=float, default=1.0,
                    help="collect: pause at the surface between loading cycles, "
                         "s, recorded")
    ap.add_argument("--approach-clear", type=float, default=0.3,
                    help="collect: switch from free to contact speed this far "
                         "above the gel surface, mm")
    ap.add_argument("--max-joint-step", type=float, default=1.0,
                    help="joint-change ceiling for probe steps")
    ap.add_argument("--approach-joint-step", type=float, default=15.0,
                    help="ceiling for positioning moves, which travel further; "
                        "still far below the 200-plus degrees a reconfiguration takes")
    ap.add_argument("--label", default=None, help="tag for this sample, e.g. '2N'")
    ap.add_argument("--ip", default=None)
    ap.add_argument("--seconds", type=float, default=1.0)
    ap.add_argument("--min-force", type=float, default=0.3)
    ap.add_argument("--max-force", type=float, default=30.0,
                    help="absolute safety ceiling for characterize. Not a "
                         "policy target: the collection ceiling comes from "
                         "where the image saturates, which has to be passed to "
                         "be found. 5.0 until 2026-09-04, when it turned out "
                         "always to bind before saturation ever could")
    ap.add_argument("--zero-step", type=float, default=None,
                    help="approach step while finding the surface; defaults to "
                         "probes.yaml zero_policy.step_mm (0.02 mm). At the "
                         "0.05 mm used before, the image-onset zero was "
                         "quantised by the step itself")
    ap.add_argument("--zero-repeats", type=int, default=None,
                    help="independent approaches averaged into the zero; "
                         "defaults to probes.yaml zero_policy.repeats. Two, "
                         "not three: the scatter is 0.0062 mm and came out the "
                         "same on two independent runs, so the third approach "
                         "buys 0.0036 -> 0.0044 mm on the mean, under half a "
                         "percent of a ladder step, for 55 s per probe")
    ap.add_argument("--zero-margin", type=float, default=1.0,
                    help="height above the SEARCHED surface each approach and "
                         "each ladder rung starts from. The searched contact is "
                         "itself below the surface by however deep the tip must "
                         "go to reach the 0.11 N search threshold, and for a "
                         "SPHERE that depth is (0.11/a)^(2/3) -- 0.06 mm for a "
                         "flat 4 mm face but 0.47 mm on the softest gel measured "
                         "(9DTact_soft_3mm_r1, a = 0.339). 0.5 mm was set to that "
                         "estimate and was not enough: 2026-09-06 the search on "
                         "that sensor reported 26.757 mm when the surface was "
                         "27.4, an overshoot of 0.67 mm once the two-hit "
                         "confirmation and the step size are added, so the "
                         "approach began 0.085 N INTO the gel and the run "
                         "aborted. 1.0 mm clears that measured 0.67 mm with "
                         "0.33 mm to spare. 1.5 mm was tried first and is NOT "
                         "better: on the same sensor it left the per-approach "
                         "sigma at 0.034-0.043 mm against 0.027 mm at 0.5 mm, "
                         "so the standoff is not what was limiting the ball4 "
                         "zero -- a longer approach only exposes it to more "
                         "F/T drift.")
    ap.add_argument("--zero-read-s", type=float, default=0.1,
                    help="how long each approach reading averages, in seconds. "
                         "0.1 s carries 0.02 N of scatter, which is fine when a "
                         "4 mm face raises 1 N over the fitted range. The "
                         "paired-cylinder probes have a tenth of that area and "
                         "may not be pressed past 0.3 mm, so their whole fit "
                         "range is 0.09-0.19 N and 0.02 N of noise leaves d0 "
                         "scattered over 0.46 mm (measured 2026-09-07 on "
                         "9DTact_soft_3mm_r1/pair100: R2 0.68-0.88). Noise "
                         "falls as sqrt(time), so buy the signal with seconds "
                         "instead of with depth the probe cannot survive.")
    ap.add_argument("--zero-recover-s", type=float, default=0.0,
                    help="wait off the gel before an approach, so the previous "
                         "indentation has recovered and the approaches are "
                         "independent samples rather than a creep sequence. "
                         "MEASURED 2026-09-06 on 9DTact_medium_3mm_r2, having "
                         "been a guess of 3.0 s costing 27 s per sensor: press "
                         "to the deepest rung, retract, wait T, and read the "
                         "force back at that same depth. A gel still depressed "
                         "reads LOW; over T = 0.5, 1, 2, 3 s the ratios were "
                         "1.076, 1.097, 1.120, 1.082 -- all above one, no trend, "
                         "and the repeat scatter at a single T (1.130 vs 1.021 "
                         "at 0.5 s) larger than the spread across T. Recovery is "
                         "complete by 0.5 s; the other 2.5 s bought nothing. "
                         "Set to 0.0 on request. Note this does NOT mean the "
                         "gel gets no rest: the retract and the descent are "
                         "commanded moves of about 1.2 s each, so roughly 1.2 s "
                         "still elapses between lift-off and the next contact. "
                         "That is a little under the smallest interval actually "
                         "tested (the T above each carried a descent too, so "
                         "T = 0.5 was ~1.7 s of real rest), and the response was "
                         "flat across every interval measured. If creep were "
                         "accumulating it would show as the fitted d0 walking "
                         "one way across approaches within a run -- the same "
                         "signature seen on 2026-09-05 when the stop force was "
                         "1.2 N -- so that is the thing to watch.")
    ap.add_argument("--zero-offset-s", type=float, default=1.0,
                    help="how long to average the per-approach force offset. "
                         "The whole fitted zero is referenced to it, and a "
                         "0.1 s read carries 0.02 N of scatter, which is "
                         "0.010 mm of zero on a 2 N/mm gel")
    ap.add_argument("--zero-min-r2", type=float, default=0.90,
                    help="an approach whose contact-law fit is worse than this "
                         "is dropped before the surface is averaged")
    ap.add_argument("--zero-max-sigma", type=float, default=0.10,
                    help="an approach whose own sigma(d0) exceeds this (mm) is "
                         "dropped before the surface is averaged. 0.10 mm is "
                         "five times the 0.020 mm gate that asks for another "
                         "approach: this one only rejects fits that are not "
                         "measurements at all.")
    ap.add_argument("--zero-sigma-gate", type=float, default=0.040,
                    help="with a single approach, add another if the fit's own "
                         "sigma(d0) exceeds this (mm). It was 0.020, 20%% of the "
                         "ladder's first rung -- but a sphere cannot "
                         "deliver that: over 33 measured ball4 fits the "
                         "median sigma is 0.0267 mm, so the gate fired on "
                         "76%% of them and, being unreachable, spent every "
                         "retry it was allowed without ever passing. 0.040 "
                         "fires on the worst 24%%, which is what a gate is "
                         "for. The zero a sphere gives is ~0.027 mm; "
                         "wanting better does not make it so.")
    ap.add_argument("--zero-sem-gate", type=float, default=0.020,
                    help="standard error of the MEAN fitted surface that ends "
                         "the approaches; another is added until it is met, up "
                         "to --zero-max-repeats. 20%% of a ladder step, the "
                         "same bar as --zero-sigma-gate. It was 0.006 mm, and "
                         "on ball4 that is UNREACHABLE: a single fit's own "
                         "sigma is 0.02-0.04 mm there, so sigma/sqrt(n) needs "
                         "about 25 approaches. Every soft ball4 sensor "
                         "therefore ran to the cap and spent 120 s buying "
                         "nothing -- the same failure as the old spread gate, "
                         "in a new form. Gate on what the ladder needs.")
    ap.add_argument("--zero-max-repeats", type=int, default=2,
                    help="most approaches, however bad the spread stays. Cut "
                         "from 4 on 2026-09-06: each one costs 40 s and the "
                         "fourth never moved a surface more than the third.")
    ap.add_argument("--zero-lift-check", type=float, default=0.30,
                    help="how far to lift and re-read before each approach. "
                         "A reading that does not change over this height was "
                         "drift and is removed; one that does was contact, and "
                         "the standoff is too small")
    ap.add_argument("--zero-start-tol", type=float, default=0.05,
                    help="how much the reading may change over "
                         "--zero-lift-check before it is called contact rather "
                         "than drift. Catches a standoff too small to clear "
                         "the gel, which the post-tare residual cannot")
    ap.add_argument("--zero-coarse-step", type=float, default=0.40,
                    help="approach step before the gel answers. The 0.5 mm "
                         "standoff is empty air and does not need measuring "
                         "at 0.02 mm")
    ap.add_argument("--zero-notice-force", type=float, default=0.04,
                    help="force that switches the approach to the fine step; "
                         "twice the 0.02 N noise floor")
    ap.add_argument("--zero-stop-depth", type=float, default=0.30,
                    help="depth below the searched contact that ends an "
                         "approach. This, not the force, is the real limit: it "
                         "bounds how much the measurement disturbs the surface "
                         "it is measuring, and bounds it the same way for a "
                         "stiff flat tip and a soft sphere. Half the shallowest "
                         "useful ladder span, and well under every rung of it")
    ap.add_argument("--zero-stop-force", type=float, default=1.2,
                    help="SAFETY cap only since 2026-09-05; --zero-stop-depth "
                         "is what normally ends an approach. It binds if a gel "
                         "is far stiffer than expected")
    ap.add_argument("--zero-max-travel", type=float, default=None,
                    help="total travel from the approach start before an "
                         "approach is called a miss. Measured from the START "
                         "point, which sits --zero-margin above the searched "
                         "surface, NOT from the surface. Left unset it is "
                         "derived as margin + stop-depth + 0.5 mm of slack, "
                         "because a fixed 1.5 mm silently contradicted the stop "
                         "condition (margin + stop-depth) the moment the margin "
                         "was raised to 1.5 on 2026-09-06: every approach ran "
                         "out of budget 0.3 mm before it was allowed to stop "
                         "and the run aborted with no contact. Deriving it "
                         "keeps the two in step.")
    ap.add_argument("--depths", default="0.1,0.2,0.3,0.4,0.5,0.6",
                    help="the shape/resolution ladder, mm below the FITTED "
                         "surface")
    ap.add_argument("--shape-repeats", type=int, default=1,
                    help="passes over the ladder. Cut from three on "
                         "2026-09-05: the three passes agreed to 2-4%% on "
                         "contact area everywhere they were compared, so the "
                         "second and third were re-photographing a settled "
                         "quantity for 75 s a sensor. Raise it again on a few "
                         "units if a repeatability figure is wanted")
    ap.add_argument("--scale-offsets", default="-1.5,-0.75,0,0.75,1.5",
                    help="lateral offsets, mm along the sensor axes, that the "
                         "millimetre-per-pixel scale is measured over. The "
                         "robot is the ruler: nothing in the frame has a known "
                         "length")
    ap.add_argument("--scale-force", type=float, default=2.0,
                    help="force sought at every offset, capped per gel by "
                         "--scale-force-frac of what it reaches at "
                         "--scale-max-depth. Raised 1.0 -> 2.0 N (and the depth "
                         "cap 1.0 -> 2.0 mm) on 2026-09-08: at 0.99 N the "
                         "imprint on 9DTact_hard_3mm_r1 was too faint to track "
                         "and the four rows fitted with 15.9-31.3 px of "
                         "residual; at 2.00 N, same mounting, same minute, "
                         "0.59-2.61 px. The mechanics were never the problem -- "
                         "all ten offsets reached their force to 2 %% and the "
                         "centre of pressure tracked the commanded position "
                         "with slope +0.992 -- only the image did. The per-gel "
                         "rule keeps soft gels near 1 N; it is the stiff ones "
                         "that were being asked for too little. "
                         "Force, not depth: a "
                         "fixed depth gave 0.813 N at one end of the y sweep "
                         "and 1.134 N at the other, because the gel plane is "
                         "not square to the assumed normal, and then the "
                         "contact differed from sample to sample")
    ap.add_argument("--scale-jump-frac", type=float, default=0.75,
                    help="fraction of the predicted depth taken in one move "
                         "before the fine steps begin. Under 1 so a stiffer "
                         "patch cannot overshoot the target force")
    ap.add_argument("--scale-force-frac", type=float, default=0.7,
                    help="fraction of what the gel can reach at the depth cap, "
                         "used when --scale-force is out of reach. The stiffness "
                         "comes from the zero fits of this very run")
    ap.add_argument("--scale-depth-mm", type=float, default=0.90,
                    help="depth the scale imprint aims for. This is what "
                         "governs whether the imprint can be tracked -- see the "
                         "table in phase_scale: 0.78-1.05 mm worked on four "
                         "units across all three thicknesses, 0.40 and 0.66 mm "
                         "were too faint and 1.39 mm saturated. 0.90 is the "
                         "middle of the band that worked")
    ap.add_argument("--scale-max-depth", type=float, default=2.0,
                    help="deepest the force seek may go; the registry depth "
                         "backstop still overrides it. Raised from the 0.6 mm "
                         "ladder depth on 2026-09-05. That limit was borrowed "
                         "from the ZERO phase, where it belongs -- a surface "
                         "fit must not disturb the surface it is fitting more "
                         "than the ladder does. The scale measures the OPTICS, "
                         "not the surface, so the rule does not apply; what "
                         "does is the gel's safety backstop. Inside 0.6 mm a "
                         "2 mm ball reaches only 0.16 N on a soft 3 mm gel and "
                         "the imprint is too faint to track (30.7 px residual "
                         "against 0.8-2.7 px where it worked)")
    ap.add_argument("--rotate-height", type=float, default=40.0,
                    help="standoff for the --scale-rotate reorientation, far "
                         "enough that the tool body swinging through the turn "
                         "cannot reach the gel")
    ap.add_argument("--rotate-joint-ceiling", type=float, default=200.0,
                    help="joint-change ceiling for that ONE reorientation "
                         "move. The 15 deg default exists to catch an IK "
                         "branch flip, and a deliberate 180 deg turn of the "
                         "tool about its own axis looks exactly like one")
    ap.add_argument("--plane-only", action="store_true",
                    help="measure the gel plane and stop. Three points per "
                         "axis instead of five, and no image tracking: the "
                         "plane changes with every re-mount, the image scale "
                         "does not")
    ap.add_argument("--scale-theta-tol", type=float, default=3.0,
                    help="how far the rotation angles from the two rows of the "
                         "Jacobian may disagree before the run's anisotropy is "
                         "flagged as untrustworthy. They measure the same "
                         "quantity if the model holds")
    ap.add_argument("--scale-template", type=int, default=260,
                    help="half-size of the correlation template, px")
    ap.add_argument("--scale-search", type=int, default=200,
                    help="half-size of the search margin around it, px")
    ap.add_argument("--scale-step", type=float, default=0.02,
                    help="descent step while seeking that force")
    ap.add_argument("--scale-rotate", type=float, default=0.0,
                    help="turn the tool this many degrees about the sensor "
                         "normal before pressing. Running 0 and 180 separates "
                         "a tilt that belongs to the probe, which reverses "
                         "with the tool, from one that belongs to the gel, "
                         "which does not")
    ap.add_argument("--scale-floor", type=int, default=4,
                    help="grey levels of |frame - reference| ignored as noise "
                         "before the centroid is taken; without it two "
                         "megapixels of sensor noise pull the centroid toward "
                         "the middle of the frame")
    ap.add_argument("--shape-dwell", type=float, default=0.6,
                    help="settle before the frame is taken at each rung")
    ap.add_argument("--max-drift", type=float, default=0.5)
    ap.add_argument("--max-tilt", type=float, default=5.0,
                    help="reject a sample whose probe axis is further than this "
                         "from the NOMINAL sensor normal, in degrees. Raised "
                         "from 3.0 on 2026-09-07: the probe is now deliberately "
                         "squared to each unit's MEASURED gel plane, which sits "
                         "+2.19 +- 0.65 deg from nominal and reaches 2.99 deg on "
                         "9DTact_medium_1mm_r2, so a correct alignment was "
                         "about to trip a gate meant to catch a bent or badly "
                         "seated probe. That fault shows up far larger than "
                         "5 deg; the useful check is unharmed.")
    ap.add_argument("--drop", action="store_true")
    a = ap.parse_args()
    if a.zero_max_travel is None:
        # Must exceed the stop condition (depth >= margin + stop_depth) or the
        # approach can never reach it. See --zero-max-travel.
        a.zero_max_travel = a.zero_margin + a.zero_stop_depth + 0.5

    print("=" * 58)
    print("VBTS INDENTATION RUN")
    print("  NO ROBOT MOTION   NO JOG   NO DAQ OUTPUT")
    print("=" * 58 + "\n")

    # The blanket 1.0 mm default is only for phases running WITHOUT a sensor id.
    # With one, the registry's per-sensor limit is the reasoned number and the
    # default has no business clamping it: it silently cut a 2 mm gel's 1.2 mm
    # allowance to 1.0 and ended the force ladder two rungs early. This is the
    # same override that truncated characterize before it was given the same
    # treatment.
    if a.max_travel_normal is None and not getattr(a, "sensor", None):
        a.max_travel_normal = 1.0
    if a.vel is not None:
        a.vel_contact = a.vel
    a.vel = a.vel_contact
    if a.new:
        return phase_new(a)
    if not a.phase:
        ap.print_help()
        return 2
    return {"tare": phase_tare, "zerocheck": phase_zerocheck,
            "reference": phase_reference, "sample": phase_sample,
            "series": phase_series, "shear": phase_shear,
            "force-series": phase_force_series, "force-shear": phase_force_shear,
            "collect": phase_collect, "contactmap": phase_contactmap,
            "characterize": phase_characterize,
            "zero": phase_zero, "shape": phase_shape, "scale": phase_scale,
            "calibgrid": phase_calibgrid,
            "summary": phase_summary}[a.phase](a)


# Phases that put the probe on or near the gel. Run through a pass script,
# the shell trap parks afterwards; run on their own -- which is how a phase is
# repeated with a different setting -- nothing did, and on 2026-09-08 two
# consecutive `--phase scale` runs each left the tip 2 mm above the gel until
# the operator noticed. The standing rule is that the probe ends up clear
# whatever happens, so it is enforced here as well as in the callers.
GEL_PHASES = {"search", "touchcheck", "zero", "shape", "scale", "characterize",
              "calibgrid",
              "contactmap", "collect", "series", "shear", "force-series",
              "force-shear", "sample"}


def park_after_phase(rc: int) -> int:
    """Lift clear of the gel after a standalone gel-touching phase."""
    argv = sys.argv[1:]
    if "--phase" not in argv:
        return rc
    try:
        phase = argv[argv.index("--phase") + 1]
    except IndexError:
        return rc
    if phase not in GEL_PHASES or os.environ.get("VBTS_NO_EXIT_PARK") == "1":
        return rc
    try:
        rc_cfg = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
        ip = rc_cfg["robot"]["ip"]
        if "--ip" in argv:
            ip = argv[argv.index("--ip") + 1]
        q = chk.ReadOnlyProxy(ip)
        t0, n = mv.sensor_axis()
        h = float((np.array(q("GetActualTCPPose", 0)[1:][:3]) - t0) @ n)
        want = 78.0
        if h >= want - 1.0:
            return rc
        print(f"\n  {phase} finished with the tip {h:.1f} mm above the gel — "
              f"lifting to {want:.0f} mm")
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / "move_probe.py"),
                            "--test-up", f"{want - h:.3f}", "--vel", "100",
                            "--confirm", "MOVE"], capture_output=True, text=True,
                           timeout=180)
        h2 = float((np.array(q("GetActualTCPPose", 0)[1:][:3]) - t0) @ n)
        if r.returncode != 0 or h2 < want - 1.0:
            print(f"  !! THE LIFT FAILED — still {h2:.1f} mm above the gel. Check it.")
        else:
            print(f"  parked {h2:.0f} mm above the sensor plane")
    except Exception as exc:  # noqa: BLE001
        print(f"  !! could not park after {phase} ({type(exc).__name__}: {exc}). "
              "The probe may still be on the gel.")
    return rc


if __name__ == "__main__":
    try:
        _rc = main()
    except BaseException:
        park_after_phase(1)
        raise
    raise SystemExit(park_after_phase(_rc))
