#!/usr/bin/env python3
"""
Commanded Cartesian motion for the indenter. THIS MOVES THE ROBOT.

    move_probe.py --test-up 1.0 --confirm MOVE          # stage 2: away from the sensor
    move_probe.py --status                              # read-only

Every move is checked before it is sent, and the checks are the point of this
file. The controller will happily accept a command that swings the arm through
the sensor; nothing downstream would catch that.

THE CHECK THAT MATTERS MOST
---------------------------
`MoveL` needs joint angles, and those come from inverse kinematics. Measured on
this robot, for one unchanged target pose:

    config = -1   ->  0.000 deg from the current joints
    config =  0   ->  219.002 deg
    config =  3   ->  243.282 deg

Same point in space, completely different arm postures. With the probe sitting
above the sensor, a 219-degree reconfiguration sweeps the arm through it. So
config is pinned to -1, and beyond that the solved joints are compared against
the current ones and the command is refused if any joint would move more than
--max-joint-step. A 0.1 mm probe step moves the largest joint by 0.0135 deg, so
a one-degree ceiling is enormous headroom and still catches a reconfiguration.

XML-RPC LAYOUT
--------------
From the SDK (`robot.cpp:804`), MoveL takes ONE array of 33 values:

    [j0..j5, x,y,z,rx,ry,rz, tool, user, vel, acc, ovl, blendR, blendMode,
     epos0..3, search, offset_flag, off_x..off_rz, oacc, velAccParamMode]

blendR = -1.0 means "arrive at the point, blocking". Any value >= 0 is a
blending radius and the move becomes non-blocking, which is not what stepping
wants.

The convenience overload that takes only a pose is client-side: it runs
GetInverseKin itself and calls this one. Doing the IK here instead is what makes
the guard above possible.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import xmlrpc.client
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import importlib.util


# Baseline window for the drift-immune contact test, in steps back from
# now. Far enough that a developing contact has not reached it, near
# enough that the zero drift between it and now is negligible.
BASE_START, BASE_END = 10, 25


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cal = _load("cal", ROOT / "scripts" / "prepare_tcp_calibration.py")
chk = _load("chk", ROOT / "scripts" / "robot_readonly_check.py")
from vbts_platform.robot_interface import RobotInterface  # noqa: E402

OUT = ROOT / "data" / "rig" / "motion"
TRANSFORMS = ROOT / "data" / "rig" / "frame_transform"
STATE_NAMES = {1: "stopped", 2: "running", 3: "paused", 4: "drag-teach"}


def sensor_axis() -> tuple[np.ndarray, np.ndarray]:
    runs = sorted(TRANSFORMS.glob("*/transform.yaml"))
    tr = yaml.safe_load(open(runs[-1]))
    R = np.array(tr["rotation_sensor_to_base"])
    return np.array(tr["origin_base_mm"]), R[:, 2]


def sensor_rotation() -> np.ndarray:
    runs = sorted(TRANSFORMS.glob("*/transform.yaml"))
    return np.array(yaml.safe_load(open(runs[-1]))["rotation_sensor_to_base"])


def gel_normal(slope_x: float, slope_y: float) -> np.ndarray:
    """Unit normal of the GEL, from its measured slopes in sensor coordinates.

    The gel surface is h = h0 + sx*x + sy*y above the nominal plane, so its
    outward normal is proportional to (-sx, -sy, 1) in sensor axes. Measured
    2026-09-06 over 17 units and 51 plane fits, sy is +2.19 +- 0.65 deg on every
    single unit and sx is -0.09 +- 0.50, i.e. zero. A one-sided error that
    survives re-seating every sensor is not seventeen tilted gels, it is the
    transform's own normal being wrong in y. Aligning the probe to THIS instead
    of to (0, 0, 1) is what makes the press perpendicular to the gel it is
    actually pressing.
    """
    R = sensor_rotation()
    v = R @ np.array([-float(slope_x), -float(slope_y), 1.0])
    return v / np.linalg.norm(v)


def _matrix_to_rpy(M) -> list:
    """Rotation matrix -> FAIRINO pose angles. Extrinsic XYZ, R = Rz @ Ry @ Rx."""
    ry = np.arcsin(-np.clip(M[2, 0], -1.0, 1.0))
    rz = np.arctan2(M[1, 0], M[0, 0])
    rx = np.arctan2(M[2, 1], M[2, 2])
    return [float(np.degrees(v)) for v in (rx, ry, rz)]


def spin_target(ip: str, deg: float) -> tuple[list, dict]:
    """Turn the probe about its OWN axis, holding the tip where it is.

    The paired-cylinder probes press their two posts unequally -- the weaker
    one reaches 0.45-0.99 of the stronger, and the ratio changes with the probe
    fitted, which points at the posts differing in length rather than at the
    gel being tilted. Turning the probe 180 degrees swaps which post sits on
    which side of the image. If the gel is the cause the weak SIDE stays put;
    if the probe is, it follows the post and flips. Rotating the tool in
    software beats re-seating the probe by hand, because nothing else moves.
    """
    q = chk.ReadOnlyProxy(ip)
    pose = q("GetActualTCPPose", 0)[1:]
    M = cal.rpy_to_matrix(pose[3], pose[4], pose[5])
    z_tool = M[:, 2] / np.linalg.norm(M[:, 2])
    t = np.radians(deg)
    K = np.array([[0, -z_tool[2], z_tool[1]],
                  [z_tool[2], 0, -z_tool[0]],
                  [-z_tool[1], z_tool[0], 0]])
    R = np.eye(3) + np.sin(t) * K + (1 - np.cos(t)) * (K @ K)
    rpy = _matrix_to_rpy(R @ M)

    def wrap(d):
        return float((d + 180.0) % 360.0 - 180.0)

    target = [float(pose[0]), float(pose[1]), float(pose[2])] + [wrap(v) for v in rpy]
    t0, n = sensor_axis()
    h = float((np.array(pose[:3]) - t0) @ n)
    return target, {"height_above_plane_mm": h, "spin_deg": float(deg),
                    "rpy_before": [float(v) for v in pose[3:6]],
                    "rpy_after": target[3:6]}


def align_target(ip: str, want_normal=None) -> tuple[list, dict]:
    """Pose that puts the tip on the sensor axis, probe normal to the gel,
    at exactly the height it is at now.

    Height is preserved deliberately. MoveL travels a straight line, so if both
    endpoints sit at the same distance along the sensor normal, every point
    between them does too -- the alignment cannot dip toward the gel no matter
    how far it has to travel sideways. Descending is a separate, later move with
    its own force checks.
    """
    q = chk.ReadOnlyProxy(ip)
    pose = q("GetActualTCPPose", 0)[1:]
    t0, n = sensor_axis()
    p = np.array(pose[:3])
    h = float((p - t0) @ n)
    target_p = t0 + h * n                      # on the axis, same height

    # Orientation: probe axis anti-parallel to the normal we are aligning to --
    # the nominal sensor normal by default, or the measured GEL normal when one
    # is supplied. Rotation about the probe's own axis is free for the round
    # tips, so rz is kept either way.
    ref = n if want_normal is None else np.asarray(want_normal, float)
    want = -ref / np.linalg.norm(ref)
    best = None
    for rx in np.arange(pose[3] - 20, pose[3] + 20, 0.05):
        for ry in np.arange(-8, 8, 0.05):
            z = cal.rpy_to_matrix(rx, ry, pose[5])[:, 2]
            e = float(np.degrees(np.arccos(np.clip(z @ want, -1, 1))))
            if best is None or e < best[0]:
                best = (e, float(rx), float(ry))
    resid, rx, ry = best

    def wrap(deg: float) -> float:
        """Fold an angle into [-180, 180].

        The controller rejects a pose whose RPY falls outside that range with
        errcode 112, even though rx=180.742 and rx=-179.258 are the same
        orientation. The optimiser searches a window around the current angle
        and can easily step over the boundary.
        """
        return float((deg + 180.0) % 360.0 - 180.0)

    target = [float(target_p[0]), float(target_p[1]), float(target_p[2]),
              wrap(rx), wrap(ry), wrap(float(pose[5]))]

    z_now = cal.rpy_to_matrix(pose[3], pose[4], pose[5])[:, 2]
    return target, {
        "height_above_plane_mm": h,
        "radial_offset_mm": float(np.linalg.norm((p - t0) - h * n)),
        "tilt_now_deg": float(np.degrees(np.arccos(np.clip(abs(z_now @ n), -1, 1)))),
        "tilt_after_deg": resid,
    }


def descend_target(ip: str, mm: float) -> list:
    """Current pose moved `mm` along the sensor normal, toward the gel."""
    q = chk.ReadOnlyProxy(ip)
    pose = q("GetActualTCPPose", 0)[1:]
    _, n = sensor_axis()
    p = np.array(pose[:3]) - mm * n
    return [float(p[0]), float(p[1]), float(p[2])] + [float(v) for v in pose[3:]]


def descend_from(origin, travel: float):
    """A point `travel` mm below `origin` along the sensor normal.

    Anchored to a fixed origin rather than chained off the achieved pose: the
    per-move Cartesian bias is only microns, but a 366-step search chained that
    way ended 1.4 mm off the sensor axis."""
    _, n = sensor_axis()
    return np.array(origin) - travel * n


def phase_search(a, ip: str) -> int:
    """Descend onto the gel a step at a time, stopping at first contact.

    The overshoot of this search is one step: contact is only noticed after the
    step that made it. Coarse steps are therefore only taken while the force is
    still at the noise floor, and the step drops to `--fine-step` the moment any
    force appears, so the last approach into contact is the careful one.

    Force is read fresh at every step and the zero is taken here, immediately
    before descending, because the F/T zero wanders by about 0.0012 N*m per
    minute and a search can run for minutes.
    """
    from vbts_platform.ft_interface import FTInterface
    from vbts_platform.ft_stream import ForceReader

    st = read_state(ip)
    ok, why = ready_to_move(st)
    if not ok:
        print(f"  not moving: {why}")
        return 2

    q = chk.ReadOnlyProxy(ip)
    t0, n = sensor_axis()
    start = np.array(q("GetActualTCPPose", 0)[1:][:3])
    h0 = float((start - t0) @ n)

    print(f"\n--- zeroing the F/T (nothing may be touching) ---")
    ft = FTInterface.from_config()
    ft.connect()
    reader = None
    try:
        tare = ft.tare(duration_s=2.0)
        zero = ft.read_wrench_mean(duration_s=1.0, tared=True)
        print(f"  residual |F| {np.linalg.norm(zero[:3]):.4f} N")
        if np.linalg.norm(zero[:3]) > 0.3:
            print("  something is already touching. Not searching.")
            return 1
        # A blocking MoveL takes long enough to overrun the DAQ buffer, so the
        # task is drained on its own thread from here on.
        reader = ForceReader(ft, tare).start()

        print(f"\n--- descending from {h0:.2f} mm above the sensor plane ---")
        print(f"  coarse {a.step} mm, fine {a.fine_step} mm once force appears")
        print(f"  contact at |Fz| >= {a.contact_n} N, abort at {a.abort_n} N, "
              f"travel limit {a.max_travel} mm\n")
        print(f"  {'step':>5} {'travel':>8} {'height':>8} {'Fz':>8} {'|F|':>8}")

        travel, i, fine = 0.0, 0, False
        contact_hits = 0
        outcome, surface = "not started", None
        # The F/T zero drifts, and a long descent gives it time. Measured
        # 2026-09-05: 0.08 N over two minutes, against a 0.11 N contact
        # threshold. On 9DTact_medium_1mm_r1 a 51 mm descent drifted far enough
        # that the notice threshold fired at 0.081 N with nothing touching and
        # noise carried it over 0.11 N twice: "CONTACT" was declared 0.64 mm
        # above the gel, and the touch check then could not develop force after
        # pressing 0.15 mm further. So the zero is retaken once, close to where
        # the gel is known to be but still clear of it, after which only a
        # couple of millimetres of descent remain for drift to accumulate over.
        rezero = 0.0
        rezero_done = a.expect_surface is None
        rezero_at = (None if a.expect_surface is None
                     else a.expect_surface + a.rezero_margin)
        # Three step sizes, not two. Parking the probe 60 mm clear for sensor
        # swaps turned a 3 mm descent into 29 mm, and a stray 0.05 N reading
        # 13 mm out put it in 0.05 mm steps for 276 of its 366 steps. Minutes of
        # crawling let the F/T zero drift past the 0.11 N contact threshold, so
        # the search "found" the gel 9 mm above it and the touch check then read
        # a NEGATIVE force. Where the gel is expected to be is known from the
        # registry, so the approach uses metre-scale steps until it is close.
        far_until = (a.expect_surface + a.far_margin
                     if a.expect_surface is not None else None)
        # Travel is read back from the robot rather than counted from the
        # commands issued, so the limit below governs the distance actually
        # covered.
        start_p = np.array(q("GetActualTCPPose", 0)[1:][:3])
        start_rpy = [float(v) for v in q("GetActualTCPPose", 0)[1:][3:]]
        log = []
        hist: list[float] = []
        quiet = 0
        while travel < a.max_travel:
            h_now = float((np.array(q("GetActualTCPPose", 0)[1:][:3]) - t0) @ n)
            if far_until is not None and h_now > far_until and not fine:
                step = min(a.far_step, h_now - far_until)
            else:
                step = a.fine_step if fine else a.step
            if (a.expect_surface is not None
                    and h_now < a.expect_surface - a.overshoot_abort):
                print(f"\n  ABORT: {a.overshoot_abort:.1f} mm below the expected "
                      f"surface ({a.expect_surface:.2f} mm) with no contact. The "
                      "sensor is not where the registry says it is.")
                return 1
            if travel + step > a.max_travel:
                step = a.max_travel - travel
                if step <= 1e-6:
                    break
            pt = descend_from(start_p, travel + step)
            target = [float(pt[0]), float(pt[1]), float(pt[2])] + start_rpy
            pl = plan(ip, target, a.max_joint_step)
            if not pl.get("ok"):
                print(f"\n  stopping: {pl['why']}")
                return 2
            tool = pl["active_tool"][1] if isinstance(pl["active_tool"], list) else 1
            rv = send_movel(ip, pl["target_joints"], pl["target_pose"], tool,
                            a.contact_vel, a.ovl)
            if rv != 0:
                print(f"\n  MoveL returned {rv}; stopping.")
                return 1
            i += 1
            time.sleep(a.settle)
            travel = float((start_p - np.array(q("GetActualTCPPose", 0)[1:][:3])) @ n)
            w, ferr = reader.read_fresh()
            if ferr:
                print(f"\n  F/T reading failed: {ferr}")
                return 1
            F = w[:3] - np.array([0.0, 0.0, rezero])
            fz, mag = float(F[2]), float(np.linalg.norm(F))
            pose = q("GetActualTCPPose", 0)[1:]
            h = float((np.array(pose[:3]) - t0) @ n)
            if not rezero_done and h <= rezero_at:
                w2, e2 = reader.read_fresh()
                if e2 is None:
                    rezero = float(w2[2])
                    print(f"  re-zeroing {rezero:+.4f} N at {h:.2f} mm, "
                          f"{h - a.expect_surface:.2f} mm above the gel on "
                          f"record — drift accumulated over the descent")
                rezero_done = True
                continue
            # Contact is a RISE, not a level. The F/T zero on this rig drifts
            # 0.115 N in four minutes, and the contact threshold is 0.11 N, so
            # any descent that takes minutes triggers on drift alone whether or
            # not anything is under the probe. That is exactly what happened on
            # 2026-09-08 on the first DIGIT: no surface was on record, the
            # search crawled 48 mm over five minutes, Fz slid from -0.003 to
            # -0.116 with no step in it, and "contact" was declared 0.6 mm above
            # a gel the touch check then found nothing at. The 9DTact campaign
            # never met this because after the first unit every surface was on
            # record and the empty air was crossed in one move.
            #
            # So judge against a baseline taken from where the probe was a few
            # steps ago. Drift over fifteen steps is under 0.004 N; a gel lifts
            # the reading within one or two. `abort_n` stays absolute -- that
            # one is a limit on the hardware, not a detection.
            hist.append(mag)
            base = (float(np.median(hist[-BASE_END:-BASE_START]))
                    if len(hist) >= BASE_END else 0.0)
            rise = mag - base
            log.append({"i": i, "travel_mm": travel, "height_mm": h,
                        "wrench": w.tolist(), "baseline_N": base,
                        "rise_N": rise})
            print(f"  {i:>5} {travel:>8.3f} {h:>8.3f} {fz:>8.3f} {mag:>8.3f}"
                  f" {rise:>8.3f}" + ("   fine" if fine else ""))

            if mag >= a.abort_n:
                print(f"\n  ABORT: {mag:.2f} N exceeds the {a.abort_n} N limit.")
                outcome = "force abort"
                break
            # Force read this far above the gel cannot be contact -- there is
            # nothing there to touch. Without this, one 0.05 N blip 26 mm out
            # latched fine mode for good (it never reverts), and the descent
            # crawled at 0.05 mm for hundreds of steps while the F/T zero drifted
            # toward the contact threshold. Both the fine switch and the contact
            # counter are gated on being near where the gel is known to be.
            near = far_until is None or h <= far_until
            if not near:
                contact_hits = 0
                continue
            if rise >= a.contact_n:
                contact_hits += 1
                if contact_hits >= a.contact_hits:
                    print(f"\n  CONTACT: {rise:.3f} N above the recent "
                          f"baseline ({base:.3f} N), {h:.3f} mm above the "
                          "sensor plane")
                    print(f"  descended {travel:.3f} mm from the start")
                    outcome, surface = "contact", h
                    break
                print(f"    {rise:.3f} N over baseline "
                      f"({contact_hits}/{a.contact_hits})")
            else:
                contact_hits = 0
            if not fine and rise >= a.notice_n:
                fine = True
                quiet = 0
                print(f"  ({rise:.3f} N over baseline noticed — switching to "
                      f"{a.fine_step} mm steps)")
            elif fine and rise < 0.5 * a.notice_n:
                # Fine mode used to be a one-way door: a single noise blip
                # switched it on and the descent then crawled at 0.05 mm for
                # the rest of the way. On the first DIGIT, with no surface on
                # record and so no `far_until` gate to suppress the blip, that
                # meant 1060 steps to cross 53 mm. If the rise has gone quiet
                # for several steps there is nothing under the probe after all,
                # so go back to coarse and get on with it.
                quiet += 1
                if quiet >= 5:
                    fine, quiet = False, 0
                    print("  (quiet again — back to coarse steps)")
            else:
                quiet = 0
        else:
            print(f"\n  travel limit {a.max_travel} mm reached without contact.")
            outcome = "travel limit"
    finally:
        if reader is not None:
            reader.stop()
        ft.disconnect()

    run = OUT / datetime.now().strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    (run / "search.yaml").write_text(yaml.safe_dump(json.loads(json.dumps({
        "timestamp": datetime.now().isoformat(), "kind": "force-guided descent",
        "start_height_mm": h0, "steps": log,
        "outcome": outcome, "found": outcome == "contact",
        "surface_mm": surface,
        "params": {"step": a.step, "fine_step": a.fine_step,
                   "contact_n": a.contact_n, "notice_n": a.notice_n,
                   "abort_n": a.abort_n, "max_travel": a.max_travel,
                   "expect_surface": a.expect_surface},
    }, default=str)), sort_keys=False, allow_unicode=True))
    print(f"\n  written: {run}/search.yaml")
    # A search that runs out of travel is a FAILURE and used to return 0 like
    # any other. The caller then read whatever height the probe happened to
    # stop at and recorded it as the gel surface -- on 2026-09-05 that wrote
    # "contact at 35.501 mm" for a gel at 26.1 mm, 9.4 mm of pure fiction, and
    # every step after it would have worked from that number.
    if outcome != "contact":
        print(f"  NO SURFACE FOUND ({outcome}). Nothing downstream may use "
              f"this height.")
        return 1
    return 0


def read_state(ip: str, settle: float = 1.5) -> dict:
    r = RobotInterface(ip=ip, dry_run=False, allow_real_motion=False)
    r.connect(read_only=True)
    try:
        time.sleep(settle)
        st = r.get_robot_state()
    finally:
        r.disconnect()
    return {"robot_state": st.robot_state,
            "robot_state_name": STATE_NAMES.get(st.robot_state, f"?{st.robot_state}"),
            "robot_mode": st.robot_mode, "main_code": st.main_code,
            "sub_code": st.sub_code, "emergency_stop": st.emergency_stop,
            "collision_state": st.collision_state,
            "safety_stop0": st.safety_stop0, "safety_stop1": st.safety_stop1}


def ready_to_move(s: dict) -> tuple[bool, str]:
    if s["emergency_stop"]:
        return False, "emergency stop is active"
    if s["safety_stop0"] or s["safety_stop1"]:
        return False, "a safety stop is active"
    if s["collision_state"]:
        return False, "the controller reports a collision"
    if s["main_code"] or s["sub_code"]:
        return False, f"controller error {s['main_code']}/{s['sub_code']}"
    if s["robot_mode"] != 0:
        return False, ("the controller is in manual mode; protocol motion needs "
                       "auto. Jogging from the web UI or the pendant switches it "
                       "back to manual, so this is expected after any hand "
                       "positioning. Re-run enable_protocol_motion.py")
    if s["robot_state"] == 2:
        return False, "the robot is already running something"
    if s["robot_state"] != 1:
        return False, f"robot state is {s['robot_state_name']}, expected stopped"
    return True, "ready"


def plan(ip: str, target_pose: list, max_joint_step: float) -> dict:
    """Everything that can be known before committing, computed read-only."""
    q = chk.ReadOnlyProxy(ip)
    cur_pose = q("GetActualTCPPose", 0)[1:]
    cur_joints = q("GetActualJointPosDegree", 0)[1:]
    tool = q("GetActualTCPNum", 0)

    r = q("GetInverseKin", 0, list(target_pose), -1)
    if r[0] != 0:
        return {"ok": False, "why": f"inverse kinematics failed, errcode {r[0]}",
                "cur_pose": cur_pose, "cur_joints": cur_joints}
    joints = list(r[1:])
    dj = np.array(joints) - np.array(cur_joints)
    dp = np.array(target_pose[:3]) - np.array(cur_pose[:3])

    t0, n = sensor_axis()
    cur_h = float((np.array(cur_pose[:3]) - t0) @ n)
    tgt_h = float((np.array(target_pose[:3]) - t0) @ n)

    ok, why = True, "ready"
    if np.abs(dj).max() > max_joint_step:
        ok, why = False, (f"joint {int(np.abs(dj).argmax())+1} would move "
                          f"{np.abs(dj).max():.3f} deg, over the "
                          f"{max_joint_step} deg ceiling — this is a "
                          "reconfiguration, not a step")
    return {"ok": ok, "why": why, "cur_pose": cur_pose, "cur_joints": cur_joints,
            "target_pose": list(target_pose), "target_joints": joints,
            "joint_delta": dj.tolist(), "max_joint_delta": float(np.abs(dj).max()),
            "cartesian_delta_mm": dp.tolist(),
            "distance_mm": float(np.linalg.norm(dp)),
            "active_tool": tool,
            "height_above_sensor_before_mm": cur_h,
            "height_above_sensor_after_mm": tgt_h,
            "approaching_sensor": tgt_h < cur_h}


def send_movel(ip: str, joints: list, pose: list, tool: int, vel: float,
               ovl: float) -> int:
    p = ([float(v) for v in joints] + [float(v) for v in pose]
         + [int(tool), 0,               # tool, user
            float(vel), 0.0, float(ovl),  # vel, acc (not open), ovl
            -1.0, 0,                    # blendR = -1 -> blocking; blendMode
            0.0, 0.0, 0.0, 0.0,         # epos
            0, 0,                       # search, offset_flag
            0.0, 0.0, 0.0, 0.0, 0.0, 0.0,  # offset pose
            100.0, 0])                  # oacc, velAccParamMode
    assert len(p) == 33, f"MoveL wants 33 values, built {len(p)}"
    c = xmlrpc.client.ServerProxy(f"http://{ip}:20003")
    return c.MoveL(p)


def wait_done(ip: str, timeout: float = 30.0) -> tuple[bool, float]:
    q = chk.ReadOnlyProxy(ip)
    t0 = time.time()
    while time.time() - t0 < timeout:
        r = q("GetRobotMotionDone", 0)
        if isinstance(r, list) and len(r) > 1 and r[0] == 0 and r[1] == 1:
            return True, time.time() - t0
        time.sleep(0.1)
    return False, time.time() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=None)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--search", action="store_true",
                    help="descend onto the gel, stopping at first contact")
    ap.add_argument("--step", type=float, default=0.2)
    ap.add_argument("--fine-step", type=float, default=0.05)
    ap.add_argument("--notice-n", type=float, default=0.05,
                    help=("force at which to switch to fine steps. Sits low on "
                          "purpose: a false trigger only costs finer steps, "
                          "which is the safe direction"))
    ap.add_argument("--contact-n", type=float, default=0.11,
                    help=("force that counts as contact. Five times the 0.022 N "
                          "scatter actually seen before contact in this loop. "
                          "The old 0.3 N came from a 0.057 N figure measured on "
                          "single samples, but every reading here averages a "
                          "tenth of a second, so 0.3 N was fourteen sigma, not "
                          "five -- and it meant the tip was already 0.32 mm into "
                          "the gel before contact was declared, a third of the "
                          "depth budget on a 1 mm elastomer"))
    ap.add_argument("--rezero-margin", type=float, default=3.0,
                    help="height above the surface on record at which the F/T "
                         "zero is retaken. Far enough to be certainly clear, "
                         "close enough that little drift can accumulate over "
                         "what is left of the descent")
    ap.add_argument("--contact-hits", type=int, default=2,
                    help="consecutive readings over the threshold before stopping")
    ap.add_argument("--abort-n", type=float, default=5.0)
    ap.add_argument("--max-travel", type=float, default=60.0)
    ap.add_argument("--expect-surface", type=float, default=None,
                    help="height of the gel surface on record; large steps are "
                         "used until --far-margin above it")
    ap.add_argument("--far-step", type=float, default=1.0)
    ap.add_argument("--far-margin", type=float, default=2.0)
    ap.add_argument("--overshoot-abort", type=float, default=2.0,
                    help="stop if this far below the expected surface with no "
                         "contact")
    ap.add_argument("--settle", type=float, default=0.3)
    ap.add_argument("--spin", type=float, default=None,
                    help="turn the probe about its own axis by this many "
                         "degrees, holding the tip in place. 180 swaps which "
                         "of a paired probe's two posts is on which side.")
    ap.add_argument("--gel-tilt", default=None,
                    help="sx,sy -- the sensor's MEASURED gel slopes in mm/mm. "
                         "With this, --align puts the probe perpendicular to "
                         "the gel rather than to the nominal sensor normal, "
                         "which is +2.19 deg away from it in y on every unit "
                         "measured. Matters most for the paired-cylinder "
                         "probes: over their 3 mm width that tilt is 0.11 mm, "
                         "38%% of the 0.3 mm they are pressed to, so one post "
                         "takes the load and they snap.")
    ap.add_argument("--align", action="store_true",
                    help="put the tip on the sensor axis and the probe normal "
                         "to the gel, without changing height")
    ap.add_argument("--test-up", type=float, default=None,
                    help="stage 2: move this many mm along base +Z, away from "
                         "the sensor")
    # Two speeds. In free air the arm is only repositioning and 30 % gets a
    # 2 mm retreat done in 1.4 s instead of 8. Any move that ends on or in the
    # gel stays at 15 %: at 30 % a 0.05 mm step read back as 0.111 mm before the
    # servo had settled, and that error is the size of a probe step.
    ap.add_argument("--vel", type=float, default=60.0,
                    help="speed %% for moves away from or clear of the sensor")
    ap.add_argument("--contact-vel", type=float, default=40.0,
                    help="speed %% for the search descent and any move toward "
                         "the gel; a downward --test-up is clamped to this")
    ap.add_argument("--ovl", type=float, default=10.0)
    ap.add_argument("--max-joint-step", type=float, default=1.0,
                    help="joint-change ceiling for probe-sized steps")
    ap.add_argument("--approach-joint-step", type=float, default=15.0,
                    help="ceiling for positioning moves, which travel further")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--confirm", default=None)
    a = ap.parse_args()

    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]

    print("=" * 62)
    print("FR5 COMMANDED MOTION" if not a.status else "FR5 MOTION STATUS")
    print("=" * 62 + "\n")

    if not cal.preflight(ip):
        return 2
    st = read_state(ip)
    ok, why = ready_to_move(st)
    print(f"  state {st['robot_state_name']}, mode "
          f"{'auto' if st['robot_mode'] == 0 else 'manual'}, "
          f"err {st['main_code']}/{st['sub_code']}, estop {st['emergency_stop']}")
    print(f"  ready to move: {ok} — {why}")

    t0, n = sensor_axis()
    q = chk.ReadOnlyProxy(ip)
    pose = q("GetActualTCPPose", 0)[1:]
    h = float((np.array(pose[:3]) - t0) @ n)
    radial = float(np.linalg.norm((np.array(pose[:3]) - t0)
                                  - ((np.array(pose[:3]) - t0) @ n) * n))
    print(f"\n  tip at {np.round(pose[:3], 3)} mm")
    print(f"  {h:.1f} mm above the sensor plane, {radial:.1f} mm off its axis")

    if a.search:
        if not cal.preflight(ip):
            return 2
        if a.confirm != "MOVE":
            print("\n  REFUSING: pass --confirm MOVE — this descends onto the gel.")
            return 2
        return phase_search(a, ip)

    if a.status or (a.test_up is None and not a.align and a.spin is None):
        return 0 if ok else 1
    if not ok:
        print("\n  not moving.")
        return 2

    if a.spin is not None:
        target, info = spin_target(ip, a.spin)
        # A 180 degree turn of the wrist is a large joint move by design, so
        # the step ceiling that guards probe steps has to be lifted for it --
        # and it is only safe because the tip does not move and this runs in
        # free air, far above the gel.
        if info["height_above_plane_mm"] < 20.0:
            print(f"\n  REFUSING: only {info['height_above_plane_mm']:.1f} mm above "
                  f"the gel. Spin the tool in free air.")
            return 2
        pl = plan(ip, target, max(a.max_joint_step, 200.0))
        print(f"\n--- planned spin {a.spin:+.1f} deg about the probe axis ---")
        print(f"  height above plane {info['height_above_plane_mm']:.1f} mm (tip held)")
        print(f"  rpy {np.round(info['rpy_before'], 2)} -> {np.round(info['rpy_after'], 2)}")
        if "target_pose" not in pl:
            print(f"\n  REFUSING: {pl['why']}")
            return 2
        d = float(np.linalg.norm(np.array(pl["target_pose"][:3])
                                 - np.array(pl["cur_pose"][:3])))
        print(f"  tip moves {d:.3f} mm (should be 0)")
        print(f"  joints move {np.round(pl['joint_delta'], 2)}")
        if a.dry_run:
            print("\n  --dry-run: nothing sent.")
            return 0
        if a.confirm != "MOVE":
            print("\n  REFUSING: pass --confirm MOVE to actually move the robot.")
            return 2
        tool = pl["active_tool"][1] if isinstance(pl["active_tool"], list) else 1
        rv = send_movel(ip, pl["target_joints"], pl["target_pose"], tool, a.vel, a.ovl)
        print(f"  return code {rv}" + ("   (accepted)" if rv == 0 else "   FAILED"))
        wait_done(ip)
        after = q("GetActualTCPPose", 0)[1:]
        print(f"  rpy now {np.round(after[3:6], 2)}")
        return 0 if rv == 0 else 1

    if a.align:
        want = None
        if a.gel_tilt:
            sx, sy = (float(v) for v in a.gel_tilt.split(","))
            want = gel_normal(sx, sy)
            print(f"\n  aligning to the MEASURED gel normal, not the nominal one:"
                  f"  slope x {sx:+.5f}, y {sy:+.5f} mm/mm")
        target, info = align_target(ip, want)
        # A sideways move of tens of mm turns joints by degrees; a wrong IK
        # branch turns them by hundreds. The ceiling separates those, it is not
        # the 1 degree used for probe steps.
        ceiling = max(a.max_joint_step, 15.0)
        pl = plan(ip, target, ceiling)
        print(f"\n--- planned alignment (height held) ---")
        print(f"  from   {np.round(pl['cur_pose'][:3], 3)}  "
              f"rx {pl['cur_pose'][3]:.2f} ry {pl['cur_pose'][4]:.2f}")
        if "target_pose" not in pl:
            print(f"  target {[round(v, 3) for v in target]}")
            print(f"\n  REFUSING: {pl['why']}")
            return 2
        print(f"  to     {np.round(pl['target_pose'][:3], 3)}  "
              f"rx {pl['target_pose'][3]:.2f} ry {pl['target_pose'][4]:.2f}")
        print(f"  travel {pl['distance_mm']:.2f} mm sideways")
        print(f"  radial offset {info['radial_offset_mm']:.2f} -> 0.00 mm")
        ref = "gel normal" if a.gel_tilt else "sensor normal"
        print(f"  probe tilt    {info['tilt_now_deg']:.2f} -> "
              f"{info['tilt_after_deg']:.2f} deg  (against the {ref})")
        print(f"  height above sensor plane {pl['height_above_sensor_before_mm']:.2f} "
              f"-> {pl['height_above_sensor_after_mm']:.2f} mm")
        dh = pl["height_above_sensor_after_mm"] - pl["height_above_sensor_before_mm"]
        if dh < -0.05:
            print(f"\n  REFUSING: this would descend {-dh:.2f} mm. Alignment holds height.")
            return 2
        print(f"  joints move {np.round(pl['joint_delta'], 3)}")
        print(f"  largest joint change {pl['max_joint_delta']:.3f} deg "
              f"(ceiling {ceiling})")
        if not pl["ok"]:
            print(f"\n  REFUSING: {pl['why']}")
            return 2
        if a.dry_run:
            print("\n  --dry-run: nothing sent.")
            return 0
        if a.confirm != "MOVE":
            print("\n  REFUSING: pass --confirm MOVE to actually move the robot.")
            return 2
        tool = pl["active_tool"][1] if isinstance(pl["active_tool"], list) else 1
        print(f"\n--- sending MoveL (tool {tool}) ---")
        rv = send_movel(ip, pl["target_joints"], pl["target_pose"], tool, a.vel, a.ovl)
        print(f"  return code {rv}" + ("   (accepted)" if rv == 0 else "   FAILED"))
        done, secs = (wait_done(ip) if rv == 0 else (False, 0.0))
        after = q("GetActualTCPPose", 0)[1:]
        t0b, nb = sensor_axis()
        pa = np.array(after[:3]); da = pa - t0b
        ha = float(da @ nb); ra = float(np.linalg.norm(da - ha * nb))
        za = cal.rpy_to_matrix(after[3], after[4], after[5])[:, 2]
        ta = float(np.degrees(np.arccos(np.clip(abs(za @ nb), -1, 1))))
        # Check the alignment against the normal it was actually aimed at. The
        # gate used to be `ta < 1.5` against the NOMINAL normal, which silently
        # rejected every gel-normal alignment: the whole point is to end up
        # about 2 deg away from nominal, so success looked like failure and the
        # run died at its first step.
        ref_vec = nb if want is None else np.asarray(want, float)
        ta_ref = float(np.degrees(np.arccos(np.clip(
            abs(za @ ref_vec) / np.linalg.norm(ref_vec), -1, 1))))
        print(f"\n--- result ---")
        print(f"  tip {np.round(after[:3], 3)} mm")
        print(f"  radial offset {ra:.3f} mm   height {ha:.2f} mm")
        print(f"  probe tilt {ta_ref:.3f} deg from the "
              f"{'gel' if want is not None else 'sensor'} normal"
              + (f"   ({ta:.3f} deg from the nominal one, which is the gel's "
                 f"own tilt)" if want is not None else ""))
        st2 = read_state(ip)
        print(f"  state {st2['robot_state_name']}, err {st2['main_code']}/{st2['sub_code']}, "
              f"collision {st2['collision_state']}")
        run = OUT / datetime.now().strftime("%Y%m%d_%H%M%S")
        run.mkdir(parents=True, exist_ok=True)
        (run / "align.yaml").write_text(yaml.safe_dump(json.loads(json.dumps({
            "timestamp": datetime.now().isoformat(), "kind": "align to sensor axis",
            "before": info, "plan": pl, "return_code": rv, "motion_done": done,
            "after": {"tcp": after, "radial_offset_mm": ra, "tilt_deg": ta,
                      "height_above_plane_mm": ha,
                      "tilt_from_target_normal_deg": ta_ref,
                      "aimed_at": "gel" if want is not None else "sensor"},
            "state_after": st2,
        }, default=str)), sort_keys=False, allow_unicode=True))
        print(f"\n  written: {run}/align.yaml")
        if rv == 0 and ra < 0.5 and ta_ref < 1.5:
            return 0
        print(f"\n  ALIGNMENT NOT ACHIEVED: return {rv}, radial {ra:.3f} mm "
              f"(< 0.5), tilt {ta_ref:.3f} deg (< 1.5)")
        return 1

    target = list(pose)
    target[2] = pose[2] + a.test_up          # base +Z, straight up
    if a.test_up < 0 and a.vel > a.contact_vel:
        print(f"  moving toward the sensor: speed clamped {a.vel:.0f} -> "
              f"{a.contact_vel:.0f} %")
        a.vel = a.contact_vel
    # A retreat of several millimetres is a positioning move, and its joints turn
    # by degrees; --max-joint-step is sized for a 0.1 mm probe step, where they
    # turn by hundredths. Applying the probe ceiling here refused an ordinary
    # 10 mm withdrawal as though it were a reconfiguration. The ceiling still
    # sits far below the 200-plus degrees a wrong IK branch takes.
    ceiling = max(a.max_joint_step, a.approach_joint_step)
    pl = plan(ip, target, ceiling)

    print(f"\n--- planned move: {a.test_up:+.3f} mm along base Z ---")
    print(f"  from   {np.round(pl['cur_pose'][:3], 3)}")
    print(f"  to     {np.round(pl['target_pose'][:3], 3)}")
    print(f"  joints move {np.round(pl['joint_delta'], 4)}")
    print(f"  largest joint change {pl['max_joint_delta']:.4f} deg "
          f"(ceiling {ceiling})")
    print(f"  height above sensor {pl['height_above_sensor_before_mm']:.1f} -> "
          f"{pl['height_above_sensor_after_mm']:.1f} mm  "
          f"{'TOWARD the sensor' if pl['approaching_sensor'] else 'away from the sensor'}")
    print(f"  vel {a.vel} %, ovl {a.ovl} %, blendR -1 (blocking)")
    if not pl["ok"]:
        print(f"\n  REFUSING: {pl['why']}")
        return 2

    if a.dry_run:
        print("\n  --dry-run: nothing sent.")
        return 0
    if a.confirm != "MOVE":
        print("\n  REFUSING: pass --confirm MOVE to actually move the robot.")
        return 2

    tool = pl["active_tool"][1] if isinstance(pl["active_tool"], list) else 1
    print(f"\n--- sending MoveL (tool {tool}) ---")
    rv = send_movel(ip, pl["target_joints"], pl["target_pose"], tool, a.vel, a.ovl)
    print(f"  return code {rv}" + ("   (accepted)" if rv == 0 else "   FAILED"))
    done, secs = (wait_done(ip) if rv == 0 else (False, 0.0))
    print(f"  motion done: {done} after {secs:.2f} s")

    after = q("GetActualTCPPose", 0)[1:]
    achieved = np.array(after[:3]) - np.array(pl["cur_pose"][:3])
    wanted = np.array(pl["cartesian_delta_mm"])
    err = float(np.linalg.norm(achieved - wanted))
    print(f"\n--- result ---")
    print(f"  wanted   {np.round(wanted, 4)} mm")
    print(f"  achieved {np.round(achieved, 4)} mm")
    print(f"  error    {err:.4f} mm")
    st2 = read_state(ip)
    print(f"  state {st2['robot_state_name']}, err {st2['main_code']}/{st2['sub_code']}, "
          f"collision {st2['collision_state']}")

    run = OUT / datetime.now().strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    (run / "move.yaml").write_text(yaml.safe_dump(json.loads(json.dumps({
        "timestamp": datetime.now().isoformat(), "robot_ip": ip,
        "kind": "stage-2 free-space test move along base +Z",
        "requested_mm": a.test_up, "vel": a.vel, "ovl": a.ovl,
        "blendR": -1.0, "config": -1, "tool": tool,
        "plan": pl, "return_code": rv, "motion_done": done, "seconds": secs,
        "achieved_delta_mm": achieved.tolist(),
        "error_mm": err,
        "state_before": st, "state_after": st2,
    }, default=str)), sort_keys=False, allow_unicode=True))
    print(f"\n  written: {run}/move.yaml")
    return 0 if (rv == 0 and done and err < 0.5) else 1


if __name__ == "__main__":
    raise SystemExit(main())
