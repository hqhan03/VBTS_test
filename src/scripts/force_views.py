#!/usr/bin/env python3
"""같은 학습을 세 가지로 묶어 본다 — 축별 · 블록별 · 합력.

**왜 셋인가** (2026-09-15, 운전자 요청). 하나의 학습이 프레임마다 여섯 수를
낸다. 그것을 어떻게 묶느냐가 "이 센서가 얼마나 정확한가" 의 답을 바꾼다.

* **축별** Fx · Fy · Fz — 방향마다 다른지 본다. 합치면 사라지는 것이 있다.
* **블록별** 수직 블록의 Fz, 전단 블록의 횡력 크기 — **시험 프레임을 나눠**
  잰다. 수직 블록에서 전단 라벨은 마찰 잡음(0 ~ 0.05 N)이라 어떤 모형이든
  0 에 가깝게 맞춘다. 그것을 전단 블록과 섞으면 전단 오차가 절반으로 보이고
  해상도 의존성까지 묽어진다.
* **합력** ‖F_pred − F_true‖ — 센서를 쓰는 쪽이 실제로 겪는 하나의 수.

**세 보기는 같은 자료다.** 다른 학습이 아니라 같은 예측을 다르게 센 것이다.
그래서 서로 어긋나면 그것은 센서가 아니라 **무엇을 세느냐**의 문제다.

만드는 것: `docs/figures/force_views.png` · 자료 `docs/figures/force_views.csv`
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
from palette import CAT3

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
OUT = ROOT / "docs" / "figures"
PRS = [("9DTact", "Depth-referenced\n(9DTact)"),
       ("DIGIT", "Photometric\n(DIGIT)"),
       ("DIGIT_Marker", "Photometric + marker")]
# (열 제목, [(열이름, 범례, 색)])
VIEWS = [
    ("① 축별  Fx · Fy · Fz",
     [("fx_mae", "Fx", CAT3[0]), ("fy_mae", "Fy", CAT3[1]),
      ("fz_mae", "Fz", CAT3[2])]),
    ("② 블록별  수직 · 전단",
     [("fz_mae_normal", "Fz (수직 블록)", CAT3[2]),
      ("lat_mae_shear", "|Fxy| (전단 블록)", CAT3[0])]),
    ("③ 합력  ‖ΔF‖",
     [("res_mae", "합력 (실측)", "#1a1a1a")]),
]
XT = [0.1, 1, 10, 100, 1000, 10000]
XTL = ["0.1", "1", "10", "100", "1000", "10⁴"]


def load(pr):
    f = DS / pr / "force_vs_resolution_res.csv"
    if not f.exists():
        return None
    d = RC.keep(pd.read_csv(f), pr, "sensor")
    d = d[d.sensor.isin(RC.chosen(pr))]
    return PD.add(d, pr) if len(d) else None


def main():
    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    fig, axes = plt.subplots(len(PRS), 3, figsize=(10.2, 7.6), sharex=True)
    rows, hi = [], 0.0
    for i, (pr, nice) in enumerate(PRS):
        d = load(pr)
        if d is None:
            continue
        for j, (title, cols) in enumerate(VIEWS):
            ax = axes[i][j]
            for col, lab, c in cols:
                if col not in d:
                    continue
                # 가는 선 = 시편 하나(seed 중앙), 굵은 선 = 사다리 단으로 묶은 중앙
                for u, g in d.groupby("sensor"):
                    k = g.groupby("density_px_per_mm2")[col].median().sort_index()
                    ax.plot(k.index, k.values, "-", c=c, lw=.7, alpha=.35, zorder=2)
                m = (d.groupby("width_px")
                       .agg(v=(col, "median"),
                            R=("density_px_per_mm2", "median"))
                       .dropna().sort_values("R"))
                ax.plot(m.R, m.v, "-", c="white", lw=3.4, alpha=.9, zorder=3)
                ax.plot(m.R, m.v, "-o", c=c, lw=2.0, ms=4, mec="white", mew=.6,
                        label=lab, zorder=4)
                hi = max(hi, float(m.v.max()))
                rows.append(m.assign(principle=pr, view=j + 1, metric=col)
                             .reset_index())
            ax.set_xscale("log")
            ax.set_xticks(XT); ax.set_xticklabels(XTL, fontsize=6.5)
            ax.xaxis.set_minor_locator(mticker.NullLocator())
            ax.tick_params(labelsize=7)
            ax.grid(alpha=.3, lw=.4); ax.set_axisbelow(True)
            ax.spines[["top", "right"]].set_visible(False)
            ax.legend(frameon=False, fontsize=7, loc="upper right")
            if i == 0:
                ax.set_title(title, fontsize=9.5)
            if j == 0:
                ax.set_ylabel(f"{nice}\nMAE (N)", fontsize=8)
            if i == len(PRS) - 1:
                ax.set_xlabel("화소 밀도 R (px/mm²)", fontsize=8.5)
    # **세 열이 같은 세로 눈금을 쓴다.** 합력이 축별보다 큰 것은 당연한데,
    # 축을 따로 잡으면 그 당연한 사실이 그림에서 사라진다.
    for ax in axes.ravel():
        ax.set_ylim(0, hi * 1.08)
    fig.tight_layout()
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / "force_views.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    D = pd.concat(rows)
    D.to_csv(OUT / "force_views.csv", index=False)
    print("  -> docs/figures/force_views.png")
    p = D.pivot_table(index="principle", columns="metric", values="v",
                      aggfunc="median")
    print(p.round(4).to_string())


if __name__ == "__main__":
    main()
