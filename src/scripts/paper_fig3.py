#!/usr/bin/env python3
"""Figure 3 — 겔 효과와 반복성, 그리고 허용오차 민감도.

**왜 p 값 대신 이 그림인가** (2026-09-13, 운전자 지시). "겔과 무관하다" 를 p 값
나열로 주장하면 독자는 검정을 믿거나 말거나 할 수밖에 없다. 대신 **겔 조건 간
변화와 같은 조건 안의 편차를 같은 축에 놓으면** 독자가 직접 견준다 — 복제 둘이
서로 떨어진 거리가 두께 셋이 벌어진 거리만 하다면, 그것이 답이다.

* x = 두께, y = 포화 해상도(로그), 색 = 경도.
* 같은 조건의 r1·r2 를 점 두 개와 잇는 선으로 — **복제 쌍이 얼마나 벌어지는지**
  가 이 그림의 절반이다.
* 알려진 결함(빛 누출)은 **다른 표식**으로 구분한다. 지우지 않는다.

오른쪽의 작은 표는 **허용오차를 바꾸면 포화 해상도가 어떻게 움직이는지**다.
평탄 구간의 시작은 "최솟값의 x % 안" 이라는 임의의 기준에서 나오므로, 그 기준에
얼마나 민감한지를 숨기지 않고 함께 싣는다.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

import result_common as RC
from palette import HARD3

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
OUT = ROOT / "paper" / "figures"
ROWS = [("9DTact", "Depth-referenced"), ("DIGIT", "Photometric")]
COLS = [("fz_mae", "$F_z$"), ("shear", "Shear")]
TOL = [1.05, 1.10, 1.20]
HARD = ["soft", "medium", "hard"]


def load(pr):
    f = DS / pr / "force_vs_resolution_axes.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    d["shear"] = (d.fx_mae + d.fy_mae) / 2
    d["hardness"] = d.sensor.str.split("_").str[0]
    d["thickness_mm"] = d.sensor.str.extract(r"_(\d)mm_")[0].astype(int)
    d["rep"] = d.sensor.str[-1].astype(int)
    return d


def load_single(pr):
    """시편 9 개(복제 선택 규칙)만. 민감도 표는 이 집합으로 낸다."""
    d = load(pr)
    return None if d is None else d[d.sensor.isin(RC.chosen(pr))]


def sat(v, tol):
    """포화 해상도 — 최솟값의 tol 배 안에 드는 가장 낮은 입력 폭."""
    v = v.dropna()
    return float(v.index[v <= v.min() * tol].min()) if len(v) >= 4 else np.nan


def main():
    plt.rcParams["font.family"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(2, 2, figsize=(7.16, 5.0), sharex=True, sharey=True)
    rows_out, tol_rows = [], []

    for i, (pr, nice) in enumerate(ROWS):
        d = load(pr)
        if d is None:
            continue
        for j, (col, clab) in enumerate(COLS):
            ax = axes[i, j]
            per = {}
            for u, g in d.groupby("sensor"):
                k = g.groupby("width_px")[col].median()
                per[u] = sat(k, 1.10)
            for h in HARD:
                for t in (1, 2, 3):
                    us = sorted(u for u in per
                                if u.startswith(f"{h}_{t}mm_r"))
                    pts = [(u, per[u]) for u in us if np.isfinite(per[u])]
                    if not pts:
                        continue
                    xs = t + (HARD.index(h) - 1) * .13
                    if len(pts) == 2:
                        ax.plot([xs, xs], [pts[0][1], pts[1][1]], "-",
                                c=HARD3[h], lw=1.0, alpha=.75, zorder=2)
                    for u, y in pts:
                        bad = RC.is_suspect(pr, u)
                        ax.plot([xs], [y], marker="s" if bad else "o",
                                ms=6.5 if bad else 5.0,
                                mfc="none" if bad else HARD3[h],
                                mec="#1a1a1a" if bad else "white",
                                mew=1.4 if bad else .7, zorder=4)
                        rows_out.append(dict(principle=pr, measure=col, unit=u,
                                             hardness=h, thickness_mm=t,
                                             saturation_px=y,
                                             suspect_hardware=bad))
            ax.set_yscale("log")
            ax.set_yticks([16, 32, 48, 80, 160, 320, 640])
            ax.set_yticklabels(["16", "32", "48", "80", "160", "320", "640"],
                               fontsize=7)
            ax.yaxis.set_minor_locator(mticker.NullLocator())
            ax.set_xticks([1, 2, 3]); ax.set_xlim(.6, 3.4)
            ax.tick_params(labelsize=7)
            ax.grid(alpha=.3, lw=.4, which="major")
            ax.set_axisbelow(True)
            ax.spines[["top", "right"]].set_visible(False)
            if i == 0:
                ax.set_title(clab, fontsize=9)
            if j == 0:
                ax.set_ylabel(f"{nice}\nSaturation width [px]", fontsize=8.5)
            if i == 1:
                ax.set_xlabel("Gel thickness [mm]", fontsize=8.5)
            # 허용오차 민감도
            # **민감도는 두 가지로 낸다.** 하나는 시편을 합친 중앙 곡선의
            # 포화점, 다른 하나는 시편별 포화점의 중앙값이다. 둘은 같은 수가
            # 아니고, 어느 쪽을 쓰는지 밝히지 않으면 표가 재현되지 않는다.
            ds = load_single(pr)
            for tol in TOL:
                kk = ds.groupby("width_px")[col].median()
                each = [sat(g.groupby("width_px")[col].median(), tol)
                        for _, g in ds.groupby("sensor")]
                tol_rows.append(dict(
                    principle=pr, measure=col,
                    tol_pct=int(round((tol - 1) * 100)),
                    sat_of_median_px=sat(kk, tol),
                    median_of_sat_px=float(np.nanmedian(each))))

    hh = [plt.Line2D([], [], marker="o", ls="", mfc=HARD3[h], mec="white",
                     ms=5.5, label=h) for h in HARD]
    hh.append(plt.Line2D([], [], marker="s", ls="", mfc="none", mec="#1a1a1a",
                         mew=1.4, ms=6.5, label="known defect"))
    fig.legend(handles=hh, frameon=False, fontsize=7.5, ncol=4,
               loc="lower center", bbox_to_anchor=(.55, -.015))
    fig.tight_layout(rect=[0, .05, 1, 1])
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig3_gel_and_repeatability.{ext}", dpi=300,
                    bbox_inches="tight")
    plt.close(fig)

    pd.DataFrame(rows_out).to_csv(OUT / "fig3_saturation_by_unit.csv",
                                  index=False)
    T = pd.DataFrame(tol_rows).drop_duplicates()
    T.to_csv(OUT / "fig3_tolerance_sensitivity.csv", index=False)
    print("  -> paper/figures/fig3_gel_and_repeatability.{png,pdf}")
    print("  허용오차 민감도 (입력 폭 px):")
    for v in ("sat_of_median_px", "median_of_sat_px"):
        print(f"   [{v}]")
        print(T.pivot_table(index=["principle", "measure"], columns="tol_pct",
                            values=v).to_string())


if __name__ == "__main__":
    main()
