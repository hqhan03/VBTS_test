#!/usr/bin/env python3
"""How much does the force move while a frame is being taken?

cross_principle.md 3.2 found the shear floor tracks label motion, using
`lat_rate_per_frame` -- the label change between consecutive SAVED frames. That
proxy is not comparable across principles: the saved-frame interval is 412 ms on
9DTact and 196 ms on DIGIT, and the averaging window that produces a frame's
label ([t_exposure_start, t_img]) is 205 ms against 60 ms. What actually makes a
label ambiguous is the force change inside THAT window, so measure it directly
from the 50 Hz F/T stream:

  blur_fz_N    median over frames of (max - min) Fz within [t_exposure_start, t_img]
  blur_lat_N   the same for the lateral magnitude sqrt(Fx^2 + Fy^2)
  blur_*_p90   the 90th percentile, i.e. the worst frames rather than the typical one
  rate_*_N_per_s  |dF|/dt between consecutive saved frames, per second, so the
                  glide pacing itself is comparable across principles
  win_ms, dt_ms   the two time scales above, per unit

Writes data/label_blur.csv (one row per unit, all three principles).
"""
import re, glob, yaml
import numpy as np, pandas as pd
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DS = {"9DTact": "data/20260911_VBTSresolution_dataset/9DTact/20260907_passB_ball8",
      "DIGIT_Marker": "data/20260911_VBTSresolution_dataset/DIGIT_Marker/20260908_passB_ball8",
      "DIGIT": "data/20260911_VBTSresolution_dataset/DIGIT/20260908_passB_ball8"}


def canonical_runs(principle, ds):
    can = ROOT / ds / "CANONICAL.yaml"
    if can.exists():
        c = yaml.safe_load(can.read_text())["canonical"]
        return [(u, ROOT / ds / v["run"]) for u, v in c.items() if v.get("run")]
    out = []
    for p in sorted((ROOT / ds).glob(f"{principle}_*")):
        if not re.search(r"__\d+$", p.name):
            out.append((p.name, p))
    return out


def blur_for(run):
    fr = pd.read_csv(run / "stream" / "frames.csv")
    ft = pd.read_csv(run / "stream" / "ft.csv").sort_values("t")
    t = ft.t.values
    fz = ft.Fz.values
    lat = np.hypot(ft.Fx.values, ft.Fy.values)
    a = np.searchsorted(t, fr.t_exposure_start.values)
    b = np.searchsorted(t, fr.t_img.values, side="right")
    dz, dl = [], []
    for i, j in zip(a, b):
        if j - i < 2:                      # window shorter than one F/T sample
            continue
        dz.append(fz[i:j].max() - fz[i:j].min())
        dl.append(lat[i:j].max() - lat[i:j].min())
    dz, dl = np.array(dz), np.array(dl)
    fzs = fr.get("Fz_s_corr", fr.get("Fz_s")).astype(float).values
    lats = np.hypot(fr.get("Fx_s_corr", fr.get("Fx_s")).astype(float).values,
                    fr.get("Fy_s_corr", fr.get("Fy_s")).astype(float).values)
    dt = np.diff(fr.t_img.values)
    ok = dt > 0
    return dict(
        n_frames=len(fr), n_windows=len(dz),
        win_ms=float(np.median(fr.t_img - fr.t_exposure_start) * 1000),
        dt_ms=float(np.median(dt) * 1000),
        blur_fz_N=float(np.median(dz)), blur_fz_p90=float(np.percentile(dz, 90)),
        blur_lat_N=float(np.median(dl)), blur_lat_p90=float(np.percentile(dl, 90)),
        rate_fz_N_per_s=float(np.median(np.abs(np.diff(fzs))[ok] / dt[ok])),
        rate_lat_N_per_s=float(np.median(np.abs(np.diff(lats))[ok] / dt[ok])),
    )


if __name__ == "__main__":
    rows = []
    for principle, ds in DS.items():
        for unit, run in canonical_runs(principle, ds):
            if not (run / "stream" / "ft.csv").exists():
                print(f"  skip {unit}: no ft.csv"); continue
            m = re.search(r"(soft|medium|hard)_(\d)mm_r(\d)", unit)
            r = dict(unit=unit, principle=principle,
                     hardness=m.group(1), thickness_mm=int(m.group(2)),
                     rep=int(m.group(3)), run=run.name)
            r.update(blur_for(run))
            rows.append(r)
            print(f"  {unit:30s} win {r['win_ms']:3.0f} ms  blur Fz {r['blur_fz_N']:.4f}  "
                  f"lat {r['blur_lat_N']:.4f}  rate Fz {r['rate_fz_N_per_s']:.3f} N/s", flush=True)
    out = ROOT / "data" / "label_blur.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print("  ->", out, len(rows), "units")
