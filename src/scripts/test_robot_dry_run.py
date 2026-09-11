#!/usr/bin/env python3
"""
Dry-run demonstration of RobotInterface. Touches no hardware whatsoever.

Runs a trivial Z-axis round trip through the interface so the command
formatting, the simulated state model and the safety gates can be seen working
before anything is ever connected to the robot.

    python3 src/scripts/test_robot_dry_run.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# The package lives under src/ and is NOT pip-installed (installing anything is
# out of scope). Three lines of explicit path setup beats requiring an install
# or scattering PYTHONPATH exports through the docs.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from vbts_platform import RobotInterface, RobotPose  # noqa: E402
from vbts_platform.robot_interface import MotionNotAllowedError  # noqa: E402

BANNER = """\
==================================
DRY RUN — NO ROBOT COMMANDS SENT
=================================="""

# A pose actually observed on this FR5 (from a teleop node log, 2026-07-06),
# used only to seed the simulation with realistic numbers. It is NOT a
# measurement of the robot's current position — the robot is powered off.
SEED_POSE = RobotPose(103.387, 362.701, 408.912, 95.3546, 56.8215, 177.060)


def main() -> int:
    # Route logging to stdout so the [DRY RUN] lines interleave with print() in
    # the order they actually happen. The default stderr handler makes the two
    # streams buffer independently, which scrambles the transcript when piped.
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    print(BANNER)
    print()

    robot = RobotInterface(initial_pose=SEED_POSE)
    print(f"dry_run           = {robot.dry_run}")
    print(f"allow_real_motion = {robot.allow_real_motion}")
    print(f"simulated         = {robot.simulated}")
    print()

    robot.connect(read_only=True)
    print()

    start = robot.get_tcp_pose()
    print(f"initial simulated pose : {start}")
    print()

    print("--- MoveL  +5 mm in Z ---")
    robot.move_linear(start.offset(dz=+5.0), vel=10.0)
    print(f"pose after +5 mm       : {robot.get_tcp_pose()}")
    print()

    print("--- MoveL  -5 mm in Z ---")
    robot.move_linear(robot.get_tcp_pose().offset(dz=-5.0), vel=10.0)
    print()

    final = robot.get_tcp_pose()
    print(f"final simulated pose   : {final}")
    print(f"returned to start      : {final.as_tuple() == start.as_tuple()}")
    print()

    # Show gate 2 refusing, without ever leaving dry-run territory.
    print("--- safety gate check (dry_run=False, allow_real_motion=False) ---")
    guarded = RobotInterface(dry_run=False, allow_real_motion=False)
    try:
        guarded.move_linear(SEED_POSE, joints=[0.0] * 6)
    except MotionNotAllowedError as exc:
        print(f"refused as expected: {type(exc).__name__}")
        print(f"  {str(exc).splitlines()[0]}")
    print()

    robot.disconnect()
    print()
    print(f"motion commands logged (all simulated): {len(robot.command_log)}")
    print("RPCs sent: 0    sockets opened: 0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
