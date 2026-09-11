#!/usr/bin/env python3
"""Does the F/T averaging window used to label a frame move the force floor?

cross_principle.md 3.2 found that the shear floor tracks how far the force
moves within a frame (lat_rate_per_frame), not the sensor's noise. If so, the
label's time window matters: a label averaged over the exposure is the mean
force while the picture integrated; a label taken at one instant, or over a
longer window, disagrees with the picture by a gel-dependent amount.

Re-labels every frame from stream/ft.csv (50 Hz) with several windows and trains
the same network at one size on each, same split/seed:

  exposure     mean over [t_exposure_start, t_img]           (what collect does)
  instant      the ft sample nearest t_img
  pre100       mean over [t_exposure_start - 0.10, t_img]
  sym250       mean over [t_img - 0.25, t_img + 0.25]
  sym500       mean over [t_img - 0.50, t_img + 0.50]

Output: data/analysis/label_window_ablation.csv (unit, window, fz_mae_normal,
lat_mae_shear, ...). One size (320x180), 1 seed, so ~15 s per cell on a shared GPU.
"""
import os, sys, csv, time, numpy as np, pandas as pd
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import force_vs_resolution as F

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WINDOWS = {"exposure": None, "instant": (0.0, 0.0), "pre100": (-0.10, None), "sym250": ("sym", 0.25), "sym500": ("sym", 0.50)}


def relabel(run, window):
    fr = pd.read_csv(os.path.join(run, "stream", "frames.csv"))
    fz = fr["Fz_s_corr"].fillna(fr["Fz_s"]) if "Fz_s_corr" in fr else fr["Fz_s"]
    fr = fr[(fz.abs() <= 2.0) & (fr.get("missing", pd.Series(False, index=fr.index)).astype(str) != "True")].reset_index(drop=True)
    ft = pd.read_csv(os.path.join(run, "stream", "ft.csv")).sort_values("t")
    t = ft.t.values; W = ft[["Fx", "Fy", "Fz", "Tx", "Ty", "Tz"]].values
    cs = np.vstack([np.zeros((1, 6)), np.cumsum(W, axis=0)])
    def mean_between(a, b):
        i, j = np.searchsorted(t, a), np.searchsorted(t, b, side="right")
        if j <= i: j = min(i + 1, len(t))
        return (cs[j] - cs[i]) / max(j - i, 1)
    out = np.zeros((len(fr), 6), np.float32)
    for k, r in fr.iterrows():
        te, ti = float(r.t_exposure_start), float(r.t_img)
        if window is None: a, b = te, ti
        elif window == (0.0, 0.0): a = b = ti
        elif window[0] == "sym": a, b = ti - window[1], ti + window[1]
        else: a, b = te + window[0], ti
        w = mean_between(a, b) if a < b else W[min(np.searchsorted(t, ti), len(t) - 1)]
        out[k] = w
    # drift correction as the collect did: subtract the per-segment first-frame offset used there is not
    # reproducible here, so use the difference between corrected and raw labels in frames.csv as the offset
    off = (fr[["Fx_s_corr", "Fy_s_corr", "Fz_s_corr"]].values - fr[["Fx_s", "Fy_s", "Fz_s"]].values).astype(np.float32)
    out[:, :3] += off
    return out


if __name__ == "__main__":
    units = sys.argv[1:] or ["data/20260911_VBTSresolution_dataset/9DTact/20260907_passB_ball8/9DTact_hard_1mm_r1",
                             "data/20260911_VBTSresolution_dataset/9DTact/20260907_passB_ball8/9DTact_soft_3mm_r2",
                             "data/20260911_VBTSresolution_dataset/DIGIT_Marker/20260908_passB_ball8/DIGIT_Marker_medium_2mm_r1"]
    # Two sizes: one above the knee and one below it. If the label window is what
    # sets the floor, the gap between windows is a property of the labels and
    # should survive the drop in resolution; if it were an image effect it would
    # shrink once the picture is the limit.
    SIZES = [(320, 180), (48, 27)]
    SEEDS = [0, 1, 2]                    # one seed cannot separate two windows
    rows = []
    out = os.path.join(ROOT, "data", "analysis", "label_window_ablation.csv")
    if os.path.exists(out):
        rows = pd.read_csv(out).to_dict("records")
    done = {(r["unit"], r.get("size"), r["window"], int(r.get("seed", 0)))
            for r in rows}
    for run in units:
        run = os.path.join(ROOT, run) if not os.path.isabs(run) else run
        name = os.path.basename(run)
        want = [(s, w, sd) for s in SIZES for w in WINDOWS for sd in SEEDS
                if (name, f"{s[0]}x{s[1]}", w, sd) not in done]
        if not want:
            print(f"  {name}: already done"); continue
        res = F.load_unit(Path(run), None, "none", "grey", 2.0)
        X, y0, cyc, blk = res[0], res[1], res[2], res[3]
        shrunk = {s: F.shrink(X, s) for s in SIZES}
        del X, res                       # the full-resolution stack is 6 GB
        tr, va, te = F.split_by_cycle(cyc, blk)
        labels = {}
        for w_name, win in WINDOWS.items():
            y = relabel(run, win)
            assert len(y) == len(y0), (len(y), len(y0))
            y[:, 2] = -y[:, 2]
            labels[w_name] = y
            if w_name == "exposure":
                print(f"  {name}: relabelled-vs-stored |dFz| max "
                      f"{np.abs(y[:, 2] - y0[:, 2]).max():.4f} N", flush=True)
        for size in SIZES:
            for w_name in WINDOWS:
                for sd in SEEDS:
                    if (name, f"{size[0]}x{size[1]}", w_name, sd) in done:
                        continue
                    t1 = time.time()
                    r = F.train_eval(shrunk[size], labels[w_name], tr, va, te,
                                     epochs=30, batch=64, seed=sd, size=size,
                                     blk_te=blk[te])
                    r.update(unit=name, size=f"{size[0]}x{size[1]}", window=w_name,
                             seed=sd, seconds=round(time.time() - t1, 1))
                    rows.append(r)
                    print(f"  {name:28s} {size[0]:4d}x{size[1]:<3d} {w_name:9s} "
                          f"s{sd} Fz {r['fz_mae_normal']:.4f}  "
                          f"shear {r['lat_mae_shear']:.4f}  ({r['seconds']}s)", flush=True)
                    pd.DataFrame(rows).to_csv(out, index=False)
        del shrunk, labels
    print("  ->", out)
