#!/usr/bin/env python3
"""
Read-only check of the ATI Mini45 / NI PCIe-6343 acquisition chain.

Passive analog INPUT only: no output task, no device reset, no NI MAX write,
no robot access.

    /usr/bin/python3 scripts/test_ft_readonly.py
    /usr/bin/python3 scripts/test_ft_readonly.py --seconds 5
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

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
ATI Mini45 / NI DAQ READ-ONLY TEST

NO ROBOT MOTION
NO DAQ OUTPUT
========================================="""


def describe_device(device_name: str) -> bool:
    """Print device facts read from DAQmx. Returns False if it is absent."""
    try:
        from nidaqmx.system import System
    except Exception as exc:
        print(f"  nidaqmx unavailable: {exc}")
        return False
    sysl = System.local()
    v = sysl.driver_version
    present = [d.name for d in sysl.devices]
    print(f"NI-DAQmx driver      : {v.major_version}.{v.minor_version}.{v.update_version}")
    print(f"Devices present      : {present}")
    if device_name not in present:
        print(f"  !! configured device {device_name!r} is NOT present")
        return False
    d = sysl.devices[device_name]
    print(f"Detected NI device   : {d.name}  ({d.product_type})")
    print(f"  serial             : {d.serial_num:X} (hex)")
    print(f"  simulated          : {d.is_simulated}")
    print(f"  AI channels        : {len(list(d.ai_physical_chans))}")
    print(f"  AI input ranges    : {d.ai_voltage_rngs} V")
    print(f"  AI max rate        : {d.ai_max_multi_chan_rate:,.0f} S/s aggregate")
    return True


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    print(BANNER)
    print()

    cfg, cfg_path = load_ft_config(args.config)
    cal = load_calibration(cfg, cfg_path)
    daq = cfg["daq"]

    # ---- pre-acquisition confirmation (section 19) ----------------------
    print("--- CONFIGURATION ---")
    print(f"Config file          : {cfg_path}")
    ok = describe_device(daq["device"])
    print(f"Calibration file     : {cal.source_path}")
    print(f"  sensor             : {cal.summary()}")
    print(f"  output mode        : {cal.output_mode}, range {cal.output_range}, "
          f"bipolar {cal.output_bipolar}")
    print(f"  matrix source      : UserAxis (BasicTransform already applied)")
    print(f"  self-consistent    : {cal.verify_internal_consistency()}")
    print(f"ATI interface        : {cfg['ft_sensor'].get('interface')} "
          f"via {cfg['ft_sensor'].get('terminal_block')}")

    ft = FTInterface.from_config(args.config)
    print(f"Channel mapping      :")
    for gauge, chan in ft.gauge_map.items():
        print(f"    {gauge} -> {chan}")
    print(f"  mapping confirmed  : {ft.channel_mapping_confirmed}")
    print(f"Terminal configuration: {ft.terminal_config}")
    print(f"Sampling rate        : {ft.sample_rate_hz:,.0f} Hz  "
          f"(samples/read {ft.samples_per_read}, buffer {ft.buffer_size})")
    print(f"Voltage range        : +/-{ft.voltage_range} V")
    print(f"Output frame         : {cfg['output']['frame']}")
    print()

    if not ok:
        print("Aborting: configured NI device not present.")
        return 2

    # ---- acquisition ----------------------------------------------------
    print(f"--- PASSIVE ACQUISITION, {args.seconds:g} s ---")
    errors = []
    with ft:
        health = ft.check_channel_health(0.5)
        blocks, got = [], 0
        want = int(args.seconds * ft.sample_rate_hz)
        t0 = time.monotonic()
        while got < want:
            try:
                b = ft.read_raw(min(ft.samples_per_read, want - got))
            except Exception as exc:
                errors.append(f"{type(exc).__name__}: {exc}")
                break
            blocks.append(b.volts)
            got += b.n_samples
        elapsed = time.monotonic() - t0
        last = b if blocks else None

    volts = np.hstack(blocks)
    n = volts.shape[1]
    wrench = cal.to_wrench(volts)

    print(f"Blocks read          : {len(blocks)}")
    print(f"Samples per channel  : {n}")
    print(f"Elapsed              : {elapsed:.3f} s")
    print(f"Effective rate       : {n/elapsed:,.1f} Hz  (nominal {ft.sample_rate_hz:,.0f} Hz)")
    if last is not None:
        st = last.sample_times_monotonic()
        print(f"Timestamps           : block host monotonic; per-sample from the "
              f"hardware clock (dt={st[1]-st[0]:.6e} s)")
    print(f"Errors/overrun       : {errors if errors else 'none'}")
    print()

    # ---- channel health -------------------------------------------------
    print("--- CHANNEL HEALTH ---")
    print(f"{'gauge':>6} {'channel':>12} {'mean(V)':>10} {'std(mV)':>9} "
          f"{'min(V)':>9} {'max(V)':>9}  verdict")
    for h in health:
        flag = "" if h.ok else "   <-- PROBLEM"
        print(f"{h.gauge:>6} {h.channel:>12} {h.mean_v:>10.5f} {h.std_v*1e3:>9.3f} "
              f"{h.min_v:>9.4f} {h.max_v:>9.4f}  {h.verdict}{flag}")
    bad = [h for h in health if not h.ok]
    print()

    # ---- raw ------------------------------------------------------------
    print("--- RAW VOLTAGE ---")
    print(f"{'gauge':>6} {'channel':>12} {'mean(V)':>10} {'std(mV)':>9} {'p2p(mV)':>9}")
    for gauge, chan, row in zip(GAUGE_NAMES, ft.channels, volts):
        print(f"{gauge:>6} {chan:>12} {row.mean():>10.5f} "
              f"{row.std(ddof=1)*1e3:>9.3f} {(row.max()-row.min())*1e3:>9.3f}")
    print()

    # ---- wrench ---------------------------------------------------------
    print(f"--- CALIBRATED WRENCH (untared, frame {cfg['output']['frame']}) ---")
    print(f"{'axis':>6} {'mean':>13} {'std':>13} {'p2p':>13}   unit")
    for i, ax in enumerate(WRENCH_AXES):
        unit = "N" if i < 3 else "N*m"
        r = wrench[i]
        print(f"{ax:>6} {r.mean():>13.6f} {r.std(ddof=1):>13.6f} "
              f"{r.max()-r.min():>13.6f}   {unit}")
    over = cal.exceeds_max_load(wrench.mean(axis=1))
    if over:
        print(f"  !! beyond calibrated range: {over}")
    print()

    if bad:
        print("RESULT: acquisition works, but these channels are not healthy:")
        for h in bad:
            print(f"  {h.gauge} on {h.channel}: {h.verdict}")
        print("The wrench above is therefore NOT trustworthy. Fix the wiring or")
        print("correct daq.channels in config/ft_config.yaml before believing any force.")
    elif not ft.channel_mapping_confirmed:
        print("RESULT: all six channels healthy, but the SG->ai mapping is not yet")
        print("confirmed against a known load. Run scripts/test_weight_validation.py.")
    else:
        print("RESULT: all six channels healthy and mapping confirmed.")
    print()
    print("No output task created, no device reset, no NI MAX change, no robot access.")
    return 1 if (errors or bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
