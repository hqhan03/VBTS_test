#!/usr/bin/env python3
"""Image response measured INSIDE the contact, not over the whole field.

`img_resp_at_2N` in derived_variables.py averages |frame - reference| over the
entire frame. That dilutes by however much empty gel is in view, and the field
of view is not the same across units (16.4-24.8 mm, campaign_protocol.md 4.3),
nor is the contact area (2.9-3.9 mm across). cross_principle.md 3.3 concluded
from the whole-field number that DIGIT_Marker responds less per newton than
9DTact; this script checks that against a measure that cannot be a dilution
artefact: the mean |difference| over the contact disc alone, with marker dots
masked out so their edges do not stand in for the imprint.

  resp_contact_2N   mean |diff| (levels) inside the contact at ~2 N
  resp_ring_2N      the same in an annulus 2-3 contact radii out (should be ~0)
  contact_r_px      the radius used, from the unit's Hertz a(2 N) and px_per_mm
  dot_frac          fraction of the contact disc masked as dot (markers only)

Writes data/analysis/contact_response.csv.
"""
import re, glob, yaml
import numpy as np, pandas as pd, cv2
from pathlib import Path
from scipy import ndimage

ROOT = Path(__file__).resolve().parents[2]
DS = {"9DTact": "data/20260911_VBTSresolution_dataset/9DTact/20260907_passB_ball8",
      "DIGIT_Marker": "data/20260911_VBTSresolution_dataset/DIGIT_Marker/20260908_passB_ball8",
      "DIGIT": "data/20260911_VBTSresolution_dataset/DIGIT/20260908_passB_ball8"}


def runs_for(principle, ds):
    can = ROOT / ds / "CANONICAL.yaml"
    if can.exists():
        c = yaml.safe_load(can.read_text())["canonical"]
        return [(u.replace(principle + "_", ""), ROOT / ds / v["run"])
                for u, v in c.items() if v.get("run")]
    return [(p.name.replace(principle + "_", ""), p)
            for p in sorted((ROOT / ds).glob(principle + "_*"))
            if not re.search(r"__\d+$", p.name)]


def dot_mask(refg):
    hp = cv2.GaussianBlur(refg, (0, 0), 25) - refg
    thr = hp > max(4.0, np.percentile(hp, 99.0) * 0.35)
    lab, n = ndimage.label(thr)
    if n == 0:
        return np.zeros_like(thr)
    areas = ndimage.sum(thr, lab, range(1, n + 1))
    keep = [i + 1 for i, a in enumerate(areas) if 1500 <= a <= 60000]
    return np.isin(lab, keep)


if __name__ == "__main__":
    dv = pd.read_csv(ROOT / "data" / "analysis" / "derived_variables.csv")
    rows = []
    for principle, ds in DS.items():
        for unit, run in runs_for(principle, ds):
            d = dv[(dv.principle == principle) & (dv.unit == unit)]
            if d.empty or not np.isfinite(d.px_per_mm.iloc[0]):
                print(f"  {principle}_{unit}: no scale"); continue
            a_px = float(d.a_2N_mm.iloc[0] * d.px_per_mm.iloc[0])
            ref = None
            for nm in ("reference_collect.png", "reference_working.png", "reference.png"):
                if (run / nm).exists():
                    ref = cv2.imread(str(run / nm)); break
            refg = cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY).astype(np.float32)
            dots = dot_mask(refg) if principle == "DIGIT_Marker" else np.zeros(refg.shape, bool)
            fr = pd.read_csv(run / "stream" / "frames.csv")
            fz = (fr.Fz_s_corr if "Fz_s_corr" in fr else fr.Fz_s).abs()
            nrm = fr[fr.segment.astype(str).str.startswith("normal") & (fz > 1.7) & (fz < 2.1)]
            if nrm.empty:
                print(f"  {principle}_{unit}: no ~2 N normal frame"); continue
            nrm = nrm.iloc[np.linspace(0, len(nrm) - 1, min(8, len(nrm))).astype(int)]
            H, W = refg.shape
            yy, xx = np.mgrid[0:H, 0:W]
            inner = ringv = None
            vals, rings = [], []
            for _, r in nrm.iterrows():
                im = cv2.imread(str(run / "stream" / r["file"]), cv2.IMREAD_GRAYSCALE)
                if im is None:
                    continue
                diff = im.astype(np.float32) - refg
                diff -= diff.mean()                      # the probe's shadow pedestal
                ad = np.abs(diff)
                if inner is None:                        # locate the imprint once
                    sm = cv2.GaussianBlur(ad, (0, 0), 9).copy()
                    sm[dots] = 0
                    cy, cx = np.unravel_index(np.argmax(sm), sm.shape)
                    rad = np.hypot(yy - cy, xx - cx)
                    inner = (rad <= a_px) & ~dots
                    ringv = (rad > 2 * a_px) & (rad <= 3 * a_px) & ~dots
                    dfrac = float((np.hypot(yy - cy, xx - cx) <= a_px)[dots].sum()
                                  / max((np.hypot(yy - cy, xx - cx) <= a_px).sum(), 1))
                vals.append(float(ad[inner].mean())); rings.append(float(ad[ringv].mean()))
            m = re.search(r"(soft|medium|hard)_(\d)mm", unit)
            rows.append(dict(unit=unit, principle=principle, hardness=m.group(1),
                             thickness_mm=int(m.group(2)), contact_r_px=round(a_px, 1),
                             dot_frac=round(dfrac, 3),
                             resp_contact_2N=round(float(np.mean(vals)), 3),
                             resp_ring_2N=round(float(np.mean(rings)), 3),
                             n_frames=len(vals)))
            print(f"  {principle}_{unit:16s} r {a_px:5.0f} px  접촉 {np.mean(vals):6.2f} "
                  f"고리 {np.mean(rings):5.2f} lvl  점비율 {dfrac:.2f}", flush=True)
    out = ROOT / "data" / "analysis" / "contact_response.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print("  ->", out, len(rows), "units")
