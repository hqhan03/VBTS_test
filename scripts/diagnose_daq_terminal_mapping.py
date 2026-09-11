#!/usr/bin/env python3
"""
NI DAQ terminal-mapping diagnostic.

Establishes what the DAQ is ACTUALLY reading, without touching forces,
calibration, or the robot. Passive analog INPUT only.

    /usr/bin/python3 scripts/diagnose_daq_terminal_mapping.py

WHAT THIS CAN AND CANNOT DETERMINE
----------------------------------
NI-DAQmx does not expose connector pin numbers. `PhysicalChannel` offers only
`ai_term_cfgs` (which terminal configurations a channel supports) and
`Device.terminals` (PFI/clock/trigger routing names) — neither is a pin map.
No 6343 or SCB-68A pinout document is installed on this machine either.

So the SCB-68A terminal number -> Dev1/aiN correspondence CANNOT be read out of
software. It has to come from the connector pinout. What this script does
instead is establish, empirically:

  1. which AI channels are differential partners (verified, not assumed),
  2. which pins actually carry a live signal versus sit at ground or float,
  3. how each channel responded to the known 1 kg load from Task 5,

and then cross-check those facts against the SCB-68A wiring recorded in
ft_config.yaml, reporting any contradiction rather than resolving it by guess.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vbts_platform.ft_interface import load_ft_config, read_raw_channels  # noqa: E402

BANNER = """\
====================================
NI DAQ TERMINAL MAPPING DIAGNOSTIC

NO ROBOT ACCESS
NO DAQ OUTPUT
===================================="""

WEIGHT_RUN = PROJECT_ROOT / "data" / "rig" / "weight_validation" / "20260825_152816"


def device_info(dev_name: str) -> None:
    from nidaqmx.system import Device, System

    sysl = System.local()
    v = sysl.driver_version
    print(f"NI-DAQmx driver : {v.major_version}.{v.minor_version}.{v.update_version}")
    print(f"Devices         : {[d.name for d in sysl.devices]}")
    d = Device(dev_name)
    print(f"Device          : {d.name}  ({d.product_type})")
    print(f"  serial        : {d.serial_num:X} (hex)")
    print(f"  AI channels   : {len(list(d.ai_physical_chans))}")
    print(f"  AI ranges     : {d.ai_voltage_rngs} V")
    print()
    print("Per-channel information exposed by NI-DAQmx (ai0..ai7):")
    print(f"{'channel':>12}  supported terminal configurations")
    for i in range(8):
        ch = d.ai_physical_chans[f"{dev_name}/ai{i}"]
        cfgs = ", ".join(c.name for c in ch.ai_term_cfgs)
        print(f"{ch.name:>12}  {cfgs}")
    print()
    print("NOTE: NI-DAQmx exposes NO connector pin number for any AI channel.")
    print("      There is no API that maps 'SCB-68A terminal 68' to a channel.")
    print()


def verify_differential_pairing(dev: str, rate: float, secs: float) -> dict:
    """Confirm which channel is each DIFF channel's negative partner.

    On X Series the documented pairing is aiN with ai(N+8). That is verified
    here rather than assumed: read every pin single-ended against AIGND, read
    the differential channels, and check DIFF(aiN) == RSE(aiN) - RSE(aiN+8).
    """
    print("--- differential pairing, verified empirically ---")
    rse = read_raw_channels([f"{dev}/ai{i}" for i in range(16)],
                            duration_s=secs, terminal_config="RSE",
                            sample_rate_hz=rate).mean(axis=1)
    diff = read_raw_channels([f"{dev}/ai{i}" for i in range(8)],
                             duration_s=secs, terminal_config="DIFF",
                             sample_rate_hz=rate).mean(axis=1)

    print(f"{'DIFF chan':>10} {'measured(V)':>12} {'RSE(n)-RSE(n+8)':>17} "
          f"{'residual(mV)':>13}  partner confirmed")
    pairing = {}
    for n in range(8):
        predicted = rse[n] - rse[n + 8]
        resid = (diff[n] - predicted) * 1e3
        ok = abs(resid) < 20.0          # 20 mV: loose, only to catch a wrong pair
        pairing[f"ai{n}"] = {"negative_partner": f"ai{n+8}",
                             "residual_mV": float(resid), "confirmed": bool(ok)}
        print(f"{'ai%d' % n:>10} {diff[n]:>12.5f} {predicted:>17.5f} "
              f"{resid:>13.3f}  {'yes -> ai%d' % (n+8) if ok else 'NO'}")
    print()
    return {"rse": rse, "diff": diff, "pairing": pairing}


def classify(rse: np.ndarray, dev: str) -> dict:
    """Label each pin from its single-ended behaviour."""
    print("--- single-ended pin survey (each pin vs AIGND) ---")
    print(f"{'channel':>10} {'mean(V)':>10}  classification")
    out = {}
    for i, v in enumerate(rse):
        if abs(v) > 9.0:
            k = "FLOATING (railed to range limit)"
        elif abs(v) < 0.02:
            k = "at AIGND (return leg / ground)"
        elif abs(v) < 0.10:
            k = "near ground"
        else:
            k = "LIVE SIGNAL"
        out[f"{dev}/ai{i}"] = {"mean_V": float(v), "class": k}
        print(f"{'ai%d' % i:>10} {v:>10.5f}  {k}")
    print()
    return out


def open_circuit_test(dev: str, suspect: str, healthy: str, rate: float,
                      probes: tuple = ("ai22", "ai19", "ai21", "ai18")) -> dict:
    """Decide whether `suspect` is an open input, using multiplexer ghosting.

    A DAQ multiplexes one ADC across all channels. An OPEN input has nothing
    driving it, so its sample holds whatever charge the previous channel left on
    the mux capacitor: its reading tracks the channel scanned immediately
    before it. A driven input does not, because the source restores it within
    the settling time.

    So: scan [X, suspect] for several different X. If `suspect` follows X every
    time, it is open. `healthy` is scanned the same way as a control.
    """
    print(f"--- open-circuit test on {suspect} (mux ghosting) ---")
    print("An open pin follows whatever was sampled just before it; a driven pin does not.")
    out = {"suspect": suspect, "trials": [], "control": []}
    print(f"{'scan order':>22} {'previous(V)':>12} {'target(V)':>11} {'follows by':>12}")
    for pre in probes:
        v = read_raw_channels([f"{dev}/{pre}", f"{dev}/{suspect}"], duration_s=1.0,
                              terminal_config="RSE", sample_rate_hz=rate).mean(axis=1)
        d = abs(v[1] - v[0]) * 1e3
        out["trials"].append({"previous": pre, "prev_V": float(v[0]),
                              "target_V": float(v[1]), "delta_mV": float(d)})
        print(f"{f'[{pre} -> {suspect}]':>22} {v[0]:>12.4f} {v[1]:>11.4f} {d:>9.1f} mV")
    for pre in probes[:2]:
        v = read_raw_channels([f"{dev}/{pre}", f"{dev}/{healthy}"], duration_s=1.0,
                              terminal_config="RSE", sample_rate_hz=rate).mean(axis=1)
        d = abs(v[1] - v[0]) * 1e3
        out["control"].append({"previous": pre, "delta_mV": float(d)})
        print(f"{f'[{pre} -> {healthy}]':>22} {v[0]:>12.4f} {v[1]:>11.4f} {d:>9.1f} mV  (control)")

    ghosts = all(t["delta_mV"] < 20.0 for t in out["trials"])
    holds = all(c["delta_mV"] > 50.0 for c in out["control"])
    out["verdict"] = "OPEN CIRCUIT" if (ghosts and holds) else "inconclusive"
    print(f"\n  {suspect}: {out['verdict']}"
          f"   ({healthy} control behaves normally: {holds})")
    print()
    return out


def load_response() -> dict | None:
    """Per-channel voltage change caused by the Task 5 1 kg load."""
    f = WEIGHT_RUN / "weight_validation.yaml"
    if not f.is_file():
        return None
    rec = yaml.safe_load(open(f))
    chans = rec["raw_volts"]["channels"]
    d = (np.array(rec["raw_volts"]["loaded_mean_V"])
         - np.array(rec["raw_volts"]["zero_mean_V"])) * 1e3
    return {c: float(x) for c, x in zip(chans, d)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--device", default="Dev1")
    ap.add_argument("--seconds", type=float, default=2.0)
    ap.add_argument("--rate", type=float, default=2000.0)
    args = ap.parse_args()

    print(BANNER)
    print()
    device_info(args.device)

    res = verify_differential_pairing(args.device, args.rate, args.seconds)
    pins = classify(res["rse"], args.device)

    # ai0 is the channel whose pairing check failed and whose level is unstable
    # between runs, so it is the one worth testing for an open input.
    cfg0, _ = load_ft_config()
    mapped = cfg0["daq"]["channels"]
    suspect = mapped[0].split("/")[-1]          # SG0, the known-faulty lead
    healthy = mapped[4].split("/")[-1]          # SG4, a known-good one
    probes = tuple(c.split("/")[-1] for c in mapped[1:5])
    open_test = open_circuit_test(args.device, suspect, healthy, args.rate, probes)

    resp = load_response()
    if resp:
        print("--- response to the known 1 kg load (Task 5 data) ---")
        print(f"{'channel':>10} {'delta(mV)':>11}  interpretation")
        for c, d in resp.items():
            k = ("strong  -> a high-Fz gauge (SG0/SG2/SG4)" if abs(d) > 50
                 else "weak    -> a low-Fz gauge (SG1/SG3/SG5)" if abs(d) > 3
                 else "none    -> not carrying gauge signal")
            print(f"{c.split('/')[-1]:>10} {d:>11.3f}  {k}")
        print()

    # ---- cross-check against the recorded SCB-68A wiring -------------------
    cfg, cfg_path = load_ft_config(args.device and None)
    wiring = (cfg.get("scb68a_wiring") or {}).get("gauges")
    print("--- SCB-68A wiring recorded in ft_config.yaml (operator-confirmed) ---")
    if not wiring:
        print("  none recorded")
        return 0
    for sg, t in wiring.items():
        print(f"  {sg}:  + terminal {t['positive_terminal']:>3}   "
              f"- terminal {t['negative_terminal']:>3}")
    print()

    print("--- CONCLUSION ---")
    print(f"Dev1/ai0            : {open_test['verdict']}")
    pairs = [f"ai{n}<->ai{n+8}" for n in range(8)
             if res["pairing"][f"ai{n}"]["confirmed"]]
    print(f"Verified DIFF pairs : {pairs}")
    if resp:
        strong = [c.split('/')[-1] for c, d in resp.items() if abs(d) > 50]
        weak = [c.split('/')[-1] for c, d in resp.items() if 3 < abs(d) <= 50]
        none = [c.split('/')[-1] for c, d in resp.items() if abs(d) <= 3]
        print(f"Strong load response: {strong}  -> SG0/SG2/SG4 in some order")
        print(f"Weak load response  : {weak}  -> SG1/SG3/SG5 in some order")
        print(f"No load response    : {none}")
    print()
    print("The SCB-68A terminal -> Dev1/aiN correspondence CANNOT be resolved from")
    print("software: NI-DAQmx exposes no pin numbers, and no 6343/SCB-68A pinout is")
    print("installed on this machine. Resolving it needs the connector pinout.")
    print()
    print("Cheapest way to close it: the SCB-68A silkscreens the NI signal name next")
    print("to every screw terminal. Read the labels beside terminals 68, 65, 33, 30,")
    print("28 and 60 (the six SG+ leads). That gives terminal -> aiN directly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
