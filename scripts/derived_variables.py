#!/usr/bin/env python3
"""One row per unit, every quantity the collected data lets us derive.

Across all three principles (9DTact, DIGIT, DIGIT_Marker), from the Pass A ball4
ladder + scale, the Pass B ball8 collect, and the registry:

  gel        principle, hardness, thickness_mm, marker
  mechanics  hertz_k, hertz_n (ball4 ladder, F = k d^n); hertz_a_ball8 (Pass B
             zero, best fit); d_2N_mm (depth at 2 N, ball8); a_2N_mm (Hertz
             contact radius sqrt(2Rd - d^2), R = 4); mu (max shear / Fz at that
             frame); creep_mm_per_cycle (shear-cycle start depth drift)
  optics     px_per_mm, tilt_deg (Pass A scale); pedestal (reference.png /
             correct reference -- the probe's shadow on DIGIT); img_slope_lvl_per_N
             and img_slope_lvl_per_mm (mean |frame - ref| over the whole frame
             against Fz / depth, normal block 0.2-2 N, correct reference);
             imprint_area_slope_px_per_N (|diff| > 12 area); bw_normal_f90,
             bw_shear_f90 (cycles/mm, 90 % energy, noise-subtracted, 0-3 c/mm);
             shear_snr (shear-signature power / noise power)
  labels     fz_noise_mae, lat_noise_mae (second-difference noise floor of the
             F/T label, gaussian MAE)
  bookkeeping n_frames, n_frames_le2N, canonical run

Output: data/derived_variables.csv. Pure CPU; a few minutes.
"""
import os, re, glob, csv, yaml, math
import numpy as np, pandas as pd, cv2

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSB = {"9DTact": "data/9DTact/20260907_passB_ball8",
         "DIGIT": "data/DIGIT/20260908_passB_ball8",
         "DIGIT_Marker": "data/DIGIT_Marker/20260908_passB_ball8"}
PASSA = {"9DTact": "data/9DTact/20260905_passA_ball4",
         "DIGIT": "data/DIGIT/20260908_passA_ball4",
         "DIGIT_Marker": "data/DIGIT_Marker/20260908_passA_ball4"}
HARD = {"soft": 0, "medium": 1, "hard": 2}
R8 = 4.0


def canonical_runs(pr):
    base = os.path.join(ROOT, PASSB[pr]); m = os.path.join(base, "CANONICAL.yaml")
    if os.path.exists(m):
        c = yaml.safe_load(open(m))["canonical"]
        return {k: os.path.join(base, v["run"]) for k, v in c.items() if v.get("run")}
    runs = {}
    for d in sorted(glob.glob(base + "/*/")):
        n = os.path.basename(d.rstrip("/")); u = re.sub(r"__\d+$", "", n)
        if os.path.exists(os.path.join(d, "stream", "frames.csv")):
            runs[u] = d.rstrip("/")
    return runs


def passa_run(pr, unit):
    base = os.path.join(ROOT, PASSA[pr])
    cands = sorted(glob.glob(os.path.join(base, unit + "*")),
                   key=lambda p: int((re.search(r"__(\d+)$", p) or [0, 0])[1]))
    for d in reversed(cands):
        if os.path.exists(os.path.join(d, "shape_ball4", "ladder.csv")):
            return d
    return None


def ref_image(D, pr):
    for name in ("reference_collect.png", "reference_working.png", "reference.png"):
        p = os.path.join(D, name)
        if os.path.exists(p):
            return cv2.imread(p), name
    return None, None


def radial(P, ppm):
    H, W = P.shape; y, x = np.mgrid[0:H, 0:W]
    f = np.hypot((x - W / 2) / W, (y - H / 2) / H) * (ppm / 2)   # half-res image
    bins = np.arange(0, 3.05, 0.1); idx = np.digitize(f.ravel(), bins)
    return bins[1:], np.array([P.ravel()[idx == k].sum() for k in range(1, len(bins))])


def spec(a, b):
    d = (a.astype(np.float32) - b.astype(np.float32))
    if d.ndim == 3: d = d.mean(2)
    d = d[::2, ::2]; d -= d.mean()
    return np.abs(np.fft.fftshift(np.fft.fft2(d))) ** 2


def f90(fb, S, N):
    sig = np.clip(S - N, 0, None); cs = np.cumsum(sig) / max(sig.sum(), 1e-9)
    return float(fb[np.searchsorted(cs, 0.90)])


def noise_mae(v, seg):
    out = []
    for _, g in pd.DataFrame({"v": v, "s": seg}).groupby("s"):
        x = g.v.values
        if len(x) > 6:
            d2 = x[2:] - 2 * x[1:-1] + x[:-2]
            out.append(0.798 * np.median(np.abs(d2)) / 0.6745 / math.sqrt(6))
    return float(np.median(out)) if out else np.nan


def unit_row(pr, unit_full, D):
    # rows are keyed by the SHORT id (hard_1mm_r1) so they join with the sweep
    # CSVs; the folder/registry names carry the principle prefix
    unit = re.sub(r"^(9DTact|DIGIT_Marker|DIGIT)_", "", unit_full)
    fr = pd.read_csv(os.path.join(D, "stream", "frames.csv"))
    fr["fz"] = fr.Fz_s_corr.abs(); fr["lat"] = np.hypot(fr.Fx_s_corr, fr.Fy_s_corr)
    seg = fr.segment.astype(str)
    nrm = fr[seg.str.startswith("normal")]; shr = fr[seg.str.startswith("shear")]
    row = dict(unit=unit, principle=pr, hardness=unit.split("_")[0], hard=HARD[unit.split("_")[0]],
               thickness_mm=int(re.search(r"(\d)mm", unit).group(1)), marker=int(pr == "DIGIT_Marker"),
               run=os.path.basename(D), n_frames=len(fr), n_frames_le2N=int((fr.fz <= 2.0).sum()))
    # --- Pass A ladder + scale
    A = passa_run(pr, unit_full)
    if A:
        lad = pd.read_csv(os.path.join(A, "shape_ball4", "ladder.csv"))
        x, y = lad.depth_mm.values, lad.force_N.values; m = (x > 0.05) & (y > 0.02)
        if m.sum() >= 3:
            n, lk = np.polyfit(np.log(x[m]), np.log(y[m]), 1); row.update(hertz_k=float(np.exp(lk)), hertz_n=float(n))
        sy = os.path.join(A, "scale_ball4", "scale.yaml")
        if os.path.exists(sy):
            s = yaml.safe_load(open(sy))
            row.update(px_per_mm=s.get("px_per_mm_image_x"), scale_trusted=bool(s.get("scale_trusted")),
                       tilt_deg=float(np.degrees(np.arctan(np.hypot(s.get("plane_slope_x", 0) or 0, s.get("plane_slope_y", 0) or 0)))))
    ppm = row.get("px_per_mm") or (100.0 if pr == "9DTact" else 95.0)
    # --- Pass B zero fit (best sigma)
    zy = os.path.join(D, "zero", "zero.yaml")
    if os.path.exists(zy):
        z = yaml.safe_load(open(zy)); fits = [f for f in (z.get("fits") or []) if f.get("ok")]
        if fits:
            b = min(fits, key=lambda f: f.get("sigma_d0_mm", 9)); row.update(hertz_a_ball8=float(b["a"]), zero_r2=float(b["r2"]))
    # --- depth at 2 N, contact radius, mu, creep
    n2 = nrm[(nrm.fz > 1.8) & (nrm.fz < 2.2)]
    if len(n2):
        d2 = float(n2.depth_mm.median()); row.update(d_2N_mm=d2, a_2N_mm=float(math.sqrt(max(2 * R8 * d2 - d2 * d2, 0))))
    out = shr[seg.loc[shr.index].str.endswith("_out")]
    if len(out):
        i = out.lat.idxmax(); row.update(mu=float(out.loc[i, "lat"] / max(out.loc[i, "fz"], 1e-6)), shear_max_N=float(out.lat.max()))
        st = [g.depth_mm.iloc[0] for _, g in shr.groupby("cycle")]
        if len(st) >= 3: row.update(creep_mm_per_cycle=float(np.polyfit(range(len(st)), st, 1)[0]))
    # --- labels
    row.update(fz_noise_mae=noise_mae(fr.fz.values, seg.values), lat_noise_mae=noise_mae(fr.lat.values, seg.values))
    # --- optics: reference, pedestal, response slopes, bandwidths
    ref, refname = ref_image(D, pr); row["reference_used"] = refname
    ref0 = cv2.imread(os.path.join(D, "reference.png"))
    if ref is not None and ref0 is not None:
        row["pedestal_ratio"] = float(ref0.mean() / max(ref.mean(), 1e-6))
        rd = lambda f: cv2.imread(os.path.join(D, "stream", f))
        sub = nrm[(nrm.fz > 0.2) & (nrm.fz <= 2.0)]
        sub = sub.iloc[np.linspace(0, len(sub) - 1, min(40, len(sub))).astype(int)] if len(sub) else sub
        resp, area, fz, dep = [], [], [], []
        for _, r in sub.iterrows():
            im = rd(r["file"])
            if im is None: continue
            d = np.abs(im.astype(np.float32) - ref.astype(np.float32))
            if pr != "9DTact":              # DIGIT: remove the per-channel mean (probe shadow) first
                d = im.astype(np.float32) - ref.astype(np.float32); d -= d.mean(axis=(0, 1), keepdims=True); d = np.abs(d)
            dm = d.max(2)
            resp.append(float(dm.mean())); area.append(float((dm > 12).mean() * 100)); fz.append(r.fz); dep.append(r.depth_mm)
        if len(fz) >= 6:
            row.update(img_slope_lvl_per_N=float(np.polyfit(fz, resp, 1)[0]),
                       img_slope_lvl_per_mm=float(np.polyfit(dep, resp, 1)[0]) if np.std(dep) > 1e-3 else np.nan,
                       imprint_area_slope_pct_per_N=float(np.polyfit(fz, area, 1)[0]),
                       img_resp_at_2N=float(np.interp(2.0, np.sort(fz), np.array(resp)[np.argsort(fz)])))
        # bandwidths (noise from two normal frames at the same Fz)
        S_n = N_n = S_s = N_s = None
        for _, r in nrm[(nrm.fz > 1.6) & (nrm.fz < 2.1)].sample(min(8, ((nrm.fz > 1.6) & (nrm.fz < 2.1)).sum()), random_state=0).iterrows():
            cand = nrm[(nrm.fz - r.fz).abs() < 0.12]
            if len(cand) < 2: continue
            c = cand.sample(2, random_state=1)
            a, b, b2 = rd(r["file"]), rd(c.iloc[0]["file"]), rd(c.iloc[1]["file"])
            if a is None or b is None or b2 is None: continue
            fb, s = radial(spec(a, ref), ppm); _, nn = radial(spec(b, b2), ppm)
            S_n = s if S_n is None else S_n + s; N_n = nn if N_n is None else N_n + nn
        if S_n is not None: row["bw_normal_f90"] = f90(fb, S_n, N_n)
        sh = shr[shr.lat > 0.35]
        for _, r in sh.sample(min(8, len(sh)), random_state=0).iterrows():
            same = shr[(shr.cycle == r.cycle) & (shr.index != r.name)]
            cand = nrm[(nrm.fz - r.fz).abs() < 0.12]
            if same.empty or len(cand) < 2: continue
            j = same.lat.idxmin(); c = cand.sample(2, random_state=2)
            a, b, b2, bref = rd(r["file"]), rd(c.iloc[0]["file"]), rd(c.iloc[1]["file"]), rd(shr.loc[j, "file"])
            if a is None or b is None or b2 is None or bref is None: continue
            fb, s = radial(spec(a, bref), ppm); _, nn = radial(spec(b, b2), ppm)
            S_s = s if S_s is None else S_s + s; N_s = nn if N_s is None else N_s + nn
        if S_s is not None:
            row["bw_shear_f90"] = f90(fb, S_s, N_s); row["shear_snr"] = float(S_s.sum() / max(N_s.sum(), 1e-9))
    return row


if __name__ == "__main__":
    rows = []
    for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
        for unit, D in sorted(canonical_runs(pr).items()):
            try:
                rows.append(unit_row(pr, unit, D)); print(f"  {pr:13s} {unit:24s} ok", flush=True)
            except Exception as e:      # noqa: BLE001
                print(f"  {pr:13s} {unit:24s} FAILED: {e}", flush=True)
    df = pd.DataFrame(rows)
    out = os.path.join(ROOT, "data", "derived_variables.csv"); df.to_csv(out, index=False)
    print(f"\n  -> {out}: {len(df)} units, {df.shape[1]} columns")
