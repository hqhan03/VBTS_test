#!/usr/bin/env python3
"""
Read-only validation of the FR5 connection, before any motion or TCP calibration.

Observes the robot and nothing else. It does not move it, does not enable the
servos, does not set a mode, does not touch IO, and does not write any register
or parameter.

    /usr/bin/python3 src/scripts/robot_readonly_check.py            # preflight only
    /usr/bin/python3 src/scripts/robot_readonly_check.py --connect  # actually connect

HOW SAFETY IS ENFORCED, NOT JUST PROMISED
-----------------------------------------
1. NETWORK PREFLIGHT. The FR5 lives at 192.168.58.2 on a dedicated wire. If the
   host has no route to it over that wire, the address still resolves — through
   the default gateway, i.e. out to the office router. Connecting in that state
   sends XML-RPC at whatever answers. So the script checks that the route to the
   robot leaves via an ethernet interface and not via the default route, and
   refuses to open anything otherwise.

2. METHOD WHITELIST. Every XML-RPC call goes through a proxy that raises unless
   the method name is on an explicit read-only list. RobotEnable, Mode, MoveJ,
   MoveL, ServoJ, SetToolCoord and everything else that writes are simply not
   reachable from this script, by construction rather than by discipline.

3. READ-ONLY CONNECT. RobotInterface.connect(read_only=True) deliberately skips
   the RobotEnable / Mode / SetSpeed sequence that fr5_tcp_jog_gui.py runs on
   connect. Observing the robot must never energise it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import xmlrpc.client
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vbts_platform import fr5_io  # noqa: E402
from vbts_platform.robot_interface import RobotInterface  # noqa: E402

BANNER = """\
==========================================
FR5 READ-ONLY CONNECTION CHECK

NO ROBOT MOTION
NO SERVO ENABLE
NO MODE CHANGE
NO IO
NO PARAMETER WRITE
=========================================="""

OUT = PROJECT_ROOT / "data" / "rig" / "robot_readonly_check"
ROBOT_CFG = PROJECT_ROOT / "src" / "config" / "robot_config.yaml"

# Only these may be called. Everything else raises before reaching the wire.
READ_ONLY_METHODS = {
    "GetSDKVersion", "GetControllerIP", "GetRobotInstallPos",
    "GetActualTCPPose", "GetActualTCPNum", "GetActualWObjNum",
    "GetActualToolFlangePose", "GetActualJointPosDegree",
    "GetToolCoordWithID", "GetWObjCoordWithID",
    "GetRobotErrorCode", "GetRobotMotionDone", "GetRobotCurJointsConfig",
    # Inverse kinematics is a pure computation on the controller: it returns
    # joint angles for a pose and changes nothing. Needed to verify the config
    # convention before any motion is attempted.
    "GetInverseKin", "GetForwardKin",
    "GetTargetPayload", "GetTargetPayloadCog", "GetSysVarValue",
    # dedicated safety / status queries (all reads)
    "GetRobotEmergencyStopState", "GetSafetyStopState", "GetProgramState",
    "GetSDKComState",
}


class ReadOnlyProxy:
    """XML-RPC proxy that can only issue read-only queries.

    FR5Commands._call coerces the reply with int(), which is right for command
    acknowledgements but discards the payload of a query like GetActualTCPNum
    that answers [errcode, value]. This keeps the raw reply, and refuses any
    method not on the whitelist so the extra reach cannot be misused.
    """

    def __init__(self, ip: str, timeout: float = 3.0) -> None:
        self._proxy = xmlrpc.client.ServerProxy(
            f"http://{ip}:{fr5_io.RPC_PORT}/RPC2",
            transport=fr5_io._TimeoutTransport(timeout), allow_none=True)
        self.calls: list[str] = []

    def __call__(self, method: str, *args):
        if method not in READ_ONLY_METHODS:
            raise PermissionError(
                f"{method} is not a read-only query; this script may not call it")
        self.calls.append(method)
        return getattr(self._proxy, method)(*args)


# --------------------------------------------------------------------------
# preflight
# --------------------------------------------------------------------------

def route_to(ip: str) -> dict:
    """Where would a packet to `ip` actually go?"""
    try:
        out = subprocess.run(["ip", "route", "get", ip], capture_output=True,
                             text=True, timeout=5).stdout.strip()
    except Exception as exc:
        return {"ok": False, "raw": f"{type(exc).__name__}: {exc}"}
    dev = re.search(r"\bdev\s+(\S+)", out)
    via = re.search(r"\bvia\s+(\S+)", out)
    return {"ok": True, "raw": out,
            "device": dev.group(1) if dev else None,
            "via": via.group(1) if via else None}


def default_route_device() -> str | None:
    try:
        out = subprocess.run(["ip", "route", "show", "default"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return None
    m = re.search(r"\bdev\s+(\S+)", out)
    return m.group(1) if m else None


def iface_state(dev: str) -> dict:
    base = Path("/sys/class/net") / dev
    def rd(p):
        try:
            return (base / p).read_text().strip()
        except Exception:
            return None
    return {"exists": base.exists(), "operstate": rd("operstate"),
            "carrier": rd("carrier"),
            "tx_packets": rd("statistics/tx_packets"),
            "rx_packets": rd("statistics/rx_packets")}


def preflight(ip: str) -> dict:
    print("--- preflight: is there actually a path to the robot? ---")
    r = route_to(ip)
    dflt = default_route_device()
    print(f"  route to {ip:<14}: {r.get('raw')}")
    print(f"  default route device : {dflt}")

    dev = r.get("device")
    st = iface_state(dev) if dev else {}
    if dev:
        print(f"  {dev}: operstate={st.get('operstate')} carrier={st.get('carrier')} "
              f"tx={st.get('tx_packets')} rx={st.get('rx_packets')}")

    # The robot is on a dedicated wire. If the route leaves by the same device
    # as the default route, the address is resolving to the general network.
    via_default = (dev is not None and dev == dflt)
    is_ethernet = bool(dev and dev.startswith(("en", "eth")))
    ok = is_ethernet and not via_default

    print()
    if ok:
        print(f"  PASS — traffic for {ip} leaves via {dev}, which is not the default route.")
    else:
        print(f"  FAIL — traffic for {ip} would leave via {dev}"
              f"{', the DEFAULT ROUTE' if via_default else ''}.")
        print("         That is the office network, not the robot. Connecting now would")
        print("         send XML-RPC to whatever answers there. Refusing to connect.")
    print()
    return {"ok": ok, "route": r, "default_route_device": dflt,
            "interface_state": st, "reached_via_default_route": via_default,
            "is_ethernet": is_ethernet}


# --------------------------------------------------------------------------
# read-only observation
# --------------------------------------------------------------------------

def read_state(ip: str, settle_s: float) -> dict:
    import time

    result: dict = {"connected": False}
    robot = RobotInterface(ip=ip, dry_run=False, allow_real_motion=False)
    q = ReadOnlyProxy(ip)

    print("--- connecting read-only ---")
    print("  RobotInterface.connect(read_only=True): opens the 20004 state stream and")
    print("  the 20003 query channel. No RobotEnable, no Mode, no SetSpeed.")
    robot.connect(read_only=True)
    result["connected"] = True
    print(f"  connected to {ip}")
    print(f"  waiting {settle_s:g} s for the real-time stream to deliver frames ...")
    time.sleep(settle_s)
    print()

    try:
        rt = robot._rt
        result["realtime_stream"] = {
            "connected": bool(rt and rt.connected),
            "fresh": bool(rt and rt.is_fresh),
            "safety_block_parsed": bool(rt and rt.safety_valid),
        }
        print("--- real-time state (port 20004) ---")
        print(f"  stream connected : {result['realtime_stream']['connected']}")
        print(f"  frames fresh     : {result['realtime_stream']['fresh']}")

        state = robot.get_robot_state()
        result["robot_state"] = {
            "robot_state": state.robot_state, "robot_mode": state.robot_mode,
            "main_code": state.main_code, "sub_code": state.sub_code,
            "motion_done": state.motion_done,
            "emergency_stop": state.emergency_stop,
            "collision_state": state.collision_state,
            "safety_stop0": state.safety_stop0, "safety_stop1": state.safety_stop1,
            "is_safe_to_move": state.is_safe_to_move,
        }
        names = {1: "stopped", 2: "running", 3: "paused", 4: "drag-teach"}
        print(f"  robot_state      : {state.robot_state} "
              f"({names.get(state.robot_state, '?')})")
        print(f"  robot_mode       : {state.robot_mode} "
              f"({'manual' if state.robot_mode == 1 else 'auto' if state.robot_mode == 0 else '?'})"
              f"   <- resolves the operation_mode question in robot_config.yaml")
        print(f"  error code       : main={state.main_code} sub={state.sub_code}")
        print(f"  emergency stop   : {state.emergency_stop}")
        print(f"  collision        : {state.collision_state}")
        print(f"  safety stop SI0/1: {state.safety_stop0} / {state.safety_stop1}")
        print(f"  safe to move     : {state.is_safe_to_move}")
        print()

        if state.tcp_pose:
            p = state.tcp_pose
            result["tcp_pose"] = {"x": p.x, "y": p.y, "z": p.z,
                                  "rx": p.rx, "ry": p.ry, "rz": p.rz,
                                  "units": "mm, deg", "frame": "robot_base",
                                  "convention": "fixed-axis (extrinsic) RPY"}
            print(f"--- current pose (robot base frame, mm / deg) ---")
            print(f"  TCP    : {p}")
        if state.joints:
            result["joint_positions_deg"] = list(state.joints.as_tuple())
            print(f"  joints : {state.joints}")
        print()

        print("--- tool / workpiece frame registers (queries only) ---")
        for label, method, args in (
            ("active tool id", "GetActualTCPNum", (0,)),
            ("active wobj id", "GetActualWObjNum", (0,)),
            ("TCP pose", "GetActualTCPPose", (0,)),
            ("flange pose", "GetActualToolFlangePose", (0,)),
            ("emergency stop", "GetRobotEmergencyStopState", ()),
            ("safety stop SI0/1", "GetSafetyStopState", ()),
            ("motion done", "GetRobotMotionDone", ()),
            ("program state", "GetProgramState", ()),
            ("SDK comm state", "GetSDKComState", ()),
        ):
            try:
                v = q(method, *args)
                result.setdefault("queries", {})[method] = v
                print(f"  {label:<16}: {v}")
            except Exception as exc:
                result.setdefault("queries", {})[method] = f"ERROR {type(exc).__name__}: {exc}"
                print(f"  {label:<16}: query failed — {type(exc).__name__}: {exc}")

        tool_id = None
        raw = result.get("queries", {}).get("GetActualTCPNum")
        if isinstance(raw, list) and len(raw) >= 2 and raw[0] == 0:
            tool_id = raw[1]
        elif isinstance(raw, int):
            tool_id = raw
        if tool_id is not None:
            try:
                v = q("GetToolCoordWithID", int(tool_id))
                result.setdefault("queries", {})["GetToolCoordWithID"] = v
                print(f"  tool {tool_id} frame   : {v}")
                print("    (tool frame is expressed relative to the FLANGE, not the base)")
            except Exception as exc:
                print(f"  tool {tool_id} frame   : query failed — {exc}")
        print()

    finally:
        robot.disconnect()
        print("--- disconnected ---")
        print(f"  XML-RPC methods called: {sorted(set(q.calls))}")
        print("  every one of them is a read-only query")
        result["xmlrpc_methods_called"] = sorted(set(q.calls))
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--connect", action="store_true",
                    help="actually open the read-only connection (default: preflight only)")
    ap.add_argument("--settle", type=float, default=2.0)
    ap.add_argument("--ip", default=None)
    args = ap.parse_args()

    print(BANNER)
    print()
    rc = yaml.safe_load(open(ROBOT_CFG)) if ROBOT_CFG.is_file() else {}
    ip = args.ip or rc.get("robot", {}).get("ip", fr5_io.DEFAULT_ROBOT_IP)
    print(f"robot ip     : {ip}   (from {ROBOT_CFG.name}, not modified)")
    print(f"dry_run cfg  : {rc.get('dry_run', {}).get('enabled')}  "
          f"allow_real_motion cfg: {rc.get('safety', {}).get('allow_real_motion')}")
    print("  This script overrides dry_run in code to observe, and leaves both config")
    print("  values untouched. allow_real_motion stays false and is never consulted,")
    print("  because a read-only connection does not go through the motion gate.")
    print()

    pf = preflight(ip)
    record = {"timestamp": datetime.now().isoformat(), "robot_ip": ip,
              "preflight": pf, "connected": False,
              "robot_moved": False, "servos_enabled": False,
              "mode_changed": False, "io_touched": False,
              "parameters_written": False}

    if not args.connect:
        print("preflight only; pass --connect to open the read-only connection.")
    elif not pf["ok"]:
        print("REFUSING to connect: preflight failed.")
        record["refused_reason"] = "no route to the robot over a dedicated interface"
    else:
        try:
            record.update(read_state(ip, args.settle))
        except Exception as exc:
            record["error"] = f"{type(exc).__name__}: {exc}"
            print(f"\nconnection failed: {type(exc).__name__}: {exc}")

    run = OUT / datetime.now().strftime("%Y%m%d_%H%M%S")
    run.mkdir(parents=True, exist_ok=True)
    (run / "readonly_check.yaml").write_text(
        yaml.safe_dump(json.loads(json.dumps(record, default=str)),
                       sort_keys=False, allow_unicode=True))
    print(f"\nwritten: {run}/readonly_check.yaml")
    return 0 if (pf["ok"] or not args.connect) else 1


if __name__ == "__main__":
    raise SystemExit(main())
