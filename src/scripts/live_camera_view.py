#!/usr/bin/env python3
"""
Live VBTS camera view, with capture.

    live_camera_view.py                  # raw view
    live_camera_view.py --with-force     # also read the F/T (holds the DAQ)
    live_camera_view.py --reference path/to/reference.png

KEYS
    c / SPACE   capture the current frame (lossless PNG)
    r           take the current frame as the reference
    d           cycle view: raw -> difference -> difference, amplified
    + / -       change the difference gain
    q / ESC     quit

WHY THE DIFFERENCE VIEW MATTERS
-------------------------------
A raw VBTS frame is a smooth illumination blob and a contact barely shows in it.
What carries the contact is the difference from the unloaded gel, so that is the
view to jog against. The reference is loaded from the active indentation run if
there is one; 'r' re-takes it, which is what to do after the gel has been left
to settle.

The camera is a single resource. While this is open, run_indentation.py cannot
grab a frame -- quit first, then sample. The same applies to --with-force and
the DAQ.
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from vbts_platform.camera_interface import Camera  # noqa: E402
from vbts_platform.ft_stream import ForceReader  # noqa: E402

OUT = ROOT / "data" / "camera_captures"
ACTIVE_RUN = ROOT / "data" / "_active_run.txt"

MODES = ("raw", "difference", "difference x4")


def find_reference(explicit: str | None) -> tuple[np.ndarray | None, str]:
    if explicit:
        img = cv2.imread(explicit)
        return (img, explicit) if img is not None else (None, f"{explicit} (unreadable)")
    if ACTIVE_RUN.is_file():
        p = ROOT / "data" / ACTIVE_RUN.read_text().strip() / "reference.png"
        if p.is_file():
            return cv2.imread(str(p)), str(p)
    return None, "none — press r to take one"


def render(frame: np.ndarray, ref: np.ndarray | None, mode: str, gain: float):
    if mode == "raw" or ref is None or ref.shape != frame.shape:
        return frame
    g = gain * (4.0 if mode.endswith("x4") else 1.0)
    d = frame.astype(np.int16) - ref.astype(np.int16)
    return np.clip(128 + g * d, 0, 255).astype(np.uint8)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", default=None)
    ap.add_argument("--with-force", action="store_true",
                    help="also show the F/T reading; holds the DAQ")
    ap.add_argument("--scale", type=float, default=0.66, help="display scale")
    a = ap.parse_args()

    ref, ref_src = find_reference(a.reference)
    mode_i, gain = 0, 1.0

    ft = None
    tare = None
    if a.with_force:
        from vbts_platform.ft_interface import FTInterface
        state = None
        if ACTIVE_RUN.is_file():
            sp = (ROOT / "data" / ACTIVE_RUN.read_text().strip()
                  / "state.json")
            if sp.is_file():
                state = json.loads(sp.read_text())
        if state and state.get("tare"):
            tare = np.array(state["tare"]["tare_wrench"], dtype=float)
        ft = FTInterface.from_config()
        ft.connect()

    session = OUT / datetime.now().strftime("%Y%m%d_%H%M%S")
    cam = Camera.from_config()
    cam.open()
    print(f"  camera {cam.applied['width']}x{cam.applied['height']} "
          f"{cam.applied['fourcc']}, auto_exposure {cam.applied['auto_exposure']} "
          "(1 = manual)")
    print(f"  reference: {ref_src}")
    if a.with_force:
        print(f"  F/T: connected, zero {'from the active run' if tare is not None else 'NOT set — showing untared'}")
    print("\n  c capture   r reference   d view   +/- gain   q quit\n")

    win = "VBTS live"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    reader = ForceReader(ft, tare).start() if ft is not None else None
    n_cap, t0, frames, fps = 0, time.time(), 0, 0.0
    wrench = np.zeros(6)
    ft_error = None
    try:
        while True:
            try:
                frame, _ = cam.grab()
            except Exception as exc:
                print(f"  grab failed: {exc}")
                break
            frames += 1
            if time.time() - t0 >= 1.0:
                fps = frames / (time.time() - t0)
                frames, t0 = 0, time.time()

            if reader is not None:
                wrench, err = reader.read()
                if err and not ft_error:
                    ft_error = err
                    print(f"  F/T reading stopped: {err}")

            q = Camera.quality(frame)
            view = render(frame, ref, MODES[mode_i], gain)
            disp = cv2.resize(view, None, fx=a.scale, fy=a.scale,
                              interpolation=cv2.INTER_AREA)

            lines = [f"{MODES[mode_i]}"
                     + (f"  gain {gain:.1f}" if mode_i else "")
                     + f"   {fps:4.1f} fps   captured {n_cap}",
                     f"centre mean {q['centre_mean']:6.1f}   "
                     f"sat {q['centre_saturated_pct']:5.2f}%   "
                     f"black {q['centre_black_pct']:5.2f}%"]
            if reader is not None:
                F = wrench[:3]
                lines.append(f"F {F[0]:+6.2f} {F[1]:+6.2f} {F[2]:+7.2f} N   "
                             f"|F| {np.linalg.norm(F):6.2f} N"
                             + ("   [STOPPED]" if ft_error else ""))
            if q["centre_saturated_pct"] > 0.5:
                lines.append("SATURATED - contact region is clipped")
            if ref is None and mode_i:
                lines.append("no reference - press r")

            y = 26
            for i, s in enumerate(lines):
                col = ((60, 60, 255) if ("SATURATED" in s or "no reference" in s)
                       else (255, 255, 255))
                cv2.putText(disp, s, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 0, 0), 3, cv2.LINE_AA)
                cv2.putText(disp, s, (12, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            col, 1, cv2.LINE_AA)
                y += 24

            cv2.imshow(win, disp)
            k = cv2.waitKey(1) & 0xFF
            if k in (ord("q"), 27):
                break
            if k in (ord("c"), 32):
                session.mkdir(parents=True, exist_ok=True)
                n_cap += 1
                name = f"{n_cap:04d}.png"
                cv2.imwrite(str(session / name), frame,
                            [cv2.IMWRITE_PNG_COMPRESSION, 1])
                rec = {"file": name, "at": datetime.now().isoformat(),
                       "quality": q, "camera_controls": cam.applied}
                if reader is not None and not ft_error:
                    rec["wrench"] = wrench.tolist()
                    rec["wrench_tared"] = tare is not None
                with open(session / "captures.jsonl", "a") as fh:
                    fh.write(json.dumps(rec) + "\n")
                print(f"  captured {name}"
                      + (f"   |F| {np.linalg.norm(wrench[:3]):.2f} N"
                         if reader is not None and not ft_error else ""))
            elif k == ord("r"):
                ref = frame.copy()
                ref_src = "taken live"
                print("  reference taken from the current frame")
            elif k == ord("d"):
                mode_i = (mode_i + 1) % len(MODES)
            elif k in (ord("+"), ord("=")):
                gain = min(gain * 1.5, 64.0)
            elif k in (ord("-"), ord("_")):
                gain = max(gain / 1.5, 0.25)
    finally:
        cv2.destroyAllWindows()
        if reader is not None:
            reader.stop()
        cam.close()
        if ft is not None:
            ft.disconnect()
    if n_cap:
        print(f"\n  {n_cap} capture(s) in {session}")
    print("  camera released" + ("; DAQ released" if ft is not None else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
