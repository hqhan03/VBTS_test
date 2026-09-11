#!/usr/bin/env python3
"""
Does a repeated small MoveL go as far as it is told?

Characterising a gel showed the probe travelling 2.169 mm when 39 steps of
0.050 mm had been commanded -- 11 % more, with the steps alternating large and
small. That was found only because the depth was cross-checked against the
robot rather than counted from the commands.

Three explanations survive: the pose used to compute each target is read before
the previous move has fully landed, the arm deflects under the contact load, or
the moves genuinely overshoot. This runs the same step pattern in FREE AIR,
which removes the load from the question, and logs the commanded target beside
the pose actually reached.

    diagnose_step_accuracy.py --confirm MOVE
    diagnose_step_accuracy.py --confirm MOVE --settle 2.0    # longer wait
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


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cal = _load("cal", ROOT / "scripts" / "prepare_tcp_calibration.py")
chk = _load("chk", ROOT / "scripts" / "robot_readonly_check.py")
mv = _load("mv", ROOT / "scripts" / "move_probe.py")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ip", default=None)
    ap.add_argument("--step", type=float, default=0.05)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--settle", type=float, default=0.5)
    ap.add_argument("--min-clearance", type=float, default=3.0,
                    help="refuse unless the tip ends this far above the gel")
    ap.add_argument("--surface", type=float, default=27.72)
    ap.add_argument("--vel", type=float, default=5.0)
    ap.add_argument("--ovl", type=float, default=10.0)
    ap.add_argument("--confirm", default=None)
    a = ap.parse_args()

    rc = yaml.safe_load(open(ROOT / "config" / "robot_config.yaml"))
    ip = a.ip or rc["robot"]["ip"]
    print("=" * 62)
    print("STEP ACCURACY — free air, no contact")
    print("=" * 62 + "\n")
    if not cal.preflight(ip):
        return 2
    ok, why = mv.ready_to_move(mv.read_state(ip))
    print(f"  ready: {ok} — {why}")
    if not ok:
        return 2

    q = chk.ReadOnlyProxy(ip)
    t0, n = mv.sensor_axis()

    def pose():
        return np.array(q("GetActualTCPPose", 0)[1:][:3])

    def height(p):
        return float((p - t0) @ n)

    start = pose()
    h0 = height(start)
    end_h = h0 - a.n * a.step
    print(f"  start {h0:.3f} mm above the gel, ending near {end_h:.3f} mm")
    if end_h < a.surface + a.min_clearance:
        print(f"\n  REFUSING: that would come within {end_h - a.surface:.2f} mm of the")
        print(f"  gel. This test must stay in free air. Raise the probe first.")
        return 2
    if a.confirm != "MOVE":
        print("\n  REFUSING: pass --confirm MOVE")
        return 2

    print(f"\n  {a.n} steps of {a.step} mm, settle {a.settle} s\n")
    print(f"  {'#':>3} {'target h':>9} {'reached h':>10} {'this step':>10} "
          f"{'err':>8} {'cum err':>9}")
    rows = []
    cum_cmd = 0.0
    prev = start
    for i in range(a.n):
        p_read = pose()
        target = p_read - a.step * n
        pl = mv.plan(ip, [float(target[0]), float(target[1]), float(target[2])]
                     + [float(v) for v in q("GetActualTCPPose", 0)[1:][3:]], 1.0)
        if not pl.get("ok"):
            print(f"  refused: {pl.get('why')}")
            return 2
        tool = pl["active_tool"][1] if isinstance(pl["active_tool"], list) else 1
        if mv.send_movel(ip, pl["target_joints"], pl["target_pose"], tool,
                         a.vel, a.ovl) != 0:
            return 1
        time.sleep(a.settle)
        got = pose()
        cum_cmd += a.step
        step_real = height(prev) - height(got)
        err = step_real - a.step
        cum_err = (h0 - height(got)) - cum_cmd
        print(f"  {i+1:>3} {height(target):>9.3f} {height(got):>10.3f} "
              f"{step_real:>10.4f} {err:>+8.4f} {cum_err:>+9.4f}")
        rows.append({"i": i + 1, "target_h": height(target),
                     "reached_h": height(got), "step_real": step_real,
                     "err": err, "cum_err": cum_err,
                     "read_before_h": height(p_read)})
        prev = got

    st = np.array([r["step_real"] for r in rows])
    print(f"\n  commanded {cum_cmd:.3f} mm, travelled {h0 - height(prev):.3f} mm, "
          f"difference {(h0 - height(prev)) - cum_cmd:+.3f} mm "
          f"({100*((h0 - height(prev)) / cum_cmd - 1):+.1f} %)")
    print(f"  step mean {st.mean():.4f} mm against {a.step} commanded")
    if len(st) >= 4:
        print(f"  odd steps {st[0::2].mean():.4f}, even steps {st[1::2].mean():.4f}")
        alt = abs(st[0::2].mean() - st[1::2].mean())
        print(f"  alternation {alt:.4f} mm — "
              + ("the pose is being read before the previous move has landed"
                 if alt > 0.3 * a.step else
                 "no alternation, so the reads are keeping up"))
    scale = st.mean() / a.step
    direction = "further than" if scale > 1 else "short of"
    print(f"\n  verdict: free-air steps land {abs(scale - 1) * 100:.1f} % "
          f"{direction} commanded"
          + ("" if abs(scale - 1) > 0.03 else " — within tolerance"))
    # The FR5 repeats to about 0.02 mm. A 0.05 mm command is only 2.5 times
    # that, so a tenth of a percent of arm is a fifth of the step. Relative
    # error at this size says more about the step being small than about the
    # robot being wrong.
    print(f"  per-step spread {st.std():.4f} mm against a stated repeatability "
          f"of about 0.02 mm")
    if a.step < 0.1:
        print(f"  a {a.step} mm step sits close to that repeatability; the same "
              "test at 0.1 or 0.2 mm separates a scale error from quantisation")

    out = ROOT / "data" / "rig" / "diagnostics" / datetime.now().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "step_accuracy.yaml").write_text(yaml.safe_dump(json.loads(json.dumps({
        "timestamp": datetime.now().isoformat(),
        "step_mm": a.step, "n": a.n, "settle_s": a.settle,
        "vel": a.vel, "ovl": a.ovl,
        "commanded_total_mm": cum_cmd,
        "travelled_total_mm": float(h0 - height(prev)),
        "scale": float(scale), "rows": rows,
        "in_contact": False,
    }, default=str)), sort_keys=False, allow_unicode=True))
    print(f"  written: {out}/step_accuracy.yaml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
