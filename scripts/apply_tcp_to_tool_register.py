#!/usr/bin/env python3
"""
Write one calibrated TCP into an FR5 tool register, then read it back.

This is the ONLY script in this project that writes to the controller. It is
deliberately separate from the read-only tooling so that nothing can reach a
write by accident.

    apply_tcp_to_tool_register.py --dry-run                 # show the exact call
    apply_tcp_to_tool_register.py --api set_tool_list --confirm WRITE-TOOL-1

WHAT IT WILL NOT DO
-------------------
No motion, no jog, no servo enable, no mode change, no IO, no payload change,
no user-frame change. It never writes tool 0. It refuses to run unless the
robot is stopped, in manual mode, error-free and not in e-stop or safety stop.

THE TWO WRITE APIS ARE NOT INTERCHANGEABLE
------------------------------------------
FAIRINO's own API_Instruction (2024-05-30) describes them differently:

    SetToolCoord : "set AND LOAD specific index tool coordinate"
    SetToolList  : "set tool coordinate list"

So SetToolCoord activates the register it writes; SetToolList only stores it.
Which one is correct depends on whether the caller wants the tool to become
active. That is a decision, not a detail, so this script makes it explicit
rather than picking one.

XML-RPC parameter layout, taken from the C++ SDK (robot.cpp:3069 and 3115),
not guessed:

    SetToolCoord(id, [x,y,z,rx,ry,rz], type, install, toolID, loadNum)
    SetToolList (id, [x,y,z,rx,ry,rz], type, install, loadNum)

    type    0 = tool coordinate system, 1 = sensor coordinate system
    install 0 = robot end, 1 = external
"""

from __future__ import annotations

import argparse
import hashlib
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
sys.path.insert(0, str(ROOT / "scripts"))

import importlib.util


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cal = _load("cal", ROOT / "scripts" / "prepare_tcp_calibration.py")
chk = _load("chk", ROOT / "scripts" / "robot_readonly_check.py")

from vbts_platform.robot_interface import RobotInterface  # noqa: E402

OUT = ROOT / "data" / "tcp_application"

# The value being written, and where each part of it came from. The rotation is
# a definition, not a measurement: a sphere in a cone constrains position only.
TCP = {
    "tcp_mm_deg": [0.003, 0.322, 36.794, 0.0, 0.0, 0.0],
    "position_source": "pivot_calibration_mean_Run2_Run3",
    "orientation_source": "defined_flange_aligned",
    "orientation_is_calibrated": False,
}

# Only these two methods may be sent. Anything else is a bug in this file.
WRITE_METHODS = {"SetToolCoord", "SetToolList"}


def state_ok(ip: str) -> tuple[bool, dict]:
    """Refuse to write unless the robot is genuinely idle and healthy."""
    robot = RobotInterface(ip=ip, dry_run=False, allow_real_motion=False)
    robot.connect(read_only=True)
    try:
        time.sleep(2.0)
        st = robot.get_robot_state()
    finally:
        robot.disconnect()
    s = {"robot_state": st.robot_state, "robot_mode": st.robot_mode,
         "main_code": st.main_code, "sub_code": st.sub_code,
         "emergency_stop": st.emergency_stop, "collision_state": st.collision_state,
         "safety_stop0": st.safety_stop0, "safety_stop1": st.safety_stop1}
    ok = (st.robot_state == 1 and st.robot_mode == 1 and st.main_code == 0
          and st.sub_code == 0 and not st.emergency_stop and not st.collision_state
          and not st.safety_stop0 and not st.safety_stop1)
    return ok, s


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=None)
    ap.add_argument("--tool-id", type=int, default=1)
    ap.add_argument("--api", choices=("set_tool_coord", "set_tool_list"),
                    default="set_tool_list")
    ap.add_argument("--type", type=int, default=0, help="0 tool frame, 1 sensor frame")
    ap.add_argument("--install", type=int, default=0, help="0 robot end, 1 external")
    ap.add_argument("--tool-id-arg", type=int, default=0,
                    help="SetToolCoord's separate toolID argument")
    ap.add_argument("--load-num", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true",
                    help="print the exact call and exit without sending it")
    ap.add_argument("--confirm", default=None,
                    help="must be WRITE-TOOL-<id> for the write to proceed")
    a = ap.parse_args()

    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]

    if a.tool_id == 0:
        print("REFUSING: tool 0 is the flange reference and is never overwritten.")
        return 2
    if not (1 <= a.tool_id <= 14):
        print(f"REFUSING: tool id {a.tool_id} outside the documented range.")
        return 2

    method = "SetToolCoord" if a.api == "set_tool_coord" else "SetToolList"
    pose = TCP["tcp_mm_deg"]
    if method == "SetToolCoord":
        params = [a.tool_id, pose, a.type, a.install, a.tool_id_arg, a.load_num]
    else:
        params = [a.tool_id, pose, a.type, a.install, a.load_num]
    assert method in WRITE_METHODS

    print("=" * 60)
    print("FR5 TOOL REGISTER WRITE")
    print("  NO MOTION   NO JOG   NO IO   NO SERVO ENABLE   NO MODE CHANGE")
    print("=" * 60)
    print(f"\n  method : {method}")
    print(f"  params : {json.dumps(params)}")
    print(f"  meaning: id={a.tool_id}  coord={pose}  type={a.type} "
          f"install={a.install}" + (f" toolID={a.tool_id_arg}" if method == "SetToolCoord" else "")
          + f" loadNum={a.load_num}")
    if method == "SetToolCoord":
        print("\n  NOTE: SetToolCoord is documented as 'set AND LOAD'. It is expected")
        print("        to make this tool active. Active tool will be re-checked after.")
    else:
        print("\n  SetToolList stores into the list without loading. Active tool is")
        print("  expected to stay unchanged. It is re-checked after regardless.")

    if a.dry_run:
        print("\n  --dry-run: nothing sent.")
        return 0

    if a.confirm != f"WRITE-TOOL-{a.tool_id}":
        print(f"\n  REFUSING: pass --confirm WRITE-TOOL-{a.tool_id} to proceed.")
        return 2

    print("\n--- preflight ---")
    if not cal.preflight(ip):
        print("  route check FAILED; not writing.")
        return 2
    ok, st = state_ok(ip)
    print(f"  state {st}")
    if not ok:
        print("  robot is not in a settled, error-free manual stop; not writing.")
        return 2
    print("  PASS")

    q = chk.ReadOnlyProxy(ip)
    before = {i: q("GetToolCoordWithID", i) for i in range(16)}
    active_before = q("GetActualTCPNum", 0)
    print(f"\n  active tool before : {active_before}")
    print(f"  tool 0 before      : {before[0][1:]}")
    print(f"  tool {a.tool_id} before      : {before[a.tool_id][1:]}")

    print(f"\n--- sending {method} ---")
    client = xmlrpc.client.ServerProxy(f"http://{ip}:20003")
    rv = getattr(client, method)(*params)
    print(f"  return code: {rv}   ({'success' if rv == 0 else 'FAILURE'})")

    time.sleep(0.5)
    after = {i: q("GetToolCoordWithID", i) for i in range(16)}
    active_after = q("GetActualTCPNum", 0)

    print(f"\n--- read-back ---")
    print(f"  tool {a.tool_id} after : {after[a.tool_id][1:]}")
    got = np.array(after[a.tool_id][1:], dtype=float)
    want = np.array(pose, dtype=float)
    err = np.abs(got - want)
    print(f"  expected      : {pose}")
    print(f"  abs error     : {np.round(err, 6).tolist()}   max {err.max():.6f}")
    match = bool(err.max() < 1e-3)
    print(f"  match         : {'YES' if match else 'NO'}")

    print(f"\n  tool 0 after  : {after[0][1:]}   "
          f"{'unchanged' if after[0] == before[0] else 'CHANGED  <-- PROBLEM'}")
    print(f"  active tool   : {active_before} -> {active_after}   "
          f"{'unchanged' if active_after == active_before else 'CHANGED'}")

    strays = [i for i in range(16)
              if i != a.tool_id and after[i] != before[i]]
    print(f"  other registers touched: {strays if strays else 'none'}")

    ok2, st2 = state_ok(ip)
    print(f"\n  state after: {st2}")

    run = OUT / datetime.now().strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    (run / "write_result.yaml").write_text(yaml.safe_dump(json.loads(json.dumps({
        "timestamp": datetime.now().isoformat(), "robot_ip": ip,
        "api_method": method,
        "api_signature_source": "fairino-cpp-sdk robot.cpp:3069 (SetToolCoord) / 3115 (SetToolList)",
        "xmlrpc_params": params,
        "return_code": rv,
        "tool_id": a.tool_id,
        "written": TCP,
        "read_back": after[a.tool_id],
        "read_back_matches": match,
        "max_abs_error_mm_deg": float(err.max()),
        "active_tool_before": active_before, "active_tool_after": active_after,
        "active_tool_changed": active_after != active_before,
        "tool_0_before": before[0], "tool_0_after": after[0],
        "tool_0_unchanged": after[0] == before[0],
        "other_registers_changed": strays,
        "robot_state_before": st, "robot_state_after": st2,
        "robot_moved": False, "motion_commands_issued": 0,
        "cad_discrepancy_status": "unresolved systematic; NOT corrected for",
    }, default=str)), sort_keys=False, allow_unicode=True))
    print(f"\n  written: {run}/write_result.yaml")
    return 0 if (rv == 0 and match and after[0] == before[0]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
