#!/usr/bin/env python3
"""
Find which NI physical channel actually carries ATI SG5.

Passive analog INPUT only: no output task, no device reset, no NI MAX write,
no robot access. Reads nothing from ft_config.yaml's channel list and writes
nothing to it — this exists to establish the answer independently.

    diagnose_sg5_mapping.py --phase zero    # sensor unloaded
    ... operator places the 1.004 kg mass ...
    diagnose_sg5_mapping.py --phase load    # sensor loaded -> report

WHAT IS KNOWN GOING IN
----------------------
SG5+ : ATI IFPS pin 4  -> SCB-68A terminal 60   (continuity confirmed)
SG5- : ATI IFPS pin 13 -> SCB-68A terminal 26   (continuity confirmed)
Meter across 60-26, power on: 1.348 V unloaded, 1.340 V loaded, delta -8 mV.

So the analog signal exists at the terminal block. The open question is only
which DAQ input it lands on. SG5 = ai5 is NOT assumed.

WHY BOTH RSE AND DIFF ARE SCANNED
---------------------------------
The 6343 has 32 single-ended inputs bonded into 16 differential pairs: DIFF is
available on ai0-ai7 and ai16-ai23 only, and the negative leg of aiN is
physically ai(N+8). That bonding is fixed in the hardware, so a signal whose
reference lands on some other pin cannot be read differentially no matter how
the wiring is labelled.

That distinction is the whole point here:

  * If terminal 60 is a valid AI positive AND terminal 26 is its bonded
    negative, the signal shows up in the DIFF scan.
  * If terminal 60 is a valid AI positive but terminal 26 is NOT its bonded
    negative, then RSE will see the signal on terminal 60's channel while DIFF
    on that channel reads an undriven negative leg and ghosts.

This is exactly the failure SG0 had: its reference was on terminal 35 (AI GND)
instead of 34 (AI0-), so DIFF ai0 behaved as an open circuit while the signal
was really present. Scanning both modes tells the two cases apart.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vbts_platform.ft_interface import read_raw_channels  # noqa: E402

BANNER = """\
====================================
SG5 -> NI CHANNEL MAPPING DIAGNOSTIC

NO ROBOT ACCESS
NO DAQ OUTPUT
===================================="""

OUT = PROJECT_ROOT / "data" / "rig" / "sg5_mapping"
STATE = OUT / "_state.json"

RSE_CHANNELS = [f"Dev1/ai{i}" for i in range(32)]
DIFF_CHANNELS = [f"Dev1/ai{i}" for i in list(range(8)) + list(range(16, 24))]

# Operator's meter reading at the terminals.
METER = {"terminals": "60 - 26", "unloaded_V": 1.348, "loaded_V": 1.340, "delta_mV": -8.0}

# Gauges already confirmed in Task 9/10, so their channels can be excluded when
# looking for the one that is still unaccounted for.
KNOWN = {"SG0": "Dev1/ai0", "SG1": "Dev1/ai2", "SG2": "Dev1/ai1",
         "SG3": "Dev1/ai3", "SG4": "Dev1/ai4"}

# A channel whose reading tracks its predecessor by less than this is ghosting.
GHOST_MV = 20.0


def acquire(rate: float, secs: float) -> dict:
    rse = read_raw_channels(RSE_CHANNELS, duration_s=secs,
                            terminal_config="RSE", sample_rate_hz=rate)
    dif = read_raw_channels(DIFF_CHANNELS, duration_s=secs,
                            terminal_config="differential", sample_rate_hz=rate)
    return {
        "rse": {c: [float(r.mean()), float(r.std(ddof=1))] for c, r in zip(RSE_CHANNELS, rse)},
        "diff": {c: [float(r.mean()), float(r.std(ddof=1))] for c, r in zip(DIFF_CHANNELS, dif)},
    }


def confirm(msg: str, skip: bool) -> bool:
    print(msg)
    if skip:
        print("  [--yes] assumed already done")
        return True
    try:
        return not input("    Press Enter when ready, or 'n' to abort: ").strip().lower().startswith("n")
    except (EOFError, KeyboardInterrupt):
        print("\naborted.")
        return False


def phase_zero(a) -> int:
    if not confirm("STATE A — sensor must be UNLOADED.", a.yes):
        print("aborted."); return 2
    print(f"  scanning 32 single-ended + {len(DIFF_CHANNELS)} differential, {a.seconds:g} s each ...")
    data = acquire(a.rate, a.seconds)
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"zero": data, "rate": a.rate, "seconds": a.seconds}))
    print(f"  saved -> {STATE}")
    print()
    print("Now place the 1.004 kg mass centred on the VBTS, then run:  --phase load")
    return 0


def ghost_test(channels: list[str], term: str, rate: float) -> dict:
    """Which of `channels` merely track the channel scanned before them."""
    out = {}
    for target in channels:
        probes = [c for c in channels if c != target][:4]
        deltas = []
        for pre in probes:
            v = read_raw_channels([pre, target], duration_s=0.6,
                                  terminal_config=term, sample_rate_hz=rate).mean(axis=1)
            deltas.append(abs(v[1] - v[0]) * 1e3)
        out[target] = {"min_gap_mV": float(min(deltas)),
                       "ghosting": all(d < GHOST_MV for d in deltas)}
    return out


def phase_load(a) -> int:
    if not STATE.is_file():
        print(f"no State A found at {STATE}; run --phase zero first"); return 2
    st = json.loads(STATE.read_text())
    if not confirm("STATE B — sensor must be LOADED with the 1.004 kg mass.", a.yes):
        print("aborted."); return 2
    print("  scanning ...")
    now = acquire(st["rate"], st["seconds"])

    def deltas(mode, chans):
        return {c: (now[mode][c][0] - st["zero"][mode][c][0]) * 1e3 for c in chans}

    d_rse = deltas("rse", RSE_CHANNELS)
    d_diff = deltas("diff", DIFF_CHANNELS)

    print()
    print("--- SG5 at the terminal block (operator meter) ---")
    print(f"  terminals {METER['terminals']}: {METER['unloaded_V']} V unloaded, "
          f"{METER['loaded_V']} V loaded, delta {METER['delta_mV']:+.1f} mV")
    print()

    print("--- SINGLE-ENDED scan, all 32 inputs (each pin vs AIGND) ---")
    print(f"{'channel':>9} {'zero(V)':>10} {'load(V)':>10} {'delta(mV)':>11}  responds")
    for c in RSE_CHANNELS:
        z, l, dd = st["zero"]["rse"][c][0], now["rse"][c][0], d_rse[c]
        print(f"{c.split('/')[-1]:>9} {z:>10.5f} {l:>10.5f} {dd:>11.3f}"
              f"  {'YES' if abs(dd) > 2.0 else '-'}")
    print()

    print("--- DIFFERENTIAL scan (aiN minus ai(N+8), hardware-bonded pairs) ---")
    print(f"{'channel':>9} {'pair':>12} {'zero(V)':>10} {'load(V)':>10} "
          f"{'delta(mV)':>11}  responds")
    for c in DIFF_CHANNELS:
        n = int(c.rsplit("ai", 1)[1])
        z, l, dd = st["zero"]["diff"][c][0], now["diff"][c][0], d_diff[c]
        print(f"{c.split('/')[-1]:>9} {'ai%d-ai%d' % (n, n+8):>12} {z:>10.5f} "
              f"{l:>10.5f} {dd:>11.3f}  {'YES' if abs(dd) > 2.0 else '-'}")
    print()

    # Which single-ended pins moved, and which are not already spoken for.
    resp_rse = {c: v for c, v in d_rse.items() if abs(v) > 2.0}
    unaccounted = {c: v for c, v in resp_rse.items() if c not in KNOWN.values()}
    print(f"Single-ended pins that responded : {[c.split('/')[-1] for c in resp_rse]}")
    print(f"Already assigned to SG0-SG4      : {[c.split('/')[-1] for c in KNOWN.values()]}")
    print(f"Unaccounted for                  : {[c.split('/')[-1] for c in unaccounted]}")
    print()

    # Ghosting is what separates "signal present" from "channel readable".
    print("--- ghosting check on the differential channels of interest ---")
    interest = [c for c in DIFF_CHANNELS if int(c.rsplit("ai", 1)[1]) < 8]
    gh = ghost_test(interest, "differential", st["rate"])
    print(f"{'channel':>9} {'min gap to predecessor(mV)':>28}  verdict")
    for c in interest:
        g = gh[c]
        print(f"{c.split('/')[-1]:>9} {g['min_gap_mV']:>28.1f}  "
              f"{'OPEN (ghosting)' if g['ghosting'] else 'driven'}")
    print()

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "sg5_scan.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["channel", "mode", "zero_mean_V", "zero_std_V",
                    "loaded_mean_V", "loaded_std_V", "delta_mV"])
        for mode, chans in (("RSE", RSE_CHANNELS), ("DIFF", DIFF_CHANNELS)):
            for c in chans:
                z, zs = st["zero"][mode.lower()][c]
                l, ls = now[mode.lower()][c]
                w.writerow([c, mode, f"{z:.9f}", f"{zs:.9f}", f"{l:.9f}", f"{ls:.9f}",
                            f"{(l-z)*1e3:.4f}"])

    import yaml
    (OUT / "sg5_result.yaml").write_text(yaml.safe_dump({
        "meter_at_terminals": METER,
        "known_gauge_channels": KNOWN,
        "rse_deltas_mV": {c: float(v) for c, v in d_rse.items()},
        "diff_deltas_mV": {c: float(v) for c, v in d_diff.items()},
        "responding_single_ended": [c for c in resp_rse],
        "unaccounted_single_ended": [c for c in unaccounted],
        "ghosting_check": {c: gh[c] for c in interest},
        "sample_rate_hz": st["rate"], "seconds_per_scan": st["seconds"],
        "config_modified": False,
        "robot": "NOT USED",
    }, sort_keys=False, allow_unicode=True))
    print(f"written: {OUT}/sg5_scan.csv")
    print(f"         {OUT}/sg5_result.yaml")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=("zero", "load"), required=True)
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--rate", type=float, default=1000.0)
    ap.add_argument("--yes", action="store_true")
    a = ap.parse_args()
    print(BANNER); print()
    return phase_zero(a) if a.phase == "zero" else phase_load(a)


if __name__ == "__main__":
    raise SystemExit(main())
