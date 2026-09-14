#!/usr/bin/env python3
"""Figure 2 — 논문의 핵심 결과. 행 = 감지 원리, 열 = (두께로 나눈 Fz·전단) +
(경도로 나눈 Fz·전단).

**무엇을 보이려는 그림인가.** 입력 해상도를 줄여 가며 힘 추정 오차가 어떻게
변하는지, 그리고 그 곡선이 **겔 설계에 따라 갈리는지**를 한눈에 놓는다. 겔 설계는
두께와 경도 둘이고, **둘을 나란히 놓아야** "어느 쪽도 곡선을 가르지 않는다" 는
주장이 그림으로 읽힌다 (2026-09-14, 운전자 지시).

**설계 원칙** (2026-09-13/14, 운전자 지시):

* 가는 선 = 시편 하나의 seed 중앙값 곡선. 굵은 선 = 그 시편 곡선들의 중앙값.
* 왼쪽 두 열은 **두께**로, 오른쪽 두 열은 **경도**로 색을 나눈다. 같은 자료를 두 번
  자른 것이므로 가는 선은 양쪽이 똑같고 굵은 선만 달라진다 — 그것이 요점이다.
* **불확실성 음영을 넣지 않는다.** seed 범위와 시편 간 범위를 같은 음영으로
  섞으면 읽는 사람이 둘을 구별하지 못한다. 가는 선이 시편 간 산포를 그대로
  보여주므로 음영이 필요 없다.
* **"48 px 면 충분" 같은 수직선을 크게 넣지 않는다.** 그것은 특정 허용오차에서
  얻은 요약이고, 기준을 바꾸면 움직인다. 평탄 구간은 축 아래의 작은 표식으로만
  가리킨다.
* y 축은 **같은 측정끼리** 공유한다(Fz 넷, 전단 넷). Fz 와 전단은 크기가 배 이상
  다르므로 여덟을 함께 묶으면 전단이 눌린다.
* y 축 이름에 **센서 이름을 괄호로** 적는다 — "Depth-referenced" 만으로는 어느
  하드웨어인지 독자가 짚지 못한다.

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

import pixel_density as PD
import result_common as RC
from palette import HARD3, THICK3

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
OUT = ROOT / "paper" / "figures"

ROWS = [("9DTact", "Depth-referenced\n(9DTact)"),
        ("DIGIT", "Photometric\n(DIGIT)"),
        ("DIGIT_Marker", "Photometric + marker\n(Marker)")]
MEAS = [("fz_mae", "Normal force, $F_z$"), ("shear", "Shear, mean $F_x$/$F_y$")]
# (나누는 변수, 열 이름, 색표, 범례 제목, 범례에 적을 이름)
GROUPS = [("thickness_mm", THICK3, "Gel thickness", lambda v: f"{v} mm"),
          ("hardness", HARD3, "Gel hardness", lambda v: v)]
# x 축은 **화소 밀도** R (px/mm^2) 다. 카메라의 총 픽셀 수가 같아도 유닛마다 보는
# 면적이 다르므로, 픽셀 폭을 쓰면 그 차이가 숨는다 (`pixel_density.py`).
XT = [0.1, 1, 10, 100, 1000, 10000]
XTL = ["0.1", "1", "10", "100", "1000", "10⁴"]


def load(pr, single=True):
    f = DS / pr / "force_vs_resolution_axes.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    d["shear"] = (d.fx_mae + d.fy_mae) / 2
    d["thickness_mm"] = d.sensor.str.extract(r"_(\d)mm_")[0].astype(int)
    d["hardness"] = d.sensor.str.extract(r"^(soft|medium|hard)_")[0]
    d = PD.add(d, pr)          # 유닛마다 제 시야로 환산한 R
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
    fig, axes = plt.subplots(len(ROWS), 4, figsize=(7.16, 6.4), sharex=True)

    ylim, handles = {}, {}
    for i, (pr, nice) in enumerate(ROWS):
        d = load(pr)
        if d is None:
            continue
        for j in range(4):
            gcol, cmap, gtitle, glab = GROUPS[j // 2]
            col, clab = MEAS[j % 2]
            ax = axes[i, j]
            # 가는 선 — 시편 하나의 seed 중앙값. **x 는 그 유닛 자신의 밀도.**
            # 같은 유닛이 두 나눔에 모두 나오므로 색만 바뀌고 선은 같다.
            for u, g in d.groupby("sensor"):
                k = g.groupby("density_px_per_mm2")[col].median().sort_index()
                ax.plot(k.index, k.values, "-", c=cmap[g[gcol].iloc[0]],
                        lw=.8, alpha=.45, zorder=2)
            # 굵은 선 — 군별 시편 중앙값. 유닛마다 x 가 다르므로 **원 해상도 단으로
            # 묶고 그 묶음의 중앙 밀도**에 찍는다.
            for v in cmap:
                g = d[d[gcol] == v]
                if not len(g):
                    continue
                per = g.groupby(["sensor", "width_px"])[col].median().unstack()
                med = per.median(axis=0)
                xs = g.groupby("width_px").density_px_per_mm2.median()
                xs = xs.reindex(med.index)
                ax.plot(xs.values, med.values, "-", c="white", lw=3.6,
                        alpha=.9, zorder=3)
                ln, = ax.plot(xs.values, med.values, "-", c=cmap[v], lw=2.0,
                              label=glab(v), zorder=4)
                handles.setdefault(j // 2, {}).setdefault(glab(v), ln)
            # 평탄 구간의 시작 — 축 아래 작은 표식으로만
            pl = plateau(d.groupby("width_px")[col].median())
            if pl:
                xp = float(d[d.width_px == pl].density_px_per_mm2.median())
                ax.plot([xp], [0], marker="^", ms=4.5, c="#1a1a1a",
                        clip_on=False, transform=ax.get_xaxis_transform(),
                        zorder=6)
            # y 는 선형이다(2026-09-14, 운전자 지시). 로그는 낮은 밀도의 붕괴와
            # 평탄 구간을 한 화면에 담지만, 평탄 구간 안의 군 간 차이를 눌러
            # "굵은 선 셋이 가는 선들의 산포 안에 있다" 를 읽기 어렵게 한다.
            ax.set_xscale("log")
            ax.set_xticks(XT); ax.set_xticklabels(XTL, fontsize=5.8)
            ax.xaxis.set_minor_locator(mticker.NullLocator())
            ax.tick_params(labelsize=6.5)
            ax.grid(True, which="major", alpha=.3, lw=.4, color="#b8b8b8")
            ax.set_axisbelow(True)
            ax.spines[["top", "right"]].set_visible(False)
            if i == 0:
                ax.set_title(clab, fontsize=7.5)
            if j == 0:
                ax.set_ylabel(f"{nice}\nMAE [N]", fontsize=7.5)
            # x 이름은 두 묶음의 가운데에 하나씩 — 아래 fig.text 가 그린다.
            ylim.setdefault(j % 2, []).append(ax.get_ylim())

    # y 축은 **같은 측정끼리** 공유한다 — Fz 넷, 전단 넷
    for m in (0, 1):
        hi = max(b for _, b in ylim.get(m, [(1, 1)]))
        # 선형 축은 0 에서 시작한다. 바닥을 잘라 올리면 군 간 차이가 실제보다
        # 커 보이는데, 이 그림의 요점이 바로 "그 차이가 작다" 는 것이다.
        for j in (m, m + 2):
            for i in range(len(ROWS)):
                ax = axes[i, j]
                ax.set_ylim(0, hi)
                ax.yaxis.set_major_locator(mticker.MaxNLocator(5))
                ax.tick_params(axis="y", labelleft=(j in (0, 2)), labelsize=6.5)

    # 두 나눔을 가르는 머리글 — 같은 색이 왼쪽에서는 두께, 오른쪽에서는 경도를
    # 뜻하므로 이 표시가 없으면 범례 둘이 충돌한다.
    for (x, txt) in ((.295, "Split by gel thickness"),
                     (.775, "Split by gel hardness")):
        fig.text(x, 1.005, txt, fontsize=8.5, weight="bold", ha="center")
        fig.text(x, .072, "Pixel density $R$ [px/mm$^2$]", fontsize=8,
                 ha="center")
    for g, x in ((0, .295), (1, .775)):
        h = handles.get(g, {})
        if h:
            fig.legend(h.values(), h.keys(), frameon=False, fontsize=7.5,
                       title=GROUPS[g][2], title_fontsize=7.5, ncol=3,
                       loc="lower center", bbox_to_anchor=(x, -.012))
    fig.tight_layout(rect=[0, .085, 1, .985])
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
        for col, _ in MEAS:
            k = (d.groupby(["sensor", "hardness", "thickness_mm", "width_px",
                            "density_px_per_mm2"])[col].median().reset_index())
            k["principle"] = pr; k["measure"] = col
            rows.append(k.rename(columns={col: "mae_N"}))
    pd.concat(rows).to_csv(OUT / "fig2_force_vs_resolution.csv", index=False)
    print("  -> paper/figures/fig2_force_vs_resolution.{png,pdf,csv}")


if __name__ == "__main__":
    main()
