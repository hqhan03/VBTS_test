#!/usr/bin/env python3
"""Re-fit an image scale from the frames a scale sweep already wrote.

The sweep is the expensive part: five presses per axis, two minutes of robot
time, and a gel that has to be mounted. The fit is a page of arithmetic over
ten PNGs. When the fit improves -- as it did on 2026-09-08, when
`_track_series` learned to notice that a correlation had collapsed to zero
shift rather than fitting a straight line through the collapse -- every sweep
on disk can be re-fitted without touching the robot.

It reads `scale_ball4/scale.csv` for the achieved offsets and the file names
(never a directory listing: a re-run at a different sweep width leaves both
runs' PNGs side by side, and globbing them mixes two sweeps into one fit), and
runs exactly the tracking and Jacobian code the live phase runs. The result
replaces `scale.rot0` in `state.json` and rewrites `scale.yaml`, with
`refit_from_frames_at` recording when and `refit_note` recording why.

    scripts/refit_scale.py                    # every run in the dataset
    scripts/refit_scale.py --unit 9DTact_medium_1mm_r2   # one unit's runs
    scripts/refit_scale.py --dry-run          # report, write nothing
"""
import argparse
import csv
import datetime as dt
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import cv2
import numpy as np
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from run_indentation import (_diff_f32, _scale_jacobian, _track_series,  # noqa: E402
                             _window_for, shadows_the_gel)

DATASET = "20260905_passA_ball4"


def refit(run: Path, probe: str, theta_tol: float, max_rms: float,
          template: int, search: int, verbose: bool):
    out = run / f"scale_{probe}"
    csv_path = out / "scale.csv"
    state_path = run / "state.json"
    if not csv_path.exists() or not state_path.exists():
        return None
    ref = cv2.imread(str(run / "reference.png"))
    if ref is None:
        return None
    rows = list(csv.DictReader(csv_path.open()))
    if not rows:
        return None
    st = json.loads(state_path.read_text())
    # Grey loses a DIGIT's imprint; see `_diff_f32`. The unit is read from the
    # run so a re-fit uses the same reduction the live phase did.
    sid = (yaml.safe_load((run / "meta.yaml").read_text()) or {}).get("sensor_id") \
        if (run / "meta.yaml").exists() else None
    colour = shadows_the_gel(sid)
    old = ((st.get("scale") or {}).get("rot0") or {})
    result = dict(old)                      # keep plane, cop, force, offsets
    log = []
    for axis in ("x", "y"):
        r = sorted([x for x in rows if x["axis"] == axis],
                   key=lambda z: float(z["offset_mm"]))
        if len(r) < 3:
            continue
        imgs = []
        for x in r:
            f = out / x["file"]
            im = cv2.imread(str(f))
            if im is None:
                log.append(f"  axis {axis}: {x['file']} is missing")
                imgs = []
                break
            imgs.append(_diff_f32(im, ref, colour))
        if not imgs:
            continue
        mid = len(r) // 2
        m = (imgs[mid] >= 6).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
        nb, _, stt, cen = cv2.connectedComponentsWithStats(m, 8)
        if nb < 2:
            log.append(f"  axis {axis}: no contact region to track")
            continue
        k = 1 + int(np.argmax(stt[1:, cv2.CC_STAT_AREA]))
        cx, cy = int(cen[k][0]), int(cen[k][1])
        half, srch = _window_for(imgs[mid].shape, cx, cy, template, search)
        if half == 0:
            log.append(f"  axis {axis}: no correlation window fits at ({cx}, {cy})")
            continue
        p = _track_series(imgs, cx, cy, half, srch, log=log.append)
        o = np.array([float(x[f"achieved_{axis}_mm"])
                      - float(r[mid][f"achieved_{axis}_mm"]) for x in r])
        for ci, comp in ((0, "x"), (1, "y")):
            v = p[:, ci]
            g = np.isfinite(v)
            if int(g.sum()) < 3:
                continue
            sl, ic = np.polyfit(o[g], v[g], 1)
            result[f"px_per_mm_{axis}{comp}"] = float(sl)
            result[f"rms_px_{axis}{comp}"] = float(
                np.sqrt(((v[g] - (sl * o[g] + ic)) ** 2).mean()))
            result[f"n_fit_{axis}{comp}"] = int(g.sum())
    buf = io.StringIO()
    with redirect_stdout(buf):
        _scale_jacobian(result, theta_tol, max_rms)
    if verbose:
        print(buf.getvalue().rstrip())
    return result, old, log, st


def summary(d):
    return (max(d.get("rms_px_xx", float("nan")), d.get("rms_px_yy", float("nan"))),
            d.get("theta_disagreement_deg", float("nan")),
            d.get("px_per_mm_image_x", float("nan")),
            bool(d.get("scale_trusted")))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", default=DATASET)
    ap.add_argument("--unit", default=None, help="only runs of this sensor")
    ap.add_argument("--probe", default="ball4")
    ap.add_argument("--scale-theta-tol", type=float, default=3.0)
    ap.add_argument("--scale-max-rms-px", type=float, default=5.0)
    ap.add_argument("--scale-template", type=int, default=260)
    ap.add_argument("--scale-search", type=int, default=200)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()

    base = ROOT / "data" / "9DTact" / a.dataset
    runs = sorted(d for d in base.iterdir() if d.is_dir()
                  and (a.unit is None or d.name == a.unit
                       or d.name.startswith(a.unit + "__")))
    stamp = dt.datetime.now().astimezone().isoformat(timespec="seconds")
    changed = 0
    print(f"{'run':32} {'rms':>13} {'dtheta':>13} {'kx px/mm':>15}   verdict")
    for run in runs:
        got = refit(run, a.probe, a.scale_theta_tol, a.scale_max_rms_px,
                    a.scale_template, a.scale_search, a.verbose)
        if got is None:
            continue
        new, old, log, st = got
        ro, to, ko, po = summary(old)
        rn, tn, kn, pn = summary(new)
        verdict = ("now trusted" if pn and not po else
                   "no longer trusted" if po and not pn else
                   "trusted" if pn else "still not trusted")
        print(f"{run.name:32} {ro:6.2f}->{rn:6.2f} {to:6.2f}->{tn:6.2f} "
              f"{ko:7.2f}->{kn:7.2f}   {verdict}")
        for z in log:
            print(f"    {z.strip()}")
        if a.dry_run:
            continue
        new["refit_from_frames_at"] = stamp
        new["refit_note"] = ("re-fitted from the frames on disk with the "
                             "collapsed-correlation repair of 2026-09-08")
        st.setdefault("scale", {})["rot0"] = new
        state = run / "state.json"
        state.write_text(json.dumps(st, indent=2, sort_keys=False))
        with (run / f"scale_{a.probe}" / "scale.yaml").open("w") as fh:
            yaml.safe_dump(new, fh, sort_keys=False)
        changed += 1
    print(f"\n{changed} run(s) rewritten" if not a.dry_run else "\ndry run: nothing written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
