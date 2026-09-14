#!/usr/bin/env python3
"""Figure 4 — 형상 복원: 실제 복원 예시 + 오차 곡선.

**이 그림이 분리해 보여야 하는 것** (2026-09-13, 운전자 지시): *형상이 비슷해
보이는 것*과 *깊이 배율이 맞는 것*은 다르다. 상관계수만 싣고 넘어가면 그 둘이
섞인다. 그래서 높이맵 옆에 **단면**을 놓고 참 깊이를 점선으로 그린다 — 모양은
맞는데 깊이가 절반인 것이 눈으로 보여야 한다.

배치: 왼쪽 세 칸이 같은 held-out 프레임을 320 · 80 · 16 px 로 복원한 높이맵
(**색 눈금 공유**), 그 아래가 중심을 지나는 단면, 오른쪽이 오차 대 해상도 곡선.

**접촉 중심은 원해상도에서 한 번 찾아 세 해상도가 함께 쓴다.** 낮은 해상도에서
다시 찾으면 중심이 흔들려 단면이 서로 다른 곳을 자르게 된다. 이것은 편의가
아니라 비교 가능성을 위한 선택이고, 캡션에 밝힌다.
"""
import pickle
import sys
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
warnings.filterwarnings("ignore")
import cv2
import digit_shape as D
import pixel_density as PD

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset" / "DIGIT"
AN = ROOT / "data" / "analysis" / "digit_shape"
OUT = ROOT / "paper" / "figures"

# 높이맵은 깊이 배율이 잘 맞는 유닛으로 (기울기 0.92, 상관 0.999).
UNIT = "medium_3mm_r2"
# 단면 비교용 — **상관 0.992 인데 기울기 0.24.** 모양은 맞고 깊이만 4 배 작다.
# 이 둘을 나란히 놓는 것이 이 그림의 요점이다.
UNIT_LOW = "soft_1mm_r2"
SHAPE = "cyl4"
WIDTHS = [320, 80, 16]
PROF_W = 160          # 두 유닛을 견줄 때 쓰는 해상도


def recon(unit, w, frame=None):
    """한 유닛의 가장 깊은 held-out 프레임을 해상도 w 로 복원한다."""
    run = DS / f"20260910_passA_{SHAPE}" / f"DIGIT_{unit}"
    lad = pd.read_csv(run / f"shape_{SHAPE}" / "ladder.csv")
    if "area_px" in lad:
        lad = lad[lad.area_px >= 5000]
    r = lad.sort_values("depth_mm").iloc[-1] if frame is None else frame
    img = cv2.imread(str(run / f"shape_{SHAPE}" / Path(str(r.file)).name))
    ref = D.load_ref(run)
    M = pickle.load(open(AN / f"DIGIT_{unit}_lut.pkl", "rb"))
    h = int(round(w * 9 / 16))
    z, p = D.predict_depth(M["model"], img, ref, M["px_per_mm"], size=(w, h))
    return z, p, float(r.depth_mm)


def cut(z, ppm, fy, fx):
    """중심을 지나는 가로 단면. 중심은 밖에서 받는다 — 해상도마다 다시 찾으면
    서로 다른 곳을 자르게 된다."""
    row = int(fy * z.shape[0])
    x = (np.arange(z.shape[1]) - fx * z.shape[1]) / ppm
    return x, -z[row], row


def main():
    plt.rcParams["font.family"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False

    zs, ppm, true = {}, {}, None
    for w in WIDTHS:
        zs[w], ppm[w], true = recon(UNIT, w)
    # **접촉 중심은 원해상도에서 한 번만 찾아 세 해상도가 함께 쓴다.**
    z0 = zs[max(WIDTHS)]
    cy0, cx0 = np.unravel_index(np.argmin(z0), z0.shape)
    fy, fx = cy0 / z0.shape[0], cx0 / z0.shape[1]

    lo = min(float(np.percentile(z, .3)) for z in zs.values())
    fig = plt.figure(figsize=(7.16, 4.2))
    gs = fig.add_gridspec(2, 3, height_ratios=[.72, 1], hspace=.38, wspace=.42)
    top = gs[0, :].subgridspec(1, 4, width_ratios=[1, 1, 1, .055], wspace=.12)

    prof = {}
    for k, w in enumerate(WIDTHS):
        ax = fig.add_subplot(top[0, k])
        im = ax.imshow(-zs[w], cmap="viridis", vmin=0, vmax=-lo)
        ax.set_title(f"{w}×{int(round(w*9/16))}", fontsize=8.5)
        ax.set_xticks([]); ax.set_yticks([])
        x, y, row = cut(zs[w], ppm[w], fy, fx)
        ax.axhline(row, c="white", lw=.9, ls="--", alpha=.9)
        prof[w] = (x, y)
    cax = fig.add_subplot(top[0, 3])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label("depth [mm]", fontsize=7); cb.ax.tick_params(labelsize=6.5)

    # (a) 해상도를 줄여도 모양은 남는다
    ax = fig.add_subplot(gs[1, 0])
    for w, c in zip(WIDTHS, ("#0072B2", "#D55E00", "#009E73")):
        ax.plot(*prof[w], "-", c=c, lw=1.6, label=f"{w} px")
    ax.axhline(true, c="#1a1a1a", lw=1.1, ls=":")
    ax.annotate(f"true {true:.2f} mm", (2.6, true), fontsize=6.5,
                va="bottom", ha="right", color="#1a1a1a")
    ax.set_xlim(-2.8, 2.8); ax.set_ylim(-.02, max(true, .5) * 1.25)
    ax.set_xlabel("across contact [mm]", fontsize=8)
    ax.set_ylabel("depth [mm]", fontsize=8)
    ax.set_title("(a) resolution", fontsize=8, loc="left")
    ax.legend(frameon=False, fontsize=6.3, ncol=3, loc="upper left",
              handlelength=1.1, columnspacing=.8)
    ax.tick_params(labelsize=7); ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=.3, lw=.4)

    # (b) 다른 유닛 — 모양은 같은데 깊이가 4 배 작다
    zl, pl, tl = recon(UNIT_LOW, PROF_W)
    cyl, cxl = np.unravel_index(np.argmin(zl), zl.shape)
    xl, yl, _ = cut(zl, pl, cyl / zl.shape[0], cxl / zl.shape[1])
    xg, yg = prof[80]
    ax = fig.add_subplot(gs[1, 1])
    ax.plot(xg, yg / max(true, 1e-9), "-", c="#0072B2", lw=1.6,
            label=f"{UNIT}  ({yg.max()/true:.2f}×)")
    ax.plot(xl, yl / max(tl, 1e-9), "-", c="#D55E00", lw=1.6,
            label=f"{UNIT_LOW}  ({yl.max()/tl:.2f}×)")
    ax.axhline(1.0, c="#1a1a1a", lw=1.1, ls=":")
    ax.annotate("true depth", (2.6, 1.0), fontsize=6.5, va="top",
                ha="right", color="#1a1a1a")
    ax.set_xlim(-2.8, 2.8); ax.set_ylim(-.05, 1.35)
    ax.set_xlabel("across contact [mm]", fontsize=8)
    ax.set_ylabel("depth / true depth", fontsize=8)
    ax.set_title("(b) shape vs. depth scale", fontsize=8, loc="left")
    ax.legend(frameon=False, fontsize=6.3, loc="upper left")
    ax.tick_params(labelsize=7); ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=.3, lw=.4)

    # (c) 오차 대 해상도
    ax = fig.add_subplot(gs[1, 2])
    d = pd.read_csv(AN / "DIGIT_shape_vs_resolution.csv")
    d["e"] = (d.depth_pred_mm - d.depth_true_mm).abs()
    for sh, c, lab in (("cyl4", "#0072B2", "cylinder"),
                       ("cube4", "#D55E00", "cube")):
        g = d[d["shape"] == sh]
        if not len(g):
            continue
        per = g.groupby(["unit", "width_px"]).e.mean().unstack()
        med = per.median(axis=0)
        for u, row in per.iterrows():
            xs = [PD.density("DIGIT", u, w) for w in row.index]
            ax.plot(xs, row.values, "-", c=c, lw=.6, alpha=.22)
        xm = [np.median([PD.density("DIGIT", u, w) for u in per.index])
              for w in med.index]
        ax.plot(xm, med.values, "-", c="white", lw=3.4, alpha=.9)
        ax.plot(xm, med.values, "-", c=c, lw=2.0, label=lab)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks([0.1, 1, 10, 100, 1000, 10000])
    ax.set_xticklabels(["0.1", "1", "10", "100", "1000", "10⁴"], fontsize=6.5,
                       rotation=90)
    ax.minorticks_off()
    ax.set_yticks([.02, .05, .1, .2, .5])
    ax.set_yticklabels(["0.02", "0.05", "0.1", "0.2", "0.5"], fontsize=7)
    ax.set_xlabel("$R$ [px/mm$^2$]", fontsize=8)
    ax.set_ylabel("Depth MAE [mm]", fontsize=8)
    ax.set_title("(c) error vs. resolution", fontsize=8, loc="left")
    ax.legend(frameon=False, fontsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=.3, lw=.4, which="major")

    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig4_shape.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)
    pd.concat([pd.DataFrame(dict(unit=UNIT, width_px=w, x_mm=prof[w][0],
                                 depth_mm=prof[w][1], true_mm=true))
               for w in WIDTHS]
              + [pd.DataFrame(dict(unit=UNIT_LOW, width_px=PROF_W, x_mm=xl,
                                   depth_mm=yl, true_mm=tl))]
              ).to_csv(OUT / "fig4_profiles.csv", index=False)
    print(f"  -> fig4  {UNIT} true {true:.3f} peak "
          + " ".join(f"{w}px {prof[w][1].max():.3f}" for w in WIDTHS)
          + f"  |  {UNIT_LOW} true {tl:.3f} peak {yl.max():.3f}")


if __name__ == "__main__":
    main()
