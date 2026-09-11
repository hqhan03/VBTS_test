#!/usr/bin/env python3
"""
Measure the ATI Mini45 baseline and noise floor with the sensor at rest.

Passive analog INPUT only: no output task, no device reset, no NI MAX write,
no robot access.

    /usr/bin/python3 scripts/measure_ft_baseline.py
    /usr/bin/python3 scripts/measure_ft_baseline.py --seconds 10 --yes

Writes data/rig/ft_baseline/YYYYMMDD_HHMMSS/:
    raw.csv        per-sample gauge voltages, with hardware-clock timestamps
    wrench.csv     per-sample Fx..Tz in N and N*m
    summary.yaml   mean / std / min / max / p2p per gauge and per axis,
                   plus full DAQ and calibration provenance

CSV + YAML rather than NPZ/HDF5: this baseline exists to be eyeballed and
sanity-checked, and both open anywhere with no loader code. At 10 s x 2 kHz x
6 ch that costs a few MB, which is nothing. Bulk experiment data later, read by
code rather than by people, is a separate decision.
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vbts_platform.ati_calibration import GAUGE_NAMES, WRENCH_AXES  # noqa: E402
from vbts_platform.ft_interface import (  # noqa: E402
    FTInterface,
    load_calibration,
    load_ft_config,
)

BANNER = """\
=========================================
ATI Mini45 BASELINE / NOISE MEASUREMENT

NO ROBOT MOTION
NO DAQ OUTPUT
========================================="""

OUTPUT_ROOT = PROJECT_ROOT / "data" / "rig" / "ft_baseline"


def confirm(skip: bool) -> bool:
    print("Confirm ALL of the following before measuring:")
    print("  1. The sensor and holder are stationary.")
    print("  2. Nothing is touching the sensor, holder or cabling.")
    print("  3. No one will disturb the bench during the measurement.")
    print("  4. The robot is powered off / not in contact.")
    print()
    if skip:
        print("--yes given: operator confirmation SKIPPED (non-interactive run).")
        print("If anything was in contact, discard this run and repeat interactively.")
        print()
        return True
    try:
        reply = input("Press Enter to start, or 'n' to abort: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\naborted.")
        return False
    if reply.startswith("n"):
        print("aborted.")
        return False
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--yes", action="store_true", help="skip the interactive confirmation")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    print(BANNER)
    print()

    cfg, cfg_path = load_ft_config(args.config)
    cal = load_calibration(cfg, cfg_path)
    ft = FTInterface.from_config(args.config)
    daq = cfg["daq"]

    print(f"Sensor        : {cal.summary()}")
    print(f"Interface     : {cfg['ft_sensor'].get('interface')} via "
          f"{cfg['ft_sensor'].get('terminal_block')}")
    print(f"DAQ           : {daq['model']} {daq['device']}, {ft.terminal_config}, "
          f"+/-{ft.voltage_range} V")
    print(f"Sampling      : {ft.sample_rate_hz:,.0f} Hz for {args.seconds:g} s")
    print(f"Channel map   : {ft.gauge_map}")
    print(f"  confirmed   : {ft.channel_mapping_confirmed}")
    print(f"Frame         : {cfg['output']['frame']}")
    print()

    if not confirm(args.yes):
        return 2

    run_dir = OUTPUT_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    print(f"measuring {args.seconds:g} s ...")
    with ft:
        health = ft.check_channel_health(0.5)
        t_wall0 = time.time()
        result = ft.acquire_baseline(args.seconds)
    volts = result.pop("_raw_array")
    wrench = result.pop("_wrench_array")
    n = volts.shape[1]
    dt = 1.0 / ft.sample_rate_hz

    # -- raw.csv -------------------------------------------------------------
    with open(run_dir / "raw.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sample_index", "t_rel_s"] +
                   [f"{g}_{c.split('/')[-1]}_V" for g, c in zip(GAUGE_NAMES, ft.channels)])
        for i in range(n):
            w.writerow([i, f"{i*dt:.6f}"] + [f"{v:.9f}" for v in volts[:, i]])

    # -- wrench.csv ----------------------------------------------------------
    with open(run_dir / "wrench.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sample_index", "t_rel_s",
                    "Fx_N", "Fy_N", "Fz_N", "Tx_Nm", "Ty_Nm", "Tz_Nm"])
        for i in range(n):
            w.writerow([i, f"{i*dt:.6f}"] + [f"{v:.9f}" for v in wrench[:, i]])

    # -- summary.yaml --------------------------------------------------------
    summary = {
        **result,
        "acquired_at_wall": datetime.fromtimestamp(t_wall0).isoformat(),
        "channel_health": {h.gauge: h.verdict for h in health},
        "all_channels_healthy": all(h.ok for h in health),
        "timestamp_strategy": (
            "Block-level host monotonic + wall clock; per-sample times are "
            "t_i = i/fs from the NI hardware sample clock, never host polling time."
        ),
        "settle_samples_discarded": ft.settle_samples,
        "operator_confirmation": "skipped (--yes)" if args.yes else "interactive Enter",
        "daq": {
            "manufacturer": "NI", "model": daq["model"], "device": daq["device"],
            "channels_in_gauge_order": list(ft.channels),
            "terminal_configuration": ft.terminal_config,
            "voltage_range_v": ft.voltage_range,
            "sample_rate_hz": ft.sample_rate_hz,
            "samples_per_read": ft.samples_per_read,
            "buffer_size": ft.buffer_size,
            "timing": "hardware-timed continuous (cfg_samp_clk_timing)",
        },
        "ft_sensor": {
            "manufacturer": "ATI", "model": cfg["ft_sensor"]["model"],
            "interface": cfg["ft_sensor"].get("interface"),
            "terminal_block": cfg["ft_sensor"].get("terminal_block"),
        },
        "calibration": cal.metadata(),
        "robot": "NOT USED — FAIRINO not accessed in this measurement",
    }
    (run_dir / "summary.yaml").write_text(
        yaml.safe_dump(summary, sort_keys=False, default_flow_style=False))

    # -- report --------------------------------------------------------------
    print(f"done: {n} samples/channel in {result['actual_duration_s']:.3f} s "
          f"(effective {result['effective_sample_rate_hz']:,.1f} Hz)")
    print(f"channel health: {'all ok' if all(h.ok for h in health) else [h.gauge for h in health if not h.ok]}")
    print()
    print("--- RAW VOLTAGE BASELINE ---")
    print(f"{'gauge':>6} {'channel':>12} {'mean(V)':>11} {'std(uV)':>10} {'p2p(uV)':>10}")
    for g, c in zip(GAUGE_NAMES, ft.channels):
        s = result["raw_volts"][g]
        print(f"{g:>6} {c:>12} {s['mean']:>11.6f} {s['std']*1e6:>10.1f} "
              f"{s['peak_to_peak']*1e6:>10.1f}")
    print()
    print(f"--- WRENCH BASELINE (untared, frame {result['frame']}) ---")
    print(f"{'axis':>6} {'mean':>13} {'std':>13} {'min':>13} {'max':>13} {'p2p':>13}  unit")
    for i, ax in enumerate(WRENCH_AXES):
        s, unit = result["wrench"][ax], ("N" if i < 3 else "N*m")
        print(f"{ax:>6} {s['mean']:>13.6f} {s['std']:>13.6f} {s['min']:>13.6f} "
              f"{s['max']:>13.6f} {s['peak_to_peak']:>13.6f}  {unit}")
    print()
    print("Noise floor (std) is the number that matters for contact detection:")
    for i, ax in enumerate(WRENCH_AXES):
        s, unit = result["wrench"][ax], ("N" if i < 3 else "N*m")
        print(f"  sigma_{ax} = {s['std']:.6f} {unit}")
    print()
    print(f"written: {run_dir}")
    for f in sorted(run_dir.iterdir()):
        print(f"  {f.name}  ({f.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
