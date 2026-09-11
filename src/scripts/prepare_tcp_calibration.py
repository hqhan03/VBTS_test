#!/usr/bin/env python3
"""
FR5 indenter TCP calibration — read, record, calculate, report. Never move.

The robot is NEVER commanded. The operator positions it by hand or pendant; this
script only reads the pose back. No motion, no jog, no IO, no servo enable, no
mode change, no register write.

    prepare_tcp_calibration.py --self-test          # verify the maths, no hardware
    prepare_tcp_calibration.py --phase connect      # Step 1+2: read state, back it up
    prepare_tcp_calibration.py --phase record --reset   # Step 3: record taught poses
    prepare_tcp_calibration.py --phase compute      # Step 4+5: solve and report

METHOD
------
The indenter's spherical tip sits in a cone vertex. Its centre therefore stays
at one fixed point in the base frame while the flange is re-oriented around it. For pose i,
with flange rotation R_i and flange position p_i, and unknown tool offset t
(in flange coordinates) and unknown cone vertex c (in base coordinates):

    R_i t + p_i = c        for every pose

Rearranged into a linear system in the six unknowns [t; c]:

    [ R_i  -I ] [t]  =  -p_i
                [c]

Each pose contributes three rows. Two poses would be six equations for six
unknowns, but the system is badly conditioned unless the orientations differ
substantially, which is exactly why several well-spread poses are asked for.
Solved by least squares; the residual per pose is ||R_i t + p_i - c||.

WHAT THIS METHOD CANNOT DO
--------------------------
A sphere in a cone constrains POSITION ONLY. A sphere has no orientation, so no
amount of tip-in-cone data can determine the tool's rotation. This script
therefore reports a TCP POSITION and leaves the orientation at zero relative to
the flange, and says so. If a rotated tool frame is ever needed, that requires
the FR5's six-point method, which teaches axis directions separately.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vbts_platform import fr5_io  # noqa: E402
from vbts_platform.robot_interface import RobotInterface  # noqa: E402

BANNER = """\
==========================================
FR5 INDENTER TCP CALIBRATION

NO ROBOT MOTION
NO JOG
NO IO
NO SERVO ENABLE
NO TCP WRITE
==========================================="""

OUT = PROJECT_ROOT / "data" / "rig" / "tcp_calibration"
ROBOT_CFG = PROJECT_ROOT / "src" / "config" / "robot_config.yaml"
POSES = OUT / "_recorded_poses.json"
MARKER = OUT / "_active_run.txt"


def start_run() -> Path:
    """Open a new run directory and make it the one every later phase writes to."""
    run = OUT / datetime.now().strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    MARKER.write_text(run.name)
    return run


def active_run() -> Path:
    """The run opened by --phase connect, so record and compute land beside it."""
    if MARKER.is_file():
        run = OUT / MARKER.read_text().strip()
        if run.is_dir():
            return run
    return start_run()

# Mechanical design estimate for the CURRENT indenter. An estimate only: it is
# what the calibration checks against, never a value to fall back on.
CAD_TCP_MM = np.array([0.0, 0.0, 35.97])

# The indenter was redesigned. The tip is now part of the printed body, so the
# error sources changed: adhesive thickness and ball-placement error no longer
# exist, and print accuracy and tip form error take their place.
INDENTER = {
    "type": "monolithic_Form4_printed_indenter",
    "spherical_tip": "integrated 3D printed geometry",
    "manufacturing": "Formlabs Form 4",
    "steel_ball": False,
    "adhesive": False,
    "tcp_definition": "centre of the printed spherical tip",
    "cad_flange_face_to_tip_centre_mm": [0.0, 0.0, 35.97],
    "mounting": "bolted directly to the FR5 flange",
}

# Superseded design, kept for traceability of the change. Do not use.
HISTORICAL_INDENTER = {
    "type": "printed_indenter_with_glued_steel_ball",
    "steel_ball_diameter_mm": 4.0,
    "adhesive": "instant adhesive",
    "cad_flange_face_to_ball_centre_mm": [0.0, 0.0, 34.4],
    "status": "OBSOLETE — the ball detached 2026-08-26 and the part was redesigned",
}

CONE = {"bottom_diameter_mm": 6.0, "depth_mm": 3.0, "included_angle_deg": 90.0,
        "mounting": "fixed to the optical table, independent of the F/T sensor"}

ERROR_SOURCES = [
    "Form 4 dimensional accuracy",
    "print shrinkage and warping",
    "spherical tip form error",
    "spherical surface roughness",
    "flange mating / assembly error",
    "calibration cone fixture geometry",
    "cone seating repeatability",
    "manual teaching repeatability",
    "robot flange pose repeatability",
]

READ_ONLY_METHODS = {
    "GetSDKVersion", "GetActualTCPPose", "GetActualTCPNum", "GetActualWObjNum",
    "GetActualToolFlangePose", "GetActualJointPosDegree", "GetToolCoordWithID",
    "GetWObjCoordWithID", "GetRobotErrorCode", "GetRobotCurJointsConfig",
    "GetRobotInstallPos", "GetTargetPayload", "GetTargetPayloadCog",
}


class ReadOnlyProxy:
    """XML-RPC proxy that refuses anything that is not a read-only query."""

    def __init__(self, ip: str, timeout: float = 3.0) -> None:
        import xmlrpc.client
        self._proxy = xmlrpc.client.ServerProxy(
            f"http://{ip}:{fr5_io.RPC_PORT}/RPC2",
            transport=fr5_io._TimeoutTransport(timeout), allow_none=True)
        self.calls: list[str] = []

    def __call__(self, method: str, *args):
        if method not in READ_ONLY_METHODS:
            raise PermissionError(f"{method} writes or moves; not callable here")
        self.calls.append(method)
        return getattr(self._proxy, method)(*args)


# --------------------------------------------------------------------------
# geometry
# --------------------------------------------------------------------------

def rpy_to_matrix(rx_deg: float, ry_deg: float, rz_deg: float) -> np.ndarray:
    """FAIRINO pose angles -> rotation matrix.

    robot_types.h documents rx/ry/rz as rotations about the FIXED axes, i.e.
    extrinsic XYZ. Extrinsic X then Y then Z composes as Rz @ Ry @ Rx.
    """
    rx, ry, rz = np.radians([rx_deg, ry_deg, rz_deg])
    cx, sx = np.cos(rx), np.sin(rx)
    cy, sy = np.cos(ry), np.sin(ry)
    cz, sz = np.cos(rz), np.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def solve_tcp(poses: list[dict]) -> dict:
    """Least-squares TCP offset from flange poses sharing one tip point."""
    n = len(poses)
    if n < 3:
        raise ValueError(f"need at least 3 poses, got {n}")

    A = np.zeros((3 * n, 6))
    b = np.zeros(3 * n)
    for i, p in enumerate(poses):
        R = rpy_to_matrix(p["rx"], p["ry"], p["rz"])
        A[3*i:3*i+3, 0:3] = R
        A[3*i:3*i+3, 3:6] = -np.eye(3)
        b[3*i:3*i+3] = -np.array([p["x"], p["y"], p["z"]])

    sol, *_ = np.linalg.lstsq(A, b, rcond=None)
    t, c = sol[:3], sol[3:]

    resid = []
    for p in poses:
        R = rpy_to_matrix(p["rx"], p["ry"], p["rz"])
        pred = R @ t + np.array([p["x"], p["y"], p["z"]])
        resid.append(float(np.linalg.norm(pred - c)))
    resid = np.array(resid)

    # Condition number says whether the orientations were spread enough to
    # separate t from c. A near-singular system returns a confident-looking
    # answer that is mostly arbitrary, so it has to be reported.
    cond = float(np.linalg.cond(A))
    return {
        "tcp_mm": t.tolist(), "cone_vertex_base_mm": c.tolist(),
        "residual_mm": {"per_pose": resid.tolist(), "rms": float(np.sqrt((resid**2).mean())),
                        "max": float(resid.max()), "mean": float(resid.mean())},
        "n_poses": n, "condition_number": cond,
        "orientation_spread_deg": orientation_spread(poses),
    }


def orientation_spread(poses: list[dict]) -> dict:
    """How much the flange orientation actually varied between poses."""
    zs = [rpy_to_matrix(p["rx"], p["ry"], p["rz"])[:, 2] for p in poses]
    angs = [float(np.degrees(np.arccos(np.clip(zs[i] @ zs[j], -1, 1))))
            for i in range(len(zs)) for j in range(i + 1, len(zs))]
    return {"max_pairwise_deg": max(angs) if angs else 0.0,
            "mean_pairwise_deg": float(np.mean(angs)) if angs else 0.0}


# --------------------------------------------------------------------------
# self-test
# --------------------------------------------------------------------------

def self_test() -> int:
    """Recover a known TCP from synthetic poses, before trusting real ones."""
    print("--- self-test: can the solver recover a TCP it was not told? ---")
    rng = np.random.default_rng(0)
    true_t = np.array([1.7, -2.3, 34.9])       # deliberately not the CAD value
    true_c = np.array([420.0, -110.0, 180.0])

    def make(rx, ry, rz):
        R = rpy_to_matrix(rx, ry, rz)
        p = true_c - R @ true_t
        return {"x": p[0], "y": p[1], "z": p[2], "rx": rx, "ry": ry, "rz": rz}

    sets = {
        "6 well-spread poses": [make(180, 0, 0), make(150, 0, 0), make(210, 0, 0),
                                make(180, 30, 0), make(180, -30, 0), make(165, 20, 45)],
        "4 poses (minimum)":   [make(180, 0, 0), make(155, 0, 0),
                                make(180, 25, 0), make(170, -20, 30)],
        "3 nearly identical":  [make(180, 0, 0), make(180.5, 0, 0), make(180, 0.5, 0)],
    }
    def noisy(poses, sd_mm=0.1, sd_deg=0.1):
        out = []
        for p in poses:
            q = dict(p)
            for k, sd in (("x", sd_mm), ("y", sd_mm), ("z", sd_mm),
                          ("rx", sd_deg), ("ry", sd_deg), ("rz", sd_deg)):
                q[k] += rng.normal(0, sd)
            out.append(q)
        return out

    # Noiseless data solves exactly even when badly conditioned, so it proves
    # nothing about robustness. The honest comparison adds realistic noise: the
    # condition number then predicts how far the answer actually drifts.
    ok = True
    print(f"  {'pose set':<22} {'exact err':>10} {'cond':>9} {'noisy err (mean of 100)':>24}")
    for name, poses in sets.items():
        r = solve_tcp(poses)
        exact = np.linalg.norm(np.array(r["tcp_mm"]) - true_t)
        errs = [np.linalg.norm(np.array(solve_tcp(noisy(poses))["tcp_mm"]) - true_t)
                for _ in range(100)]
        mean_err = float(np.mean(errs))
        degenerate = "identical" in name
        good = exact < 1e-6 and (mean_err > 5.0 if degenerate else mean_err < 1.0)
        ok &= good
        print(f"  {name:<22} {exact:>10.1e} {r['condition_number']:>9.1f} "
              f"{mean_err:>21.3f} mm  {'as expected' if good else 'UNEXPECTED'}")
    print()
    print("    All three solve exactly on noiseless data — ill-conditioning does not")
    print("    show up there. With realistic noise the near-identical set degrades by")
    print("    orders of magnitude while the spread sets stay sub-millimetre. That is")
    print("    why the condition number is reported alongside the residual: a small")
    print("    residual on a degenerate pose set means nothing.")

    print("\n--- noise sensitivity (0.1 mm position, 0.1 deg orientation) ---")
    base = sets["6 well-spread poses"]
    errs = []
    for _ in range(200):
        noisy = []
        for p in base:
            q = dict(p)
            q["x"] += rng.normal(0, 0.1); q["y"] += rng.normal(0, 0.1); q["z"] += rng.normal(0, 0.1)
            q["rx"] += rng.normal(0, 0.1); q["ry"] += rng.normal(0, 0.1); q["rz"] += rng.normal(0, 0.1)
            noisy.append(q)
        errs.append(np.linalg.norm(np.array(solve_tcp(noisy)["tcp_mm"]) - true_t))
    errs = np.array(errs)
    print(f"  TCP error over 200 trials: mean {errs.mean():.3f} mm, "
          f"95th pct {np.percentile(errs,95):.3f} mm, max {errs.max():.3f} mm")

    print("\n--- rotation convention check ---")
    R = rpy_to_matrix(0, 0, 90)
    got, want = R @ np.array([1, 0, 0]), np.array([0, 1, 0])
    print(f"  Rz(90) applied to x_hat -> {np.round(got,9)}   expected {want}   "
          f"{'ok' if np.allclose(got, want) else 'WRONG'}")
    R = rpy_to_matrix(90, 0, 0)
    got, want = R @ np.array([0, 1, 0]), np.array([0, 0, 1])
    print(f"  Rx(90) applied to y_hat -> {np.round(got,9)}   expected {want}   "
          f"{'ok' if np.allclose(got, want) else 'WRONG'}")
    print(f"\n  self-test {'PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


# --------------------------------------------------------------------------
# phases
# --------------------------------------------------------------------------

def preflight(ip: str) -> bool:
    import re
    import subprocess
    out = subprocess.run(["ip", "route", "get", ip], capture_output=True,
                         text=True, timeout=5).stdout
    dflt = subprocess.run(["ip", "route", "show", "default"], capture_output=True,
                          text=True, timeout=5).stdout
    dev = re.search(r"\bdev\s+(\S+)", out)
    dd = re.search(r"\bdev\s+(\S+)", dflt)
    dev = dev.group(1) if dev else None
    ok = bool(dev and dev.startswith(("en", "eth")) and dev != (dd.group(1) if dd else None))
    print(f"  route to {ip}: {out.strip().splitlines()[0] if out.strip() else 'none'}")
    print(f"  {'PASS' if ok else 'FAIL — that is the general network, not the robot wire'}")
    return ok


def phase_connect(a) -> int:
    rc = yaml.safe_load(open(ROBOT_CFG))
    ip = a.ip or rc["robot"]["ip"]
    print("--- Step 1: read-only connection ---")
    if not preflight(ip):
        print("\nREFUSING to connect. Fix the route first; see")
        print("docs/robot_ft_integration_status.md section 3.")
        return 2

    robot = RobotInterface(ip=ip, dry_run=False, allow_real_motion=False)
    q = ReadOnlyProxy(ip)
    rec: dict = {"timestamp": datetime.now().isoformat(), "robot_ip": ip}
    import time
    robot.connect(read_only=True)
    try:
        time.sleep(a.settle)
        st = robot.get_robot_state()
        print(f"  robot_state {st.robot_state}, robot_mode {st.robot_mode} "
              f"({'manual' if st.robot_mode == 1 else 'auto' if st.robot_mode == 0 else '?'})")
        print(f"  error main={st.main_code} sub={st.sub_code}, "
              f"e-stop={st.emergency_stop}, collision={st.collision_state}")
        rec["robot_state"] = {"robot_state": st.robot_state, "robot_mode": st.robot_mode,
                              "main_code": st.main_code, "sub_code": st.sub_code,
                              "emergency_stop": st.emergency_stop,
                              "collision_state": st.collision_state,
                              "safety_stop0": st.safety_stop0,
                              "safety_stop1": st.safety_stop1}
        for label, meth, args in (("active tool id", "GetActualTCPNum", (0,)),
                                  ("active wobj id", "GetActualWObjNum", (0,)),
                                  ("TCP pose", "GetActualTCPPose", (0,)),
                                  ("flange pose", "GetActualToolFlangePose", (0,))):
            try:
                v = q(meth, *args)
                rec.setdefault("queries", {})[meth] = v
                print(f"  {label:<16}: {v}")
            except Exception as exc:
                rec.setdefault("queries", {})[meth] = f"ERROR {exc}"
                print(f"  {label:<16}: failed — {exc}")
        raw = rec.get("queries", {}).get("GetActualTCPNum")
        tid = raw[1] if isinstance(raw, list) and len(raw) > 1 and raw[0] == 0 else raw
        if isinstance(tid, int):
            try:
                v = q("GetToolCoordWithID", tid)
                rec.setdefault("queries", {})["GetToolCoordWithID"] = v
                print(f"  tool {tid} frame     : {v}   (relative to the FLANGE)")
            except Exception as exc:
                print(f"  tool {tid} frame     : failed — {exc}")
    finally:
        robot.disconnect()
        rec["xmlrpc_methods_called"] = sorted(set(q.calls))
        print(f"  disconnected; methods called: {rec['xmlrpc_methods_called']}")

    print("\n--- Step 2: backup ---")
    run = start_run()
    rec["run"] = {
        "run_id": a.run_id,
        "purpose": a.purpose,
        "directory": str(run),
        "independent_of_previous_runs": True,
        "indenter_reinstalled_since_previous_run": a.reinstalled,
        "previous_run": a.previous_run,
        "note": ("this run reuses no earlier pose and overwrites no earlier file; "
                 "the earlier run stays exactly as recorded"),
    }
    rec["indenter"] = INDENTER
    rec["historical_indenter_superseded"] = HISTORICAL_INDENTER
    rec["fixture"] = {"cone": CONE}
    rec["cad_tcp_mm"] = CAD_TCP_MM.tolist()
    rec["cad_status"] = ("design intent, not ground truth — it is the value this "
                         "calibration measures against, never a fallback")
    rec["physical_error_sources"] = ERROR_SOURCES
    rec["pose_source"] = "GetActualToolFlangePose"
    rec["robot_config_snapshot"] = rc
    rec["coordinate_convention"] = {
        "position": "mm", "orientation": "deg",
        "rpy": "fixed-axis (extrinsic) XYZ; R = Rz @ Ry @ Rx",
        "pose_order": "[x, y, z, rx, ry, rz]",
        "tool_frame_reference": "tool coordinates are relative to the flange, not the base"}
    rec["nothing_written"] = True
    (run / "backup.yaml").write_text(yaml.safe_dump(
        json.loads(json.dumps(rec, default=str)), sort_keys=False, allow_unicode=True))
    print(f"  written: {run}/backup.yaml   (new file; nothing overwritten)")
    return 0


def phase_capture(a) -> int:
    """Record exactly one pose and exit.

    The interactive loop in --phase record holds the connection open and asks the
    operator to drive it. This variant does one pose per invocation instead, so
    the teaching can be conducted as a conversation: the operator is asked for a
    pose, takes it, says so, and this runs once to capture it.
    """
    rc = yaml.safe_load(open(ROBOT_CFG))
    ip = a.ip or rc["robot"]["ip"]
    if a.reset and POSES.is_file():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = POSES.with_name(f"_recorded_poses_archived_{stamp}.json")
        archive.write_text(POSES.read_text())
        POSES.unlink()
        print(f"  --reset: previous pose set archived to {archive.name}")
        print("  starting an independent run; no earlier pose is reused.")
    if not preflight(ip):
        print("\nREFUSING to connect.")
        return 2

    poses = json.loads(POSES.read_text()) if POSES.is_file() else []
    if a.drop:
        if not poses:
            print("  nothing to drop")
            return 1
        gone = poses.pop()
        POSES.write_text(json.dumps(poses, indent=2))
        print(f"  dropped the pose recorded at {gone['recorded_at']}; "
              f"{len(poses)} remain")
        return 0

    robot = RobotInterface(ip=ip, dry_run=False, allow_real_motion=False)
    q = ReadOnlyProxy(ip)
    robot.connect(read_only=True)
    try:
        import time
        time.sleep(a.settle)
        st = robot.get_robot_state()
        if st.robot_state != 1 or st.main_code or st.emergency_stop:
            print(f"  robot_state={st.robot_state} error={st.main_code}/{st.sub_code} "
                  f"e-stop={st.emergency_stop} — not a settled stopped state; "
                  "pose NOT recorded")
            return 1
        # Two reads a moment apart. If the flange is still drifting, the pose is
        # not the one the operator taught, and averaging it away would hide that.
        v1 = q("GetActualToolFlangePose", 0)
        time.sleep(0.3)
        v2 = q("GetActualToolFlangePose", 0)
    finally:
        robot.disconnect()

    for v in (v1, v2):
        if not (isinstance(v, list) and len(v) >= 7 and v[0] == 0):
            print(f"  flange pose query returned {v}; pose NOT recorded")
            return 1
    drift = float(np.linalg.norm(np.array(v2[1:4]) - np.array(v1[1:4])))
    if drift > 0.05:
        print(f"  flange moved {drift:.3f} mm between two reads; still settling. "
              "pose NOT recorded — hold still and re-run.")
        return 1

    p = {"x": v2[1], "y": v2[2], "z": v2[3], "rx": v2[4], "ry": v2[5], "rz": v2[6],
         "recorded_at": datetime.now().isoformat(),
         "static_check_mm": drift}

    if a.distinct_from:
        prior = json.loads(Path(a.distinct_from).read_text())
        here = np.array([p["x"], p["y"], p["z"]])
        near = min(((float(np.linalg.norm(here - np.array([q["x"], q["y"], q["z"]]))), j + 1)
                    for j, q in enumerate(prior)), default=None)
        if near and near[0] < 1.0:
            print(f"  this pose is {near[0]:.2f} mm from pose {near[1]} of the previous "
                  "run — that is the same pose, not a new one. NOT recorded.")
            return 1
        if near:
            print(f"    nearest previous-run pose: {near[0]:.1f} mm away (pose {near[1]})")
    poses.append(p)
    POSES.parent.mkdir(parents=True, exist_ok=True)
    POSES.write_text(json.dumps(poses, indent=2))

    print(f"  pose {len(poses)} recorded   (static to {drift:.3f} mm)")
    print(f"    x={p['x']:9.3f}  y={p['y']:9.3f}  z={p['z']:9.3f}")
    print(f"    rx={p['rx']:8.3f} ry={p['ry']:8.3f} rz={p['rz']:8.3f}")
    if len(poses) >= 2:
        sp = orientation_spread(poses)
        print(f"    orientation spread so far: max {sp['max_pairwise_deg']:.1f} deg, "
              f"mean {sp['mean_pairwise_deg']:.1f} deg")
    if len(poses) >= 3:
        try:
            sol = solve_tcp(poses)
            print(f"    running estimate: TCP {np.round(sol['tcp_mm'], 3)} mm, "
                  f"rms {sol['residual_mm']['rms']:.3f} mm, "
                  f"cond {sol['condition_number']:.0f}")
        except Exception as exc:
            print(f"    (no estimate yet: {exc})")
    return 0


def phase_record(a) -> int:
    rc = yaml.safe_load(open(ROBOT_CFG))
    ip = a.ip or rc["robot"]["ip"]
    print("--- Step 3: record operator-taught poses ---")
    print()
    print("  YOU position the robot. This script only reads the pose back.")
    print("  It issues no motion command of any kind.")
    print()
    print("  For each pose, in this order:")
    print("    1. retract the tip fully clear of the cone")
    print("    2. change the robot orientation while clear of the fixture")
    print("    3. approach slowly and seat the printed tip lightly in the cone")
    print("    4. let robot and fixture settle, then press Enter here")
    print()
    print("  Do NOT re-orient while the tip is constrained in the cone. Seating it")
    print("  and then twisting drags the tip across the cone face, which moves the")
    print("  very point the solver assumes is fixed.")
    print()
    print("  Suggested orientations — retract fully between each one:")
    for i, d in enumerate((
            "flange approximately normal to the cone",
            "roll +30 deg", "roll -30 deg",
            "pitch +30 deg", "pitch -30 deg",
            "combined roll and pitch"), 1):
        print(f"    {i}. {d}")
    print()
    if not preflight(ip):
        print("\nREFUSING to connect.")
        return 2

    robot = RobotInterface(ip=ip, dry_run=False, allow_real_motion=False)
    q = ReadOnlyProxy(ip)
    if a.reset and POSES.is_file():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        archive = POSES.with_name(f"_recorded_poses_archived_{stamp}.json")
        archive.write_text(POSES.read_text())
        POSES.unlink()
        print(f"  --reset: previous pose set archived to {archive.name}")
        print("  starting an independent run; no earlier pose is reused.")
        print()
    poses = json.loads(POSES.read_text()) if POSES.is_file() else []
    if poses:
        print(f"  {len(poses)} pose(s) already recorded; new ones are appended.")
        print("  pass --reset if you meant to start an independent run.")
    robot.connect(read_only=True)
    try:
        import time
        time.sleep(a.settle)
        while True:
            try:
                r = input(f"  pose {len(poses)+1}: Enter to record, 'd' to drop the last, "
                          f"'q' to finish: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                break
            if r == "q":
                break
            if r == "d":
                if poses:
                    poses.pop()
                    print(f"    dropped; {len(poses)} remain")
                continue
            v = q("GetActualToolFlangePose", 0)
            if not (isinstance(v, list) and len(v) >= 7 and v[0] == 0):
                print(f"    flange pose query returned {v}; not recorded")
                continue
            p = {"x": v[1], "y": v[2], "z": v[3], "rx": v[4], "ry": v[5], "rz": v[6],
                 "recorded_at": datetime.now().isoformat()}
            poses.append(p)
            print(f"    recorded  x={p['x']:.3f} y={p['y']:.3f} z={p['z']:.3f}  "
                  f"rx={p['rx']:.3f} ry={p['ry']:.3f} rz={p['rz']:.3f}")
            if len(poses) >= 3:
                try:
                    s = solve_tcp(poses)
                    print(f"    running estimate: TCP {np.round(s['tcp_mm'],3)} mm, "
                          f"rms {s['residual_mm']['rms']:.3f} mm, "
                          f"cond {s['condition_number']:.0f}")
                except Exception as exc:
                    print(f"    (no estimate yet: {exc})")
    finally:
        robot.disconnect()
    POSES.parent.mkdir(parents=True, exist_ok=True)
    POSES.write_text(json.dumps(poses, indent=2))
    print(f"\n  {len(poses)} pose(s) saved to {POSES}")
    print("  run --phase compute when you have at least 4, preferably 6-8.")
    return 0


def phase_compute(a) -> int:
    if not POSES.is_file():
        print(f"no recorded poses at {POSES}; run --phase record first")
        return 2
    poses = json.loads(POSES.read_text())
    print(f"--- Step 4: TCP from {len(poses)} recorded pose(s) ---")
    if len(poses) < 4:
        print(f"  WARNING: {len(poses)} poses. Four is the minimum, six to eight preferred.")
    s = solve_tcp(poses)
    t = np.array(s["tcp_mm"])
    d = t - CAD_TCP_MM

    print()
    print(f"{'':>22} {'X':>10} {'Y':>10} {'Z':>10}   (mm)")
    print(f"{'calibrated TCP':>22} {t[0]:>10.3f} {t[1]:>10.3f} {t[2]:>10.3f}")
    print(f"{'CAD estimate':>22} {CAD_TCP_MM[0]:>10.3f} {CAD_TCP_MM[1]:>10.3f} "
          f"{CAD_TCP_MM[2]:>10.3f}")
    print(f"{'difference':>22} {d[0]:>10.3f} {d[1]:>10.3f} {d[2]:>10.3f}"
          f"   |d| = {np.linalg.norm(d):.3f} mm")
    print()
    print("  TCP orientation: NOT DETERMINED, and not determinable this way.")
    print("  A sphere in a cone fixes a point but carries no orientation. The")
    print("  tool frame rotation stays zero relative to the flange. If a rotated")
    print("  tool frame is needed, use the FR5 six-point method instead.")
    print()
    print("--- Step 5: residuals and confidence ---")
    r = s["residual_mm"]
    print(f"  rms residual      : {r['rms']:.4f} mm")
    print(f"  max residual      : {r['max']:.4f} mm")
    print(f"  per pose          : {' '.join(f'{x:.3f}' for x in r['per_pose'])}")
    print(f"  condition number  : {s['condition_number']:.1f}")
    sp = s["orientation_spread_deg"]
    print(f"  orientation spread: max {sp['max_pairwise_deg']:.1f} deg between flange z axes, "
          f"mean {sp['mean_pairwise_deg']:.1f} deg")
    print()
    # -- cumulative convergence ------------------------------------------
    print("--- cumulative convergence (poses added one at a time) ---")
    print(f"{'n':>4} {'X':>9} {'Y':>9} {'Z':>10} {'rms':>8} {'cond':>8}")
    convergence = []
    for n in range(3, len(poses) + 1):
        c = solve_tcp(poses[:n])
        convergence.append({"n": n, "tcp_mm": c["tcp_mm"],
                            "rms_mm": c["residual_mm"]["rms"],
                            "condition_number": c["condition_number"]})
        print(f"{n:>4} {c['tcp_mm'][0]:>9.3f} {c['tcp_mm'][1]:>9.3f} "
              f"{c['tcp_mm'][2]:>10.3f} {c['residual_mm']['rms']:>8.3f} "
              f"{c['condition_number']:>8.1f}")
    print()

    # -- leave-one-out ----------------------------------------------------
    print("--- leave-one-out: how far does the answer move without each pose? ---")
    print(f"{'drop':>5} {'X':>9} {'Y':>9} {'Z':>10} {'shift':>8} {'rms':>8} {'cond':>8}")
    loo, shifts = [], []
    for i in range(len(poses)):
        c = solve_tcp([q for j, q in enumerate(poses) if j != i])
        ti = np.array(c["tcp_mm"])
        sh = float(np.linalg.norm(ti - t))
        shifts.append(sh)
        loo.append({"dropped_pose": i + 1, "tcp_mm": c["tcp_mm"], "shift_mm": sh,
                    "rms_mm": c["residual_mm"]["rms"],
                    "condition_number": c["condition_number"]})
        print(f"{i+1:>5} {ti[0]:>9.3f} {ti[1]:>9.3f} {ti[2]:>10.3f} {sh:>8.3f} "
              f"{c['residual_mm']['rms']:>8.3f} {c['condition_number']:>8.1f}")
    max_shift = max(shifts)
    print(f"\n  largest shift {max_shift:.3f} mm "
          f"-> {'no single pose dominates the fit' if max_shift < 0.5 else 'ONE POSE DOMINATES'}")
    print()

    # -- comparison with a previous run -----------------------------------
    comparison = None
    if a.compare_with:
        prev_path = Path(a.compare_with)
        prev = yaml.safe_load(open(prev_path))
        pt = np.array(prev["result"]["tcp_mm"])
        dr = t - pt
        comparison = {
            "previous_run": str(prev_path),
            "previous_tcp_mm": pt.tolist(),
            "delta_mm": dr.tolist(),
            "delta_xy_magnitude_mm": float(np.hypot(dr[0], dr[1])),
            "delta_3d_mm": float(np.linalg.norm(dr)),
            "previous_vs_cad_mm": (pt - CAD_TCP_MM).tolist(),
            "previous_rms_mm": prev["residual_mm"]["rms"],
            "previous_condition_number": prev["condition_number"],
        }
        print("--- comparison with the previous run ---")
        print(f"  previous : {prev_path}")
        print(f"{'':>18} {'X':>10} {'Y':>10} {'Z':>10}")
        print(f"{'this run':>18} {t[0]:>10.3f} {t[1]:>10.3f} {t[2]:>10.3f}")
        print(f"{'previous run':>18} {pt[0]:>10.3f} {pt[1]:>10.3f} {pt[2]:>10.3f}")
        print(f"{'difference':>18} {dr[0]:>10.3f} {dr[1]:>10.3f} {dr[2]:>10.3f}")
        print(f"    XY magnitude {np.hypot(dr[0], dr[1]):.3f} mm, "
              f"3D {np.linalg.norm(dr):.3f} mm")
        print(f"    rms  this {r['rms']:.3f} mm  vs previous "
              f"{prev['residual_mm']['rms']:.3f} mm")
        print(f"    cond this {s['condition_number']:.1f}   vs previous "
              f"{prev['condition_number']:.1f}")
        print(f"    previous run vs CAD: {np.round(pt - CAD_TCP_MM, 3)} mm")
        print()

    flags = []
    if max_shift > 0.5:
        flags.append(f"one pose moves the answer by {max_shift:.2f} mm; the fit leans on it")
    rp = np.array(r["per_pose"])
    if rp.size > 3 and rp.max() > rp.mean() + 3 * rp.std():
        flags.append(f"pose {int(rp.argmax())+1} residual {rp.max():.3f} mm is an outlier "
                     "against the others; reported as measured, not removed")
    if s["condition_number"] > 1e3:
        flags.append("condition number is high: the orientations were too similar, so the "
                     "fit is poorly determined regardless of how small the residual looks")
    if sp["max_pairwise_deg"] < 30:
        flags.append(f"only {sp['max_pairwise_deg']:.0f} deg of orientation spread; "
                     "30-60 deg between the extreme poses is what makes this method work")
    if r["rms"] > 1.0:
        flags.append(f"rms {r['rms']:.2f} mm is large: the tip probably shifted in the "
                     "cone between poses, or a pose was taught off-vertex")
    if len(poses) < 4:
        flags.append("fewer than four poses")
    for f in flags:
        print(f"  ! {f}")
    if not flags:
        print("  no warnings; the fit is well conditioned and consistent")
    print()
    print("  NOT applied to the robot. Writing a tool frame is a separate, deliberate act.")

    run = active_run()
    (run / "tcp_result.yaml").write_text(yaml.safe_dump({
        "timestamp": datetime.now().isoformat(),
        "method": ("least-squares sphere-in-cone: R_i t + p_i = c solved for [t; c] "
                   "over all poses"),
        "poses": poses,
        "result": {"tcp_mm": s["tcp_mm"],
                   "tcp_orientation": "not determined; a sphere carries no orientation",
                   "cone_vertex_base_mm": s["cone_vertex_base_mm"]},
        "cad_estimate_mm": CAD_TCP_MM.tolist(),
        "difference_from_cad_mm": d.tolist(),
        "difference_norm_mm": float(np.linalg.norm(d)),
        "residual_mm": r,
        "condition_number": s["condition_number"],
        "orientation_spread_deg": sp,
        "warnings": flags,
        "cumulative_convergence": convergence,
        "leave_one_out": loo,
        "leave_one_out_max_shift_mm": max_shift,
        "comparison": comparison,
        "indenter": INDENTER,
        "historical_indenter_superseded": HISTORICAL_INDENTER,
        "fixture": {"cone": CONE},
        "physical_error_sources": ERROR_SOURCES,
        "tcp_orientation": {"status": "not calibrated",
                            "assumption": "flange-aligned",
                            "reason": ("a sphere seated in a cone constrains position only; "
                                       "no orientation information exists in the constraint")},
        "pose_source": "GetActualToolFlangePose",
        "applied_to_robot": False,
        "robot_moved": False,
    }, sort_keys=False, allow_unicode=True))
    print(f"  written: {run}/tcp_result.yaml")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=("connect", "record", "capture", "compute"))
    ap.add_argument("--distinct-from", default=None,
                    help="archived pose file from an earlier run; refuse to record a "
                         "pose that merely repeats one of its poses")
    ap.add_argument("--drop", action="store_true",
                    help="with --phase capture: discard the most recent pose")
    ap.add_argument("--reset", action="store_true",
                    help="archive any existing pose set and start a fresh run")
    ap.add_argument("--run-id", default=None,
                    help="label for this run, e.g. Run3")
    ap.add_argument("--purpose", default=None,
                    help="what this run is for, recorded in metadata")
    ap.add_argument("--reinstalled", action="store_true",
                    help="set if the indenter was removed or re-seated since the "
                         "previous run; changes how a run-to-run difference reads")
    ap.add_argument("--previous-run", default=None,
                    help="path to the earlier run, recorded in metadata for traceability")
    ap.add_argument("--compare-with", default=None,
                    help="path to a previous tcp_result.yaml to compare against")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--settle", type=float, default=2.0)
    ap.add_argument("--ip", default=None)
    a = ap.parse_args()
    print(BANNER)
    print()
    if a.self_test:
        return self_test()
    if not a.phase:
        ap.error("give --phase or --self-test")
    return {"connect": phase_connect, "record": phase_record, "capture": phase_capture,
            "compute": phase_compute}[a.phase](a)


if __name__ == "__main__":
    raise SystemExit(main())
