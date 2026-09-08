#!/usr/bin/env python3
"""
Take one sensor through the whole protocol, stopping at the first thing wrong.

    run_one_sensor.py --sensor 9DTact_soft_1mm_r1 --confirm RUN
    run_one_sensor.py --sensor ... --from characterize    # resume part-way
    run_one_sensor.py --sensor ... --dry-run              # list the steps

WHY THIS EXISTS
---------------
A sensor takes about ten commands in a fixed order, and several of them are
only correct if the ones before them ran. Handling the robot by hand drops it
back to manual mode and moves it off the sensor axis, so the alignment has to be
redone every time -- that happened five times in one afternoon, and each time it
was noticed by reading output rather than by anything refusing to continue.
Over 54 sensors a skipped realignment is data collected off-centre with a tilted
probe, and nothing downstream would say so.

Each step here checks its own result before the next one starts. Alignment must
actually land on the axis; the reference image must be taken with nothing
touching; the sensor must be characterised before anything drives to a force.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import importlib.util


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cal = _load("cal", ROOT / "scripts" / "prepare_tcp_calibration.py")
chk = _load("chk", ROOT / "scripts" / "robot_readonly_check.py")
mv = _load("mv", ROOT / "scripts" / "move_probe.py")

PY = "/usr/bin/python3"
STEPS = ["enable", "liftoff", "align", "newrun", "tare", "reference", "qc",
         "search", "touchcheck", "zero", "shape", "scale", "characterize",
         "contactmap", "collect", "retract", "zerocheck", "summary", "park"]

# Pass A mounts a sensor once and swaps eight probes onto it, so `zero` and
# `shape` are re-entered seven more times with `--from zero` after the first
# probe. That skips `search`, which is the only step that measures the surface
# height, so the search writes it into state.json and the later entries read it
# back rather than descending onto the gel again for each tip.
SURFACE_KEY = "searched_surface_mm"


def run(cmd: list, label: str) -> bool:
    print(f"\n{'=' * 62}\n  {label}\n{'=' * 62}")
    print("  $ " + " ".join(str(c) for c in cmd) + "\n")
    env = {**os.environ, 'PYTHONUNBUFFERED': '1'}
    r = subprocess.run(cmd, env=env)
    if r.returncode != 0:
        print(f"\n  !! {label} exited {r.returncode}")
    return r.returncode == 0


def _probe_offsets(probe: str, reg_all: dict, skip: str | None = None):
    """How far above its recorded surface this probe has contacted, per unit.

    The recorded surface comes from the 4 mm probes; a different tip reaches a
    different distance, but by a CONSTANT amount, because the tips are rigid.
    Measured 2026-09-07 for pair100 over ten units: +1.104 mm median, sd 0.129,
    range 0.930 to 1.339. So a run whose offset is far from the others is not
    measuring what it says it is.
    """
    import glob
    out = []
    for p in (glob.glob(str(ROOT / "data" / "*" / "*" / "state.json"))
              + glob.glob(str(ROOT / "data" / "*" / "*" / "*" / "state.json"))):
        run = Path(p).parent
        base = run.name
        for suf in ("__2", "__3", "__4", "__5", "__6", "__7"):
            base = base.replace(suf, "")
        if any(x in run.name for x in ("WRONG", "__over", "__noisy", "__read06",
                                       "__badzero", "__settle015", "__failed")):
            continue
        if base == skip or base not in reg_all or not reg_all[base]:
            continue
        try:
            st = json.loads(Path(p).read_text())
        except Exception:
            continue
        if st.get("probe") != probe and probe not in run.parent.name:
            continue
        z = st.get("zero")
        if not z:
            continue
        f = [x for x in z["fits"] if x.get("ok")]
        if not f:
            continue
        surf = sum(x["base_height_mm"] - x["d0_mm"] for x in f) / len(f)
        out.append(surf - float(reg_all[base]))
    return out


def check_surface_plausible(run_dir: Path, sensor: str, probe: str,
                            ent: dict, tol: float = 0.5) -> bool:
    """Does the surface just measured belong to the sensor we think is mounted?

    Twice on 2026-09-07 a run was started before the named sensor was actually
    in the holder, and both times the data was collected, written and only
    caught later by eye. The surface is the cheapest possible check: it is
    measured before the ladder is collected, and a 1 mm gel sits about 1.2 mm
    lower than a 2 mm one, far outside anything re-seating moves.
    """
    rec = (ent.get("gel_model") or {}).get("surface_mm")
    st = json.loads((run_dir / "state.json").read_text())
    z = st.get("zero")
    if not rec or not z:
        return True
    f = [x for x in z["fits"] if x.get("ok")]
    if not f:
        return True
    surf = sum(x["base_height_mm"] - x["d0_mm"] for x in f) / len(f)
    off = surf - float(rec)
    reg_all = {e["id"]: (e.get("gel_model") or {}).get("surface_mm")
               for e in yaml.safe_load(open(ROOT / "config" /
                                            "sensor_registry.yaml"))["sensors"]}
    others = _probe_offsets(probe, reg_all, skip=sensor)
    if len(others) < 3:
        return True                       # nothing to compare against yet
    med = sorted(others)[len(others) // 2]
    print(f"\n  surface check: {surf:.3f} mm, {off:+.3f} mm above this unit's "
          f"record; {probe} has averaged {med:+.3f} mm over {len(others)} "
          f"other units")
    if abs(off - med) <= tol:
        return True
    print(f"  !! that is {abs(off - med):.3f} mm off, past the {tol:.1f} mm "
          f"tolerance.")
    print(f"     The usual cause is that the sensor in the holder is not "
          f"{sensor}.")
    print(f"     Stopping before the ladder is collected under the wrong name.")
    return False


def _measured_gel_tilt(sensor: str):
    """Mean gel slope (sx, sy) for this unit over every pass that fitted one."""
    import glob
    sx, sy = [], []
    for p in (glob.glob(str(ROOT / "data" / "*" / "*" / "state.json"))
              + glob.glob(str(ROOT / "data" / "*" / "*" / "*" / "state.json"))):
        name = Path(p).parent.name
        for suf in ("__2", "__3", "__badzero", "__settle015",
                    "__failed1", "__failed2"):
            name = name.replace(suf, "")
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
    if not sx:
        return None
    return sum(sx) / len(sx), sum(sy) / len(sy)


def _recentre(ip, a, M) -> bool:
    """Put the tip back on the sensor axis at the height it is at now.

    Alignment is done once at park height, but any move along base Z after it
    walks the tip off the axis again, because the two directions differ by
    about a degree. This is the same align command, re-run wherever centring
    has to be true rather than to have once been true.
    """
    r0 = geometry(ip)["radial_mm"]
    if r0 <= a.max_radial:
        return True
    cmd = M + ["--align", "--confirm", "MOVE"]
    tilt = _measured_gel_tilt(a.sensor)
    ref_n = None
    if tilt is not None and not a.no_gel_align:
        cmd += [f"--gel-tilt={tilt[0]:.6f},{tilt[1]:.6f}"]
        ref_n = mv.gel_normal(*tilt)
    print(f"\n  {r0:.3f} mm off the sensor axis after the descent — re-centring")
    if not run(cmd, "re-centre on the axis"):
        return False
    r1 = geometry(ip)["radial_mm"]
    print(f"  back to {r1:.3f} mm off the axis")
    return check_alignment(ip, a, ref_n)


def _active_run_dir() -> Path | None:
    f = ROOT / "data" / "_active_run.txt"
    if not f.exists():
        return None
    p = ROOT / "data" / f.read_text().strip()
    return p if p.exists() else None


def _remember_surface(surface: float) -> None:
    """Keep the searched surface with the run, not just in this process.

    The eight probes of Pass A are separate invocations of this script against
    one sensor mounting. Only the first descends onto the gel to find the
    surface; the rest must not, both because it costs a minute each and because
    every extra descent is another chance to press a gel that has already been
    measured.
    """
    d = _active_run_dir()
    if d is None:
        return
    f = d / "state.json"
    try:
        st = json.loads(f.read_text()) if f.exists() else {}
        st[SURFACE_KEY] = float(surface)
        f.write_text(json.dumps(st, indent=2))
    except Exception as e:                       # noqa: BLE001
        print(f"  (could not record the surface height: {e})")


def _recall_surface() -> float | None:
    d = _active_run_dir()
    if d is None:
        return None
    f = d / "state.json"
    if not f.exists():
        return None
    try:
        return float(json.loads(f.read_text())[SURFACE_KEY])
    except Exception:                            # noqa: BLE001
        return None


def geometry(ip: str, ref_normal=None) -> dict:
    """Where the tip is, and how square the probe is to `ref_normal`.

    Height and radial offset are always along the NOMINAL sensor axis, because
    that is the frame the rest of the run commands moves in. Tilt is different:
    it asks whether the probe is square to the surface it is about to press,
    and since 2026-09-07 that surface is the unit's MEASURED gel plane, about
    2 deg off nominal. Judging tilt against the nominal normal there rejects a
    correct alignment -- which it did, twice, before this argument existed.
    """
    q = chk.ReadOnlyProxy(ip)
    tcp = q("GetActualTCPPose", 0)[1:]
    t0, n = mv.sensor_axis()
    p = np.array(tcp[:3])
    d = p - t0
    h = float(d @ n)
    z = cal.rpy_to_matrix(tcp[3], tcp[4], tcp[5])[:, 2]
    r = n if ref_normal is None else np.asarray(ref_normal, float)
    r = r / np.linalg.norm(r)
    return {"height_mm": h,
            "radial_mm": float(np.linalg.norm(d - h * n)),
            "tilt_deg": float(np.degrees(np.arccos(np.clip(abs(z @ r), -1, 1)))),
            "tilt_vs_nominal_deg": float(np.degrees(np.arccos(np.clip(abs(z @ n), -1, 1)))),
            "tool": q("GetActualTCPNum", 0)}


def ensure_clear(ip: str, a, sensor_entry: dict) -> bool:
    """Get the probe off the gel before anything is zeroed.

    A run leaves the tip wherever its last step put it, which after a force
    ladder is inside the elastomer. The next run then aligned at that height and
    tared -- and taring a loaded contact defines the load as zero. Every check
    that followed asked whether the residual was near zero, which it now was by
    construction: the reference image was of a gel already indented 0.13 mm, and
    the force curve came out with an exponent of 0.67 against Hertz's 1.5.

    Clearance is judged from the geometry, not the force, because the force is
    exactly what the mistake destroys.
    """
    gm = (sensor_entry.get("gel_model") or {})
    surf = gm.get("surface_mm")
    g = geometry(ip)
    if surf is None:
        print(f"\n  no surface on record for this sensor; lifting "
              f"{a.liftoff} mm as a precaution")
        need = a.liftoff
    else:
        clearance = g["height_mm"] - float(surf)
        print(f"\n  tip is {clearance:+.3f} mm from the last known surface "
              f"({surf:.3f} mm)")
        if clearance >= a.min_clearance:
            print(f"  already clear by more than {a.min_clearance} mm")
            return True
        need = a.min_clearance - clearance + a.liftoff
    print(f"  lifting {need:.3f} mm before anything is zeroed")
    if not run([PY, str(ROOT / "scripts" / "move_probe.py"), "--test-up",
                f"{need:.3f}", "--confirm", "MOVE"], "lift clear of the gel"):
        return False
    g2 = geometry(ip)
    if surf is not None and g2["height_mm"] - float(surf) < a.min_clearance:
        print(f"  !! still only {g2['height_mm'] - float(surf):.3f} mm clear")
        return False
    return True


def check_alignment(ip: str, a, ref_normal=None) -> bool:
    g = geometry(ip, ref_normal)
    what = "gel" if ref_normal is not None else "sensor"
    print(f"\n  alignment: {g['radial_mm']:.3f} mm off axis, "
          f"{g['tilt_deg']:.3f} deg from the {what} normal, "
          f"{g['height_mm']:.2f} mm above the plane")
    if ref_normal is not None:
        print(f"             ({g['tilt_vs_nominal_deg']:.3f} deg from the nominal "
              f"normal, which is what the gel's own tilt should be)")
    ok = g["radial_mm"] <= a.max_radial and g["tilt_deg"] <= a.max_tilt
    if not ok:
        print(f"  !! outside {a.max_radial} mm / {a.max_tilt} deg. Not continuing:")
        print("     an off-axis, tilted probe collects data that looks fine and is not.")
    return ok


def camera_config_for_run(run_dir):
    """The camera file this run's principle needs.

    `qc_touch` opened the camera itself and got the default config, so on the
    first DIGIT the reference was written at exposure 600 and the touch-check
    frame at 2047: the whole picture came out 100 grey levels brighter with
    10 % of it clipped, and the check duly reported "100 % of pixels moved" --
    a lighting change read as a contact. Measured 2026-09-08. Any code that
    opens the camera has to know which sensor it is looking at.
    """
    import sys as _sys
    _sys.path.insert(0, str(ROOT / "scripts"))
    from run_indentation import camera_config_for  # noqa: E402
    try:
        sid = (yaml.safe_load((Path(run_dir) / "meta.yaml").read_text())
               or {}).get("sensor_id")
    except Exception:
        sid = None
    return camera_config_for(sid)


def qc_reference(run_dir: Path, a) -> bool:
    """Is this sensor worth thirty more minutes?"""
    st = json.loads((run_dir / "state.json").read_text())
    ref = st.get("reference")
    if not ref:
        print("  !! no reference image")
        return False
    q = ref["quality"]
    s = ref["stability"]
    print(f"\n  reference centre mean {q['centre_mean']:.1f}, "
          f"saturated {q['centre_saturated_pct']:.2f} %, "
          f"black {q['centre_black_pct']:.2f} %")
    print(f"  frame-to-frame std {s['frame_to_frame_std']:.4f} at "
          f"{s['fps']:.1f} fps")
    fails = []
    if q["centre_saturated_pct"] > 0.5:
        fails.append("the centre is clipped, so contact cannot be read there")
    if q["centre_black_pct"] > 0.5:
        fails.append("the centre is crushed to black")
    # Absolute brightness is NOT a pass/fail. It was, briefly, with a window
    # taken from a single 3 mm sensor reading 190 -- which then rejected a 1 mm
    # one at 82 that had no clipping at either end and the steadiest image of
    # the set. Thickness and hardness change the optical path, so different
    # designs sit at different levels and that is not a fault. What matters is
    # headroom, which the clipping checks already cover, and whether contact
    # actually shows, which the response check measures directly.
    if not (a.qc_mean_lo <= q["centre_mean"] <= a.qc_mean_hi):
        print(f"  note: centre mean {q['centre_mean']:.0f} is outside the "
              f"{a.qc_mean_lo:.0f}-{a.qc_mean_hi:.0f} band seen so far. Recorded, "
              "not treated as a fault — the response check decides.")
    if s["frame_to_frame_std"] > a.qc_stability:
        fails.append(f"brightness varies by {s['frame_to_frame_std']:.3f} between "
                     "frames — auto exposure may have re-enabled itself")
    for f in fails:
        print(f"  !! {f}")
    return not fails


def qc_touch(run_dir: Path, a) -> str:
    """Does the image move when the probe is resting on the gel?

    Returns "ok", "light" (touching, but the load has relaxed below the gate)
    or "fail". The distinction matters: the gel keeps creeping after the search
    stops, so a contact found at 0.134 N was reading 0.070 N by the time this
    check ran. That is 3.5 sigma above the pre-contact noise -- real contact,
    not the blank frame this gate exists to catch -- and the answer is to press
    a little further, not to abandon the sensor.

    The search leaves the tip in contact, so one frame taken here answers the
    question that actually matters -- is this sensor alive -- before the
    protocol spends half an hour on it. A dead camera, an unseated gel or failed
    illumination all pass the static checks and fail this one.
    """
    import cv2
    sys.path.insert(0, str(ROOT / "src"))
    from vbts_platform.camera_interface import Camera
    ref = cv2.imread(str(run_dir / "reference.png"))
    if ref is None:
        print("  !! no reference image to compare against")
        return "fail"
    with Camera.from_config(camera_config_for_run(run_dir)) as cam:
        frame, _ = cam.grab_settled()
    # Confirm the F/T agrees that something is being touched before reading
    # anything into the picture.
    from vbts_platform.ft_interface import FTInterface

    def read_fz() -> float:
        ft = FTInterface.from_config()
        ft.connect()
        try:
            return float(ft.read_wrench_mean(duration_s=0.5, tared=False)[2])
        finally:
            ft.disconnect()

    # The load is the CHANGE over a known lift, not a reading against a stored
    # zero. The tare in state.json was taken minutes earlier at the start of the
    # run, and the F/T drifts 0.08 N in two minutes (measured 2026-09-05), which
    # is the whole size of the quantity being tested. On 9DTact_medium_1mm_r1
    # that stale zero reported -0.088 N -- a negative load -- while the search's
    # own zero had reported contact. Two readings seconds apart cancel the drift
    # between them, and lifting clear is the one manipulation that certainly
    # removes the contact and nothing else.
    fz_down = read_fz()
    if not run([PY, str(ROOT / "scripts" / "move_probe.py"), "--test-up",
                f"{a.qc_lift:.3f}", "--vel", "15", "--confirm", "MOVE"],
               f"lift {a.qc_lift} mm to weigh the contact"):
        return "fail"
    fz_up = read_fz()
    if not run([PY, str(ROOT / "scripts" / "move_probe.py"), "--test-up",
                f"{-a.qc_lift:.3f}", "--vel", "15", "--confirm", "MOVE"],
               "back down"):
        return "fail"
    load = -(fz_down - fz_up)
    print(f"\n  normal force at the touch check: {load:.3f} N"
          f"   (Fz {fz_down:+.3f} down, {fz_up:+.3f} up {a.qc_lift} mm)")
    if load < a.qc_touch_force:
        print(f"  under {a.qc_touch_force} N — the load has relaxed since the "
              "search stopped.")
        return "light"
    d = np.abs(frame.astype(np.int16) - ref.astype(np.int16))
    changed = float(100 * (d.max(axis=2) > a.qc_diff_level).mean())
    cv2.imwrite(str(run_dir / "touchcheck.png"), frame,
                [cv2.IMWRITE_PNG_COMPRESSION, 1])
    print(f"\n  in contact: {changed:.1f} % of pixels moved more than "
          f"{a.qc_diff_level} levels")
    if changed < a.qc_touch_pct:
        print(f"  !! under {a.qc_touch_pct} %. The gel image is not responding to "
              "a contact the F/T can feel. Check focus, illumination, and that "
              "the gel is seated against the optics.")
        return "fail"
    return "ok"


def qc_response(run_dir: Path, a) -> bool:
    """Did the gel image actually change when the probe pressed on it?

    A sensor can pass every static check and still be dead: camera focused on
    nothing, gel detached, illumination failed. The cheapest proof is that the
    deepest sample differs from the unloaded reference by more than the
    frame-to-frame noise.
    """
    import cv2
    st = json.loads((run_dir / "state.json").read_text())
    samples = [s for s in st["samples"] if s.get("phase") == "force_series"]
    if not samples:
        print("  (no force-series samples yet; response check skipped)")
        return True
    ref = cv2.imread(str(run_dir / "reference.png")).astype(np.int16)
    deepest = max(samples, key=lambda s: -s["wrench"][2])
    load = -deepest["wrench"][2]
    # The image differs from the reference by a few per cent from noise and
    # drift alone. Asking only "did pixels move" passed a frame taken at
    # -0.01 N, with the probe hanging in air two millimetres above the gel.
    # The force has to be real before the picture means anything.
    if load < a.qc_touch_force:
        print(f"\n  !! the deepest sample carries only {load:.3f} N. Nothing was "
              "pressed hard enough for the image to be evidence of anything.")
        return False
    img = cv2.imread(str(run_dir / "frames" / deepest["image"])).astype(np.int16)
    diff = np.abs(img - ref)
    changed = float(100 * (diff.max(axis=2) > a.qc_diff_level).mean())
    print(f"\n  deepest sample {load:.2f} N: "
          f"{changed:.1f} % of pixels moved more than {a.qc_diff_level} levels")
    if changed < a.qc_diff_pct:
        print(f"  !! under {a.qc_diff_pct} %. The image is not responding to "
              "contact — check focus, illumination and that the gel is seated.")
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sensor", required=True)
    ap.add_argument("--dataset", default=None,
                    help="dataset folder under data/. One per probe, e.g. "
                         "20260905_passA_cyl4")
    ap.add_argument("--probe", default=None,
                    help="probe id from config/probes.yaml, required by the "
                         "zero and shape steps")
    ap.add_argument("--ip", default=None)
    ap.add_argument("--from", dest="start", default="enable", choices=STEPS)
    ap.add_argument("--to", dest="stop", default="park", choices=STEPS)
    ap.add_argument("--speed", type=int, default=5)  # global SetSpeed; per-move vel is what governs
    ap.add_argument("--park-vel", type=float, default=100.0,
                    help="speed %% for the final park lift only")
    ap.add_argument("--park-mm", type=float, default=50.0,
                    help="how far to lift after the run, for swapping sensors. "
                         "Set by the operator, who does the swapping: 60 -> 30 "
                         "-> 50 -> 80 -> 50 mm over 2026-09-04/05. Height is "
                         "not free -- the search has to come back down through "
                         "it -- but since the fast drop was added that costs "
                         "one move rather than one force-reading step per "
                         "millimetre")
    ap.add_argument("--no-exit-park", action="store_true",
                    help="on a SUCCESSFUL partial run (--to given), leave the "
                         "probe where the last step put it instead of parking; "
                         "the caller must park if it does not continue. Failures "
                         "park regardless")
    ap.add_argument("--skip", default="",
                    help="comma-separated steps to leave out of the range. "
                         "touchcheck is the usual one: it weighs the contact "
                         "the search found, which the zero phase then does "
                         "again per approach with its own lift check, so in a "
                         "pass that runs zero it costs 16 s to learn nothing "
                         "new.")
    ap.add_argument("--no-gel-align", action="store_true",
                    help="align to the nominal sensor normal, as before, "
                         "instead of to this unit's measured gel plane")
    ap.add_argument("--no-surface-check", action="store_true",
                    help="skip the check that the surface just measured matches "
                         "the sensor named. Only for a unit whose recorded "
                         "surface is known to be stale.")
    ap.add_argument("--zero-margin", type=float, default=None,
                    help="passed to the zero phase: how high above the assumed "
                         "surface each approach starts. The pair probes' tips "
                         "reach about 1.0-1.2 mm further than the 4 mm ones, "
                         "which eats the standoff.")
    ap.add_argument("--zero-stop-depth", type=float, default=None,
                    help="passed to the zero phase: how far past FIRST CONTACT "
                         "an approach presses. The ladder depth is separate.")
    ap.add_argument("--zero-read-s", type=float, default=None,
                    help="passed to the zero phase: seconds averaged per "
                         "reading. Low-area probes need this instead of depth.")
    ap.add_argument("--depths", default=None,
                    help="override the shape ladder, e.g. 0.1,0.2,0.3. The "
                         "paired-cylinder probes are two 1 mm posts and snap, "
                         "so their pass stops at 0.3 mm.")
    ap.add_argument("--search-from", type=float, default=1.5,
                    help="height above the surface on record that the one fast "
                         "drop stops at, and the step-by-step search begins. "
                         "Cut from 4.0 on 2026-09-06: re-seating a sensor moved "
                         "its fitted surface by 0.019-0.126 mm over eight "
                         "measured re-mounts, so 1.5 mm is ten times the "
                         "observed shift and the crawl covers 1.5 mm instead of "
                         "4, saving ~24 s of the ~40 s search.")
    ap.add_argument("--vel-free", type=float, default=60.0,
                    help="speed %% for that drop and other free-air moves")
    ap.add_argument("--travel-margin", type=float, default=8.0,
                    help="extra descent allowed past the surface on record, so "
                         "a gel that has been re-seated lower is still found")
    ap.add_argument("--liftoff", type=float, default=2.0,
                    help="extra height taken before zeroing")
    ap.add_argument("--min-clearance", type=float, default=1.0,
                    help="the tip must be at least this far above the last known "
                         "gel surface before the F/T is zeroed")
    ap.add_argument("--max-radial", type=float, default=0.05)
    ap.add_argument("--max-tilt", type=float, default=0.10)
    ap.add_argument("--qc-mean-lo", type=float, default=100.0,
                    help="informational band only; outside it is noted, not failed")
    ap.add_argument("--qc-mean-hi", type=float, default=230.0)
    ap.add_argument("--qc-stability", type=float, default=1.0)
    ap.add_argument("--qc-diff-level", type=int, default=6)
    ap.add_argument("--qc-diff-pct", type=float, default=2.0)
    ap.add_argument("--touch-nudge-mm", type=float, default=0.05,
                    help="how far to press in when the touch load has relaxed")
    ap.add_argument("--touch-retries", type=int, default=3,
                    help="how many times to press in before giving up")
    ap.add_argument("--qc-lift", type=float, default=0.30,
                    help="how far to lift to weigh the contact. The load is "
                         "the change over this height, so the F/T zero drift "
                         "that a stored tare cannot see cancels out")
    ap.add_argument("--qc-touch-force", type=float, default=0.08,
                    help="force the F/T must read before an image is accepted as "
                         "showing contact")
    ap.add_argument("--qc-touch-pct", type=float, default=1.0,
                    help="pixels that must move at first contact, where the force "
                         "is small; the deeper check later uses --qc-diff-pct")
    ap.add_argument("--normal-hold", type=float, default=None)
    ap.add_argument("--range-normal", type=float, default=2.0,
                    help="fixed normal range; the shear hold is 60 %% of it. "
                         "3 N since 2026-09-07 -- and this default was 5 N "
                         "while run_indentation's was 4, so the hold was "
                         "being sized against a range nothing else used")
    ap.add_argument("--frames", type=int, default=None,
                    help="frame budget for this run; default is the registry's "
                         "capture_policy.frames_per_sensor")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--confirm", default=None)
    a = ap.parse_args()

    reg = yaml.safe_load(open(ROOT / "config" / "sensor_registry.yaml"))
    ent = next((e for e in reg["sensors"] if e["id"] == a.sensor), None)
    if ent is None:
        print(f"  {a.sensor} is not in the registry")
        return 2
    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]

    order = STEPS[STEPS.index(a.start):STEPS.index(a.stop) + 1]
    drop = {x.strip() for x in a.skip.split(",") if x.strip()}
    if drop - set(STEPS):
        print(f"  !! --skip names no such step: {sorted(drop - set(STEPS))}")
        return 1
    if drop:
        print(f"  skipping: {', '.join(x for x in order if x in drop)}")
        order = [x for x in order if x not in drop]
    print("=" * 62)
    print(f"SENSOR RUN — {ent['id']}")
    print(f"  {ent['principle']}, {ent['hardness']}, {ent['thickness_mm']} mm, "
          f"replicate {ent['replicate']}")
    print("  no depth limit (removed 2026-09-04); the ramp ends at the force "
          "ceiling or where the image stops responding")
    print("=" * 62)
    print("\n  steps: " + " -> ".join(order))
    if a.dry_run:
        print("\n  --dry-run: nothing executed.")
        return 0
    if a.confirm != "RUN":
        print("\n  REFUSING: pass --confirm RUN. This moves the robot.")
        return 2

    # This script drives most phases as subprocesses under PY, but reads the
    # F/T itself in qc_touch, so it needs nidaqmx in ITS OWN interpreter. On
    # 2026-09-05 it was launched with the anaconda python3, which has no
    # nidaqmx: every subprocess ran fine and the run then died at the touch
    # check, after the robot had already been enabled and driven 60 mm. Fail
    # here instead, before anything moves.
    try:
        import nidaqmx                          # noqa: F401
    except ModuleNotFoundError:
        print(f"\n  REFUSING: nidaqmx is not importable from {sys.executable}.")
        print(f"  Run this script with {PY}, which has it.")
        return 2

    R = [PY, str(ROOT / "scripts" / "run_indentation.py")]
    if a.dataset:
        # One dataset per PROBE. The campaign loops probe-outer, so each sensor
        # is mounted once per probe and visited eight times overall; without
        # this every visit after the first lands in <sensor>__2, __3 ... and
        # nothing in the folder name says which tip made it.
        R += ["--dataset", a.dataset]
    M = [PY, str(ROOT / "scripts" / "move_probe.py")]
    surface = None
    run_dir = None
    t0 = time.time()

    timings: list = []
    for step in order:
        t_step = time.time()
        if step == "enable":
            if not run([PY, str(ROOT / "scripts" / "enable_protocol_motion.py"),
                        "--confirm", "ENABLE-MOTION", "--speed", str(a.speed)],
                       "enable protocol motion"):
                return 1
        elif step == "liftoff":
            if not ensure_clear(ip, a, ent):
                return 1
        elif step == "align":
            # Align to the gel this unit actually has, not to the nominal
            # normal. Every one of the 17 units measured sits +2.19 +- 0.65 deg
            # away from nominal in sensor y, always the same sign, so the
            # nominal normal is simply wrong; see docs/gel_normal.md.
            cmd = M + ["--align", "--confirm", "MOVE"]
            tilt = _measured_gel_tilt(a.sensor)
            ref_n = None
            if tilt is not None and not a.no_gel_align:
                # "--gel-tilt=..." not ["--gel-tilt", "..."]: a slope can be
                # negative, and argparse reads a leading "-" as another option
                # rather than as this one's value. 9DTact_medium_1mm_r1 has
                # slope x -0.0114 and was the first pair sensor to hit it.
                cmd += [f"--gel-tilt={tilt[0]:.6f},{tilt[1]:.6f}"]
                ref_n = mv.gel_normal(*tilt)
            elif tilt is None:
                print("  no measured gel plane for this unit yet — "
                      "aligning to the nominal normal")
            if not run(cmd, "align to the axis"):
                return 1
            if not check_alignment(ip, a, ref_n):
                return 1
        elif step == "newrun":
            if not run(R + ["--new", "--note", ent["id"],
                            "--sensor", ent["id"]], "open a run"):
                return 1
            run_dir = (ROOT / "data"
                       / (ROOT / "data" / "_active_run.txt").read_text().strip())
        elif step == "tare":
            if not run(R + ["--phase", "tare", "--sensor", a.sensor], "zero the F/T"):
                return 1
        elif step == "reference":
            if not run(R + ["--phase", "reference", "--sensor", a.sensor], "reference image"):
                return 1
        elif step == "qc":
            run_dir = run_dir or (ROOT / "data"
                / (ROOT / "data" / "_active_run.txt").read_text().strip())
            if not qc_reference(run_dir, a):
                print("\n  stopping before spending the rest of the protocol on it.")
                return 1
        elif step == "search":
            cmd = M + ["--search", "--confirm", "MOVE"]
            known = (ent.get("gel_model") or {}).get("surface_mm")
            if known:
                cmd += ["--expect-surface", f"{float(known):.3f}"]
                print(f"\n  gel surface on record: {float(known):.2f} mm — "
                      "approaching in 1 mm steps until 2 mm above it")
                # The travel limit has to cover the gap the probe is actually
                # starting from, not a fixed guess. On 2026-09-05 the arm
                # started 95.5 mm above the plane and the 60 mm default ran out
                # 9.4 mm short of a gel at 26.1 mm -- the search reported no
                # contact, which was correct, and everything after it treated
                # the height it stopped at as the surface anyway.
                # Cross the empty air in ONE move, then search only where the
                # gel might be. Parking 80 mm clear for the swap meant the
                # search crawled that 80 mm in 1 mm force-reading steps: 94 s
                # of the 6 min per sensor, spent proving there is nothing above
                # a surface whose height is already on record. The descent
                # below still happens step by step, because that is the part
                # that has to notice contact.
                h_now = geometry(ip)["height_mm"]
                drop = h_now - float(known) - a.search_from
                if drop > 1.0:
                    if not run(M + ["--test-up", f"{-drop:.3f}", "--vel",
                                    f"{a.vel_free:.0f}", "--confirm", "MOVE"],
                               f"drop {drop:.0f} mm to {a.search_from:.0f} mm "
                               f"above the surface on record"):
                        return 1
                    # --test-up travels along base +Z, and the sensor axis is
                    # not parallel to it: measured 2026-09-07, a 37.85 mm drop
                    # from an aligned start left the tip 0.70 mm off the axis,
                    # i.e. 1.06 deg between the two directions. The collect
                    # phase aborts past 0.3 mm off axis, so the drop alone was
                    # enough to fail every run before a single cycle finished.
                    # Re-align here rather than descend along the normal:
                    # align_target holds the height it is at exactly (both
                    # endpoints the same distance along the normal, so a
                    # straight MoveL between them cannot dip), which is what
                    # makes it safe to do 4 mm above the gel.
                    if not _recentre(ip, a, M):
                        return 1
                    h_now = geometry(ip)["height_mm"]
                need = h_now - float(known) + a.travel_margin
                cmd += ["--max-travel", f"{max(need, 5.0):.1f}"]
                print(f"  searching from {h_now:.1f} mm, travel limit "
                      f"{max(need, 5.0):.1f} mm")
            if not run(cmd, "find the gel surface"):
                return 1
            g = geometry(ip)
            surface = g["height_mm"]
            print(f"\n  contact at {surface:.3f} mm above the sensor plane")
            _remember_surface(surface)
        elif step == "touchcheck":
            run_dir = run_dir or (ROOT / "data"
                / (ROOT / "data" / "_active_run.txt").read_text().strip())
            for attempt in range(a.touch_retries + 1):
                verdict = qc_touch(run_dir, a)
                if verdict != "light":
                    break
                if attempt == a.touch_retries:
                    print(f"  !! still under {a.qc_touch_force} N after "
                          f"{a.touch_retries} nudges of {a.touch_nudge_mm} mm. "
                          "The probe is not resting on the gel.")
                    return 1
                print(f"  pressing {a.touch_nudge_mm} mm further "
                      f"({attempt + 1}/{a.touch_retries})")
                if not run(M + ["--test-up", f"{-a.touch_nudge_mm}",
                                "--vel", "15", "--confirm", "MOVE"],
                           "press in a little"):
                    return 1
                surface = geometry(ip)["height_mm"]
                _remember_surface(surface)
            if verdict != "ok":
                return 1
        elif step in ("zero", "shape", "scale"):
            if not a.probe:
                print(f"  !! --probe is required by the {step} step")
                return 1
            if surface is None:
                surface = _recall_surface()
                if surface is None:
                    # With `search` skipped there is nothing from this run, so
                    # fall back to the height on record. Re-seating a sensor
                    # moved its fitted surface by 0.019-0.126 mm over eight
                    # measured re-mounts, and the zero phase starts
                    # --zero-margin (1.0 mm) above whatever it is given and
                    # aborts if it finds itself already touching, so a recorded
                    # surface is a safe starting point -- and the zero phase
                    # then measures the real one anyway, which is the whole
                    # reason the 40 s search is optional.
                    rec = (ent.get("gel_model") or {}).get("surface_mm")
                    if rec:
                        surface = float(rec)
                        print(f"\n  surface {surface:.3f} mm, from the registry "
                              f"(search skipped); the zero phase re-measures it")
                if surface is None:
                    print("  !! no surface height on file; run the search step "
                          "first, or start this run from an earlier step")
                    return 1
                print(f"\n  surface {surface:.3f} mm, from the search earlier "
                      f"in this run")
            cmd = R + ["--phase", step, "--sensor", a.sensor,
                       "--probe", a.probe]
            if step == "shape" and a.depths:
                cmd += ["--depths", a.depths]
            if step == "zero" and a.zero_read_s:
                cmd += ["--zero-read-s", f"{a.zero_read_s:.3f}"]
            if step == "zero" and a.zero_stop_depth:
                cmd += ["--zero-stop-depth", f"{a.zero_stop_depth:.3f}"]
            if step == "zero" and a.zero_margin:
                cmd += ["--zero-margin", f"{a.zero_margin:.3f}"]
            if step == "zero":
                # The zero phase starts its own approaches from
                # surface + --zero-margin, so it wants the searched surface
                # itself, not the raised start characterize is given.
                cmd += ["--surface", f"{surface:.3f}"]
            label = {"zero": "locate the gel surface finely",
                     "shape": "depth ladder",
                     "scale": "millimetres per pixel"}[step]
            if not run(cmd, f"{label} ({a.probe})"):
                return 1
            # Check WHO we just measured before spending the ladder on it.
            if step == "zero" and run_dir is not None and not a.no_surface_check:
                if not check_surface_plausible(run_dir, a.sensor, a.probe, ent):
                    return 1
            # From here on, the surface IS the zero fit. It is the most precise
            # height in the run (sigma 0.01-0.03 mm) and until 2026-09-07 it
            # went nowhere: characterize kept the searched height, or the
            # registry's when the search was skipped. On 9DTact_soft_1mm_r1
            # that registry height was 0.27 mm off for ball8, the ramp's depths
            # were under-read by that much, the local exponent inflated past
            # the 2.0 substrate alarm at 1.30 mm / 1.94 N, and the run was
            # refused as unable to reach 2 N. Four minutes later, with the
            # surface right, the same gel gave 3.56 N at 1.52 mm. The alarm
            # was reading a wrong zero, not a stiffening gel.
            if step == "zero" and run_dir is not None:
                try:
                    zf = json.loads((Path(run_dir) / "state.json").read_text()).get("zero") or {}
                    if zf.get("surface_mm") is not None:
                        old_s = surface
                        surface = float(zf["surface_mm"])
                        _remember_surface(surface)
                        print(f"\n  surface {surface:.3f} mm from the zero fit"
                              + (f" ({surface - old_s:+.3f} mm from the height used so far)"
                                 if old_s is not None else ""))
                except Exception as exc:  # noqa: BLE001
                    print(f"  (could not read the zero fit back: {exc})")
        elif step == "characterize":
            if surface is None:
                print("  !! no surface height; run the search step first")
                return 1
            # Stop the ramp once the sensor has demonstrably cleared the range
            # it will be collected over, instead of driving on to find a true
            # ceiling. sensor_limits() takes 0.9 x this, so 3 N of collection
            # needs 3.34 N demonstrated and no more. Without the cap the
            # deepened backstop (2026-09-07) would send characterize to about
            # 10 N on the hard 2 and 3 mm units -- two to three times any force
            # they have ever carried -- for a number nothing reads. Finding
            # where each gel actually gives out is test 4's job, run last
            # precisely because it damages them.
            need = a.range_normal / 0.9 + 0.65
            if not run(R + ["--phase", "characterize", "--sensor", a.sensor,
                            "--surface", f"{surface + 0.3:.3f}",
                            "--max-force", f"{need:.2f}"],
                       "characterise the safe envelope"):
                return 1
        elif step == "contactmap":
            if not run(R + ["--phase", "contactmap", "--sensor", a.sensor],
                       "deformed region at 0.5 mm and at 0.5 N"):
                return 1
        elif step == "collect":
            # Re-centre once more, because everything between here and the last
            # alignment has walked the tip off the axis again. Measured on
            # 9DTact_hard_3mm_r1 2026-09-07: on the axis to 0.000 mm after the
            # search AND after the touch check, then 0.329 mm off by the time
            # collect started -- gained entirely inside zero/characterize/
            # contactmap. Those phases step with _move_along_normal, which
            # chains each target off the pose just achieved rather than off a
            # fixed origin, so MoveL's ~3 um per-move Cartesian bias
            # accumulates; a hundred moves is 0.3 mm, and collect aborts past
            # 0.3 mm. It is the same accumulation descend_from() was written to
            # avoid inside the search.
            #
            # Once is enough: collect's own ramps go through _seek_force, which
            # IS origin-anchored, and the radial held to 0.010 mm across a full
            # load-unload cycle in both runs. So this fixes the starting point,
            # not a leak.
            #
            # Lift first. The tip is sitting on the gel here, and align moves
            # sideways at constant height -- which off the gel is safe and on it
            # would drag the probe across the surface.
            if not run(M + ["--test-up", "3.0", "--vel", f"{a.vel_free:.0f}",
                            "--confirm", "MOVE"],
                       "lift clear before re-centring"):
                return 1
            if not _recentre(ip, a, M):
                return 1
            reg2 = yaml.safe_load(open(ROOT / "config" / "sensor_registry.yaml"))
            e2 = next(e for e in reg2["sensors"] if e["id"] == a.sensor)
            # 60 % of the FIXED range, not of this sensor's own ceiling --
            # the hold has to be the same everywhere for the shear rungs to
            # mean the same thing, and friction (mu x hold) is what caps them.
            hold = a.normal_hold if a.normal_hold is not None else \
                round(0.6 * min(a.range_normal, float(e2["safe_force_N"])), 2)
            cmd = R + ["--phase", "collect", "--sensor", a.sensor,
                       "--normal-hold", str(hold)]
            if a.frames:
                cmd += ["--frames", str(a.frames)]
            print(f"\n  shearing at {hold} N normal (60 % of the fixed "
                  f"{a.range_normal:.1f} N range)")
            if not run(cmd, "continuous capture: loading cycles + shear cycles"):
                return 1
            run_dir = run_dir or (ROOT / "data"
                / (ROOT / "data" / "_active_run.txt").read_text().strip())
            if not qc_response(run_dir, a):
                return 1
        elif step == "retract":
            if not run(M + ["--test-up", "5.0", "--confirm", "MOVE"], "retract"):
                return 1
        elif step == "zerocheck":
            if not run(R + ["--phase", "zerocheck"], "F/T drift check"):
                return 1
        elif step == "summary":
            if not run(R + ["--phase", "summary"], "summary"):
                return 1
        elif step == "park":
            # Swapping a sensor by hand needs room the 5 mm retract does not
            # give. This runs after summary, so the data is already written and
            # a refused lift costs nothing: if the planner rejects the full
            # height (joint-change ceiling, reach), it steps down and tries
            # again rather than failing a completed run.
            # Park at an ABSOLUTE height above the plane, not "+park_mm from
            # wherever you happen to be". Relative lifts compound: on
            # 2026-09-07 three consecutive failed pair100 attempts each ended
            # with a lift, and the tip walked 96 -> 146 -> 196 -> 246 mm above
            # the gel, heading for a joint limit. Anything already high enough
            # stays put.
            g_now = geometry(ip)["height_mm"]
            want = float(a.park_mm) + 28.0        # the usual resting height
            lift = want - g_now
            if lift <= 1.0:
                print(f"  already {g_now:.0f} mm above the plane "
                      f"(target {want:.0f}); not lifting further")
                continue
            for mm in (lift, lift / 2, 10.0):
                # Full speed here and nowhere else. This is the one move that
                # is purely away from the gel, ends in free air, and has no
                # measurement depending on where it lands -- and at 80 mm it is
                # the longest single move in the run.
                if run(M + ["--test-up", f"{mm:.1f}", "--vel", f"{a.park_vel:.0f}",
                            "--confirm", "MOVE"],
                       f"park {mm:.0f} mm clear for the sensor swap"):
                    break
                print(f"  {mm:.0f} mm refused; trying less")
            else:
                print("  !! could not lift clear; move the arm by hand before "
                      "swapping the sensor")
            g = geometry(ip)
            print(f"\n  parked {g['height_mm']:.0f} mm above the sensor plane")

        timings.append((step, time.time() - t_step))

    total = time.time() - t0
    print(f"\n{'=' * 62}")
    print(f"  {ent['id']} complete in {total / 60:.1f} min")
    print("=" * 62)
    print(f"\n  {'step':<14}{'seconds':>9}{'share':>8}")
    for name, dt in sorted(timings, key=lambda x: -x[1]):
        if dt >= 1.0:
            print(f"  {name:<14}{dt:>9.1f}{dt / total:>7.0%}")
    if run_dir is not None:
        try:
            st = json.loads((Path(run_dir) / "state.json").read_text())
            # Merge, not replace: a two-stage run (pass_b_sensor.sh) writes
            # its first stage's timings and then its second's, and the second
            # used to erase the first.
            prev = st.get("step_timings_s") or {}
            prev.update({n: round(v, 2) for n, v in timings})
            st["step_timings_s"] = prev
            st["total_s"] = round(float(st.get("total_s") or 0.0) + total, 1)
            (Path(run_dir) / "state.json").write_text(json.dumps(st, indent=2))
        except Exception:
            pass
    return 0


def park_whatever_happens(rc: int) -> int:
    """Lift clear of the gel on EVERY exit path, not just the successful one.

    On 2026-09-07 the collect phase aborted on a radial check, main() returned
    1 without reaching its park step, and the probe sat resting on
    9DTact_hard_3mm_r1 for 28 minutes before anyone looked. The operator's
    standing instruction is that the probe ends up at least 50 mm clear of the
    gel whatever else happens; pass_a_sensor.sh has had a shell trap doing this
    since 2026-09-06, and every path that does not go through that script had
    nothing.

    It talks to move_probe directly rather than re-entering this script. The
    first version spawned `run_one_sensor --from park`, which meant the
    emergency lift needed the registry, the probe file and a valid sensor id --
    exactly the things that may be what failed. A bad sensor name made the
    rescue fail too. Lifting needs none of them: the sensor AXIS is a property
    of the rig, not of the unit mounted on it.

    Best-effort, and it never changes the exit code -- but it is LOUD when it
    cannot do its job, because a silent failure here is a loaded probe nobody
    knows about.
    """
    argv = sys.argv[1:]
    if "--dry-run" in argv or "--status" in argv:
        return rc
    if rc == 0 and "--to" not in argv:
        return rc                      # the run's own park step already ran
    if rc == 0 and "--no-exit-park" in argv:
        # A successful partial run whose caller starts the next stage at
        # once (pass_b_sensor.sh). Parking here cost ~45 s per unit: lift,
        # then descend 50 mm again for collect. The caller's own EXIT trap
        # parks if the next stage never runs. Failures still park.
        return rc
    try:
        ip = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))["robot"]["ip"]
        if "--ip" in argv:
            ip = argv[argv.index("--ip") + 1]
        want = 50.0 + 28.0
        if "--park-mm" in argv:
            want = float(argv[argv.index("--park-mm") + 1]) + 28.0
        h = geometry(ip)["height_mm"]
        if h >= want - 1.0:
            return rc                  # already clear; a lift would only add risk
        print(f"\n{'=' * 62}\n  exit {rc}: {h:.1f} mm above the gel — lifting to "
              f"{want:.0f} mm before quitting\n{'=' * 62}")
        r = subprocess.run([PY, str(ROOT / "scripts" / "move_probe.py"),
                            "--test-up", f"{want - h:.3f}",
                            "--vel", "100", "--confirm", "MOVE"],
                           capture_output=True, text=True, timeout=180)
        h2 = geometry(ip)["height_mm"]
        if r.returncode != 0 or h2 < want - 1.0:
            print(f"\n  !! THE LIFT FAILED — still {h2:.1f} mm above the gel. "
                  f"The probe may be loaded. Check it before anything else.")
            print("     " + (r.stderr or r.stdout or "").strip()[-400:])
        else:
            print(f"  parked {h2:.0f} mm above the sensor plane")
    except Exception as exc:  # noqa: BLE001
        print(f"\n  !! THE PARK COULD NOT RUN ({type(exc).__name__}: {exc}). "
              "The probe may still be on the gel. Check it.")
    return rc


if __name__ == "__main__":
    try:
        _rc = main()
    except BaseException:              # KeyboardInterrupt included, on purpose
        park_whatever_happens(130)
        raise
    raise SystemExit(park_whatever_happens(_rc))
