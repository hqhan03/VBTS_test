#!/usr/bin/env python3
"""
Put the FR5 into the state protocol motion needs. Sends NO motion command.

    enable_protocol_motion.py --dry-run
    enable_protocol_motion.py --confirm ENABLE-MOTION --speed 5
    enable_protocol_motion.py --restore            # back to manual (servos stay on)
    enable_protocol_motion.py --restore --servos-off   # ... and de-energise

THE SEQUENCE, AND WHY IT IS NOT THE JOG ONE
-------------------------------------------
`fr5_tcp_jog_gui.py` connects with RobotEnable(1) -> Mode(1) -> SetSpeed and
jogs happily. That is the MANUAL path. Protocol MoveJ/MoveL needs AUTO, and the
order is reversed. Taken from the node that ran this robot for 521 MoveJ calls
(`teleop_slave/src/fairino_lowlevel_controller_node.cpp:275-300`):

    ResetAllError()
    Mode(0)            0 = auto, 1 = manual
    RobotEnable(1)     servos energised
    SetSpeed(percent)

Copying the jog sequence instead would leave the controller in manual and the
MoveL would fail, or worse, half-succeed.

WHAT THIS DOES NOT DO
---------------------
No MoveJ, MoveL, ServoJ, jog, or IO. Enabling only makes the robot *able* to
act on a later motion command; nothing here is one.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import xmlrpc.client
from datetime import datetime
from pathlib import Path

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
from vbts_platform.robot_interface import RobotInterface  # noqa: E402

OUT = ROOT / "data" / "motion_enable"
STATE_NAMES = {1: "stopped", 2: "running", 3: "paused", 4: "drag-teach"}

# Only these may be sent. Every one changes controller state; none is a motion.
ALLOWED = {"ResetAllError", "Mode", "RobotEnable", "SetSpeed"}


def read_state(ip: str, settle: float = 2.0) -> dict:
    r = RobotInterface(ip=ip, dry_run=False, allow_real_motion=False)
    r.connect(read_only=True)
    try:
        time.sleep(settle)
        st = r.get_robot_state()
    finally:
        r.disconnect()
    return {"robot_state": st.robot_state,
            "robot_state_name": STATE_NAMES.get(st.robot_state, f"?{st.robot_state}"),
            "robot_mode": st.robot_mode,
            "robot_mode_name": "manual" if st.robot_mode == 1 else "auto",
            "main_code": st.main_code, "sub_code": st.sub_code,
            "emergency_stop": st.emergency_stop,
            "collision_state": st.collision_state,
            "safety_stop0": st.safety_stop0, "safety_stop1": st.safety_stop1}


def show(tag: str, s: dict) -> None:
    print(f"  {tag:<8} state {s['robot_state']} ({s['robot_state_name']})   "
          f"mode {s['robot_mode']} ({s['robot_mode_name']})   "
          f"err {s['main_code']}/{s['sub_code']}   "
          f"estop {s['emergency_stop']}   safety {s['safety_stop0']}/{s['safety_stop1']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=None)
    ap.add_argument("--speed", type=int, default=5,
                    help="global speed percent; low for a first bring-up")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--servos-off", action="store_true",
                    help="with --restore, also de-energise the servos. Off by "
                         "default since 2026-09-10: the operator swaps gels "
                         "with the arm parked and wants the mode changed only.")
    ap.add_argument("--restore", action="store_true",
                    help="return to manual mode; add --servos-off to also "
                         "de-energise")
    ap.add_argument("--confirm", default=None)
    a = ap.parse_args()

    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]

    if a.restore:
        # Mode only, servos left energised (operator, 2026-09-10). Dropping
        # RobotEnable(0) between runs was not wanted: the gel swap does not need
        # the servos off, and re-energising them is one more thing to go wrong.
        seq = [("Mode", (1,))]
        if a.servos_off:
            seq = [("RobotEnable", (0,))] + seq
        token, what = "RESTORE-MANUAL", "return to manual, servos off"
    else:
        seq = [("ResetAllError", ()), ("Mode", (0,)),
               ("RobotEnable", (1,)), ("SetSpeed", (a.speed,))]
        token, what = "ENABLE-MOTION", f"auto mode, servos on, speed {a.speed} %"

    print("=" * 60)
    print("FR5 CONTROLLER STATE CHANGE")
    print("  NO MoveJ   NO MoveL   NO ServoJ   NO JOG   NO IO")
    print("=" * 60)
    print(f"\n  intent: {what}")
    for m, args in seq:
        assert m in ALLOWED, f"{m} is not permitted by this script"
        print(f"    {m}{args if args else '()'}")

    if a.dry_run:
        print("\n  --dry-run: nothing sent.")
        return 0
    if a.confirm != token:
        print(f"\n  REFUSING: pass --confirm {token}")
        return 2

    print("\n--- preflight ---")
    if not cal.preflight(ip):
        return 2
    before = read_state(ip)
    show("before", before)
    if not a.restore:
        if before["emergency_stop"] or before["safety_stop0"] or before["safety_stop1"]:
            print("\n  e-stop or safety stop is active. Not enabling.")
            return 2
        if before["robot_state"] == 2:
            print("\n  the robot reports it is already RUNNING. Not enabling while")
            print("  something else is driving it.")
            return 2

    print("\n--- sending ---")
    c = xmlrpc.client.ServerProxy(f"http://{ip}:20003")
    results = []
    for m, args in seq:
        rv = getattr(c, m)(*args)
        results.append({"method": m, "args": list(args), "return": rv})
        print(f"  {m}{args if args else '()'} -> {rv}"
              + ("   (success)" if rv == 0 else "   FAILED"))
        if rv != 0:
            print("\n  aborting the sequence; the controller is part-way through.")
            break
        time.sleep(0.4)

    print("\n--- after ---")
    after = read_state(ip)
    show("after", after)

    ok = all(r["return"] == 0 for r in results)
    if not a.restore and ok:
        if after["robot_mode"] != 0:
            print("\n  mode did not become auto; protocol motion will not work.")
            ok = False
        else:
            print("\n  the controller is now in auto mode with the servos energised.")
            print("  It will act on a motion command. None has been sent.")

    run = OUT / datetime.now().strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    (run / "result.yaml").write_text(yaml.safe_dump(json.loads(json.dumps({
        "timestamp": datetime.now().isoformat(), "robot_ip": ip,
        "intent": what, "sequence": results,
        "sequence_source": ("teleop_slave/src/fairino_lowlevel_controller_node.cpp"
                            ":275-300, the node that ran this robot"),
        "state_before": before, "state_after": after,
        "motion_commands_sent": 0, "robot_moved": False,
    }, default=str)), sort_keys=False, allow_unicode=True))
    print(f"\n  written: {run}/result.yaml")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
