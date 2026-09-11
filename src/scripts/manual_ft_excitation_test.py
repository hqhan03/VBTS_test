#!/usr/bin/env python3
"""
Manual 6-axis excitation test for the ATI Mini45.

Passive analog INPUT only: no output task, no device reset, no NI MAX write,
no robot access.

    # you press ENTER between steps (default)
    /usr/bin/python3 src/scripts/manual_ft_excitation_test.py

    # hands-free: each step is announced, then counted down and recorded
    /usr/bin/python3 src/scripts/manual_ft_excitation_test.py --auto

PURPOSE
-------
Observe whether each wrench axis responds in the expected direction when a
person pushes or twists the sensor by hand. This is a DIRECTION and
CROSS-TALK check, not a calibration: the numbers are whatever a hand produces,
so only signs and relative magnitudes mean anything.

It uses the existing FTInterface and the existing FT29831.cal conversion
unchanged. No value is substituted, no channel is remapped, no gain or
compensation is applied. In particular SG5 is left exactly as the current
configuration reads it, because the point is to see what the known SG5 channel
fault actually does to the six outputs.

METHOD
------
Eight conditions, five seconds each. The first second of every segment is
discarded so the operator's hand can settle, and the mean is taken over the
following three seconds. Results are reported both as absolute wrench and as a
change from the unloaded baseline; the baseline-referenced numbers are the ones
that show direction.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from vbts_platform.ati_calibration import GAUGE_NAMES, WRENCH_AXES  # noqa: E402
from vbts_platform.ft_interface import (  # noqa: E402
    FTInterface,
    load_calibration,
    load_ft_config,
)

BANNER = """\
=================================
Manual F/T excitation test

NO ROBOT MOTION
NO DAQ OUTPUT
================================="""

OUTPUT_ROOT = PROJECT_ROOT / "data" / "rig" / "manual_ft_excitation"

# (key, instruction, the axis a correct rig should move most)
STEPS = [
    ("baseline",   "Remove all external load. Do not touch the sensor.",      None),
    ("push_+X",    "Push the sensor in the +X direction.",                    "Fx"),
    ("push_-X",    "Push the sensor in the -X direction.",                    "Fx"),
    ("push_+Y",    "Push the sensor in the +Y direction.",                    "Fy"),
    ("push_-Y",    "Push the sensor in the -Y direction.",                    "Fy"),
    ("push_+Z",    "Press straight down on the sensor (+Z).",                 "Fz"),
    ("torque_CW",  "Apply a clockwise torque about the vertical axis.",       "Tz"),
    ("torque_CCW", "Apply a counter-clockwise torque about the vertical axis.", "Tz"),
]

HOLD_S = 5.0        # recorded per condition
DISCARD_S = 1.0     # settling time thrown away at the start
AVERAGE_S = 3.0     # averaged window, taken after the discard


def countdown(msg: str, seconds: int) -> None:
    for k in range(seconds, 0, -1):
        print(f"\r  {msg} in {k} ... ", end="", flush=True)
        time.sleep(1.0)
    print("\r" + " " * 60 + "\r", end="", flush=True)


def run_segment(ft: FTInterface, cal, hold_s: float) -> tuple[np.ndarray, np.ndarray]:
    """Record `hold_s` of raw volts and return (volts, wrench), both (6, n)."""
    volts = ft.collect_raw(hold_s)
    return volts, cal.to_wrench(volts)


def segment_episodes(wrench: np.ndarray, base: np.ndarray, base_std: np.ndarray,
                     fs: float, k: float = 8.0, min_s: float = 0.6,
                     gap_s: float = 0.3) -> list[tuple[int, int]]:
    """Find the intervals where a hand was actually loading the sensor.

    Threshold on the force-magnitude deviation from baseline rather than on any
    single axis, so an episode is caught whichever direction it was pushed in.
    Short dropouts are bridged and brief blips discarded, so one push does not
    fragment into several and hand tremor does not register as an episode.
    """
    dev = np.linalg.norm(wrench[:3] - base[:3, None], axis=0)
    thr = max(k * float(np.linalg.norm(base_std[:3])), 0.25)     # N, with a floor
    active = dev > thr

    gap = int(gap_s * fs)
    idx = np.flatnonzero(active)
    if idx.size == 0:
        return []
    spans, start, prev = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - prev > gap:
            spans.append((start, prev))
            start = i
        prev = i
    spans.append((start, prev))
    return [(a, b) for a, b in spans if (b - a) / fs >= min_s]


def run_continuous(args, cfg, cfg_path, cfg_hash, cal, ft, run_dir, faults) -> int:
    """Record until told to stop, then work out what was applied when."""
    stop = Path(args.stop_file) if args.stop_file else None
    fs = ft.sample_rate_hz
    print("CONTINUOUS MODE")
    print(f"  baseline    : first {args.baseline_seconds:g} s — do not touch the sensor")
    print(f"  stop signal : {stop if stop else '(none: runs to --max-seconds)'}")
    print(f"  hard limit  : {args.max_seconds:g} s")
    print()

    chunks = []
    t0 = time.monotonic()
    with ft:
        print("  recording ...", flush=True)
        while True:
            chunks.append(ft.read_raw().volts)
            if stop is not None and stop.exists():
                print("  stop signal received.")
                break
            if time.monotonic() - t0 > args.max_seconds:
                print("  hard limit reached.")
                break
    volts = np.hstack(chunks)
    wrench = cal.to_wrench(volts)
    n = volts.shape[1]
    dur = n / fs
    print(f"  captured {n} samples ({dur:.1f} s) at {fs:,.0f} Hz")
    print()

    nb = int(args.baseline_seconds * fs)
    if n <= nb + int(fs):
        print("recording too short to contain a baseline plus any excitation.")
        return 2
    base = wrench[:, :nb].mean(axis=1)
    base_std = wrench[:, :nb].std(axis=1, ddof=1)

    spans = segment_episodes(wrench, base, base_std, fs)
    print(f"--- {len(spans)} excitation episode(s) detected ---")
    print(f"{'#':>3} {'t_start':>8} {'t_end':>7} {'dur':>6} " +
          " ".join(f"{a:>9}" for a in WRENCH_AXES) + "   dominant")
    episodes, seg_rows = [], []
    for j, (a, b) in enumerate(spans, 1):
        # average the middle half of the episode: skip the ramp in and out
        m0 = a + (b - a) // 4
        m1 = b - (b - a) // 4
        d = wrench[:, m0:m1].mean(axis=1) - base
        sd = wrench[:, m0:m1].std(axis=1, ddof=1)
        forces = {ax: d[i] for i, ax in enumerate(WRENCH_AXES[:3])}
        torques = {ax: d[i + 3] for i, ax in enumerate(WRENCH_AXES[3:])}
        dom_f = max(forces, key=lambda x: abs(forces[x]))
        dom_t = max(torques, key=lambda x: abs(torques[x]))
        dom = dom_f if abs(forces[dom_f]) / max(abs(torques[dom_t]), 1e-9) > 20 else f"{dom_f}/{dom_t}"
        print(f"{j:>3} {a/fs:>8.2f} {b/fs:>7.2f} {(b-a)/fs:>6.2f} " +
              " ".join(f"{v:>9.3f}" for v in d) + f"   {dom}")
        ep = {"index": j, "t_start_s": float(a / fs), "t_end_s": float(b / fs),
              "duration_s": float((b - a) / fs),
              "delta": {ax: float(v) for ax, v in zip(WRENCH_AXES, d)},
              "std": {ax: float(v) for ax, v in zip(WRENCH_AXES, sd)},
              "dominant_force_axis": dom_f, "dominant_torque_axis": dom_t,
              "cross_axis_ratio": {ax: float(d[i] / d[WRENCH_AXES.index(dom_f)])
                                   for i, ax in enumerate(WRENCH_AXES)
                                   if abs(d[WRENCH_AXES.index(dom_f)]) > 1e-9}}
        episodes.append(ep)
        seg_rows.append([j, f"{a/fs:.3f}", f"{b/fs:.3f}", f"{(b-a)/fs:.3f}", dom_f, dom_t] +
                        [f"{v:.6f}" for v in d] + [f"{v:.6f}" for v in sd])
    print()

    dt = 1.0 / fs
    with open(run_dir / "raw.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["sample_index", "t_rel_s", "episode"] +
                   [f"{g}_V" for g in GAUGE_NAMES] +
                   ["Fx_N", "Fy_N", "Fz_N", "Tx_Nm", "Ty_Nm", "Tz_Nm"])
        ep_of = np.zeros(n, dtype=int)
        for j, (a, b) in enumerate(spans, 1):
            ep_of[a:b] = j
        for s in range(n):
            w.writerow([s, f"{s*dt:.6f}", int(ep_of[s])] +
                       [f"{v:.9f}" for v in volts[:, s]] +
                       [f"{v:.9f}" for v in wrench[:, s]])
    with open(run_dir / "segment_summary.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["episode", "t_start_s", "t_end_s", "duration_s",
                    "dominant_force_axis", "dominant_torque_axis"] +
                   [f"d{a}" for a in WRENCH_AXES] + [f"{a}_std" for a in WRENCH_AXES])
        w.writerows(seg_rows)
    (run_dir / "summary.yaml").write_text(yaml.safe_dump({
        "mode": "continuous", "timestamp": datetime.now().isoformat(),
        "configuration_sha256": cfg_hash, "configuration_file": str(cfg_path),
        "calibration_file_name": cal.source_path.name, "calibration_serial": cal.serial,
        "daq_channel_list": list(ft.channels), "gauge_map": ft.gauge_map,
        "connector": cfg["daq"].get("connector"), "sample_rate_hz": fs,
        "terminal_configuration": ft.terminal_config,
        "channel_mapping_confirmed": ft.channel_mapping_confirmed,
        "all_channels_healthy": cfg["daq"].get("all_channels_healthy"),
        "known_hardware_faults": faults, "frame": cfg["output"]["frame"],
        "duration_s": float(dur), "n_samples": int(n),
        "baseline_seconds": float(args.baseline_seconds),
        "baseline": {a: float(v) for a, v in zip(WRENCH_AXES, base)},
        "baseline_std": {a: float(v) for a, v in zip(WRENCH_AXES, base_std)},
        "episodes": episodes,
        "note": ("Direction and cross-talk observation only. No calibration change, no "
                 "channel remap, no substituted value, no gain or software compensation."),
        "robot": "NOT USED — FAIRINO not accessed",
    }, sort_keys=False, allow_unicode=True))
    print(f"written: {run_dir}")
    for f in sorted(run_dir.iterdir()):
        print(f"  {f.name}  ({f.stat().st_size:,} bytes)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--auto", action="store_true",
                    help="hands-free: announce, count down, then record")
    ap.add_argument("--lead-in", type=int, default=4,
                    help="seconds of warning before recording in --auto (default 4)")
    ap.add_argument("--hold", type=float, default=HOLD_S)
    ap.add_argument("--continuous", action="store_true",
                    help="record freely until --stop-file appears, then auto-segment")
    ap.add_argument("--stop-file", default=None,
                    help="continuous mode: recording ends when this path exists")
    ap.add_argument("--max-seconds", type=float, default=600.0,
                    help="continuous mode: hard stop, so a lost stop-file cannot run forever")
    ap.add_argument("--baseline-seconds", type=float, default=3.0,
                    help="continuous mode: untouched interval at the start")
    ap.add_argument("--output-root", default=None,
                    help="directory to write the run into (default data/rig/manual_ft_excitation)")
    ap.add_argument("--config", default=None)
    args = ap.parse_args()

    print(BANNER)
    print()

    cfg, cfg_path = load_ft_config(args.config)
    cal = load_calibration(cfg, cfg_path)
    ft = FTInterface.from_config(args.config)
    cfg_hash = hashlib.sha256(cfg_path.read_bytes()).hexdigest()

    print(f"Sensor    : {cal.summary()}")
    print(f"DAQ       : {cfg['daq']['model']} {ft.device}, connector "
          f"{cfg['daq'].get('connector')}, {ft.terminal_config}, {ft.sample_rate_hz:,.0f} Hz")
    print(f"Channels  : {ft.gauge_map}")
    print(f"  mapping confirmed : {ft.channel_mapping_confirmed}")
    print(f"  all channels ok   : {cfg['daq'].get('all_channels_healthy')}")
    faults = cfg["daq"].get("known_hardware_faults") or []
    for f in faults:
        # The fault record schema has changed once already, so read it
        # defensively rather than let a header line crash an acquisition.
        chan = f.get("daq_channel") or f.get("channel") or f.get("path") or "?"
        what = (f.get("status") or f.get("fault") or "").strip().splitlines()
        print(f"  !! KNOWN FAULT: {chan} — {what[0] if what else 'see ft_config.yaml'}")
        if chan in ft.channels:
            print(f"     WARNING: {chan} is assigned to a gauge in the active mapping")
    print(f"Frame     : {cfg['output']['frame']}")
    print()
    print(f"Each condition records {args.hold:g} s; the first {DISCARD_S:g} s is discarded "
          f"and the next {AVERAGE_S:g} s averaged.")
    print()

    root = Path(args.output_root) if args.output_root else OUTPUT_ROOT
    run_dir = root / datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    if args.continuous:
        return run_continuous(args, cfg, cfg_path, cfg_hash, cal, ft, run_dir, faults)

    segments = {}
    raw_rows = []
    dt = 1.0 / ft.sample_rate_hz

    with ft:
        for i, (key, instruction, expect) in enumerate(STEPS):
            print(f"--- Step {i}: {key} ---")
            print(f"  {instruction}")
            if args.auto:
                countdown("recording starts", args.lead_in)
            else:
                try:
                    r = input("  Press ENTER to record (or 'q' to stop): ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print("\n  aborted by operator."); break
                if r.startswith("q"):
                    print("  stopped by operator."); break

            print(f"  recording {args.hold:g} s — hold steady ...", flush=True)
            volts, wrench = run_segment(ft, cal, args.hold)
            n = volts.shape[1]

            i0 = int(DISCARD_S * ft.sample_rate_hz)
            i1 = min(n, i0 + int(AVERAGE_S * ft.sample_rate_hz))
            win = wrench[:, i0:i1]
            segments[key] = {
                "instruction": instruction, "expected_axis": expect,
                "n_samples": int(n), "n_averaged": int(win.shape[1]),
                "mean": {a: float(v) for a, v in zip(WRENCH_AXES, win.mean(axis=1))},
                "std": {a: float(v) for a, v in zip(WRENCH_AXES, win.std(axis=1, ddof=1))},
                "volts_mean": {g: float(v) for g, v in zip(GAUGE_NAMES, volts[:, i0:i1].mean(axis=1))},
            }
            for s in range(n):
                raw_rows.append([key, s, f"{s*dt:.6f}"] +
                                [f"{v:.9f}" for v in volts[:, s]] +
                                [f"{v:.9f}" for v in wrench[:, s]])
            m = segments[key]["mean"]
            print("  -> " + "  ".join(f"{a}={m[a]:+8.3f}" for a in WRENCH_AXES))
            print()

    if "baseline" not in segments:
        print("no baseline recorded; nothing to report.")
        return 2

    base = segments["baseline"]["mean"]
    base_std = segments["baseline"]["std"]
    # A change smaller than this is indistinguishable from the sensor sitting
    # still, so naming a "dominant axis" for it would be reading meaning into
    # noise. 5 sigma of the baseline scatter on that same axis.
    NOISE_K = 5.0

    # ---- raw.csv -----------------------------------------------------------
    with open(run_dir / "raw.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["condition", "sample_index", "t_rel_s"] +
                   [f"{g}_V" for g in GAUGE_NAMES] +
                   ["Fx_N", "Fy_N", "Fz_N", "Tx_Nm", "Ty_Nm", "Tz_Nm"])
        w.writerows(raw_rows)

    # ---- segment_summary.csv ----------------------------------------------
    with open(run_dir / "segment_summary.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["condition", "expected_axis"] +
                   [f"{a}_abs" for a in WRENCH_AXES] +
                   [f"d{a}" for a in WRENCH_AXES] +
                   [f"{a}_std" for a in WRENCH_AXES])
        for k, s in segments.items():
            w.writerow([k, s["expected_axis"] or ""] +
                       [f"{s['mean'][a]:.6f}" for a in WRENCH_AXES] +
                       [f"{s['mean'][a]-base[a]:.6f}" for a in WRENCH_AXES] +
                       [f"{s['std'][a]:.6f}" for a in WRENCH_AXES])

    # ---- report ------------------------------------------------------------
    print("=" * 78)
    print("ABSOLUTE WRENCH (untared)          frame:", cfg["output"]["frame"])
    print(f"{'condition':<12} " + " ".join(f"{a:>9}" for a in WRENCH_AXES))
    for k, s in segments.items():
        print(f"{k:<12} " + " ".join(f"{s['mean'][a]:>9.3f}" for a in WRENCH_AXES))
    print()
    print("CHANGE FROM BASELINE  (this is what shows direction)")
    print(f"{'condition':<12} " + " ".join(f"{a:>9}" for a in WRENCH_AXES) +
          "   dominant / expected")
    analysis = {}
    for k, s in segments.items():
        if k == "baseline":
            continue
        d = {a: s["mean"][a] - base[a] for a in WRENCH_AXES}
        forces = {a: d[a] for a in ("Fx", "Fy", "Fz")}
        torques = {a: d[a] for a in ("Tx", "Ty", "Tz")}
        dom_f = max(forces, key=lambda a: abs(forces[a]))
        dom_t = max(torques, key=lambda a: abs(torques[a]))
        exp = s["expected_axis"]
        dom = dom_t if (exp and exp.startswith("T")) else dom_f
        floor = NOISE_K * base_std[dom]
        responded = abs(d[dom]) > floor
        analysis[k] = {
            "delta": d, "dominant_force_axis": dom_f, "dominant_torque_axis": dom_t,
            "expected_axis": exp,
            "responded_above_noise": bool(responded),
            "noise_floor_used": float(floor),
            "dominant_matches_expected": (dom == exp) if (exp and responded) else None,
            "secondary_force_axes": {a: v for a, v in forces.items() if a != dom_f},
            "cross_axis_ratio": ({a: (v / d[dom]) for a, v in d.items() if a != dom}
                                 if responded and abs(d[dom]) > 0 else None),
        }
        if not responded:
            mark = f"   no response (all < {floor:.3f})"
        elif exp is None:
            mark = f"   {dom}"
        else:
            mark = f"   {dom}" + ("  match" if dom == exp else f"  <- expected {exp}")
        print(f"{k:<12} " + " ".join(f"{d[a]:>9.3f}" for a in WRENCH_AXES) + mark)
    print("=" * 78)
    print()
    print("Force units N, torque units N*m. Magnitudes are whatever the operator's")
    print("hand applied, so compare signs and ratios, not absolute values.")
    print()

    # ---- summary.yaml ------------------------------------------------------
    (run_dir / "summary.yaml").write_text(yaml.safe_dump({
        "timestamp": datetime.now().isoformat(),
        "configuration_sha256": cfg_hash,
        "configuration_file": str(cfg_path),
        "calibration_file_name": cal.source_path.name,
        "calibration_serial": cal.serial,
        "daq_channel_list": list(ft.channels),
        "gauge_map": ft.gauge_map,
        "connector": cfg["daq"].get("connector"),
        "sample_rate_hz": ft.sample_rate_hz,
        "terminal_configuration": ft.terminal_config,
        "channel_mapping_confirmed": ft.channel_mapping_confirmed,
        "all_channels_healthy": cfg["daq"].get("all_channels_healthy"),
        "known_hardware_faults": faults,
        "frame": cfg["output"]["frame"],
        "segment_timing": {"hold_s": args.hold, "discarded_s": DISCARD_S,
                           "averaged_s": AVERAGE_S},
        "baseline": base,
        "segments": segments,
        "analysis": analysis,
        "note": ("Direction and cross-talk observation only. No calibration change, no "
                 "channel remap, no substituted value, no gain or software compensation. "
                 "SG5 is read exactly as the current configuration defines it."),
        "robot": "NOT USED — FAIRINO not accessed",
    }, sort_keys=False, allow_unicode=True))

    print(f"written: {run_dir}")
    for f in sorted(run_dir.iterdir()):
        print(f"  {f.name}  ({f.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
