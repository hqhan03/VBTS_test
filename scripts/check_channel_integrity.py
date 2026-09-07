#!/usr/bin/env python3
"""
Prove every configured gauge channel is actually driven, not ghosting.

Passive analog INPUT only: no output task, no device reset, no NI MAX write,
no robot access.

    /usr/bin/python3 scripts/check_channel_integrity.py

WHY THIS EXISTS
---------------
`FTInterface.check_channel_health` looks at level and noise, and an OPEN input
passes it: the DAQ multiplexes one ADC across all channels, so an undriven pin
returns whatever charge the previously sampled channel left on the mux
capacitor. That reads as a stable, in-range, low-noise value — indistinguishable
from a real signal by statistics alone.

It has bitten this rig twice. SG0 read as a plausible gauge while its reference
was mis-wired to terminal 35 instead of 34. SG5 read as a plausible gauge while
duplicating SG4. In both cases forces came out looking reasonable: Fz stayed
close to correct because the affected gauges have small Fz coefficients, while
Fx picked up a multi-newton error, because SG5's Fx coefficient is +23.7 N/V.

The test that does work is to change what precedes the channel in the scan and
see whether the reading follows. A driven input holds its value; an open one
tracks its predecessor.

Run this after ANY change to wiring, terminal block, or connector.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vbts_platform.ati_calibration import GAUGE_NAMES  # noqa: E402
from vbts_platform.ft_interface import load_ft_config, read_raw_channels  # noqa: E402

BANNER = """\
====================================
ATI / NI DAQ CHANNEL INTEGRITY CHECK

NO ROBOT ACCESS
NO DAQ OUTPUT
===================================="""

# A driven channel must differ from its predecessor by more than this; an open
# one tracks it to well under it. Real gauge levels here differ by 100s of mV,
# and observed ghosting was under 2 mV, so 20 mV separates them with margin.
GHOST_THRESHOLD_MV = 20.0


def integrity(channels: list[str], term: str, rate: float, secs: float) -> list[dict]:
    """For each channel, vary the preceding channel and watch for tracking."""
    results = []
    for target in channels:
        probes = [c for c in channels if c != target][:4]
        deltas, readings = [], []
        for pre in probes:
            v = read_raw_channels([pre, target], duration_s=secs,
                                  terminal_config=term, sample_rate_hz=rate).mean(axis=1)
            deltas.append(abs(v[1] - v[0]) * 1e3)
            readings.append(float(v[1]))
        spread = (max(readings) - min(readings)) * 1e3
        ghosting = all(d < GHOST_THRESHOLD_MV for d in deltas)
        results.append({
            "channel": target,
            "own_value_spread_mV": float(spread),
            "min_delta_to_predecessor_mV": float(min(deltas)),
            "verdict": "OPEN (ghosting)" if ghosting else "driven",
            "ok": not ghosting,
        })
    return results


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=1.0)
    ap.add_argument("--rate", type=float, default=2000.0)
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    print(BANNER)
    print()
    cfg, cfg_path = load_ft_config(args.config)
    daq = cfg["daq"]
    channels = daq["channels"]
    term = daq.get("terminal_configuration", "differential")

    print(f"config    : {cfg_path}")
    print(f"connector : {daq.get('connector')}")
    print(f"channels  : {dict(zip(GAUGE_NAMES, channels))}")
    print(f"mode      : {term}, {args.rate:,.0f} Hz")
    print()
    print("Varying the channel scanned immediately before each target.")
    print("A driven input keeps its own value; an open one follows its predecessor.")
    print()

    res = integrity(channels, term, args.rate, args.seconds)
    print(f"{'gauge':>6} {'channel':>11} {'own spread(mV)':>15} "
          f"{'min gap to prev(mV)':>21}  verdict")
    for g, r in zip(GAUGE_NAMES, res):
        flag = "" if r["ok"] else "   <-- NOT CONNECTED"
        print(f"{g:>6} {r['channel'].split('/')[-1]:>11} "
              f"{r['own_value_spread_mV']:>15.1f} "
              f"{r['min_delta_to_predecessor_mV']:>21.1f}  {r['verdict']}{flag}")
    print()

    bad = [(g, r) for g, r in zip(GAUGE_NAMES, res) if not r["ok"]]
    declared = daq.get("all_channels_healthy")
    if bad:
        print(f"RESULT: {len(bad)} of {len(res)} gauge channels are NOT connected:")
        wiring = (cfg.get("scb68a_wiring") or {}).get("gauges", {})
        for g, r in bad:
            t = wiring.get(g, {})
            print(f"  {g} on {r['channel']}  -> check SCB-68A terminals "
                  f"{t.get('positive_terminal')} (+) and {t.get('negative_terminal')} (-)")
        print()
        print("Forces computed from these channels are wrong even when Fz looks")
        print("plausible: a gauge with a small Fz coefficient can still dominate Fx/Fy.")
        if declared:
            print()
            print("!! config says daq.all_channels_healthy: true, which is not true. !!")
        return 1

    print(f"RESULT: all {len(res)} gauge channels are driven.")
    if declared is False:
        print("config says daq.all_channels_healthy: false — it can now be set true.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
