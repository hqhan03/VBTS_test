#!/usr/bin/env python3
"""Figure 4 — 형상 복원: 실제 복원 예시 + 오차 곡선.

**이 그림이 분리해 보여야 하는 것** (2026-09-13, 운전자 지시): *형상이 비슷해
보이는 것*과 *깊이 배율이 맞는 것*은 다르다. 상관계수만 싣고 넘어가면 그 둘이
섞인다. 그래서 높이맵 옆에 **단면**을 놓고 참 깊이를 점선으로 그린다 — 모양은
맞는데 깊이가 절반인 것이 눈으로 보여야 한다.

**깊이만 보면 안 된다** (2026-09-14, 운전자 지적). 압자는 ⌀4 mm 원기둥과 한 변
4 mm 정육면체다 — 형상 센서가 되찾아야 할 것은 깊이**와** 가로 크기 둘이다. 전에는
네 패널의 y 가 전부 깊이였다. (d) 에 **복원된 가로 크기**를 넣는다.

**(d) 만 깊이 참조형(9DTact) 이다.** 가로 크기는 그쪽에만 측정돼 있다 — 광도
스테레오 파이프라인(`digit_shape.py`)은 화소별 깊이만 채점하고 윤곽을 재지 않는다.
계열이 섞이므로 패널마다 어느 계열인지 제목에 적는다.

배치: 왼쪽 세 칸이 같은 held-out 프레임을 320 · 80 · 16 px 로 복원한 높이맵
(**색 눈금 공유**, 참 지름 4 mm 를 막대로 얹었다), 그 아래가 단면과 네 곡선.

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


def head(ax, title, arm):
    """패널 제목 + 그 아래 작은 계열 꼬리표. 한 줄로 붙이면 칸을 넘는다."""
    ax.set_title(title, fontsize=7.8, loc="left", pad=13)
    ax.text(0, 1.015, arm, transform=ax.transAxes, fontsize=6,
            color="#777", ha="left", va="bottom")

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
TRUE_SIZE_MM = 4.0    # 두 압자 모두 4 mm (원기둥 지름, 정육면체 변)
# 반깊이 윤곽이 화면을 다 덮으면 "크기" 가 아니라 검출 실패다. 참값의 두 배를
# 넘으면 값이 아니라 실패로 읽는다 (`shape_reconstruction.md` §6.2).
SIZE_BLOWUP_MM = 2 * TRUE_SIZE_MM
NINE = (ROOT / "data" / "20260911_VBTSresolution_dataset" / "9DTact"
        / "shape_vs_resolution.csv")


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
    fig = plt.figure(figsize=(7.16, 4.3))
    gs = fig.add_gridspec(2, 4, height_ratios=[.72, 1], hspace=.42, wspace=.46)
    top = gs[0, :].subgridspec(1, 4, width_ratios=[1, 1, 1, .05], wspace=.12)

    prof = {}
    for k, w in enumerate(WIDTHS):
        ax = fig.add_subplot(top[0, k])
        im = ax.imshow(-zs[w], cmap="viridis", vmin=0, vmax=-lo)
        ax.set_title(f"{w}×{int(round(w*9/16))}", fontsize=8)
        ax.set_xticks([]); ax.set_yticks([])
        x, y, row = cut(zs[w], ppm[w], fy, fx)
        ax.axhline(row, c="white", lw=.9, ls="--", alpha=.9)
        # 참 지름 4 mm 를 자로 얹는다 — 높이맵만 보면 가로 크기가 맞는지 알 수 없다.
        bar = TRUE_SIZE_MM * ppm[w]
        y0 = zs[w].shape[0] * .88
        x0 = zs[w].shape[1] * .5 - bar / 2
        ax.plot([x0, x0 + bar], [y0, y0], "-", c="white", lw=1.6,
                solid_capstyle="butt")
        if k == 0:
            ax.text(zs[w].shape[1] * .5, y0 - zs[w].shape[0] * .06,
                    f"{TRUE_SIZE_MM:.0f} mm", c="white", fontsize=6,
                    ha="center", va="bottom")
        prof[w] = (x, y)
    cax = fig.add_subplot(top[0, 3])
    cb = fig.colorbar(im, cax=cax)
    cb.set_label("depth [mm]", fontsize=7); cb.ax.tick_params(labelsize=6.5)

    # (a) 해상도를 줄여도 모양은 남는다
    ax = fig.add_subplot(gs[1, 0])
    for w, c in zip(WIDTHS, ("#0072B2", "#D55E00", "#009E73")):
        ax.plot(*prof[w], "-", c=c, lw=1.6, label=f"{w} px")
    ax.axhline(true, c="#1a1a1a", lw=1.1, ls=":")
    # 참깊이 라벨은 **오른쪽 끝 선 아래**, 범례는 아래쪽 왼쪽 — 곡선이 가운데에서
    # 솟고 양끝이 낮으므로 이 둘이 서로도, 곡선과도 닿지 않는다.
    ax.annotate(f"true {true:.2f} mm", (2.7, true), fontsize=6.5,
                va="top", ha="right", color="#1a1a1a")
    ax.set_xlim(-2.8, 2.8); ax.set_ylim(-.02, max(true, .5) * 1.32)
    ax.set_xlabel("across contact [mm]", fontsize=8)
    ax.set_ylabel("depth [mm]", fontsize=8)
    head(ax, "(a) depth vs. resolution", "photometric")
    ax.legend(frameon=False, fontsize=6.2, ncol=1, loc="lower left",
              handlelength=1.0, labelspacing=.2, borderaxespad=.3)
    ax.tick_params(labelsize=7); ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=.3, lw=.4)

    # (b) 다른 유닛 — 모양은 같은데 깊이가 4 배 작다
    zl, pl, tl = recon(UNIT_LOW, PROF_W)
    cyl, cxl = np.unravel_index(np.argmin(zl), zl.shape)
    xl, yl, _ = cut(zl, pl, cyl / zl.shape[0], cxl / zl.shape[1])
    xg, yg = prof[80]
    ax = fig.add_subplot(gs[1, 1])
    ax.plot(xg, yg / max(true, 1e-9), "-", c="#0072B2", lw=1.6,
            label=f"3 mm gel  ({yg.max()/true:.2f}×)")
    ax.plot(xl, yl / max(tl, 1e-9), "-", c="#D55E00", lw=1.6,
            label=f"1 mm gel  ({yl.max()/tl:.2f}×)")
    ax.axhline(1.0, c="#1a1a1a", lw=1.1, ls=":")
    ax.annotate("true depth", (2.6, 1.0), fontsize=6.5, va="top",
                ha="right", color="#1a1a1a")
    ax.set_xlim(-2.8, 2.8); ax.set_ylim(-.05, 1.35)
    ax.set_xlabel("across contact [mm]", fontsize=8)
    ax.set_ylabel("depth / true depth", fontsize=8)
    head(ax, "(b) shape vs. depth scale", "photometric")
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
    head(ax, "(c) depth error", "photometric")
    ax.legend(frameon=False, fontsize=7)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=.3, lw=.4, which="major")

    # (d) 깊이만이 아니라 **가로 크기**도 되찾는가 — 9DTact
    ax = fig.add_subplot(gs[1, 3])
    size_rows = []
    if NINE.exists():
        n = pd.read_csv(NINE)
        n["width_px"] = (1920 / n.downscale).round().astype(int)
        for sh, c, lab in (("cyl4", "#0072B2", "cylinder ⌀4"),
                           ("cube4", "#D55E00", "cube 4")):
            col = f"{sh}_raw_size"
            if col not in n:
                continue
            g = n[["sensor", "width_px", col]].dropna()
            # 윤곽이 화면을 덮은 단은 크기가 아니라 검출 실패다 — 빼고, 아래에
            # 어디서부터 그런지 적는다.
            g = g[g[col] <= SIZE_BLOWUP_MM]
            if not len(g):
                continue
            per = g.pivot_table(index="sensor", columns="width_px", values=col)
            for u, row in per.iterrows():
                xs = [PD.density("9DTact", u, w) for w in row.index]
                ax.plot(xs, row.values, "-", c=c, lw=.6, alpha=.22)
            med = per.median(axis=0)
            xm = [np.median([PD.density("9DTact", u, w) for u in per.index])
                  for w in med.index]
            ax.plot(xm, med.values, "-", c="white", lw=3.4, alpha=.9)
            ax.plot(xm, med.values, "-", c=c, lw=2.0, label=lab)
            size_rows.append(g.assign(shape=sh).rename(columns={col: "size_mm"}))
    ax.axhline(TRUE_SIZE_MM, c="#1a1a1a", lw=1.1, ls=":")
    # 곡선이 오른쪽에서 참값선 위를 지나므로 라벨은 **왼쪽 끝 선 아래**에 둔다.
    ax.annotate("true 4 mm", (1.4, TRUE_SIZE_MM), fontsize=6.3, va="top",
                ha="left", color="#1a1a1a")
    ax.set_xscale("log")
    ax.set_xticks([0.1, 1, 10, 100, 1000, 10000])
    ax.set_xticklabels(["0.1", "1", "10", "100", "1000", "10⁴"], fontsize=6.5,
                       rotation=90)
    ax.minorticks_off()
    ax.set_ylim(2.4, 6.2)
    ax.tick_params(labelsize=7)
    ax.set_xlabel("$R$ [px/mm$^2$]", fontsize=8)
    ax.set_ylabel("recovered size [mm]", fontsize=8)
    head(ax, "(d) lateral size", "depth-referenced")
    ax.legend(frameon=False, fontsize=6.3, loc="upper right")
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
    if size_rows:
        pd.concat(size_rows).to_csv(OUT / "fig4_lateral_size.csv", index=False)
    print(f"  -> fig4  {UNIT} true {true:.3f} peak "
          + " ".join(f"{w}px {prof[w][1].max():.3f}" for w in WIDTHS)
          + f"  |  {UNIT_LOW} true {tl:.3f} peak {yl.max():.3f}")


if __name__ == "__main__":
    main()
