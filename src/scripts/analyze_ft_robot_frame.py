#!/usr/bin/env python3
"""
Report what is known, and what is still missing, to express ATI wrench data in
the robot's frame.

Read-only in every sense: opens no DAQ task, opens no robot connection, moves
nothing, and writes nothing outside data/rig/frame_analysis/. It applies NO
transformation — the point is to establish what a transformation would need
before any is written.

    /usr/bin/python3 src/scripts/analyze_ft_robot_frame.py
    /usr/bin/python3 src/scripts/analyze_ft_robot_frame.py --excitation-run <dir>

WHY THIS RIG IS NOT THE USUAL CASE
----------------------------------
The common arrangement is an F/T sensor bolted to the robot flange, where the
sensor frame rides with the TCP and the transform of interest is
sensor -> flange -> TCP.

Here the sensor is stationary and the robot moves against it:

    VBTS -> 3D printed holder -> ATI Mini45 -> mount -> optical table

So the transform of interest is a FIXED rigid transform between the ATI sensor
frame and the ROBOT BASE frame. It does not change as the robot moves, which
makes it easier to determine but means it cannot be read out of the robot's
tool or workpiece frame registers — those describe the robot's own end
effector, not a table-mounted sensor.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vbts_platform.ati_calibration import SENSOR_FRAME, WRENCH_AXES  # noqa: E402
from vbts_platform.ft_interface import load_calibration, load_ft_config  # noqa: E402

BANNER = """\
==========================================
ATI <-> ROBOT FRAME ANALYSIS

READ-ONLY
NO ROBOT CONNECTION
NO ROBOT MOTION
NO DAQ ACQUISITION
=========================================="""

OUT = PROJECT_ROOT / "data" / "rig" / "frame_analysis"
ROBOT_CFG = PROJECT_ROOT / "src" / "config" / "robot_config.yaml"
DEFAULT_EXCITATION = PROJECT_ROOT / "data" / "rig" / "manual_ft_excitation_final"


def latest_excitation(root: Path) -> Path | None:
    if not root.is_dir():
        return None
    runs = sorted(d for d in root.iterdir() if d.is_dir() and (d / "summary.yaml").is_file())
    return runs[-1] if runs else None


def report_ft_frame(cfg: dict, cal, run: Path | None) -> dict:
    print("--- 1. ATI wrench output frame, as currently defined ---")
    print(f"  frame name    : {cfg['output']['frame']}  (constant SENSOR_FRAME = {SENSOR_FRAME})")
    print(f"  force unit    : {cfg['output']['force_unit']}")
    print(f"  torque unit   : {cfg['output']['torque_unit']}")
    print(f"  sensor        : ATI {cfg['ft_sensor']['model']} s/n {cal.serial}, {cal.part_number}")
    print(f"  calibration   : {cal.source_path.name}, native {cal.force_units}/{cal.torque_units}")
    print(f"  matrix source : UserAxis, BasicTransform Dz={cal.basic_transform.get('Dz')} m "
          f"already applied")
    print()
    print("  The <BasicTransform> in the calibration file means the wrench origin is NOT the")
    print("  sensor's mechanical mounting face: ATI has already shifted it along z. Any")
    print("  translation measured mechanically has to account for that offset.")
    print()

    conv = None
    if run is not None:
        s = yaml.safe_load(open(run / "summary.yaml"))
        conv = s.get("coordinate_interpretation")
    if not conv:
        print("  !! no excitation run with a coordinate interpretation was found")
        print("     run src/scripts/manual_ft_excitation_test.py first")
        return {}

    print("  Sign convention, established by manual excitation (Task 17):")
    print(f"    +Fx  <- {conv['Fx']['positive_direction']}")
    print(f"    +Fy  <- {conv['Fy']['positive_direction']}")
    print(f"    +Fz  <- compression is {conv['Fz']['compression_sign']}; "
          f"{conv['Fz']['implication']}")
    print(f"    +Tz  <- {conv['Tz']['positive_direction']}")
    print(f"    right-hand rule verified: {conv['right_hand_rule']['verified']}")
    print()
    print("  CAVEAT, and it is the important one: those directions are expressed relative to")
    print("  where the OPERATOR was standing. 'Left' and 'back' are not durable references.")
    print("  Before any transform can be built they must be re-expressed against something")
    print("  fixed — the optical table's axes, or the robot base itself.")
    print()
    return conv


def report_robot_frame() -> dict:
    print("--- 2. Robot frame information available ---")
    if not ROBOT_CFG.is_file():
        print(f"  {ROBOT_CFG} not found")
        return {}
    rc = yaml.safe_load(open(ROBOT_CFG))
    r = rc.get("robot", {})
    print(f"  controller ip     : {r.get('ip')}")
    print(f"  default tool id   : {r.get('default_tool_id')}   (FR5 tool coordinate register)")
    print(f"  default user id   : {r.get('default_user_frame_id')}   (FR5 workpiece register)")
    print(f"  units             : {r.get('units')}")
    print(f"  pose convention   : [x, y, z, rx, ry, rz], mm and deg, "
          f"fixed-axis (extrinsic) RPY")
    print(f"  operation_mode    : {r.get('operation_mode')}  "
          f"{'(still unverified)' if r.get('operation_mode') is None else ''}")
    print()
    print("  What the robot can report once connected read-only:")
    for name, what in (
        ("GetActualTCPPose", "TCP pose in the ROBOT BASE frame"),
        ("GetActualToolFlangePose", "flange pose in the ROBOT BASE frame"),
        ("GetActualTCPNum / GetActualWObjNum", "which tool / workpiece register is active"),
        ("GetToolCoordWithID", "a stored tool frame, relative to the flange"),
        ("GetForwardKin / GetInverseKin", "joint <-> Cartesian, both in the base frame"),
    ):
        print(f"    {name:<36} {what}")
    print()
    print("  None of these describes the ATI sensor. The FR5's tool and workpiece registers")
    print("  hold frames attached to the ROBOT; a table-mounted sensor is invisible to them.")
    print("  The sensor's pose has to be established by touching it with the robot, or by")
    print("  mechanical measurement.")
    print()
    return rc


def report_transform_requirements(conv: dict) -> dict:
    print("--- 3. What a transform would require ---")
    print()
    print("  Wanted:  W_base = [ R      0 ] W_sensor      (forces and torques rotate;")
    print("                     [ [t]xR  R ]               torques additionally pick up")
    print("                                                t x F from the origin shift)")
    print()
    print("  R : 3x3 rotation, ATI sensor frame -> robot base frame     3 DOF   UNKNOWN")
    print("  t : sensor origin expressed in the robot base frame        3 DOF   UNKNOWN")
    print()
    print("  Both are FIXED here, because the sensor is bolted to the table and the robot")
    print("  base does not move. Six numbers, measured once, valid until either is moved.")
    print()
    print("  Note the asymmetry: expressing FORCES in the base frame needs only R.")
    print("  Torques, and any statement about where contact occurred, additionally need t.")
    print()

    known, missing = [], []
    known.append("ATI wrench is a right-handed, self-consistent 6-axis frame (Task 17)")
    known.append("sign convention of every axis, relative to the operator's position")
    known.append("units are N and N*m, no scale factor anywhere in the chain")
    known.append("sensor is rigidly fixed to the optical table, so R and t are constant")
    missing.append("orientation of the ATI sensor frame with respect to the robot base (R)")
    missing.append("position of the ATI sensor origin in robot base coordinates (t)")
    missing.append("where the sensor's wrench origin sits physically, given that "
                   "<BasicTransform> already shifted it 6.858 mm along z")
    missing.append("the robot's own TCP calibration — the indenter tip is not yet defined, "
                   "so there is no known robot-side point to correlate against")
    missing.append("a durable reference for the axis directions: Task 17 fixed them relative "
                   "to the operator, not to the table or the robot")

    print("  KNOWN:")
    for k in known:
        print(f"    + {k}")
    print("  MISSING:")
    for m in missing:
        print(f"    - {m}")
    print()
    return {"known": known, "missing": missing}


def report_procedure() -> list:
    print("--- 4. Recommended order of work ---")
    steps = [
        ("TCP calibration of the indenter",
         "The robot needs a known point before it can be used to probe anything. "
         "Use the FR5's 4-point method (SetTcp4RefPoint / ComputeTcp4) on the "
         "steel-ball indenter. Until this exists there is no robot-side reference."),
        ("Establish R by axis-aligned probing",
         "With the sensor tared, press the indenter onto the VBTS along the robot base "
         "+X, then +Y, then +Z, one at a time. Each push gives a force direction in the "
         "sensor frame for a known direction in the base frame; three of them determine R. "
         "Orthonormalise the result and report the residual, which is the honest error bar."),
        ("Establish t by touching known points",
         "Move the TCP to several points on the sensor or its holder whose position is "
         "known in the sensor frame, and read the TCP pose in the base frame. "
         "Alternatively measure the mount geometry directly, remembering the 6.858 mm "
         "BasicTransform offset."),
        ("Verify with a load the transform did not see",
         "Apply a push along a direction not used to fit R and check that the transformed "
         "force points where the robot thinks it pushed. Fitting three directions and "
         "testing on a fourth is what separates a real calibration from a tautology."),
    ]
    for i, (t, d) in enumerate(steps, 1):
        print(f"  {i}. {t}")
        for line in textwrap.wrap(d, width=72):
            print(f"     {line}")
        print()
    return [{"step": t, "detail": d} for t, d in steps]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--excitation-run", default=None)
    args = ap.parse_args()

    print(BANNER)
    print()
    cfg, cfgp = load_ft_config()
    cal = load_calibration(cfg, cfgp)
    run = Path(args.excitation_run) if args.excitation_run else latest_excitation(DEFAULT_EXCITATION)
    if run:
        print(f"excitation reference: {run}")
        print()

    conv = report_ft_frame(cfg, cal, run)
    rc = report_robot_frame()
    req = report_transform_requirements(conv)
    steps = report_procedure()

    print("--- CONCLUSION ---")
    print("  No transformation is defined, and none should be written yet: R and t are")
    print("  both unmeasured, and the robot has no calibrated TCP to measure them with.")
    print(f"  All wrench data stays in {SENSOR_FRAME} until that work is done.")
    print()

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "frame_analysis.yaml").write_text(yaml.safe_dump({
        "generated_by": "src/scripts/analyze_ft_robot_frame.py",
        "ft_frame": {"name": cfg["output"]["frame"],
                     "force_unit": cfg["output"]["force_unit"],
                     "torque_unit": cfg["output"]["torque_unit"],
                     "sensor_serial": cal.serial,
                     "calibration_file": cal.source_path.name,
                     "basic_transform_m": cal.basic_transform,
                     "sign_convention": conv or None},
        "robot_frame": {"config_file": str(ROBOT_CFG),
                        "tool_id": rc.get("robot", {}).get("default_tool_id"),
                        "user_frame_id": rc.get("robot", {}).get("default_user_frame_id"),
                        "units": rc.get("robot", {}).get("units"),
                        "pose_convention": "[x,y,z,rx,ry,rz] mm/deg, fixed-axis RPY",
                        "tcp_calibrated": False,
                        "note": ("FR5 tool/workpiece registers describe frames attached to the "
                                 "robot; a table-mounted sensor is not visible to them")},
        "mounting": ("VBTS -> 3D printed holder -> ATI Mini45 -> mount -> optical table; "
                     "the sensor is stationary and the robot moves against it, so the "
                     "transform of interest is sensor -> robot base and is constant"),
        "transform_status": "NOT DEFINED — no transformation applied anywhere",
        "requirements": req,
        "recommended_procedure": steps,
        "robot_accessed": False,
        "daq_accessed": False,
    }, sort_keys=False, allow_unicode=True))
    print(f"written: {OUT}/frame_analysis.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
