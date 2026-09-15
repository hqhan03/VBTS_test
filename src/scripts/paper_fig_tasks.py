#!/usr/bin/env python3
"""한 카메라에서 두 과제가 요구하는 화소 밀도 — 힘과 형상을 나란히.

Figure 1(c) 를 넓힌 것이다. (c) 는 힘 곡선 하나였는데, 여기서는 **같은
9DTact 카메라**에서 힘과 형상을 같은 x 축에 놓는다. 위의 섬네일 셋은 그
밀도에서 영상이 실제로 어떻게 보이는지다.

**왜 한 카메라인가.** 두 과제의 요구를 견주려면 시야·광학·겔이 같아야 한다.
원리를 가로지르면 요구량 차이에 하드웨어 차이가 섞인다.

**축 아래 표식** — ▲ 는 평탄 구간이 시작하는 곳(그 유닛 자신의 최솟값의
110 % 안에 드는 가장 낮은 밀도, 유닛 중앙), ✕ 는 그 아래로는 값이 나오지
않는 곳(복원이 실패하기 시작하는 밀도)이다. 둘 사이가 "쓸 수는 있으나
나빠지는" 구간이다.

띠는 아홉 유닛의 사분위 범위다 — 불확실성이 아니라 **유닛 사이의 산포**이고,
이 캠페인에서 그것이 해상도 효과보다 큰 경우가 많다.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import cv2

import pixel_density as PD
import result_common as RC

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
SRC = ROOT / "paper" / "figures" / "sources"
OUT = ROOT / "paper" / "figures"
PR = "9DTact"
UNIT = "hard_2mm_r1"
SHOW = [320, 80, 16]
CYL, CUBE = "#0047B3", "#D40000"
XT = [0.1, 1, 10, 100, 1000, 10000]
XTL = ["0.1", "1", "10", "100", "1000", "10⁴"]


def plateau(v, tol=1.10):
    v = v.dropna()
    return int(v.index[v <= v.min() * tol].min()) if len(v) >= 4 else None


def force():
    f = DS / PR / "force_vs_resolution_res.csv"
    if not f.exists():
        f = DS / PR / "force_vs_resolution_axes.csv"
    d = RC.keep(pd.read_csv(f), PR, "sensor")
    d = d[d.sensor.isin(RC.chosen(PR))].copy()
    d["res"] = (d.res_mae if "res_mae" in d else
                np.sqrt(d.fx_mae ** 2 + d.fy_mae ** 2 + d.fz_mae ** 2))
    return PD.add(d, PR)


def shape():
    f = DS / PR / "shape_vs_resolution.csv"
    d = pd.read_csv(f)
    d = d[d.width_px.notna()].copy()
    d["width_px"] = d.width_px.astype(int)
    d = RC.keep(d, PR, "sensor")
    d = d[d.sensor.isin(RC.chosen(PR))]
    return PD.add(d, PR)


def band(ax, d, col, c, lab, ls="-"):
    """유닛 중앙선 + 사분위 띠. x 는 그 단의 중앙 밀도."""
    g = d.groupby(["sensor", "width_px"])[col].median().reset_index()
    m = g.groupby("width_px")[col].agg(["median",
                                        lambda v: v.quantile(.25),
                                        lambda v: v.quantile(.75)])
    m.columns = ["med", "lo", "hi"]
    R = d.groupby("width_px").density_px_per_mm2.median().reindex(m.index)
    ok = m.med.notna()
    ax.fill_between(R[ok], m.lo[ok], m.hi[ok], color=c, alpha=.15, lw=0)
    ax.plot(R[ok], m.med[ok], ls, c=c, lw=2.0, label=lab)
    return m, R


def marks(ax, d, col, c, y, bad=2.0):
    """축 아래에 ▲(평탄 시작)와 ✕(못 쓰는 곳).

    **▲ 는 유닛마다 평탄점을 구한 뒤 그 중앙값**이다 — 곡선을 먼저 중앙값으로
    합친 뒤 평탄점을 구하면 값이 다르고, 이 캠페인의 표(Table IX 등)는 전자를
    쓴다. 섞으면 같은 그림과 표가 다른 수를 말한다.

    ✕ 는 그 유닛의 평탄 오차의 `bad` 배를 처음 넘는 밀도다 — 값이 나오기는
    하지만 두 배 틀리면 쓸 수 없다는 뜻이고, 결측만으로는 표시가 안 잡힌다
    (커널을 고친 뒤로는 어느 단에서도 값이 나온다).
    """
    g = d.groupby(["sensor", "width_px"])[col].median()
    R = d.groupby("width_px").density_px_per_mm2.median()
    plat, worse = [], []
    for u, gg in g.groupby(level=0):
        v = gg.reset_index(level=0)[col].dropna()
        if len(v) < 4:
            continue
        w = plateau(v)
        if w:
            plat.append(PD.density(PR, u, w))
        lim = v.min() * bad
        below = v.index[(v > lim) & (v.index < (w or v.index.max()))]
        if len(below):
            worse.append(PD.density(PR, u, int(max(below))))
    if plat:
        ax.plot([np.median(plat)], [y], "^", ms=6, c=c, clip_on=False,
                transform=ax.get_xaxis_transform(), zorder=6)
    if worse:
        ax.plot([np.median(worse)], [y], "x", ms=6, mew=1.8, c=c,
                clip_on=False, transform=ax.get_xaxis_transform(), zorder=6)


def main():
    plt.rcParams["font.family"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig = plt.figure(figsize=(7.16, 3.9))
    gs = fig.add_gridspec(2, 2, height_ratios=[.62, 1], hspace=.55, wspace=.30,
                          left=.085, right=.985, top=.93, bottom=.13)

    # 위 — 같은 프레임을 세 밀도로
    top = gs[0, :].subgridspec(1, 3, wspace=.10)
    base = cv2.imread(str(SRC / "fig1c_hard_2mm_r1_ball8_000501.png"),
                      cv2.IMREAD_GRAYSCALE)
    for k, w in enumerate(SHOW):
        ax = fig.add_subplot(top[0, k])
        if base is not None:
            h = int(round(w * base.shape[0] / base.shape[1]))
            ax.imshow(cv2.resize(base, (w, h), interpolation=cv2.INTER_AREA),
                      cmap="gray")
        ax.set_title(f"$R$ = {PD.fmt(PD.density(PR, UNIT, w))}", fontsize=8)
        ax.set_xticks([]); ax.set_yticks([]); ax.set_anchor("N")

    # 아래 왼쪽 — 힘
    ax = fig.add_subplot(gs[1, 0])
    d = force()
    # **Fz 가 아니라 합력을 그린다.** 허용치 10 % 에서도 Fz 혼자의 평탄점은
    # 학습 판 사이에서 재현되지 않는다(9DTact 17.3 -> 44.7, 2.6 배). 같은 두
    # 판에서 전단은 5.9 -> 6.2, 합력은 13.6 -> 13.6 으로 재현된다. 합력이 Fz 에
    # 끌려가는데도 더 안정적인 것은, 전단 항이 더해지면서 최솟값이 칼날 위에
    # 서 있지 않게 되기 때문으로 보인다 — 사후 설명이고 검정한 것은 아니다.
    band(ax, d, "res", "#1a1a1a", "‖ΔF‖")
    marks(ax, d, "res", "#1a1a1a", 0)
    ax.set_ylabel("force MAE  ‖ΔF‖ [N]", fontsize=8.5)
    ax.set_ylim(0, None)

    # 아래 오른쪽 — 형상
    ax2 = fig.add_subplot(gs[1, 1])
    sd = shape()
    band(ax2, sd, "cyl4_raw_mae", CYL, "cylinder ⌀4")
    band(ax2, sd, "cube4_raw_mae", CUBE, "cube 4 mm", ls="--")
    marks(ax2, sd, "cyl4_raw_mae", CYL, 0)
    marks(ax2, sd, "cube4_raw_mae", CUBE, -0.055)
    ax2.set_ylabel("depth MAE [mm]", fontsize=8.5)
    ax2.set_ylim(0, None)
    ax2.legend(frameon=False, fontsize=7.5, loc="upper right")

    for a in (ax, ax2):
        a.set_xscale("log")
        a.set_xticks(XT); a.set_xticklabels(XTL, fontsize=7)
        a.xaxis.set_minor_locator(mticker.NullLocator())
        a.set_xlabel("pixel density $R$ [px/mm$^2$]", fontsize=8.5)
        a.tick_params(labelsize=7)
        a.grid(alpha=.3, lw=.4); a.set_axisbelow(True)
        a.spines[["top", "right"]].set_visible(False)

    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig_task_requirement.{ext}", dpi=300,
                    bbox_inches="tight")
    plt.close(fig)
    print("  -> paper/figures/fig_task_requirement.{png,pdf}")


if __name__ == "__main__":
    main()
