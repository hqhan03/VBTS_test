#!/usr/bin/env python3
"""Figure 2 — 논문의 핵심 결과. 행 = 감지 원리, 열 = Fz · 전단.

**무엇을 보이려는 그림인가.** 입력 해상도를 줄여 가며 힘 추정 오차가 어떻게
변하는지, 그리고 그 곡선이 **겔 두께에 따라 갈리는지**를 한눈에 놓는다.

**설계 원칙** (2026-09-13, 운전자 지시):

* 가는 선 = 시편 하나의 seed 중앙값 곡선. 굵은 선 = 그 시편 곡선들의 중앙값.
* 색은 **두께**만 쓴다. 경도는 이 그림에서 나누지 않는다(Figure 3 의 몫).
* **불확실성 음영을 넣지 않는다.** seed 범위와 시편 간 범위를 같은 음영으로
  섞으면 읽는 사람이 둘을 구별하지 못한다. 가는 선이 시편 간 산포를 그대로
  보여주므로 음영이 필요 없다.
* **"48 px 면 충분" 같은 수직선을 크게 넣지 않는다.** 그것은 특정 허용오차에서
  얻은 요약이고, 기준을 바꾸면 움직인다(Figure 3 의 민감도 표). 평탄 구간은
  축 아래의 작은 표식으로만 가리킨다.
* y 축은 **열끼리** 공유한다. Fz 와 전단은 크기가 배 이상 다르므로 넷을 함께
  묶으면 전단이 눌린다.

**전단의 정의.** `(Fx MAE + Fy MAE) / 2`, **전체 시험 프레임**에 대한 것이다.
전단 블록만의 크기 MAE 와 섞지 말 것 — 다른 수다.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

import result_common as RC
from palette import THICK3

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
OUT = ROOT / "paper" / "figures"

# 마커 없는 두 팔만. 마커 변형은 Figure 3 이후에 나온다.
ROWS = [("9DTact", "Depth-referenced"), ("DIGIT", "Photometric")]
COLS = [("fz_mae", "Normal force, $F_z$"), ("shear", "Shear, mean $F_x$/$F_y$")]
SIZES_WH = [(1920, 1080), (1280, 720), (854, 480), (640, 360), (426, 240),
            (320, 180), (160, 90), (80, 45), (48, 27), (32, 18), (16, 9), (8, 5)]
XT = [w for w, _ in SIZES_WH]
XTL = [f"{w}" for w, _ in SIZES_WH]


def load(pr, single=True):
    f = DS / pr / "force_vs_resolution_axes.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    d["shear"] = (d.fx_mae + d.fy_mae) / 2
    d["thickness_mm"] = d.sensor.str.extract(r"_(\d)mm_")[0].astype(int)
    if single:
        ch = RC.chosen(pr)
        d = d[d.sensor.isin(ch)]
    return d


def plateau(v, tol=1.10):
    """평탄 구간이 시작하는 곳 — 최솟값의 110 % 안에 드는 가장 낮은 해상도."""
    v = v.dropna()
    return int(v.index[v <= v.min() * tol].min()) if len(v) >= 4 else None


def main():
    plt.rcParams["font.family"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(2, 2, figsize=(7.16, 5.4), sharex=True)

    ylim = {}
    for i, (pr, nice) in enumerate(ROWS):
        d = load(pr)
        if d is None:
            continue
        for j, (col, clab) in enumerate(COLS):
            ax = axes[i, j]
            # 가는 선 — 시편 하나의 seed 중앙값
            for u, g in d.groupby("sensor"):
                k = g.groupby("width_px")[col].median()
                t = int(u.split("_")[1][0])
                ax.plot(k.index, k.values, "-", c=THICK3[t], lw=.8, alpha=.45,
                        zorder=2)
            # 굵은 선 — 두께별로 시편 곡선의 중앙값
            for t in (1, 2, 3):
                g = d[d.thickness_mm == t]
                if not len(g):
                    continue
                per = g.groupby(["sensor", "width_px"])[col].median().unstack()
                med = per.median(axis=0)
                ax.plot(med.index, med.values, "-", c="white", lw=3.6,
                        alpha=.9, zorder=3)
                ax.plot(med.index, med.values, "-", c=THICK3[t], lw=2.0,
                        label=f"{t} mm", zorder=4)
            # 평탄 구간의 시작 — 축 아래 작은 표식으로만
            allu = d.groupby("width_px")[col].median()
            pl = plateau(allu)
            if pl:
                ax.plot([pl], [0], marker="^", ms=5, c="#1a1a1a",
                        clip_on=False, transform=ax.get_xaxis_transform(),
                        zorder=6)
            ax.set_xscale("log"); ax.set_yscale("log")
            ax.set_xticks(XT); ax.set_xticklabels(XTL, fontsize=6, rotation=90)
            ax.xaxis.set_minor_locator(mticker.NullLocator())
            ax.tick_params(labelsize=7)
            ax.grid(True, which="major", alpha=.3, lw=.4, color="#b8b8b8")
            ax.set_axisbelow(True)
            ax.spines[["top", "right"]].set_visible(False)
            if i == 0:
                ax.set_title(clab, fontsize=9)
            if j == 0:
                ax.set_ylabel(f"{nice}\nMAE [N]", fontsize=8.5)
            if i == 1:
                ax.set_xlabel("Input width [px]", fontsize=8.5)
            ylim.setdefault(j, []).append(ax.get_ylim())

    # y 축은 **열끼리** 공유한다
    for j in (0, 1):
        lo = min(a for a, _ in ylim.get(j, [(1, 1)]))
        hi = max(b for _, b in ylim.get(j, [(1, 1)]))
        for i in (0, 1):
            ax = axes[i, j]
            ax.set_ylim(lo, hi)
            # 로그 축이 한 자리 남짓이라 기본 눈금이 "0.1" 하나뿐이다.
            # 사다리에서 축 범위 안에 드는 것만 명시적으로 찍는다.
            yt = [v for v in (0.01, 0.02, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.3)
                  if lo <= v <= hi]
            ax.set_yticks(yt)
            ax.set_yticklabels([f"{v:g}" for v in yt], fontsize=7)
            ax.yaxis.set_minor_formatter(mticker.NullFormatter())
            ax.yaxis.set_minor_locator(mticker.NullLocator())

    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, frameon=False, fontsize=8, title="Gel thickness",
               title_fontsize=8, ncol=3, loc="lower center",
               bbox_to_anchor=(.55, -.02))
    fig.tight_layout(rect=[0, .045, 1, 1])
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig2_force_vs_resolution.{ext}", dpi=300,
                    bbox_inches="tight")
    plt.close(fig)

    # 그린 숫자를 그대로 남긴다
    rows = []
    for pr, _ in ROWS:
        d = load(pr)
        if d is None:
            continue
        for col, _ in COLS:
            k = d.groupby(["sensor", "width_px"])[col].median().reset_index()
            k["principle"] = pr; k["measure"] = col
            rows.append(k.rename(columns={col: "mae_N"}))
    pd.concat(rows).to_csv(OUT / "fig2_force_vs_resolution.csv", index=False)
    print(f"  -> paper/figures/fig2_force_vs_resolution.{{png,pdf,csv}}")


if __name__ == "__main__":
    main()
