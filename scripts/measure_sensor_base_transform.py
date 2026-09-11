#!/usr/bin/env python3
"""
Measure the fixed transform between the ATI sensor frame and the robot base.

The sensor is bolted to the table, so this transform is a constant: six numbers
measured once. Reads only — the robot is never commanded, the DAQ never outputs.

    measure_sensor_base_transform.py --self-test        # maths only, no hardware
    measure_sensor_base_transform.py --phase tare       # zero, nothing touching
    measure_sensor_base_transform.py --phase gravity    # known mass on the sensor
    measure_sensor_base_transform.py --phase press      # one press per invocation
    measure_sensor_base_transform.py --phase solve      # fit and report

WHY NOT THE PUSH METHOD IN ft_robot_frame_integration.md §5
-----------------------------------------------------------
That method presses laterally and reads the force direction. It needs a
compliant contact: on a rigid surface a sideways push measures normal force plus
friction, and the friction coefficient is unknown, so the measured direction is
not the pushed direction. With no VBTS mounted there is nothing compliant.

Pressing straight DOWN avoids this entirely. There is no sliding, so no
friction term, and the torque locates the contact point directly. For a contact
force that is essentially along the sensor's -Z:

    T = r x F,   F = (0, 0, -F)
    T_x = -F r_y                r_x =  T_y / F
    T_y =  F r_x       ==>      r_y = -T_x / F

So every press reports where it landed in SENSOR coordinates, while the robot
reports the same point in BASE coordinates. Several presses at different places
turn that into the rotation and the offset.

WHAT THIS CAN AND CANNOT DETERMINE
----------------------------------
Gravity fixes the sensor's z axis: two of the rotation's three degrees of
freedom, with no contact at all. Vertical presses supply the third (the azimuth
about vertical) and the sensor origin's position in the plane perpendicular to
its own z axis.

The origin's height ALONG the sensor z axis is invisible to a vertical press —
moving the origin up or down its own axis changes r_z, which a vertical force
produces no torque about. That component needs a lateral load (so, a compliant
contact) or a mechanical measurement. It is reported as undetermined rather
than quietly filled in.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

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

from vbts_platform.ft_interface import FTInterface  # noqa: E402

OUT = ROOT / "data" / "rig" / "frame_transform"
STATE = OUT / "_measurements.json"

# The press must be a real contact, mostly vertical, and gentle. A Mini45 takes
# 145 N on z; these bounds are about measurement quality, not sensor limits.
MIN_FORCE_N = 3.0
MAX_FORCE_N = 40.0
# Sideways force is wanted, not feared: it is the only thing that separates the
# sensor origin's height from its lateral position. The cap is about slipping,
# not about the model -- past roughly a third of the normal force a plastic tip
# breaks static friction, and a slipping contact is not where the robot says.
MAX_LATERAL_FRACTION = 0.45


def load_state() -> dict:
    if STATE.is_file():
        return json.loads(STATE.read_text())
    return {"tare": None, "gravity": None, "presses": []}


def save_state(s: dict) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(s, indent=2))


def read_tared(ft: FTInterface, state: dict, duration_s: float) -> np.ndarray:
    """Wrench with the stored zero removed.

    FTInterface.tare() keeps the zero on the instance, and every phase here runs
    as its own process, so that zero does not survive between them. The zero is
    written to the state file instead and subtracted here. Subtracting the tare
    WRENCH is equivalent to subtracting the tare volts because the calibration
    conversion is linear.
    """
    w = ft.read_wrench_mean(duration_s=duration_s, tared=False)
    t = state.get("tare")
    if not t:
        raise RuntimeError("no stored zero; run --phase tare first")
    return w - np.array(t["tare_wrench"], dtype=float)


def robot_read(ip: str) -> dict:
    """TCP pose in the base frame, plus the state that makes it trustworthy."""
    q = chk.ReadOnlyProxy(ip)
    tool = q("GetActualTCPNum", 0)
    tcp = q("GetActualTCPPose", 0)
    flange = q("GetActualToolFlangePose", 0)
    tool_coord = q("GetToolCoordWithID", tool[1]) if isinstance(tool, list) else None
    return {"active_tool": tool, "tcp_pose": tcp, "flange_pose": flange,
            "tool_coord": tool_coord}


def require_indenter_tool(r: dict) -> tuple[bool, str]:
    """GetActualTCPPose only means the indenter tip if the indenter tool is live."""
    t = r["active_tool"]
    if not (isinstance(t, list) and len(t) > 1 and t[0] == 0):
        return False, f"could not read the active tool: {t}"
    if t[1] == 0:
        return False, ("active tool is 0, so GetActualTCPPose reports the FLANGE, "
                       "not the indenter tip. Select tool 1 before measuring.")
    c = r["tool_coord"]
    if not (isinstance(c, list) and len(c) >= 4):
        return False, f"could not read tool {t[1]}: {c}"
    if abs(c[3]) < 1.0:
        return False, (f"tool {t[1]} has z offset {c[3]:.3f} mm, which is not the "
                       "indenter. Refusing to record a contact point from it.")
    return True, f"tool {t[1]}, z offset {c[3]:.3f} mm"


def contact_point_sensor(wrench: np.ndarray) -> tuple[np.ndarray, dict]:
    """Where the press landed, in sensor coordinates, from the torque it made.

    Returns (r_xy_mm, diagnostics). r_z is not recoverable from a vertical force.
    """
    F = wrench[:3]
    T = wrench[3:]
    fz = F[2]
    lateral = float(np.linalg.norm(F[:2]))
    mag = float(np.linalg.norm(F))
    # r_x = T_y / F ; r_y = -T_x / F, with F the downward magnitude (-fz).
    # N*m / N = m, so scale to mm.
    denom = -fz
    r_x = T[1] / denom * 1000.0
    r_y = -T[0] / denom * 1000.0
    return np.array([r_x, r_y]), {
        "force_magnitude_N": mag,
        "fz_N": float(fz),
        "lateral_N": lateral,
        "lateral_fraction": lateral / mag if mag > 0 else float("nan"),
    }


def drift_at(state: dict, when_iso: str) -> np.ndarray:
    """Zero offset at a moment, interpolated between the zero checks around it.

    The zero wanders. A press taken between two zero checks is corrected by
    where the drift had got to at that time, which turns a slow wander from an
    error into a measured and removed quantity. With no checks yet this is zero,
    and the fit simply carries the drift as residual.
    """
    checks = state.get("zero_checks") or []
    if not checks:
        return np.zeros(6)
    t0 = datetime.fromisoformat(state["tare"]["at"])
    pts = [(0.0, np.zeros(6))]
    for c in checks:
        pts.append(((datetime.fromisoformat(c["at"]) - t0).total_seconds(),
                    np.array(c["drift_wrench"], dtype=float)))
    pts.sort(key=lambda kv: kv[0])
    x = (datetime.fromisoformat(when_iso) - t0).total_seconds()
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (xa, va), (xb, vb) in zip(pts, pts[1:]):
        if xa <= x <= xb:
            f = 0.0 if xb == xa else (x - xa) / (xb - xa)
            return va + f * (vb - va)
    return pts[-1][1]


def fit_transform(gravity_sensor: np.ndarray, presses: list[dict]) -> dict:
    """Rotation sensor->base and the sensor origin, from gravity plus presses.

    Gravity is base -z exactly, so the direction it takes in the sensor frame
    fixes two of the rotation's three degrees of freedom. What remains is one
    angle psi about the vertical.

    For each press the contact point is known in base coordinates (the robot
    reports it, via the calibrated TCP) and the wrench is known in sensor
    coordinates. The two are tied together by

        T = r x F,     r = R(psi)^T (p - t)

    which is solved for psi and t together. The full cross product is used, not
    a vertical-force approximation: a press always carries some sideways force,
    and dropping the r_z F_xy terms would put that straight into the answer.
    Keeping them is also what makes t's component along the sensor z axis
    observable at all -- with a purely vertical force it is not.
    """
    g = np.asarray(gravity_sensor, dtype=float)
    g = g / np.linalg.norm(g)

    P = np.array([q["tcp_mm"][:3] for q in presses], dtype=float) / 1000.0   # m
    W = np.array([q.get("wrench_corrected", q["wrench"]) for q in presses],
                 dtype=float)
    F = W[:, :3]
    T = W[:, 3:]

    def rotation(psi_deg: float) -> np.ndarray:
        """Sensor->base rotation whose third row is -g, turned by psi about base z."""
        # Sensor axes expressed in base. Start from the sensor z direction implied
        # by gravity, then choose x and y by rotating about base z by psi.
        z_s_in_base = -g              # sensor z, in base coords? see below
        # g is base -z written in sensor coords, so R g = (0,0,-1) => R^T(0,0,-1)=g.
        # Build R by aligning its third ROW to -g, then applying the spin.
        c, s_ = np.cos(np.radians(psi_deg)), np.sin(np.radians(psi_deg))
        Rz = np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]])
        # A rotation taking the sensor z axis onto base z.
        v = np.cross(g, np.array([0.0, 0.0, -1.0]))
        s_n = np.linalg.norm(v)
        if s_n < 1e-12:
            A = np.eye(3)
        else:
            cth = float(g @ np.array([0.0, 0.0, -1.0]))
            vx = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
            A = np.eye(3) + vx + vx @ vx * ((1 - cth) / (s_n ** 2))
        return Rz @ A

    def solve_t(psi_deg: float):
        """With psi fixed the residual is linear in t, so t comes from lstsq."""
        R = rotation(psi_deg)
        Rt = R.T
        rows, rhs = [], []
        for i in range(len(presses)):
            Fi = F[i]
            Fx = np.array([[0, -Fi[2], Fi[1]], [Fi[2], 0, -Fi[0]], [-Fi[1], Fi[0], 0]])
            # T = (R^T p - R^T t) x F = [R^T p]x F - [R^T t]x F
            #   => T - (R^T p) x F = -(R^T t) x F = Fx @ (R^T t)
            rows.append(Fx @ Rt)
            rhs.append(T[i] - np.cross(Rt @ P[i], Fi))
        A = np.vstack(rows)
        b = np.concatenate(rhs)
        t, *_ = np.linalg.lstsq(A, b, rcond=None)
        res = A @ t - b
        return t, float(np.sqrt((res ** 2).mean())), A

    # psi enters only through a rotation, so a coarse sweep then a refinement is
    # both robust and enough; there is no gradient to get lost in.
    coarse = np.arange(-180.0, 180.0, 1.0)
    scores = [solve_t(v)[1] for v in coarse]
    best = float(coarse[int(np.argmin(scores))])
    for step in (0.1, 0.01, 0.001):
        grid = np.arange(best - 10 * step, best + 10 * step + step / 2, step)
        scores = [solve_t(v)[1] for v in grid]
        best = float(grid[int(np.argmin(scores))])

    t, rms_torque, A = solve_t(best)
    R = rotation(best)
    cond = float(np.linalg.cond(A))

    # Per-press geometry, and how well each one's torque is reproduced.
    r_s, per_press, pred_T = [], [], []
    for i in range(len(presses)):
        ri = R.T @ (P[i] - t)
        Ti = np.cross(ri, F[i])
        r_s.append((ri * 1000.0).tolist())
        pred_T.append(Ti.tolist())
        per_press.append(float(np.linalg.norm(Ti - T[i])))

    # A torque residual is easier to judge as the position error it implies.
    fmean = float(np.linalg.norm(F, axis=1).mean())
    pos_equiv_mm = [1000.0 * v / fmean for v in per_press]

    return {
        "rotation_sensor_to_base": R.tolist(),
        "azimuth_psi_deg": best,
        "gravity_direction_in_sensor": g.tolist(),
        "sensor_z_tilt_from_vertical_deg": float(
            np.degrees(np.arccos(np.clip(-g[2], -1, 1)))),
        "origin_base_mm": (t * 1000.0).tolist(),
        "contact_points_sensor_mm": r_s,
        "residual_torque_Nm": {"per_press": per_press,
                               "rms": rms_torque,
                               "max": float(max(per_press))},
        "residual_position_equivalent_mm": {
            "per_press": pos_equiv_mm,
            "rms": float(np.sqrt(np.mean(np.square(pos_equiv_mm)))),
            "max": float(max(pos_equiv_mm))},
        "condition_number": cond,
        "n_presses": len(presses),
        "mean_force_N": fmean,
        "lateral_fractions": [float(np.linalg.norm(F[i][:2]) / np.linalg.norm(F[i]))
                              for i in range(len(presses))],
        "press_spread_mm": float(
            np.linalg.norm(P[:, :2] - P[:, :2].mean(axis=0), axis=1).max() * 2000.0),
        "orthonormality_error": float(np.abs(R @ R.T - np.eye(3)).max()),
        "determinant": float(np.linalg.det(R)),
    }


def self_test() -> int:
    """Recover a known transform from synthetic presses, with realistic noise.

    The presses carry a sideways component on purpose. A solver that assumed a
    purely vertical force would fail this test, which is the point: the first
    real press measured 15 % lateral.
    """
    print("--- self-test: recover a known transform from synthetic presses ---")
    rng = np.random.default_rng(11)
    psi_true = 37.0
    c, s_ = np.cos(np.radians(psi_true)), np.sin(np.radians(psi_true))
    tilt = np.radians(0.635)                       # the measured sensor tilt
    A = np.array([[1, 0, 0],
                  [0, np.cos(tilt), -np.sin(tilt)],
                  [0, np.sin(tilt), np.cos(tilt)]])
    R_true = np.array([[c, -s_, 0.0], [s_, c, 0.0], [0.0, 0.0, 1.0]]) @ A
    t_true = np.array([0.040, 0.360, 0.010])       # m

    presses = []
    for dx, dy in ((0, 0), (20, 0), (0, 20), (-18, 14), (12, -19)):
        r_s = np.array([dx, dy, 22.0]) / 1000.0    # contact 22 mm up the sensor z
        p_base = t_true + R_true @ r_s
        f = 8.0 + rng.normal(0, 1.0)
        F_s = np.array([rng.normal(0, 0.15 * f), rng.normal(0, 0.15 * f), -f])
        T_s = np.cross(r_s, F_s)
        F_s = F_s + rng.normal(0, 0.02, 3)         # force noise, measured
        T_s = T_s + rng.normal(0, 5e-4, 3)         # torque noise, measured
        presses.append({"tcp_mm": (p_base * 1000.0).tolist(),
                        "wrench": np.concatenate([F_s, T_s]).tolist()})

    g_sensor = R_true.T @ np.array([0.0, 0.0, -1.0])
    fit = fit_transform(g_sensor, presses)
    dpsi = abs(fit["azimuth_psi_deg"] - psi_true)
    dt = np.linalg.norm(np.array(fit["origin_base_mm"]) - t_true * 1000.0)
    print(f"  psi     true {psi_true:.3f}   fitted {fit['azimuth_psi_deg']:.3f}   "
          f"error {dpsi:.3f} deg")
    print(f"  origin  true {np.round(t_true*1000,2)}   fitted "
          f"{np.round(fit['origin_base_mm'], 2)}")
    print(f"          error {dt:.3f} mm  (all three components, including the one")
    print(f"          a vertical-force-only solver cannot see)")
    print(f"  residual {fit['residual_position_equivalent_mm']['rms']:.3f} mm equivalent, "
          f"cond {fit['condition_number']:.1f}")

    # A solver that ignored the sideways force would be wrong by r_z * F_xy / F.
    print(f"\n  for contrast, the vertical-only approximation would misplace each")
    print(f"  contact by about r_z*|F_xy|/|F| = 22 * 0.15 = 3.3 mm")

    ok = dpsi < 1.0 and dt < 2.0
    print(f"\n  self-test {'PASSED' if ok else 'FAILED'}")
    return 0 if ok else 1


def phase_tare(a) -> int:
    print("--- zero the sensor: nothing may be touching it ---")
    print("  The holder's own weight is part of the zero, so it must be in place")
    print("  and the indenter must be clear of it.\n")
    ft = FTInterface.from_config()
    ft.connect()
    try:
        w = ft.tare(duration_s=a.seconds)
        tv = ft.tare_volts
        tv = tv.tolist() if tv is not None else None
        check = ft.read_wrench_mean(duration_s=1.0, tared=True)
    finally:
        ft.disconnect()
    print(f"  zero stored (untared wrench at zero): {np.round(w, 4)}")
    print(f"  residual after taring: {np.round(check, 4)}")
    print(f"  |F| {np.linalg.norm(check[:3]):.4f} N  |T| {np.linalg.norm(check[3:]):.6f} N*m")
    s = load_state()
    s["tare"] = {"at": datetime.now().isoformat(), "tare_wrench": w.tolist(),
                 "tare_volts": tv, "residual": check.tolist(),
                 "duration_s": a.seconds}
    s["presses"] = []
    s["gravity"] = None
    save_state(s)
    print("\n  press list cleared; gravity reading cleared.")
    return 0


def phase_zerocheck(a) -> int:
    """How far the zero has moved since it was set. Nothing may be touching.

    A torque zero that wanders shows up in the fit as a residual that does not
    shrink with more presses, because each press carries a different constant
    offset. Interleaving this between presses is what tells the two apart.
    """
    s = load_state()
    if not s.get("tare"):
        print("  no stored zero: --phase tare")
        return 2
    print("--- zero check: the indenter must be clear, holder empty ---\n")
    ft = FTInterface.from_config()
    ft.connect()
    try:
        w = read_tared(ft, s, a.seconds)
    finally:
        ft.disconnect()
    dF = float(np.linalg.norm(w[:3]))
    dT = float(np.linalg.norm(w[3:]))
    print(f"  drift F : {np.round(w[:3], 4)} N      |dF| {dF:.4f} N")
    print(f"  drift T : {np.round(w[3:], 5)} N*m    |dT| {dT:.5f} N*m")
    typical = 0.045
    print(f"\n  press-fit residual to explain: about {typical:.3f} N*m")
    if dT > 0.3 * typical:
        print(f"  the zero has moved {100*dT/typical:.0f} % of that. Drift is a real")
        print("  part of the residual; re-zero and interleave this check.")
    else:
        print(f"  the zero has moved only {100*dT/typical:.0f} % of that, so drift does")
        print("  not explain the residual. Look elsewhere.")
    s.setdefault("zero_checks", []).append(
        {"at": datetime.now().isoformat(), "drift_wrench": w.tolist(),
         "dF_N": dF, "dT_Nm": dT})
    save_state(s)
    return 0


def phase_gravity(a) -> int:
    s = load_state()
    if not s.get("tare"):
        print("  tare first: --phase tare")
        return 2
    print("--- gravity reference ---")
    print(f"  With the {a.mass_kg} kg mass resting on the holder and nothing else")
    print("  touching it. Gravity is base -Z exactly, so this fixes the sensor's")
    print("  z axis without any contact from the robot.\n")
    ft = FTInterface.from_config()
    ft.connect()
    try:
        w = read_tared(ft, s, a.seconds)
    finally:
        ft.disconnect()
    F = w[:3]
    mag = float(np.linalg.norm(F))
    expected = a.mass_kg * 9.80665
    print(f"  wrench: F {np.round(F, 4)} N   |F| {mag:.4f} N")
    print(f"  expected from {a.mass_kg} kg: {expected:.4f} N   "
          f"error {100*(mag-expected)/expected:+.2f} %")
    if mag < 0.5 * expected:
        print("\n  that is far below the expected weight — is the mass actually on?")
        print("  NOT recorded.")
        return 1
    g = F / mag
    tilt = float(np.degrees(np.arccos(np.clip(-g[2], -1, 1))))
    print(f"  gravity direction in sensor frame: {np.round(g, 5)}")
    print(f"  sensor z axis is {tilt:.3f} deg from vertical")
    s["gravity"] = {"at": datetime.now().isoformat(), "mass_kg": a.mass_kg,
                    "wrench": w.tolist(), "direction_in_sensor": g.tolist(),
                    "magnitude_N": mag, "expected_N": expected,
                    "tilt_from_vertical_deg": tilt}
    save_state(s)
    return 0


def phase_press(a) -> int:
    s = load_state()
    if not s.get("tare"):
        print("  tare first: --phase tare")
        return 2
    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    if not cal.preflight(ip):
        return 2

    if a.drop:
        if not s["presses"]:
            print("  nothing to drop")
            return 1
        s["presses"].pop()
        save_state(s)
        print(f"  dropped; {len(s['presses'])} remain")
        return 0

    r = robot_read(ip)
    ok, why = require_indenter_tool(r)
    print(f"  active tool check: {why}")
    if not ok:
        print("  NOT recorded.")
        return 1

    ft = FTInterface.from_config()
    ft.connect()
    try:
        w1 = read_tared(ft, s, a.seconds)
        r_mid = robot_read(ip)
        time.sleep(0.3)
        w2 = read_tared(ft, s, a.seconds)
    finally:
        ft.disconnect()

    drift = float(np.linalg.norm(w2[:3] - w1[:3]))
    w = (w1 + w2) / 2.0
    r_xy, diag = contact_point_sensor(w)

    print(f"  F {np.round(w[:3], 3)} N     |F| {diag['force_magnitude_N']:.3f} N")
    print(f"  T {np.round(w[3:], 5)} N*m")
    print(f"  lateral fraction {diag['lateral_fraction']:.3f}   "
          f"force drift between reads {drift:.3f} N")

    if diag["force_magnitude_N"] < MIN_FORCE_N:
        print(f"\n  only {diag['force_magnitude_N']:.2f} N — that is not a firm contact.")
        print(f"  press harder (aim for {MIN_FORCE_N}-{MAX_FORCE_N} N). NOT recorded.")
        return 1
    if diag["force_magnitude_N"] > MAX_FORCE_N:
        print(f"\n  {diag['force_magnitude_N']:.2f} N is harder than needed. Ease off "
              f"below {MAX_FORCE_N} N. NOT recorded.")
        return 1
    if diag["fz_N"] > 0:
        print("\n  Fz is positive — the sensor is being pulled up, not pressed down.")
        print("  NOT recorded.")
        return 1
    if diag["lateral_fraction"] > MAX_LATERAL_FRACTION:
        print(f"\n  {100*diag['lateral_fraction']:.0f} % of the force is sideways — past the")
        print("  point where a plastic tip holds. Ease off the lateral push a little;")
        print("  a slipping contact is not where the robot says it is. NOT recorded.")
        return 1
    if drift > 0.5:
        print(f"\n  force moved {drift:.2f} N between two reads — still settling.")
        print("  Hold still and re-run. NOT recorded.")
        return 1

    tcp = r_mid["tcp_pose"][1:]
    entry = {"at": datetime.now().isoformat(), "tcp_mm": tcp[:3], "tcp_rpy_deg": tcp[3:],
             "wrench": w.tolist(), "r_sensor_xy_mm": r_xy.tolist(),
             "diagnostics": diag, "force_drift_N": drift,
             "active_tool": r_mid["active_tool"], "tool_coord": r_mid["tool_coord"]}
    s["presses"].append(entry)
    save_state(s)

    print(f"\n  press {len(s['presses'])} recorded")
    print(f"    contact in BASE : {np.round(tcp[:3], 3)} mm")
    if len(s["presses"]) >= 2:
        P = np.array([q["tcp_mm"][:2] for q in s["presses"]])
        print(f"    base spread so far: {np.linalg.norm(P - P.mean(axis=0), axis=1).max()*2:.1f} mm")
    if s.get("gravity") and len(s["presses"]) >= 3:
        try:
            fit = fit_transform(np.array(s["gravity"]["direction_in_sensor"]), s["presses"])
            print(f"    running fit: psi {fit['azimuth_psi_deg']:.2f} deg, "
                  f"origin {np.round(fit['origin_base_mm'],2)} mm, "
                  f"residual {fit['residual_position_equivalent_mm']['rms']:.3f} mm, "
                  f"cond {fit['condition_number']:.0f}")
        except Exception as exc:
            print(f"    (no fit yet: {exc})")
    return 0


def phase_solve(a) -> int:
    s = load_state()
    if not s.get("gravity"):
        print("  no gravity reading: --phase gravity")
        return 2
    presses = s["presses"]
    if len(presses) < 3:
        print(f"  only {len(presses)} press(es); need at least 3, preferably 4-5")
        return 2

    g = np.array(s["gravity"]["direction_in_sensor"])
    for q in presses:
        q["drift_removed"] = drift_at(s, q["at"]).tolist()
        q["wrench_corrected"] = (np.array(q["wrench"])
                                 - np.array(q["drift_removed"])).tolist()
    nchk = len(s.get("zero_checks") or [])
    print(f"  zero checks available: {nchk}"
          + ("  (drift interpolated out of every press)" if nchk else
             "  — NO drift correction possible; residual will carry it"))
    if nchk:
        dmax = max(float(np.linalg.norm(np.array(q["drift_removed"])[3:]))
                   for q in presses)
        print(f"  largest torque drift removed: {dmax:.5f} N*m\n")
    fit_all = fit_transform(g, presses)

    use = presses
    if a.holdout and len(presses) >= 4:
        use = presses[:-1]
        print(f"  fitting on presses 1-{len(use)}, holding press {len(presses)} back "
              "for verification\n")
    fit = fit_transform(g, use)
    R = np.array(fit["rotation_sensor_to_base"])
    t = np.array(fit["origin_base_mm"])

    print("--- rotation, ATI sensor frame -> robot base ---")
    for row in R:
        print("   " + "  ".join(f"{v:+9.6f}" for v in row))
    print(f"\n  azimuth about vertical : {fit['azimuth_psi_deg']:+.3f} deg")
    print(f"  sensor z off vertical  : {fit['sensor_z_tilt_from_vertical_deg']:.3f} deg")
    print(f"  det {fit['determinant']:+.8f}   orthonormality "
          f"{fit['orthonormality_error']:.2e}")

    print("\n--- sensor origin, in robot base coordinates ---")
    print(f"  t = [{t[0]:+.3f}, {t[1]:+.3f}, {t[2]:+.3f}] mm")
    print("  This is the wrench origin, which the calibration's BasicTransform")
    print("  already shifted 6.858 mm off the mounting face. Do not apply that")
    print("  offset again.")

    print("\n--- fit quality ---")
    print(f"  presses used      : {fit['n_presses']}")
    print(f"  base spread       : {fit['press_spread_mm']:.1f} mm")
    print(f"  mean contact force: {fit['mean_force_N']:.2f} N")
    print(f"  lateral fractions : " +
          " ".join(f"{100*v:.0f}%" for v in fit["lateral_fractions"]))
    print(f"  condition number  : {fit['condition_number']:.1f}")
    pe = fit["residual_position_equivalent_mm"]
    print(f"  residual (as position error): rms {pe['rms']:.3f} mm, max {pe['max']:.3f} mm")
    print(f"  per press         : " + " ".join(f"{v:.3f}" for v in pe["per_press"]))

    print("\n--- contact points, in sensor coordinates ---")
    print(f"  {'#':>3} {'x':>9} {'y':>9} {'z':>9}")
    for i, r in enumerate(fit["contact_points_sensor_mm"], 1):
        print(f"  {i:>3} {r[0]:>9.3f} {r[1]:>9.3f} {r[2]:>9.3f}")

    verify = None
    if a.holdout and len(presses) >= 4:
        q = presses[-1]
        p_base = np.array(q["tcp_mm"][:3]) / 1000.0
        F = np.array(q["wrench"][:3])
        T_meas = np.array(q["wrench"][3:])
        r_pred = R.T @ (p_base - t / 1000.0)
        T_pred = np.cross(r_pred, F)
        err_T = float(np.linalg.norm(T_pred - T_meas))
        err_mm = 1000.0 * err_T / float(np.linalg.norm(F))
        verify = {"predicted_torque_Nm": T_pred.tolist(),
                  "measured_torque_Nm": T_meas.tolist(),
                  "error_Nm": err_T, "error_position_equivalent_mm": err_mm,
                  "contact_point_sensor_mm": (r_pred * 1000.0).tolist()}
        print("\n--- verification on the held-back press ---")
        print(f"  predicted torque : {np.round(T_pred, 5)} N*m")
        print(f"  measured  torque : {np.round(T_meas, 5)} N*m")
        print(f"  error            : {err_T:.6f} N*m  =  {err_mm:.3f} mm equivalent")
        ratio = err_mm / max(pe["rms"], 1e-9)
        print(f"  in-fit rms was {pe['rms']:.3f} mm, so this is {ratio:.1f}x that")
        print("  " + ("consistent with the fit's own accuracy — it generalises"
                      if ratio <= 2.0 else
                      "well beyond the fit's own accuracy — it does NOT generalise"))

    flags = []
    if fit["press_spread_mm"] < 15:
        flags.append(f"presses span only {fit['press_spread_mm']:.1f} mm; the azimuth "
                     "rests on a short baseline")
    if fit["condition_number"] > 50:
        flags.append(f"condition number {fit['condition_number']:.0f}; the presses are "
                     "too alike to separate the unknowns")
    if pe["rms"] > 1.0:
        flags.append(f"residual {pe['rms']:.2f} mm is large; contacts may have shifted")
    if all(v < 0.03 for v in fit["lateral_fractions"]):
        flags.append("every press was almost purely vertical, which leaves t's "
                     "component along the sensor z axis weakly determined")
    if verify and verify["error_position_equivalent_mm"] > 2.0 * pe["rms"]:
        flags.append(
            f"the held-back press misses by "
            f"{verify['error_position_equivalent_mm']/pe['rms']:.1f}x the in-fit rms; "
            "the fit does not extend to a press it has not seen")
    print("\n" + ("\n".join("  WARNING: " + f for f in flags) if flags
                  else "  no warnings"))

    run = OUT / datetime.now().strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    (run / "transform.yaml").write_text(yaml.safe_dump(json.loads(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "frames": {"from": "ATI_sensor_frame", "to": "robot_base"},
        "units": {"length": "mm", "angle": "deg", "force": "N", "torque": "N_m"},
        "usage": {
            "force":  "F_base = R @ F_sensor",
            "torque": "T_base = R @ T_sensor + cross(t, R @ F_sensor)",
            "point":  "p_base = R @ r_sensor + t",
            "inverse": "r_sensor = R.T @ (p_base - t)"},
        "method": ("gravity fixes the sensor z axis with no contact; vertical "
                   "presses tie base-frame contact points to sensor-frame torque "
                   "through T = r x F, solved for the azimuth and the origin"),
        "note_on_lateral_force": (
            "the full cross product is used. A vertical-force approximation would "
            "drop r_z*F_xy, which at the observed 15 % lateral and r_z ~ 22 mm is "
            "a 3 mm error per contact -- larger than the quantity being measured"),
        **fit,
        "fit_including_all_presses": fit_all,
        "verification_holdout": verify,
        "warnings": flags,
        "gravity": s["gravity"],
        "tare": s["tare"],
        "presses": presses,
        "basic_transform_note": (
            "t refers to the wrench origin. FT29831.cal's BasicTransform Dz=6.858 mm "
            "is already folded into the calibration matrix; do not apply it again"),
        "robot_moved": False,
        "daq_output": False,
    }, default=str)), sort_keys=False, allow_unicode=True))
    print(f"\n  written: {run}/transform.yaml")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", choices=("tare", "zerocheck", "gravity", "press", "solve"))
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--ip", default=None)
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--mass-kg", type=float, default=1.004)
    ap.add_argument("--drop", action="store_true")
    ap.add_argument("--holdout", action="store_true", default=True)
    ap.add_argument("--no-holdout", dest="holdout", action="store_false")
    a = ap.parse_args()

    print("=" * 58)
    print("ATI SENSOR -> ROBOT BASE TRANSFORM")
    print("  NO ROBOT MOTION   NO JOG   NO DAQ OUTPUT   NO TCP WRITE")
    print("=" * 58 + "\n")

    if a.self_test:
        return self_test()
    if not a.phase:
        ap.print_help()
        return 2
    return {"tare": phase_tare, "zerocheck": phase_zerocheck,
            "gravity": phase_gravity, "press": phase_press,
            "solve": phase_solve}[a.phase](a)


if __name__ == "__main__":
    raise SystemExit(main())
