#!/usr/bin/env python3
"""
Locate the ATI gauge signals among the PCIe-6343's analog inputs, by measurement.

Passive analog INPUT only: no output task, no device reset, no NI MAX write,
no robot access. Reads nothing from ft_config.yaml's channel list and writes
nothing to it — this script exists to establish the mapping independently.

METHOD
------
A strain-gauge output is identified by how it RESPONDS, not by its level. So
scan every analog input twice, once unloaded and once with a known mass, and
look at the change:

    delta(channel) = mean_loaded(channel) - mean_unloaded(channel)

A channel wired to a gauge moves; an unconnected one does not. Matching the
per-channel delta against the deltas measured independently at the SCB-68A
screw terminals with a meter then names each channel.

The two measurements need the operator to change the load in between, so this
runs in two phases and keeps state in a file:

    diagnose_ati_daq_mapping.py --phase zero    # sensor unloaded
    ... operator places the mass ...
    diagnose_ati_daq_mapping.py --phase load    # sensor loaded -> report

TERMINAL REFERENCE (operator-measured with a meter, 2026-08-25)
---------------------------------------------------------------
    SG0 = terminal 68 - terminal 34 : 1.175 V unloaded, 1.155 V loaded, -20 mV
    SG5 = terminal 60 - terminal 26 : 1.348 V unloaded, 1.340 V loaded,  -8 mV

Note terminal 34, not 35. On the NI 68-pin connector AI0+ is pin 68 and its
differential partner AI0- is pin 34, so SG0 IS a proper differential pair. An
earlier diagnosis of "ai0 open circuit" was made against a single-ended read
of pin 68 alone and does not survive that correction; it is not reused here.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vbts_platform.ft_interface import read_raw_channels  # noqa: E402

BANNER = """\
====================================
ATI Mini45 -> NI DAQ MAPPING DIAGNOSTIC

NO ROBOT ACCESS
NO DAQ OUTPUT
===================================="""

STATE = PROJECT_ROOT / "data" / "daq_mapping" / "_scan_state.json"

# Differential channels on a 68-pin X Series device: aiN pairs with ai(N+8).
# Connector 0 serves ai0-ai15, connector 1 serves ai16-ai31.
DIFF_CHANNELS = [f"Dev1/ai{i}" for i in list(range(8)) + list(range(16, 24))]

# What the operator measured at the terminals, in millivolts.
TERMINAL_REFERENCE = {
    "SG0": {"terminals": "68 - 34", "unloaded_V": 1.175, "loaded_V": 1.155, "delta_mV": -20.0},
    "SG5": {"terminals": "60 - 26", "unloaded_V": 1.348, "loaded_V": 1.340, "delta_mV": -8.0},
}


def scan(rate: float, secs: float) -> dict:
    diff = read_raw_channels(DIFF_CHANNELS, duration_s=secs,
                             terminal_config="differential", sample_rate_hz=rate)
    rse_ch = [f"Dev1/ai{i}" for i in range(32)]
    rse = read_raw_channels(rse_ch, duration_s=secs,
                            terminal_config="RSE", sample_rate_hz=rate)
    return {
        "diff": {c: [float(r.mean()), float(r.std(ddof=1))] for c, r in zip(DIFF_CHANNELS, diff)},
        "rse": {c: [float(r.mean()), float(r.std(ddof=1))] for c, r in zip(rse_ch, rse)},
    }


def phase_zero(args) -> int:
    print("STATE A — sensor must be UNLOADED.")
    if not args.yes:
        try:
            if input("    Press Enter when unloaded, or 'n' to abort: ").strip().lower().startswith("n"):
                print("aborted."); return 2
        except (EOFError, KeyboardInterrupt):
            print("\naborted."); return 2
    print(f"  scanning {len(DIFF_CHANNELS)} differential + 32 single-ended, {args.seconds:g} s each ...")
    data = scan(args.rate, args.seconds)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"zero": data, "rate": args.rate, "seconds": args.seconds}))
    print(f"  saved -> {STATE}")
    print()
    print(f"{'channel':>11} {'DIFF mean(V)':>13} {'std(mV)':>9}")
    for c, (m, s) in data["diff"].items():
        print(f"{c.split('/')[-1]:>11} {m:>13.5f} {s*1e3:>9.3f}")
    print()
    print("Now place the 1.004 kg mass, then run:  --phase load")
    return 0


def phase_load(args) -> int:
    if not STATE.is_file():
        print(f"no zero scan found at {STATE}; run --phase zero first")
        return 2
    st = json.loads(STATE.read_text())
    print("STATE B — sensor must be LOADED with the known mass.")
    if not args.yes:
        try:
            if input("    Press Enter when loaded, or 'n' to abort: ").strip().lower().startswith("n"):
                print("aborted."); return 2
        except (EOFError, KeyboardInterrupt):
            print("\naborted."); return 2
    print(f"  scanning ...")
    now = scan(st["rate"], st["seconds"])

    print()
    print("--- ATI signals measured at the SCB-68A terminals (operator, meter) ---")
    print(f"{'signal':>7} {'terminals':>12} {'unloaded(V)':>12} {'loaded(V)':>11} {'delta(mV)':>11}")
    for sg, r in TERMINAL_REFERENCE.items():
        print(f"{sg:>7} {r['terminals']:>12} {r['unloaded_V']:>12.3f} "
              f"{r['loaded_V']:>11.3f} {r['delta_mV']:>11.1f}")
    print()

    print(f"--- DIFFERENTIAL scan: delta = loaded - unloaded ---")
    print(f"{'channel':>11} {'pair':>12} {'zero(V)':>10} {'load(V)':>10} "
          f"{'delta(mV)':>11}  responds")
    rows = []
    for c in DIFF_CHANNELS:
        z = st["zero"]["diff"][c][0]; l = now["diff"][c][0]
        d = (l - z) * 1e3
        n = int(c.rsplit("ai", 1)[1])
        resp = "YES" if abs(d) > 2.0 else "-"
        rows.append((c, d))
        print(f"{c.split('/')[-1]:>11} {'ai%d-ai%d' % (n, n+8):>12} {z:>10.5f} "
              f"{l:>10.5f} {d:>11.3f}  {resp}")
    print()

    responders = [(c, d) for c, d in rows if abs(d) > 2.0]
    print(f"Channels that responded to the load: "
          f"{[c.split('/')[-1] for c, _ in responders]}  ({len(responders)} of {len(rows)})")
    print()

    print("--- matching NI channels to the meter-measured ATI signals ---")
    print(f"{'ATI signal':>11} {'terminals':>12} {'target(mV)':>11} "
          f"{'best channel':>13} {'its delta(mV)':>14} {'diff(mV)':>10}")
    mapping = {}
    for sg, r in TERMINAL_REFERENCE.items():
        tgt = r["delta_mV"]
        best, bd = min(rows, key=lambda cd: abs(cd[1] - tgt))
        mapping[sg] = {"channel": best, "delta_mV": bd, "target_mV": tgt,
                       "mismatch_mV": bd - tgt, "terminals": r["terminals"]}
        print(f"{sg:>11} {r['terminals']:>12} {tgt:>11.1f} "
              f"{best.split('/')[-1]:>13} {bd:>14.3f} {bd - tgt:>10.3f}")
    print()

    out = PROJECT_ROOT / "data" / "daq_mapping"
    out.mkdir(parents=True, exist_ok=True)
    import csv
    with open(out / "channel_delta_scan.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["channel", "mode", "zero_mean_V", "loaded_mean_V", "delta_mV"])
        for c in DIFF_CHANNELS:
            z = st["zero"]["diff"][c][0]; l = now["diff"][c][0]
            w.writerow([c, "DIFF", f"{z:.9f}", f"{l:.9f}", f"{(l-z)*1e3:.4f}"])
        for c in [f"Dev1/ai{i}" for i in range(32)]:
            z = st["zero"]["rse"][c][0]; l = now["rse"][c][0]
            w.writerow([c, "RSE", f"{z:.9f}", f"{l:.9f}", f"{(l-z)*1e3:.4f}"])
    import yaml
    (out / "mapping_result.yaml").write_text(yaml.safe_dump({
        "method": "delta of DIFF channel means between unloaded and loaded states",
        "sample_rate_hz": st["rate"], "seconds_per_scan": st["seconds"],
        "terminal_reference_operator_meter": TERMINAL_REFERENCE,
        "responding_channels": [c for c, _ in responders],
        "all_diff_deltas_mV": {c: float(d) for c, d in rows},
        "matched": mapping,
        "note": ("Matching is by response magnitude against meter readings taken at the "
                 "screw terminals. It names the channels carrying SG0 and SG5; the other "
                 "four gauges need their own terminal measurements to be named the same way."),
        "robot": "NOT USED",
    }, sort_keys=False, allow_unicode=True))
    print(f"written: {out}/channel_delta_scan.csv")
    print(f"         {out}/mapping_result.yaml")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=("zero", "load"), required=True)
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--rate", type=float, default=1000.0)
    ap.add_argument("--yes", action="store_true")
    args = ap.parse_args()
    print(BANNER); print()
    return phase_zero(args) if args.phase == "zero" else phase_load(args)


if __name__ == "__main__":
    raise SystemExit(main())
