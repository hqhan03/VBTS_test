#!/usr/bin/env python3
"""Force estimation from the image, per unit, at a ladder of camera resolutions.

    force_vs_resolution.py                     # every unit, every size
    force_vs_resolution.py 9DTact_hard_2mm_r1  # one unit
    force_vs_resolution.py --sizes 1920x1080,320x180 --epochs 10   # a quick pass

WHAT IS ASKED
-------------
Test 1 collected 1000 labelled frames per unit: an image and the wrench measured
over that frame's own exposure window. This asks how much of the CAMERA is
needed to read the force back out -- the same question `shape_vs_resolution.md`
asks of shape reconstruction, on the same twelve 16:9 sizes so the two curves
can be laid side by side.

9DTACT'S PIPELINE, TAKEN AS IT IS
---------------------------------
Preprocessing is their `Sensor.raw_image_2_representation`
(`shape_reconstruction/sensor.py`), which is what `_1_Force_Estimation.py`
feeds the estimator. Three channels, built from the grey reference and the
grey frame:

    diff_darker   = ref - img, negatives clipped to 0
    diff_brighter = img - ref, negatives clipped to 0
    channel 0 = ref            (the reference itself, unscaled)
    channel 1 = diff_brighter * 3
    channel 2 = diff_darker * 3

with `scale = 3` as in their source, values kept as 0-255 uint8. Their
`lighting_threshold` (2) belongs to the shape path, not this one, and is not
applied here either.

The model and its training are theirs as well (`force_estimation/train.py`,
`model/cnn.py`, `force_config.yaml`):

  * ResNet-18, ImageNet-pretrained, final fc replaced by a 6-output linear
    layer -- the full wrench, which this rig measures too.
  * Pixel values fed as 0-255 floats, unnormalised, as in `dtact_dataset.py`.
  * L1 loss with `reduction='sum'`, Adam at 5e-4, a linear decay, batch 64.
  * Labels min-max scaled to [0, 1] over the training set, which is what
    their `*_norm.npy` wrenches and the `force[force<0]=0; force[force>1]=1`
    clamp in `estimator.py` imply. Errors are converted back to newtons.

Three departures, each forced by the question being asked and none of them a
change to the method. Their images are a fixed 345x460 crop; here the size is
the independent variable, so the batch is reduced at the large end to fit the
card. They train 200 epochs on one sensor; 17 units x 12 sizes at 200 epochs
is days, so the epoch count is a flag and the value used is written into the
CSV. And their crop is a rectified 345x460 region of a 640x480 camera, while
this rig's frames are the full 1920x1080 -- rectification needs a checkerboard
inside a sealed sensor, which is why this campaign measures the scale with the
robot instead (see `contact_variable.md`).

ResNet-18 runs at every size in the ladder: its five stride-2 stages take
8x5 down to 1x1, which the adaptive pool accepts. Nothing about the network
changes between sizes.

THE SPLIT
---------
Held out by CYCLE, not at random. Neighbouring frames of one press are nearly
the same picture at nearly the same force, so a random split scores a model on
data it has effectively seen and reports an error several times too small. The
last 30 % of the loading cycles and the last 30 % of the shear cycles are the
test set; everything earlier is training.

WHAT IS REPORTED
----------------
MAE in newtons on the held-out cycles, for Fz and for the lateral magnitude,
against the MAE of predicting the training mean. A model that cannot beat that
baseline has learnt nothing, which is the expected answer at the small end.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data" / "9DTact" / "20260907_passB_ball8"
SIZES = [(1920, 1080), (1280, 720), (854, 480), (640, 360), (426, 240),
         (320, 180), (160, 90), (80, 45), (48, 27), (32, 18), (16, 9), (8, 5)]


# ------------------------------------------------------------------ data --
REP_SCALE = 3          # sensor.py: scale = 3
AXES = ("Fx", "Fy", "Fz", "Tx", "Ty", "Tz")


def representation(ref_gray, img_gray):
    """9DTact's `raw_image_2_representation`, channel for channel."""
    r = ref_gray.astype(np.float32)
    g = img_gray.astype(np.float32)
    darker = np.clip(r - g, 0, None)
    brighter = np.clip(g - r, 0, None)
    out = np.zeros(ref_gray.shape + (3,), dtype=np.uint8)
    out[:, :, 0] = ref_gray
    out[:, :, 1] = np.clip(brighter * REP_SCALE, 0, 255).astype(np.uint8)
    out[:, :, 2] = np.clip(darker * REP_SCALE, 0, 255).astype(np.uint8)
    return out


def load_unit(run: Path, max_frames: int | None = None):
    """Full-resolution 3-channel representations and their 6D wrench labels."""
    rows = list(csv.DictReader(open(run / "stream" / "frames.csv")))
    if max_frames:
        rows = rows[:max_frames]
    ref = cv2.cvtColor(cv2.imread(str(run / "reference.png")), cv2.COLOR_BGR2GRAY)
    h, w = ref.shape
    X = np.zeros((len(rows), h, w, 3), dtype=np.uint8)
    y = np.zeros((len(rows), 6), dtype=np.float32)
    keep = np.ones(len(rows), dtype=bool)
    cyc = np.zeros(len(rows), dtype=np.int32)
    blk = np.zeros(len(rows), dtype=np.int32)      # 0 normal, 1 shear
    for i, r in enumerate(rows):
        img = cv2.imread(str(run / "stream" / r["file"]), cv2.IMREAD_GRAYSCALE)
        if img is None or r.get("missing") == "True":
            keep[i] = False
            continue
        X[i] = representation(ref, img)
        # drift-corrected labels where present, raw otherwise
        y[i] = [float(r.get(f"{ax}_s_corr") or r[f"{ax}_s"]) for ax in AXES]
        y[i, 2] = -y[i, 2]                          # +Fz = pressing
        cyc[i] = int(r["cycle"] or 0)
        blk[i] = 1 if r["segment"].startswith("shear") else 0
    return X[keep], y[keep], cyc[keep], blk[keep]


def split_by_cycle(cyc, blk, test_frac=0.30):
    """The last `test_frac` of cycles in each block are the test set."""
    test = np.zeros(len(cyc), dtype=bool)
    for b in (0, 1):
        m = blk == b
        if not m.any():
            continue
        cs = np.unique(cyc[m])
        if len(cs) < 2:
            test[m] = False
            continue
        cut = cs[max(1, int(round(len(cs) * (1 - test_frac))))]
        test |= m & (cyc >= cut)
    return ~test, test


def shrink(X, size):
    w, h = size
    if X.shape[2] == w and X.shape[1] == h:
        return X
    out = np.zeros((len(X), h, w, 3), dtype=np.uint8)
    for i in range(len(X)):
        out[i] = cv2.resize(X[i], (w, h), interpolation=cv2.INTER_AREA)
    return out


# ----------------------------------------------------------------- model --
def resnet18_6():
    """9DTact's model: torchvision ResNet-18, pretrained, fc -> 6."""
    from torchvision import models
    import torch.nn as nn
    try:
        m = models.resnet18(weights=models.ResNet18_Weights.IMAGENET1K_V1)
    except Exception:                      # older torchvision
        m = models.resnet18(pretrained=True)
    m.fc = nn.Linear(m.fc.in_features, 6)
    return m


def batch_for(size, base=64):
    """Their batch is 64 at 345x460; scale it down by pixel count to fit."""
    px = size[0] * size[1]
    ref = 460 * 345
    return int(max(4, min(base, base * ref / max(px, 1))))


def train_eval(X, y, tr, te, epochs=40, bs=None, seed=0, device="cuda",
               size=(460, 345)):
    import torch
    import torch.nn as nn
    torch.manual_seed(seed)
    np.random.seed(seed)
    net = resnet18_6().to(device)
    bs = bs or batch_for(size)
    # min-max to [0, 1] over the TRAIN set, as their *_norm wrenches are
    lo, hi = y[tr].min(0), y[tr].max(0)
    rng = np.where(hi - lo < 1e-6, 1.0, hi - lo)
    # (N, H, W, 3) -> (N, 3, H, W), 0-255 floats as in their dataset class
    Xtr = torch.from_numpy(X[tr]).permute(0, 3, 1, 2).float()
    Xte = torch.from_numpy(X[te]).permute(0, 3, 1, 2).float()
    ytr = torch.from_numpy((y[tr] - lo) / rng).float()
    opt = torch.optim.Adam(net.parameters(), lr=5e-4, betas=(0.9, 0.999))
    sch = torch.optim.lr_scheduler.LinearLR(opt, start_factor=1.0,
                                            end_factor=0.1, total_iters=epochs)
    lossf = nn.L1Loss(reduction="sum")
    n = len(Xtr)
    for _ in range(epochs):
        net.train()
        perm = torch.randperm(n)
        for i in range(0, n, bs):
            idx = perm[i:i + bs]
            xb = Xtr[idx].to(device, non_blocking=True)
            yb = ytr[idx].to(device, non_blocking=True)
            opt.zero_grad(set_to_none=True)
            loss = lossf(net(xb), yb)
            loss.backward()
            opt.step()
        sch.step()
    net.eval()
    preds = []
    with torch.no_grad():
        for i in range(0, len(Xte), max(4, bs)):
            preds.append(net(Xte[i:i + max(4, bs)].to(device)).float().cpu().numpy())
    p = np.concatenate(preds) * rng + lo
    t = y[te]
    mae6 = np.abs(p - t).mean(0)
    fz_mae = float(mae6[2])
    lat_p = np.hypot(p[:, 0], p[:, 1])
    lat_t = np.hypot(t[:, 0], t[:, 1])
    lat_mae = float(np.abs(lat_p - lat_t).mean())
    base_fz = float(np.abs(t[:, 2] - y[tr][:, 2].mean()).mean())
    base_lat = float(np.abs(lat_t - np.hypot(y[tr][:, 0], y[tr][:, 1]).mean()).mean())
    ss = float(1 - np.sum((p[:, 2] - t[:, 2]) ** 2)
               / max(np.sum((t[:, 2] - t[:, 2].mean()) ** 2), 1e-9))
    return dict(fz_mae=fz_mae, lat_mae=lat_mae, fz_mae_baseline=base_fz,
                lat_mae_baseline=base_lat, fz_r2=ss, batch=bs,
                tx_mae=float(mae6[3]), ty_mae=float(mae6[4]), tz_mae=float(mae6[5]),
                n_train=int(tr.sum()), n_test=int(te.sum()),
                fz_range=float(t[:, 2].max() - t[:, 2].min()))


# ------------------------------------------------------------------ main --
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("units", nargs="*")
    ap.add_argument("--sizes", default=None, help="e.g. 1920x1080,320x180")
    ap.add_argument("--epochs", type=int, default=40)
    ap.add_argument("--max-frames", type=int, default=None)
    ap.add_argument("--out", default=str(ROOT / "data" / "9DTact" / "force_vs_resolution.csv"))
    a = ap.parse_args()
    sizes = SIZES if not a.sizes else [tuple(int(v) for v in s.split("x"))
                                       for s in a.sizes.split(",")]
    runs = sorted(DATASET.glob("9DTact_*")) if not a.units else \
        [DATASET / u for u in a.units]
    runs = [r for r in runs if (r / "stream" / "frames.csv").exists()]
    print(f"{len(runs)} units x {len(sizes)} sizes, {a.epochs} epochs each")
    out = Path(a.out)
    rows = []
    if out.exists():
        rows = list(csv.DictReader(open(out)))
        print(f"  resuming: {len(rows)} rows already in {out.name}")
    done = {(r["sensor"], int(r["width_px"])) for r in rows}
    for run in runs:
        sensor = run.name.replace("9DTact_", "")
        todo = [s for s in sizes if (sensor, s[0]) not in done]
        if not todo:
            continue
        t0 = time.time()
        X, y, cyc, blk = load_unit(run, a.max_frames)
        tr, te = split_by_cycle(cyc, blk)
        print(f"\n{sensor}: {len(X)} frames, train {tr.sum()} / test {te.sum()}, "
              f"Fz {y[:,2].min():+.2f}..{y[:,2].max():+.2f} N, decoded in {time.time()-t0:.0f}s")
        for size in todo:
            t1 = time.time()
            Xs = shrink(X, size)
            r = train_eval(Xs, y, tr, te, epochs=a.epochs, size=size)
            r.update(sensor=sensor, width_px=size[0], height_px=size[1],
                     epochs=a.epochs, seconds=round(time.time() - t1, 1))
            rows.append(r)
            print(f"  {size[0]:5d}x{size[1]:<4d} Fz MAE {r['fz_mae']:.4f} N "
                  f"(baseline {r['fz_mae_baseline']:.4f}, R2 {r['fz_r2']:+.3f})  "
                  f"lat {r['lat_mae']:.4f} (base {r['lat_mae_baseline']:.4f})  "
                  f"{r['seconds']:.0f}s", flush=True)
            cols = ["sensor", "width_px", "height_px", "fz_mae", "fz_mae_baseline",
                    "fz_r2", "lat_mae", "lat_mae_baseline", "n_train", "n_test",
                    "fz_range", "tx_mae", "ty_mae", "tz_mae", "epochs", "batch", "seconds"]
            with open(out, "w", newline="") as fh:
                wtr = csv.DictWriter(fh, fieldnames=cols)
                wtr.writeheader()
                for rr in rows:
                    wtr.writerow({c: rr.get(c) for c in cols})
        del X
    print(f"\n-> {out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
