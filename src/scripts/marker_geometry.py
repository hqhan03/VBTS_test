#!/usr/bin/env python3
"""How many pixels does a marker dot need, and what does that predict?

DIGIT_Marker's shear knee sits at 120 px wide against 48 px for 9DTact
(cross_principle.md 4). If the marker signal is carried by where the DOTS moved,
the resolution it needs is set by the dot lattice, not by the imprint: a dot has
to stay resolvable, which takes about 2 px across the dot, and telling two dots
apart takes about 2 px per pitch. So measure both from each unit's own reference
image and turn them into a predicted width.

  dot_d_px, pitch_px   dot diameter and nearest-neighbour spacing at 1920 px wide
  w_dot_2px            width at which the dot is 2 px across   = 2 * 1920 / dot_d_px
  w_pitch_2px          width at which the pitch is 2 px        = 2 * 1920 / pitch_px
  n_dots               dots found (sanity)

Writes data/analysis/marker_geometry.csv. 9DTact and plain DIGIT have no dots, so the
prediction applies to the marker units only -- but the same file records the
imprint width for all three from derived_variables.csv for comparison.
"""
import re, yaml
import numpy as np, pandas as pd, cv2
from pathlib import Path
from scipy import ndimage, spatial, signal

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset" / "DIGIT_Marker" / "20260908_passB_ball8"


def dots_in(img_bgr):
    """Marker dots are the dark blobs on the lit gel; find them on the grey image."""
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    bg = cv2.GaussianBlur(g, (0, 0), 25)          # illumination, not dots
    d = bg - g                                     # dots are darker than around
    thr = d > max(4.0, np.percentile(d, 99.0) * 0.35)
    lab, n = ndimage.label(thr)
    if n == 0:
        return np.zeros((0, 2)), np.array([])
    areas = ndimage.sum(thr, lab, range(1, n + 1))
    # A dot on these gels is ~110 px across, i.e. ~9500 px^2. The first version
    # of this script capped the area at 4000 px^2, which threw every real dot
    # away and kept specks -- it reported a 6 px "dot diameter" (a look at the
    # reference image settled it).
    keep = [i + 1 for i, a in enumerate(areas) if 1500 <= a <= 60000]
    if len(keep) < 8:
        return np.zeros((0, 2)), np.array([])
    cen = np.array(ndimage.center_of_mass(thr, lab, keep))
    diam = 2 * np.sqrt(np.array([areas[i - 1] for i in keep]) / np.pi)
    return cen[:, ::-1], diam                      # (x, y), diameter px


def pitch_by_autocorr(img_bgr):
    """Lattice pitch without a threshold: the first ring of the autocorrelation.

    Nearest-neighbour spacing over detected blobs is only as good as the
    detection -- on these references it found 18 to 62 of the dots and the
    spacing swung from 16 to 184 px. The autocorrelation of the high-passed
    image peaks at the lattice vector whether or not every dot was found.
    """
    g = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    d = cv2.GaussianBlur(g, (0, 0), 25) - g
    d -= d.mean()
    F = np.fft.rfft2(d)
    ac = np.fft.irfft2(F * np.conj(F), s=d.shape)
    ac = np.fft.fftshift(ac) / ac.max()
    cy, cx = np.array(ac.shape) // 2
    r = 500                                        # dots sit ~250 px apart
    win = ac[cy - r:cy + r, cx - r:cx + r].copy()
    yy, xx = np.mgrid[-r:r, -r:r]
    rad = np.hypot(yy, xx)
    # Suppress the central lobe: a dot autocorrelates with itself out to its own
    # width, so the first ring is only visible past that.
    win[rad < 150] = 0
    win[rad > 480] = 0
    k = np.unravel_index(np.argmax(win), win.shape)
    return float(rad[k]), float(win.max())


if __name__ == "__main__":
    can = yaml.safe_load((DS / "CANONICAL.yaml").read_text())["canonical"]
    rows = []
    for unit, info in can.items():
        run = DS / info["run"]
        ref = None
        for nm in ("reference_collect.png", "reference_working.png", "reference.png"):
            if (run / nm).exists():
                ref = cv2.imread(str(run / nm)); used = nm; break
        if ref is None:
            print(f"  {unit}: no reference"); continue
        cen, diam = dots_in(ref)
        if len(cen) < 8:
            print(f"  {unit}: only {len(cen)} dots found"); continue
        tree = spatial.cKDTree(cen)
        nn = tree.query(cen, k=2)[0][:, 1]
        pitch_nn = float(np.median(nn)); dd = float(np.median(diam))
        pitch, ac_peak = pitch_by_autocorr(ref)
        m = re.search(r"(soft|medium|hard)_(\d)mm_r(\d)", unit)
        rows.append(dict(unit=unit, principle="DIGIT_Marker", hardness=m.group(1),
                         thickness_mm=int(m.group(2)), rep=int(m.group(3)),
                         reference=used, n_dots=len(cen), dot_d_px=round(dd, 2),
                         pitch_px=round(pitch, 2), pitch_nn_px=round(pitch_nn, 2),
                         ac_peak=round(ac_peak, 3),
                         w_dot_2px=round(2 * 1920 / dd, 1),
                         w_pitch_2px=round(2 * 1920 / pitch, 1)))
        print(f"  {unit:30s} {len(cen):4d} dots  d {dd:5.1f} px  pitch(ac) {pitch:5.1f} px"
              f" (nn {pitch_nn:5.1f}, peak {ac_peak:.2f})"
              f"  -> dot=2px at {2*1920/dd:6.1f}, pitch=2px at {2*1920/pitch:5.1f}", flush=True)
    out = ROOT / "data" / "analysis" / "marker_geometry.csv"
    pd.DataFrame(rows).to_csv(out, index=False)
    print("  ->", out, len(rows), "units")
