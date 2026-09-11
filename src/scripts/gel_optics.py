#!/usr/bin/env python3
"""Optical properties of each gel, from the images the campaign already has.

The gels differ in hardness because they are a different silicone or a different
mixing ratio, so their optics -- how much light they pass, how far light spreads
inside them -- need not be the same, and thickness attenuates on top of that.
None of that has been measured; this measures what the collected frames allow.

Per unit, from its own Pass B run:

  unloaded (reference_collect.png, ~0 N, same session/exposure as every frame)
    ref_mean, ref_b/g/r     brightness of the resting gel, whole field and per
                            channel. DIGIT is lit from the side by R/G/B LEDs,
                            so the channel ratios say which path length the
                            light took; 9DTact is backlit through a pigment
                            layer, where brightness is transmission.
    ref_std                 texture of the resting field
    centre_edge             mean of the central 25 % over the outer ring. A gel
                            that scatters more evens the illumination out, so
                            this ratio moves toward 1
  loaded (~2 N normal frame)
    scatter_mm              decay length of |frame - reference| OUTSIDE the
                            contact: how far the optical answer to a local
                            press reaches. Fitted as exp(-r/L) over 1-3 contact
                            radii from the contact edge
    halo_ratio              response in the 2-3 radius ring over the response
                            inside the contact

CONFOUNDS, stated up front: exposure and LEDs belong to the sensor body, not the
gel, and all units of one principle were run on the same body with one camera
config -- so comparisons WITHIN a principle are gel comparisons, and comparisons
ACROSS principles are not (different bodies, different illumination, different
physics). Nothing here is calibrated radiometry: levels are camera levels.

Writes data/analysis/gel_optics.csv.
"""
import re, yaml
import numpy as np, pandas as pd, cv2
from pathlib import Path

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


def unloaded(ref_bgr):
    g = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    H, W = g.shape
    cy, cx = H // 2, W // 2
    ch, cw = int(H * 0.25), int(W * 0.25)
    centre = g[cy - ch:cy + ch, cx - cw:cx + cw]
    m = np.ones(g.shape, bool)
    m[cy - ch:cy + ch, cx - cw:cx + cw] = False
    b, gg, r = [float(ref_bgr[:, :, i].mean()) for i in range(3)]
    return dict(ref_mean=float(g.mean()), ref_std=float(g.std()),
                ref_b=b, ref_g=gg, ref_r=r,
                centre_edge=float(centre.mean() / max(g[m].mean(), 1e-6)))


def scatter(run, ref_bgr, a_px):
    """How far the optical answer to a local press reaches, outside the contact."""
    refg = cv2.cvtColor(ref_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    fr = pd.read_csv(run / "stream" / "frames.csv")
    fz = (fr.Fz_s_corr if "Fz_s_corr" in fr else fr.Fz_s).abs()
    nrm = fr[fr.segment.astype(str).str.startswith("normal") & (fz > 1.7) & (fz < 2.1)]
    if nrm.empty or not np.isfinite(a_px):
        return {}
    nrm = nrm.iloc[np.linspace(0, len(nrm) - 1, min(6, len(nrm))).astype(int)]
    H, W = refg.shape
    yy, xx = np.mgrid[0:H, 0:W]
    prof_sum, n = None, 0
    cy = cx = None
    for _, r in nrm.iterrows():
        im = cv2.imread(str(run / "stream" / r["file"]), cv2.IMREAD_GRAYSCALE)
        if im is None:
            continue
        d = im.astype(np.float32) - refg
        d -= d.mean()
        a = np.abs(d)
        if cy is None:
            sm = cv2.GaussianBlur(a, (0, 0), 9)
            cy, cx = np.unravel_index(np.argmax(sm), sm.shape)
            rad = np.hypot(yy - cy, xx - cx)
        edges = np.linspace(a_px, 3 * a_px, 13)
        idx = np.digitize(rad.ravel(), edges) - 1
        av = a.ravel()
        p = np.array([av[idx == k].mean() if (idx == k).any() else np.nan
                      for k in range(len(edges) - 1)])
        prof_sum = p if prof_sum is None else prof_sum + p
        n += 1
    if not n:
        return {}
    prof = prof_sum / n
    centres = 0.5 * (edges[:-1] + edges[1:]) - a_px      # distance past the edge
    ok = np.isfinite(prof) & (prof > 0)
    if ok.sum() < 4:
        return {}
    # exp(-r/L) on the part that is still above the far-field floor
    floor = np.nanmin(prof)
    y = prof[ok] - floor * 0.9
    y = np.clip(y, 1e-3, None)
    L = -1.0 / np.polyfit(centres[ok], np.log(y), 1)[0]
    return dict(scatter_px=float(L), halo_ratio=float(prof[-1] / max(prof[0], 1e-6)),
                imprint_edge_lvl=float(prof[0]))


if __name__ == "__main__":
    dv = pd.read_csv(ROOT / "data" / "analysis" / "derived_variables.csv")
    rows = []
    for principle, ds in DS.items():
        for unit, run in runs_for(principle, ds):
            ref = None
            for nm in ("reference_collect.png", "reference_working.png", "reference.png"):
                if (run / nm).exists():
                    ref = cv2.imread(str(run / nm)); used = nm; break
            if ref is None:
                print(f"  {principle}_{unit}: no reference"); continue
            d = dv[(dv.principle == principle) & (dv.unit == unit)]
            ppm = float(d.px_per_mm.iloc[0]) if len(d) else np.nan
            a_px = float(d.a_2N_mm.iloc[0] * ppm) if len(d) and np.isfinite(ppm) else np.nan
            m = re.search(r"(soft|medium|hard)_(\d)mm_r(\d)", unit)
            row = dict(unit=unit, principle=principle, hardness=m.group(1),
                       thickness_mm=int(m.group(2)), rep=int(m.group(3)),
                       reference=used, px_per_mm=ppm)
            row.update(unloaded(ref))
            s = scatter(run, ref, a_px)
            row.update(s)
            if "scatter_px" in row and np.isfinite(ppm):
                row["scatter_mm"] = row["scatter_px"] / ppm
            rows.append(row)
            print(f"  {principle}_{unit:16s} 밝기 {row['ref_mean']:6.1f} "
                  f"(B{row['ref_b']:5.1f} G{row['ref_g']:5.1f} R{row['ref_r']:5.1f}) "
                  f"중심/가장자리 {row['centre_edge']:.3f}  산란 "
                  f"{row.get('scatter_mm', float('nan')):.2f} mm", flush=True)
    out = ROOT / "data" / "analysis" / "gel_optics.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print("  ->", out, len(rows), "units")
