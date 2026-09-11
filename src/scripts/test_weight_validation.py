#!/usr/bin/env python3
"""
1 kg weight validation — calibration and channel-mapping sanity check.

Passive analog INPUT only: no output task, no device reset, no NI MAX write,
no robot access.

    # normal run, uses the mapping in ft_config.yaml
    /usr/bin/python3 src/scripts/test_weight_validation.py

    # also decide WHICH mapping is right, from one weight placement
    /usr/bin/python3 src/scripts/test_weight_validation.py --compare-mappings

Procedure (the operator is in the loop between the two measurements):

    1. sensor unloaded -> measure zero    W0
    2. operator places the mass on the sensor
    3. sensor loaded   -> measure         dW = W - W0

Expected: |Fz| ~= m*g = 9.81 N for 1 kg. Fx and Fy should be small. Small Tx/Ty
are normal and expected — they are m*g times the offset of the mass centre from
the sensor axis, so a few mm of eccentricity shows up as a few mN*m.

WHY THIS MATTERS ON THIS RIG
----------------------------
The SG->ai mapping is not confirmed here: a passive sweep found ai0 floating
and six live contiguous channels on ai1..ai6, one off from the expected
ai0..ai5. A wrong mapping raises no error, it silently returns wrong forces. A
known mass is the cheapest decisive test.

With --compare-mappings both measurements are taken over the UNION of every
candidate's channels in a single task, so all candidates are scored against the
same physical load and one weight placement settles it. Nothing is applied
automatically: the operator edits ft_config.yaml after seeing which one passes.

Results go to data/rig/weight_validation/YYYYMMDD_HHMMSS/.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vbts_platform.ati_calibration import WRENCH_AXES  # noqa: E402
from vbts_platform.ft_interface import (  # noqa: E402
    FTInterface,
    load_calibration,
    load_ft_config,
    read_raw_channels,
)

BANNER = """\
=========================================
ATI Mini45 1 kg WEIGHT VALIDATION

NO ROBOT MOTION
NO DAQ OUTPUT
========================================="""

OUTPUT_ROOT = PROJECT_ROOT / "data" / "rig" / "weight_validation"

# Candidate SG->ai mappings scored by --compare-mappings. All are plausible from
# the wiring evidence; the known mass decides between them.
CANDIDATE_MAPPINGS = {
    "ai1..ai6  (contiguous alternative)": [f"Dev1/ai{i}" for i in range(1, 7)],
    "ai0..ai5  (contiguous, connector 0)":           [f"Dev1/ai{i}" for i in range(0, 6)],
    "ai2..ai7  (contiguous alternative)":             [f"Dev1/ai{i}" for i in range(2, 8)],
}


def prompt(message: str, skip: bool) -> bool:
    if skip:
        print(f"[--yes] {message}  -> assumed already done")
        return True
    try:
        reply = input(f"{message}\n    Press Enter when ready, or 'n' to abort: ")
    except (EOFError, KeyboardInterrupt):
        print("\naborted.")
        return False
    if reply.strip().lower().startswith("n"):
        print("aborted.")
        return False
    return True


def fmt_wrench(w) -> str:
    return "  " + "  ".join(f"{ax}={w[i]:+9.4f}{'N' if i < 3 else 'Nm'}"
                            for i, ax in enumerate(WRENCH_AXES))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mass-kg", type=float, default=None)
    ap.add_argument("--seconds", type=float, default=3.0,
                    help="averaging time for each measurement (default 3)")
    ap.add_argument("--yes", action="store_true",
                    help="skip prompts; ONLY valid if the weight is already in place")
    ap.add_argument("--compare-mappings", action="store_true",
                    help="score every candidate SG->ai mapping on this measurement")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    print(BANNER)
    print()

    cfg, cfg_path = load_ft_config(args.config)
    cal = load_calibration(cfg, cfg_path)
    ft = FTInterface.from_config(args.config)
    val = cfg.get("validation") or {}
    mass = float(args.mass_kg if args.mass_kg is not None else val.get("test_mass_kg", 1.0))
    g = float(val.get("gravity_m_s2", 9.80665))
    tol = float(val.get("tolerance_fraction", 0.05))
    expected_fz = mass * g

    print(f"Sensor        : {cal.summary()}")
    print(f"DAQ           : {cfg['daq']['model']} {ft.device}, {ft.terminal_config}, "
          f"{ft.sample_rate_hz:,.0f} Hz")
    print(f"Channel map   : {ft.gauge_map}")
    print(f"  confirmed   : {ft.channel_mapping_confirmed}")
    print(f"Test mass     : {mass} kg   g = {g} m/s^2")
    print(f"Expected |Fz| : {expected_fz:.4f} N   tolerance +/-{tol*100:.0f}%")
    print(f"Frame         : {cfg['output']['frame']}")
    print()

    # Which channels to sample. In comparison mode, the union of all candidates
    # so every one is scored against the same physical load.
    if args.compare_mappings:
        sample_channels = sorted(
            {c for chans in CANDIDATE_MAPPINGS.values() for c in chans},
            key=lambda c: int(c.rsplit("ai", 1)[1]))
        print(f"Comparison mode: sampling union {sample_channels}")
        print()
    else:
        sample_channels = list(ft.channels)

    read_kw = dict(terminal_config=ft.terminal_config, voltage_range=ft.voltage_range,
                   sample_rate_hz=ft.sample_rate_hz, settle_samples=ft.settle_samples)
    idx_cfg = [sample_channels.index(c) for c in ft.channels]

    # ---- channel health on the configured six -----------------------------
    with ft:
        health = ft.check_channel_health(0.5)
    bad = [h for h in health if not h.ok]
    if bad:
        print("!! unhealthy channels on the configured mapping:")
        for h in bad:
            print(f"   {h.gauge} on {h.channel}: {h.verdict} "
                  f"(mean {h.mean_v:.4f} V, std {h.std_v*1e3:.2f} mV)")
        print("   Fix the wiring before trusting any force value.")
        print()

    # ---- step 1: unloaded --------------------------------------------------
    if not prompt("STEP 1/2 — remove ALL load from the sensor.", args.yes):
        return 2
    print(f"  measuring zero over {args.seconds:g} s ...")
    zero_mean = read_raw_channels(sample_channels, duration_s=args.seconds,
                                  **read_kw).mean(axis=1)
    tare_w = cal.to_wrench(zero_mean[idx_cfg])
    print("  tare wrench (absolute; this is now defined as zero):")
    print(fmt_wrench(tare_w))
    print()

    # ---- step 2: loaded ----------------------------------------------------
    if not prompt(f"STEP 2/2 — place the {mass} kg mass on the sensor, centred.", args.yes):
        return 2
    print(f"  measuring loaded over {args.seconds:g} s ...")
    loaded = read_raw_channels(sample_channels, duration_s=args.seconds, **read_kw)
    loaded_mean = loaded.mean(axis=1)
    loaded_std = loaded.std(axis=1, ddof=1)
    t_wall = time.time()

    dW = cal.to_wrench(loaded_mean[idx_cfg], bias=zero_mean[idx_cfg])
    W_abs = cal.to_wrench(loaded_mean[idx_cfg])

    print()
    print(f"--- RESULT, configured mapping (tared, frame {cfg['output']['frame']}) ---")
    print(fmt_wrench(dW))
    print()

    fz = float(dW[2])
    err = abs(fz) - expected_fz
    err_frac = err / expected_fz
    passed = abs(err_frac) <= tol

    print(f"{'Applied mass':<22}: {mass} kg")
    print(f"{'Expected |Fz|':<22}: {expected_fz:.4f} N")
    print(f"{'Measured Fz':<22}: {fz:+.4f} N")
    print(f"{'Measured |Fz|':<22}: {abs(fz):.4f} N")
    print(f"{'Sign':<22}: "
          f"{'negative (load pushes -Z)' if fz < 0 else 'positive (load pushes +Z)'}")
    print(f"{'Error':<22}: {err:+.4f} N  ({err_frac*100:+.2f} %)")
    print(f"{'Verdict':<22}: {'PASS' if passed else 'FAIL'}")
    print()
    print(f"{'Off-axis Fx':<22}: {dW[0]:+.4f} N")
    print(f"{'Off-axis Fy':<22}: {dW[1]:+.4f} N")
    print(f"{'Tx':<22}: {dW[3]:+.5f} N*m")
    print(f"{'Ty':<22}: {dW[4]:+.5f} N*m")
    print(f"{'Tz':<22}: {dW[5]:+.5f} N*m")
    if abs(fz) > 0.5:
        # A vertical load offset from the axis gives T = r x F, so r ~ T/F.
        print(f"{'Implied CoM offset':<22}: x={dW[4]/fz*1e3:+.2f} mm, "
              f"y={-dW[3]/fz*1e3:+.2f} mm  (from Ty/Fz and -Tx/Fz)")
    print()

    # ---- candidate mapping comparison --------------------------------------
    comparison, best = None, None
    if args.compare_mappings:
        print("--- CANDIDATE MAPPING COMPARISON (same physical load) ---")
        print(f"{'candidate':<52} {'Fz (N)':>10} {'err %':>9}  verdict")
        comparison = {}
        for label, chans in CANDIDATE_MAPPINGS.items():
            idx = [sample_channels.index(c) for c in chans]
            w = cal.to_wrench(loaded_mean[idx], bias=zero_mean[idx])
            e = (abs(w[2]) - expected_fz) / expected_fz
            ok = abs(e) <= tol
            print(f"{label:<52} {w[2]:>+10.4f} {e*100:>+9.2f}  {'PASS' if ok else 'fail'}")
            comparison[label] = {
                "channels": chans, "Fz_N": float(w[2]), "error_fraction": float(e),
                "passed": bool(ok),
                "wrench": {ax: float(w[i]) for i, ax in enumerate(WRENCH_AXES)},
            }
            if best is None or abs(e) < abs(comparison[best]["error_fraction"]):
                best = label
        print()
        if comparison[best]["passed"]:
            print(f"closest to {expected_fz:.3f} N: {best}")
            print(f"  -> set daq.channels to {comparison[best]['channels']}")
            print("     and daq.channel_mapping_confirmed: true in src/config/ft_config.yaml")
        else:
            # Naming a "closest" candidate when every one is ~100% wrong would
            # read as a recommendation. When nothing passes, nothing is closer.
            best = None
            print("NO candidate passed — none of them is 'closest', they are all wrong.")
            print("  -> Check the mass was actually on the sensor and on its Z axis.")
            print("     If it was, re-check the wiring: the mapping may not be a")
            print("     simple contiguous run of channels.")
        print()

    # ---- persist -----------------------------------------------------------
    run_dir = OUTPUT_ROOT / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)
    note = None
    if args.yes:
        note = ("Prompts were skipped with --yes. If no mass was actually placed between "
                "the two measurements then this run is a NO-LOAD CONTROL: dW near zero "
                "is the correct result and 'passed: false' does NOT indicate a fault.")
    record = {
        "acquired_at_wall": datetime.fromtimestamp(t_wall).isoformat(),
        "frame": cfg["output"]["frame"],
        "note": note,
        "test": {
            "mass_kg": mass, "gravity_m_s2": g, "expected_Fz_N": expected_fz,
            "tolerance_fraction": tol, "averaging_seconds": args.seconds,
            "operator_prompts": "skipped (--yes)" if args.yes else "interactive",
            "sampled_channels": sample_channels,
        },
        "result": {
            "measured_Fz_N": fz, "measured_abs_Fz_N": abs(fz),
            "error_N": err, "error_fraction": err_frac, "passed": bool(passed),
            "sign": "negative" if fz < 0 else "positive",
            "wrench_tared": {ax: float(dW[i]) for i, ax in enumerate(WRENCH_AXES)},
            "wrench_untared": {ax: float(W_abs[i]) for i, ax in enumerate(WRENCH_AXES)},
            "tare_wrench": {ax: float(tare_w[i]) for i, ax in enumerate(WRENCH_AXES)},
            "units": {"force": "N", "torque": "N_m"},
        },
        "raw_volts": {
            "channels": sample_channels,
            "zero_mean_V": [float(v) for v in zero_mean],
            "loaded_mean_V": [float(v) for v in loaded_mean],
            "loaded_std_V": [float(v) for v in loaded_std],
        },
        "channel_health": {h.gauge: h.verdict for h in health},
        "gauge_map": ft.gauge_map,
        "channel_mapping_confirmed_before_test": ft.channel_mapping_confirmed,
        "candidate_mapping_comparison": comparison,
        "best_candidate": best,
        "calibration": cal.metadata(),
        "robot": "NOT USED — FAIRINO not accessed in this measurement",
    }
    (run_dir / "weight_validation.yaml").write_text(
        yaml.safe_dump(record, sort_keys=False, default_flow_style=False))

    print(f"written: {run_dir}/weight_validation.yaml")
    print()
    if passed:
        print("PASS — calibration and channel mapping are consistent with a known load.")
        print("You may now set daq.channel_mapping_confirmed: true in src/config/ft_config.yaml.")
    else:
        print("FAIL for the configured mapping. Do NOT set channel_mapping_confirmed.")
        print("Likely causes, in order:")
        print("  1. wrong SG->ai mapping  (re-run with --compare-mappings)")
        print("  2. the mass was not actually on the sensor, or not on its Z axis")
        print("  3. a gauge channel is floating (see channel health above)")
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
