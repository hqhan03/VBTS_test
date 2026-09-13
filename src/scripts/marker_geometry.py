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

# 격자의 실제 치수. 운전자가 2026-09-13 에 실물을 재서 확인했다.
PITCH_NOMINAL_MM = 2.5
DOT_NOMINAL_MM = 1.0

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
    D = pd.DataFrame(rows)

    # ---- 축척 둘을 나란히 낸다 (2026-09-13) ----
    # 격자는 **공칭 2.5 mm** 간격이다. 운전자가 2026-09-13 에 실물을 재서 확인했다
    # (점 지름 1.0 mm, 중심 간격 2.5 mm). 그러므로 격자는 프레임마다 누워 있는 자다.
    #
    # 표면 높이 회귀로 얻은 축척과 **일관되게 1.198 배**(범위 1.075~1.260) 차이가 난다.
    # 잡음이 아니라 계통 오차다. `scale_from_markers.py` 가 2026-09-08 에 이 15 % 차이를
    # 보고 "겔이 수축해 간격이 2.33 mm 가 됐을 것" 이라 짐작하고 보류했는데, 실측이
    # 2.5 mm 이므로 **수축 가설은 죽고 회귀 축척이 낮은 쪽**이 된다.
    #
    # 검산: 격자 축척으로 점 지름을 재면 0.878 mm (공칭 1.0)가 나온다. 문턱이 무른
    # 가장자리를 깎으므로 조금 작게 나오는 것이 맞는 방향이다. 회귀 축척으로 재면
    # 1.091 mm 로 공칭보다 **크게** 나오는데, 그럴 이유가 없다.
    D["px_per_mm_grid"] = D.pitch_px / PITCH_NOMINAL_MM
    D["pitch_mm_grid"] = PITCH_NOMINAL_MM              # 정의상
    D["dot_d_mm_grid"] = D.dot_d_px / D.px_per_mm_grid


    out = ROOT / "data" / "analysis" / "marker_geometry.csv"
    # 이전 판의 열(회귀 축척으로 계산한 mm 값)이 있으면 이어 붙인다 — 두 축척을
    # 나란히 두는 것이 이 파일의 요점이다.
    if out.exists():
        old = pd.read_csv(out)
        keep = [c for c in ("unit", "px_per_mm", "pitch_mm", "dot_d_mm",
                            "a_2N_mm", "contact_d_px", "dots_in_contact")
                if c in old.columns]
        if len(keep) > 1:
            D = D.merge(old[keep], on="unit", how="left", suffixes=("", "_old"))
            D = D.rename(columns={"px_per_mm": "px_per_mm_regression",
                                  "pitch_mm": "pitch_mm_regression",
                                  "dot_d_mm": "dot_d_mm_regression"})
    # 접촉 크기를 **격자 축척**으로 다시 낸다 — 하류(`marker_occlusion.py`)가 읽는다.
    # `a_2N_mm` 은 Hertz 로 얻으므로 이미지 축척과 무관하다. 그것을 픽셀로 옮길 때만
    # 축척이 들어가는데, 옛 판은 회귀 축척(20 % 낮음)을 써서 접촉 원을 작게 그렸고
    # 가려진 비율이 그만큼 틀어졌다.
    if "a_2N_mm" in D:
        D["contact_d_px_grid"] = 2 * D.a_2N_mm * D.px_per_mm_grid
        D["contact_over_pitch_grid"] = 2 * D.a_2N_mm / PITCH_NOMINAL_MM
        # 접촉 원 안에 들어오는 점의 기대 개수 = (면적비) x (격자 밀도)
        D["dots_in_contact_grid"] = (np.pi / 4) * D.contact_over_pitch_grid ** 2

    D.to_csv(out, index=False)
    print("  ->", out, len(rows), "units")
    if "px_per_mm_regression" in D:
        r = (D.px_per_mm_grid / D.px_per_mm_regression).dropna()
        print(f"  축척: 격자 {D.px_per_mm_grid.median():.1f} px/mm, "
              f"회귀 {D.px_per_mm_regression.median():.1f} px/mm, "
              f"비 중앙 {r.median():.3f} (범위 {r.min():.3f}~{r.max():.3f})")
        print(f"  검산 — 점 지름: 격자 축척 {D.dot_d_mm_grid.median():.3f} mm, "
              f"회귀 축척 {D.dot_d_mm_regression.median():.3f} mm (공칭 1.0)")
