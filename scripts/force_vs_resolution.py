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


TRAIN_FRAC, VAL_FRAC = 0.70, 0.15      # test takes the remaining 0.15


def split_by_cycle(cyc, blk, train_frac=TRAIN_FRAC, val_frac=VAL_FRAC):
    """Whole cycles, in the order they were pressed: train, then val, then test.

    A frame's neighbours inside one ramp are nearly the same picture at nearly
    the same force, so a random frame split puts near-duplicates on both sides
    and scores a generalisation the model never had to do. Splitting by cycle
    is the honest version, and the harder one: the test cycles are the LAST
    ones pressed, after the gel has been loaded a few hundred times.

    The boundary is placed on the cumulative FRAME count, not on the cycle
    index. Cycles are not equal: a run stops when its frame budget is spent, so
    the last cycle of a block holds 5 to 55 frames where the first holds 78 to
    130. Cutting at cycle 0.85 x n therefore gave 90/8/2 on
    9DTact_soft_2mm_r1 instead of 70/15/15. Val and test still get at least one
    whole cycle each. `split_random` is then told to reproduce whatever
    proportions this reached, so the two definitions differ in HOW they cut and
    not in how much.
    """
    n = len(cyc)
    tr = np.zeros(n, bool); va = np.zeros(n, bool); te = np.zeros(n, bool)
    for b in np.unique(blk):
        m = blk == b
        cs, counts = np.unique(cyc[m], return_counts=True)
        if len(cs) < 3:
            tr |= m
            continue
        frac = np.cumsum(counts) / counts.sum()
        i1 = int(np.searchsorted(frac, train_frac) + 1)
        i2 = int(np.searchsorted(frac, train_frac + val_frac) + 1)
        i1 = min(max(1, i1), len(cs) - 2)
        i2 = min(max(i1 + 1, i2), len(cs) - 1)
        tr |= m & (cyc < cs[i1])
        va |= m & (cyc >= cs[i1]) & (cyc < cs[i2])
        te |= m & (cyc >= cs[i2])
    return tr, va, te


def split_random(cyc, blk, seed=0, like=None):
    """Frames drawn at random, in the same proportions the cycle split reached.

    Kept alongside the cycle split because the operator asked for both, and
    because the gap between the two IS a measurement: it says how much of the
    apparent accuracy comes from neighbouring frames of one ramp sitting on
    both sides of the split. For that comparison to mean anything the two must
    differ only in the cut, so the sizes are copied from `like` -- the cycle
    split's own (train, val, test) masks.
    """
    n = len(cyc)
    if like is None:
        i1, i2 = int(round(n * TRAIN_FRAC)), int(round(n * (TRAIN_FRAC + VAL_FRAC)))
    else:
        i1 = int(like[0].sum())
        i2 = i1 + int(like[1].sum())
    o = np.random.default_rng(1000 + seed).permutation(n)
    tr = np.zeros(n, bool); va = np.zeros(n, bool); te = np.zeros(n, bool)
    tr[o[:i1]] = True; va[o[i1:i2]] = True; te[o[i2:]] = True
    return tr, va, te


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


def micro_batch_for(size, base=64):
    """How many images fit on the card at once. NOT the optimiser's batch.

    The batch used to shrink with the picture -- 64 at 426x240, 4 at 1920x1080
    -- so every cell of the resolution table was trained by a different
    optimiser, and 1920x1080 (the cell with the widest seed spread) was the one
    trained with the smallest batch. Gradient accumulation separates the two:
    this is the micro-batch, chosen to fit memory, and `--batch` is the
    effective batch, which is now the same at every resolution.
    """
    px = size[0] * size[1]
    ref = 460 * 345
    return int(max(2, min(base, base * ref / max(px, 1))))


def train_eval(X, y, tr, va, te, epochs=30, batch=64, seed=0, device="cuda",
               size=(460, 345), wd=1e-4, patience=0):
    """Train on `tr`, choose the epoch on `va`, report on `te`.

    Three departures from the 2026-09-08 first pass, all asked for after that
    pass turned out to be noise-limited:

    * **One batch for every resolution.** `batch` is the optimiser's batch and
      is the same everywhere; the card sees `micro_batch_for(size)` images at a
      time and the gradients are accumulated. With an L1 loss reduced by SUM
      this is exactly one large step, not an approximation.
    * **A validation split, and the epoch is chosen on it.** Before, every fit
      ran a fixed 30 epochs and whatever it had at the end was reported, so a
      run that had already begun to overfit was scored after it did. The
      weights from the best validation epoch are restored before the test set
      is touched.
    * **Weight decay.** `patience` can also stop training early, but it is OFF
      by default: measured on 2026-09-08, a patience of 8 cut 320x180 off at
      epoch 14 of 30 with train 0.264 against val 0.276 -- the two still
      together, so the run was UNDER-trained, not over -- and the error came
      out 0.079 N where the same cell had reached 0.050 N when allowed to
      finish. Early termination saves time; it is choosing the epoch that
      guards against overfitting, and that costs nothing extra.

    The test set is touched exactly once, at the end.
    """
    import torch
    import torch.nn as nn
    torch.manual_seed(seed)
    np.random.seed(seed)
    net = resnet18_6().to(device)
    micro = min(micro_batch_for(size), batch)
    accum = max(1, int(round(batch / micro)))
    lo, hi = y[tr].min(0), y[tr].max(0)
    rng = np.where(hi - lo < 1e-6, 1.0, hi - lo)

    def prep(m):
        return torch.from_numpy(X[m]).permute(0, 3, 1, 2).float()

    Xtr, Xva, Xte = prep(tr), prep(va), prep(te)
    ytr = torch.from_numpy((y[tr] - lo) / rng).float()
    yva = torch.from_numpy((y[va] - lo) / rng).float()
    opt = torch.optim.Adam(net.parameters(), lr=5e-4, betas=(0.9, 0.999),
                           weight_decay=wd)
    sch = torch.optim.lr_scheduler.LinearLR(opt, start_factor=1.0,
                                            end_factor=0.1, total_iters=epochs)
    lossf = nn.L1Loss(reduction="sum")
    n = len(Xtr)

    def evaluate(Xs, ys=None):
        net.eval()
        out, loss = [], 0.0
        with torch.no_grad():
            for i in range(0, len(Xs), max(2, micro)):
                xb = Xs[i:i + max(2, micro)].to(device)
                pb = net(xb).float()
                if ys is not None:
                    loss += float(lossf(pb, ys[i:i + max(2, micro)].to(device)))
                out.append(pb.cpu().numpy())
        return np.concatenate(out), (loss / max(len(Xs), 1))

    best = (float("inf"), -1, None)
    hist = []
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(n)
        opt.zero_grad(set_to_none=True)
        tot, k = 0.0, 0
        for i in range(0, n, micro):
            idx = perm[i:i + micro]
            xb = Xtr[idx].to(device, non_blocking=True)
            yb = ytr[idx].to(device, non_blocking=True)
            loss = lossf(net(xb), yb)
            loss.backward()
            tot += float(loss); k += 1
            if k % accum == 0 or i + micro >= n:
                opt.step()
                opt.zero_grad(set_to_none=True)
        sch.step()
        _, vl = evaluate(Xva, yva)
        hist.append((tot / max(n, 1), vl))
        if vl < best[0] - 1e-9:
            best = (vl, ep, {kk: v.detach().cpu().clone()
                             for kk, v in net.state_dict().items()})
        elif patience and ep - best[1] >= patience:
            break
    if best[2] is not None:
        net.load_state_dict(best[2])

    p_norm, _ = evaluate(Xte)
    p = p_norm * rng + lo
    tt = y[te]
    mae6 = np.abs(p - tt).mean(0)
    lat_p = np.hypot(p[:, 0], p[:, 1])
    lat_t = np.hypot(tt[:, 0], tt[:, 1])
    ss = float(1 - np.sum((p[:, 2] - tt[:, 2]) ** 2)
               / max(np.sum((tt[:, 2] - tt[:, 2].mean()) ** 2), 1e-9))
    lat_r2 = float(1 - np.sum((lat_p - lat_t) ** 2)
                   / max(np.sum((lat_t - lat_t.mean()) ** 2), 1e-9))
    tr_loss, va_loss = hist[best[1]] if best[1] >= 0 else (np.nan, np.nan)
    return dict(fz_mae=float(mae6[2]), lat_mae=float(np.abs(lat_p - lat_t).mean()),
                fz_rmse=float(np.sqrt(((p[:, 2] - tt[:, 2]) ** 2).mean())),
                fz_mae_baseline=float(np.abs(tt[:, 2] - y[tr][:, 2].mean()).mean()),
                lat_mae_baseline=float(np.abs(lat_t - np.hypot(y[tr][:, 0],
                                                              y[tr][:, 1]).mean()).mean()),
                fz_r2=ss, lat_r2=lat_r2, batch=batch, micro_batch=micro,
                accum=accum, best_epoch=best[1] + 1, epochs_run=len(hist),
                train_loss=float(tr_loss), val_loss=float(va_loss),
                tx_mae=float(mae6[3]), ty_mae=float(mae6[4]), tz_mae=float(mae6[5]),
                n_train=int(tr.sum()), n_val=int(va.sum()), n_test=int(te.sum()),
                fz_range=float(tt[:, 2].max() - tt[:, 2].min()))


# ------------------------------------------------------------------ main --
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("units", nargs="*")
    ap.add_argument("--sizes", default=None, help="e.g. 1920x1080,320x180")
    ap.add_argument("--epochs", type=int, default=30)
    ap.add_argument("--max-frames", type=int, default=None)
    # One seed per (unit, size) makes a table whose cells cannot be compared:
    # measured 2026-09-08, a single unit's error wandered 0.022-0.096 N across
    # the twelve sizes with no order to it, which is what training noise looks
    # like, not resolution. --seeds repeats the fit so the noise can be
    # measured instead of argued about.
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--batch", type=int, default=64,
                    help="the OPTIMISER's batch, the same at every resolution; "
                         "the card sees micro_batch_for(size) at a time and the "
                         "gradients are accumulated")
    ap.add_argument("--weight-decay", type=float, default=1e-4)
    ap.add_argument("--patience", type=int, default=0,
                    help="stop early after this many epochs without a val "
                         "improvement; 0 runs every epoch and keeps the best")
    ap.add_argument("--splits", default="cycle,random",
                    help="which held-out definitions to run")
    ap.add_argument("--out", default=str(ROOT / "data" / "9DTact" / "force_vs_resolution_v2.csv"))
    a = ap.parse_args()
    sizes = SIZES if not a.sizes else [tuple(int(v) for v in s.split("x"))
                                       for s in a.sizes.split(",")]
    splits = [s.strip() for s in a.splits.split(",") if s.strip()]
    runs = sorted(DATASET.glob("9DTact_*")) if not a.units else \
        [DATASET / u for u in a.units]
    runs = [r for r in runs if (r / "stream" / "frames.csv").exists()]
    print(f"{len(runs)} units x {len(sizes)} sizes x {len(splits)} splits x "
          f"{a.seeds} seed(s), {a.epochs} epochs, batch {a.batch}")
    out = Path(a.out)
    rows = []
    if out.exists():
        rows = list(csv.DictReader(open(out)))
        print(f"  resuming: {len(rows)} rows already in {out.name}")
    done = {(r["sensor"], int(r["width_px"]), int(r.get("seed") or 0),
             r.get("split") or "cycle") for r in rows}
    cols = ["sensor", "width_px", "height_px", "split", "seed", "fz_mae", "fz_rmse",
            "fz_mae_baseline", "fz_r2", "lat_mae", "lat_mae_baseline", "lat_r2",
            "n_train", "n_val", "n_test", "fz_range", "tx_mae", "ty_mae", "tz_mae",
            "epochs", "epochs_run", "best_epoch", "train_loss", "val_loss",
            "batch", "micro_batch", "accum", "seconds"]
    for run in runs:
        sensor = run.name.replace("9DTact_", "")
        todo = [(s, k, sp) for s in sizes for k in range(a.seeds) for sp in splits
                if (sensor, s[0], k, sp) not in done]
        if not todo:
            continue
        t0 = time.time()
        X, y, cyc, blk = load_unit(run, a.max_frames)
        print(f"\n{sensor}: {len(X)} frames, Fz {y[:,2].min():+.2f}..{y[:,2].max():+.2f} N, "
              f"decoded in {time.time()-t0:.0f}s", flush=True)
        last_size, Xs = None, None
        for size, seed, sp in sorted(todo, key=lambda z: (-z[0][0], z[2], z[1])):
            t1 = time.time()
            if size != last_size:
                Xs, last_size = shrink(X, size), size
            cut = split_by_cycle(cyc, blk)
            tr, va, te = cut if sp == "cycle" else split_random(cyc, blk, seed, like=cut)
            r = train_eval(Xs, y, tr, va, te, epochs=a.epochs, batch=a.batch,
                           seed=seed, size=size, wd=a.weight_decay,
                           patience=a.patience)
            r.update(sensor=sensor, width_px=size[0], height_px=size[1], seed=seed,
                     split=sp, epochs=a.epochs, seconds=round(time.time() - t1, 1))
            rows.append(r)
            print(f"  {size[0]:5d}x{size[1]:<4d} {sp:6} s{seed} "
                  f"Fz MAE {r['fz_mae']:.4f} R2 {r['fz_r2']:+.3f}  "
                  f"lat {r['lat_mae']:.4f} R2 {r['lat_r2']:+.3f}  "
                  f"ep {r['best_epoch']}/{r['epochs_run']}  "
                  f"tr {r['train_loss']:.3f} va {r['val_loss']:.3f}  "
                  f"{r['seconds']:.0f}s", flush=True)
            with open(out, "w", newline="") as fh:
                wtr = csv.DictWriter(fh, fieldnames=cols)
                wtr.writeheader()
                for rr in rows:
                    rr.setdefault("seed", 0)
                    rr.setdefault("split", "cycle")
                    wtr.writerow({c: rr.get(c) for c in cols})
        del X
    print(f"\n-> {out} ({len(rows)} rows)")


if __name__ == "__main__":
    main()
