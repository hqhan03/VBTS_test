#!/usr/bin/env python3
"""
Live contact force readout, for the operator to watch while jogging.

Shows exactly the checks that measure_sensor_base_transform.py --phase press
applies, so what reads GOOD here is what will be accepted there.

    live_force_monitor.py            # uses the stored zero from --phase tare
    live_force_monitor.py --raw      # no zero applied

Ctrl-C to stop. The DAQ allows ONE task at a time, so this must be stopped
before a press can be recorded.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from vbts_platform.ft_interface import FTInterface  # noqa: E402

STATE = ROOT / "data" / "rig" / "frame_transform" / "_measurements.json"

MIN_FORCE_N = 3.0
MAX_FORCE_N = 40.0
MAX_LATERAL_FRACTION = 0.45


def recorded_angles() -> list[float]:
    """Lateral-force directions already banked, so the display can say what is
    still missing rather than just what is happening."""
    if not STATE.is_file():
        return []
    d = json.loads(STATE.read_text())
    out = []
    for q in d.get("presses", []):
        F = np.array(q["wrench"][:3])
        if np.linalg.norm(F[:2]) > 1e-6:
            out.append(float(np.degrees(np.arctan2(F[1], F[0]))))
    return out


def biggest_gap(angles: list[float]) -> tuple[float, float]:
    """Middle and width of the widest unsampled arc of lateral directions."""
    if len(angles) < 2:
        return 0.0, 360.0
    a = sorted(angles)
    gaps = [((a[(i + 1) % len(a)] - a[i]) % 360.0, i) for i in range(len(a))]
    w, i = max(gaps)
    mid = (a[i] + w / 2.0) % 360.0
    return (mid - 360.0 if mid > 180 else mid), w


def angle_diff(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def verdict(F: np.ndarray) -> tuple[str, str]:
    mag = float(np.linalg.norm(F))
    lat = float(np.linalg.norm(F[:2]))
    frac = lat / mag if mag > 0 else 0.0
    if mag < MIN_FORCE_N:
        return "TOO LIGHT", "press harder"
    if mag > MAX_FORCE_N:
        return "TOO HARD", "ease off"
    if F[2] > 0:
        return "PULLING UP", "you are lifting, not pressing"
    if frac > MAX_LATERAL_FRACTION:
        return "SLIP RISK", "ease off sideways a little"
    return "GOOD", "hold still, then say so"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", action="store_true", help="do not apply the stored zero")
    ap.add_argument("--seconds", type=float, default=0.2, help="averaging window")
    a = ap.parse_args()

    tare = None
    if not a.raw:
        if not STATE.is_file():
            print("no stored zero; run --phase tare first, or use --raw")
            return 2
        t = json.loads(STATE.read_text()).get("tare")
        if not t:
            print("no stored zero in the state file; run --phase tare first")
            return 2
        tare = np.array(t["tare_wrench"], dtype=float)
        print(f"zero from {t['at']}")

    banked = recorded_angles()
    want, width = biggest_gap(banked)
    if banked:
        print("lateral directions already recorded: " +
              ", ".join(f"{v:.0f}" for v in sorted(banked)) + " deg")
        print(f"widest gap is {width:.0f} deg wide, centred on {want:+.0f} deg "
              "-- aim the sideways push there")
    print(f"\ntarget {MIN_FORCE_N:.0f}-{MAX_FORCE_N:.0f} N. Ctrl-C to stop.\n")
    print(f"{'|F|':>8} {'Fz':>8} {'side%':>7} {'dir':>7} {'to gap':>8}  verdict")

    ft = FTInterface.from_config()
    ft.connect()
    try:
        while True:
            w = ft.read_wrench_mean(duration_s=a.seconds, tared=False)
            if tare is not None:
                w = w - tare
            F = w[:3]
            mag = float(np.linalg.norm(F))
            lat = float(np.linalg.norm(F[:2]))
            frac = 100.0 * lat / mag if mag > 0 else 0.0
            ang = float(np.degrees(np.arctan2(F[1], F[0]))) if lat > 0.05 else float("nan")
            off = angle_diff(ang, want) if np.isfinite(ang) else float("nan")
            v, hint = verdict(F)
            if np.isfinite(off) and frac > 15:
                if off < 30:
                    hint = "ON the gap - hold and record"
                elif off < 70:
                    hint = "near the gap - swing a bit further"
                else:
                    hint = f"wrong way - swing {off:.0f} deg round"
            astr = f"{ang:6.0f}d" if np.isfinite(ang) else "     --"
            ostr = f"{off:7.0f}d" if np.isfinite(off) else "      --"
            print(f"\r{mag:8.2f} {F[2]:8.2f} {frac:6.1f}% {astr:>7} {ostr:>8}  "
                  f"{v:<10} {hint:<34}", end="", flush=True)
    except KeyboardInterrupt:
        print("\n\nstopped. DAQ released.")
    finally:
        ft.disconnect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
