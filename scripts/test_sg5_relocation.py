#!/usr/bin/env python3
"""
Validate the temporary relocation of SG5 onto the AI6 differential pair.

Passive analog INPUT only: no output task, no device reset, no NI MAX write,
no robot access. Reads nothing from ft_config.yaml's channel list and writes
nothing to it — this is a wiring check, not a configuration change.

    test_sg5_relocation.py --phase zero    # sensor unloaded
    ... operator places the 1.004 kg mass ...
    test_sg5_relocation.py --phase load    # sensor loaded -> report

WHAT CHANGED
------------
SG5 was previously on SCB-68A terminals 60 (+) / 26 (-). The signal was present
there on a meter (1.348 V unloaded, 1.340 V loaded) but never reached the DAQ:
Dev1/ai5 behaved as an open input, returning whatever the multiplexer sampled
before it. It has now been moved to the AI6 differential pair, AI6+ / AI14-,
which is the hardware-bonded pair for Dev1/ai6.

WHAT DECIDES THE OUTCOME
------------------------
Three things have to hold together, because any one alone can mislead:

  1. LEVEL      ai6 should sit near 1.348 V unloaded, the meter's SG5 reading.
  2. RESPONSE   ai6 should change by roughly -8 mV under the 1.004 kg load.
  3. INDEPENDENCE  ai6 must not merely copy a neighbour. A ghosting input also
     produces a stable, in-range, load-correlated-looking number, which is how
     the previous fault went unnoticed. So ai6 is additionally checked by
     varying which channel is scanned before it, and its response is compared
     against SG4's: on the old wiring SG5 tracked SG4 to within 2 mV across
     deltas spanning three orders of magnitude.
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
SG5 RELOCATION VALIDATION  (AI6 pair)

NO ROBOT ACCESS
NO DAQ OUTPUT
===================================="""

OUT = PROJECT_ROOT / "data" / "rig" / "sg5_relocation"
STATE = OUT / "_state.json"

CHANNELS = [f"Dev1/ai{i}" for i in range(8)]
# Which channel SG5 is currently wired to. Overridable with --sg5-channel so
# the same validation can be pointed at successive relocation attempts without
# touching ft_config.yaml.
SG5_NEW = "Dev1/ai6"        # default: the AI6+ / AI14- pair
SG5_OLD = "Dev1/ai5"        # terminals 60/26, open
SG4 = "Dev1/ai4"

# Gauge assignments that are already confirmed and unchanged by this move.
ASSIGNED = {"Dev1/ai0": "SG0", "Dev1/ai2": "SG1", "Dev1/ai1": "SG2",
            "Dev1/ai3": "SG3", "Dev1/ai4": "SG4"}

METER = {"terminals_before": "60 / 26", "unloaded_V": 1.348,
         "loaded_V": 1.340, "delta_mV": -8.0}

GHOST_MV = 20.0     # a driven channel differs from its predecessor by far more


def scan(rate: float, secs: float) -> dict:
    v = read_raw_channels(CHANNELS, duration_s=secs,
                          terminal_config="differential", sample_rate_hz=rate)
    return {c: [float(r.mean()), float(r.std(ddof=1))] for c, r in zip(CHANNELS, v)}


def ghost_test(target: str, rate: float, hi: str = "Dev1/ai2", lo: str = "Dev1/ai3",
               reps: int = 3) -> dict:
    """Measure how much of its predecessor a channel picks up.

    Two predecessors with well-separated levels are ALTERNATED, and the target
    is re-read after each. Alternating rather than sweeping is what separates
    coupling from drift: a slow drift shifts both groups equally and cancels in
    the difference, while coupling shows up as a consistent offset between them.

    A fixed-predecessor control is run first for the same reason. Without it a
    spread across trials cannot be attributed, which is how an earlier version
    of this check reported an alarming 228 mV that turned out to be mostly the
    sensor drifting between reads.

    crosstalk = (mean target after `hi` - mean target after `lo`)
                / (level of `hi` - level of `lo`)
    """
    if target in (hi, lo):
        hi, lo = ("Dev1/ai0", "Dev1/ai3") if target != "Dev1/ai0" else ("Dev1/ai1", "Dev1/ai3")

    def read_after(pre):
        v = read_raw_channels([pre, target], duration_s=0.8,
                              terminal_config="differential", sample_rate_hz=rate).mean(axis=1)
        return float(v[0]), float(v[1])

    control = [read_after(lo)[1] for _ in range(reps)]
    drift_mV = (max(control) - min(control)) * 1e3

    prev_hi, prev_lo, tgt_hi, tgt_lo = [], [], [], []
    for _ in range(reps):
        p, t = read_after(hi); prev_hi.append(p); tgt_hi.append(t)
        p, t = read_after(lo); prev_lo.append(p); tgt_lo.append(t)

    swing = (sum(prev_hi) / reps - sum(prev_lo) / reps)
    shift = (sum(tgt_hi) / reps - sum(tgt_lo) / reps)
    xt = abs(shift / swing) * 100.0 if abs(swing) > 1e-6 else float("nan")
    gap = abs(sum(tgt_lo) / reps - sum(prev_lo) / reps) * 1e3
    return {
        "predecessors": {"high": hi, "low": lo},
        "predecessor_swing_mV": float(swing * 1e3),
        "target_shift_mV": float(shift * 1e3),
        "crosstalk_percent": float(xt),
        "control_drift_mV": float(drift_mV),
        "min_gap_mV": float(gap),
        "ghosting": bool(xt > 50.0),
        "target_mean_V": float(sum(tgt_lo) / reps),
    }


def confirm(msg: str, skip: bool) -> bool:
    print(msg)
    if skip:
        print("  [--yes] assumed already done")
        return True
    try:
        return not input("    Press Enter when ready, or 'n' to abort: ").strip().lower().startswith("n")
    except (EOFError, KeyboardInterrupt):
        print("\naborted."); return False


def phase_zero(a) -> int:
    if not confirm("STATE A — sensor must be UNLOADED.", a.yes):
        print("aborted."); return 2
    print(f"  scanning ai0..ai7 differential, {a.seconds:g} s ...")
    data = scan(a.rate, a.seconds)
    OUT.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"zero": data, "rate": a.rate, "seconds": a.seconds}))
    print()
    print(f"{'channel':>11} {'pair':>13} {'mean(V)':>10} {'std(mV)':>9}  assignment")
    for c in CHANNELS:
        n = int(c.rsplit("ai", 1)[1])
        m, s = data[c]
        tag = ASSIGNED.get(c, "SG5 (relocated)" if c == SG5_NEW
                           else "(vacated)" if c == SG5_OLD else "")
        print(f"{c.split('/')[-1]:>11} {'ai%d-ai%d' % (n, n+8):>13} {m:>10.5f} {s*1e3:>9.3f}  {tag}")
    print()
    d = data[SG5_NEW][0]
    print(f"  ai6 = {d:.5f} V vs meter SG5 unloaded {METER['unloaded_V']} V "
          f"-> difference {abs(d - METER['unloaded_V'])*1e3:.1f} mV")
    print(f"  saved -> {STATE}")
    print()
    print("Now place the 1.004 kg mass, then run:  --phase load")
    return 0


def phase_load(a) -> int:
    if not STATE.is_file():
        print(f"no State A at {STATE}; run --phase zero first"); return 2
    st = json.loads(STATE.read_text())
    if not confirm("STATE B — sensor must be LOADED with the 1.004 kg mass.", a.yes):
        print("aborted."); return 2
    print("  scanning ...")
    now = scan(st["rate"], st["seconds"])

    print()
    print("--- differential scan, ai0..ai7 ---")
    print(f"{'channel':>11} {'unloaded(V)':>12} {'loaded(V)':>11} {'delta(mV)':>11}  assignment")
    deltas = {}
    for c in CHANNELS:
        z, l = st["zero"][c][0], now[c][0]
        deltas[c] = (l - z) * 1e3
        tag = ASSIGNED.get(c, "SG5 (relocated)" if c == SG5_NEW
                           else "(vacated)" if c == SG5_OLD else "")
        print(f"{c.split('/')[-1]:>11} {z:>12.5f} {l:>11.5f} {deltas[c]:>11.3f}  {tag}")
    print()

    # -- the three criteria --------------------------------------------------
    lvl = now[SG5_NEW][0]
    lvl_ok = abs(st["zero"][SG5_NEW][0] - METER["unloaded_V"]) < 0.050
    d6 = deltas[SG5_NEW]
    resp_ok = abs(d6) > 2.0
    near_expected = abs(d6 - METER["delta_mV"]) < 6.0

    print("--- ghosting check (a copied channel also looks stable and plausible) ---")
    gh = {c: ghost_test(c, st["rate"]) for c in (SG5_NEW, SG5_OLD, SG4)}
    print(f"{'channel':>11} {'swing(mV)':>11} {'shift(mV)':>11} {'crosstalk':>11} "
          f"{'drift(mV)':>10}  verdict")
    for c in (SG5_NEW, SG4, SG5_OLD):
        g = gh[c]
        tag = {SG5_NEW: "SG5 (relocated)", SG4: "SG4 (control)",
               SG5_OLD: "old SG5 pin, now vacated"}[c]
        print(f"{c.split('/')[-1]:>11} {g['predecessor_swing_mV']:>11.1f} "
              f"{g['target_shift_mV']:>11.2f} {g['crosstalk_percent']:>10.2f}% "
              f"{g['control_drift_mV']:>10.2f}  "
              f"{'OPEN (ghosting)' if g['ghosting'] else 'driven'}   {tag}")
    indep_ok = not gh[SG5_NEW]["ghosting"]
    print()

    d4 = deltas[SG4]
    print("--- SG4 vs SG5 independence ---")
    print(f"  SG4 (ai4) delta : {d4:+8.3f} mV")
    print(f"  SG5 ({SG5_NEW.split(chr(47))[-1]}) delta : {d6:+8.3f} mV")
    print(f"  difference      : {abs(d6 - d4):8.3f} mV")
    print("  On the old wiring these matched to within 2 mV across deltas from")
    print("  2 mV to 1619 mV, which is what proved SG5 was copying SG4.")
    distinct = abs(d6 - d4) > 5.0
    print(f"  -> {'DISTINCT, not a copy of SG4' if distinct else 'still tracking SG4'}")
    print()

    detected = bool(lvl_ok and resp_ok and indep_ok and distinct)
    print("=" * 70)
    print(f"  1. level near meter (1.348 V)     : {'PASS' if lvl_ok else 'FAIL'} "
          f"({st['zero'][SG5_NEW][0]:.5f} V)")
    print(f"  2. responds to the load           : {'PASS' if resp_ok else 'FAIL'} "
          f"({d6:+.3f} mV, meter said {METER['delta_mV']:+.1f} mV"
          f"{', close match' if near_expected else ''})")
    print(f"  3. driven, not ghosting           : {'PASS' if indep_ok else 'FAIL'}")
    print(f"  4. independent of SG4             : {'PASS' if distinct else 'FAIL'}")
    print()
    print(f"  SG5 DETECTED ON {SG5_NEW}: {'YES' if detected else 'NO'}")
    print("=" * 70)

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "relocation_scan.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["channel", "assignment", "unloaded_mean_V", "unloaded_std_V",
                    "loaded_mean_V", "loaded_std_V", "delta_mV"])
        for c in CHANNELS:
            z, zs = st["zero"][c]; l, ls = now[c]
            tag = ASSIGNED.get(c, "SG5_relocated" if c == SG5_NEW
                               else "vacated" if c == SG5_OLD else "")
            w.writerow([c, tag, f"{z:.9f}", f"{zs:.9f}", f"{l:.9f}", f"{ls:.9f}",
                        f"{(l-z)*1e3:.4f}"])
    import yaml
    (OUT / "relocation_result.yaml").write_text(yaml.safe_dump({
        "sg5_temporary_connection": {"positive": "AI6+", "negative": "AI14-",
                                     "daq_channel": SG5_NEW,
                                     "previous_terminals": METER["terminals_before"],
                                     "previous_daq_channel": SG5_OLD},
        "meter_reference": METER,
        "deltas_mV": {c: float(v) for c, v in deltas.items()},
        "unloaded_V": {c: float(st["zero"][c][0]) for c in CHANNELS},
        "loaded_V": {c: float(now[c][0]) for c in CHANNELS},
        "ghosting_check": gh,
        "criteria": {"level_near_meter": bool(lvl_ok), "responds_to_load": bool(resp_ok),
                     "close_to_expected_delta": bool(near_expected),
                     "driven_not_ghosting": bool(indep_ok),
                     "independent_of_SG4": bool(distinct)},
        "sg5_detected": detected,
        "config_modified": False,
        "robot": "NOT USED",
    }, sort_keys=False, allow_unicode=True))
    print(f"\nwritten: {OUT}/relocation_scan.csv")
    print(f"         {OUT}/relocation_result.yaml")
    return 0 if detected else 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--phase", choices=("zero", "load"), required=True)
    ap.add_argument("--seconds", type=float, default=3.0)
    ap.add_argument("--rate", type=float, default=1000.0)
    ap.add_argument("--yes", action="store_true")
    ap.add_argument("--sg5-channel", default=None,
                    help="channel SG5 is currently wired to, e.g. Dev1/ai7")
    a = ap.parse_args()
    if a.sg5_channel:
        global SG5_NEW
        SG5_NEW = a.sg5_channel
    print(BANNER)
    print(f"  SG5 under test: {SG5_NEW}")
    print()
    return phase_zero(a) if a.phase == "zero" else phase_load(a)


if __name__ == "__main__":
    raise SystemExit(main())
