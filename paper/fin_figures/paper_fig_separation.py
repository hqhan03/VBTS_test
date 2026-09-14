#!/usr/bin/env python3
"""논문 그림 — 두 접촉 분리: 겔이 정하는 것과 화소가 정하는 것. (IV.B)

두 패널이 **서로 다른 질문**이다.

(a) 겔  — 두 기둥을 얼마나 가까이 붙여도 갈리는가. 전해상도에서 잰다.
(b) 화소 — 그 판정에 화소가 몇 개 드는가. 판정을 그대로 두고 입력만 줄인다.

(b) 는 힘·형상과 **같은 x 축**(화소 밀도 R)에 두 접촉 판정을 올리는 자리다.

판정을 세 갈래로 가른다
    낮은 밀도에서 "못 갈랐다" 에는 두 가지가 섞여 있다 — 골이 얕아 못 가른 것과
    **접촉 덩어리 자체를 못 찾은 것**. 둘은 다른 실패다. `resolved_pct` 와
    `contact_lost_pct` 를 쌓아 셋으로 가른다.

말하지 않는 것
    **"두 점을 가르는 데 R ≈ 387 px/mm² 가 든다" 를 쓰지 않는다.** 387 은 분해
    비율이 최대였던 밀도이고, 힘·형상에서 쓴 10 % 평탄 기준과 다른 자다. 같은
    기준을 세우기 전에는 그 둘을 나눈 배수도 말하지 않는다.

    **살아 있는 비교는 하나다** — 같은 기준 안에서 **전해상도가 손해**라는 것.
    R ≈ 7862 의 분해 비율 44 % 가 R ≈ 387 의 70 % 보다 낮다. 골이 얕아지는 것이
    아니라(0.384 대 0.472) 화소당 잡음이 5 배여서(0.109 대 0.023) "골 > 잡음
    3 배" 관문이 걸린다.

칸마다 정해진 센서 하나 (`CLAUDE.md` §1)
    (a) 는 깊이 참조형 9 시편과 광도 스테레오 **8** 시편이다 — 광도의
    `hard_2mm` 는 두 기둥 램프가 없다. 그림에 8 이라고 적는다.

자료
    (a) `result/single/extra/data/G_spatial_resolution.csv`
    (b) `result/single/extra/data/H_resolution_sweep.csv`
        (깊이 참조형, 기둥 ⌀1.0 mm, 중심 간격 2.00 mm, 9 시편의 사다리 27 단)
"""
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
from scipy.stats import spearmanr

import paper_style as PS
from paper_style import HARD3, MARKER, DISPLAY

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402

HARDNESS = ("soft", "medium", "hard")
DODGE = dict(zip(HARDNESS, (-0.055, 0.0, 0.055)))
NARROWEST_MM = 1.10                       # 우리가 만든 가장 좁은 압자 (중심 간격)

# 판정 셋. 분해는 그 원리의 색으로, 두 실패는 회색 두 단계로 — (a) 의 경도 색과
# 같은 색이 다른 뜻으로 쓰이면 안 된다. 빗금을 넣어 봤더니 실패 범주가 그림에서
# 제일 크게 보였다(2026-09-15). 눈이 먼저 가는 곳은 분해된 쪽이어야 한다.
OUTCOME = [("resolved_pct", "two contacts resolved", PS.PRINCIPLE["9DTact"]),
           ("merged_pct", "contact found, not separated", "#c0c0c0"),
           ("contact_lost_pct", "contact not detected", "#ededed")]


def panel_gel(ax):
    """분해된 가장 좁은 간격 대 두께."""
    d = pd.read_csv(PS.ROOT / "result/single/extra/data/G_spatial_resolution.csv")
    assert not d.suspect_hardware.any(), "선택 규칙이 거른 유닛이 남아 있다"
    nine, digit = d[d.principle == "9DTact"], d[d.principle == "DIGIT"]

    # 광도 스테레오는 여덟 시편 **모두** 가장 좁은 압자를 갈랐다. 값이 아니라
    # 바닥이므로 점으로 찍지 않는다 — 점을 찍으면 "1.10 mm 가 그 센서의 분해능"
    # 으로 읽힌다. 띠와 한 줄로 적는다.
    assert (digit.finest_centre_mm == NARROWEST_MM).all()
    ax.axhspan(0.88, NARROWEST_MM, color="#eeeeee", lw=0, zorder=0)
    ax.axhline(NARROWEST_MM, c=PS.MUTED, lw=0.7, ls=(0, (4, 2)), zorder=1)
    ax.annotate(f"narrowest probe built: {NARROWEST_MM:.2f} mm\n"
                f"{DISPLAY['DIGIT']} resolved it on {len(digit)}/{len(digit)} "
                "specimens,\nso its limit was never reached",
                xy=(0.025, 0.975), xycoords="axes fraction", va="top",
                ha="left", fontsize=6.0, color=PS.MUTED, linespacing=1.45)

    for h in HARDNESS:
        g = nine[nine.hardness == h].sort_values("thickness_mm")
        ax.plot(g.thickness_mm + DODGE[h], g.finest_centre_mm, "-",
                c=HARD3[h], lw=1.4, zorder=3)
        ax.plot(g.thickness_mm + DODGE[h], g.finest_centre_mm, MARKER[h],
                c=HARD3[h], ms=4.4, mec="white", mew=0.7, ls="none", zorder=4)

    rho, p = spearmanr(nine.thickness_mm, nine.finest_centre_mm)
    ax.annotate(rf"$\rho_{{\rm thickness}}$ = {rho:+.2f}   (p = {p:.2f},  n = {len(nine)})",
                xy=(0.97, 0.035), xycoords="axes fraction", ha="right",
                fontsize=6.5, color=PS.MUTED)

    ax.set_xticks([1, 2, 3])
    ax.set_xlim(0.72, 3.30)
    ax.set_ylim(0.88, 2.78)
    ax.set_xlabel("gel thickness [mm]")
    ax.set_ylabel("finest resolved separation [mm]")
    ax.set_title(f"(a)  gel  —  {DISPLAY['9DTact']}, full resolution",
                 fontsize=8.0, loc="left")
    PS.style(ax)
    return nine.assign(rho_thickness=rho, p_thickness=p), rho, p


def panel_pixels(ax):
    """판정 결과의 구성 대 화소 밀도 — 셋으로 가른다."""
    d = pd.read_csv(PS.ROOT / "result/single/extra/data/H_resolution_sweep.csv")
    d["merged_pct"] = 100 - d.resolved_pct - d.contact_lost_pct
    assert (d.merged_pct >= -1e-9).all(), "세 갈래가 100 % 를 넘는다"

    x, base = d.density_px_per_mm2.values, np.zeros(len(d))
    for col, _, c in OUTCOME:
        top = base + d[col].values
        ax.fill_between(x, base, top, step="mid", fc=c, lw=0, zorder=2)
        base = top
    ax.plot(x, d.resolved_pct, "o", c=PS.PRINCIPLE["9DTact"], ms=2.6,
            mec="white", mew=0.5, ls="none", zorder=4)

    best = d.loc[d.resolved_pct.idxmax()]
    full = d.iloc[-1]
    for r, lab, ha, dx in ((best, "best", "right", -4), (full, "full res.", "left", 4)):
        ax.annotate(f"{lab}  {r.resolved_pct:.0f} %\nR = {r.density_px_per_mm2:,.0f}",
                    xy=(r.density_px_per_mm2, r.resolved_pct),
                    xytext=(dx, 9), textcoords="offset points",
                    ha=ha, va="bottom", fontsize=6.0, color=PS.INK,
                    linespacing=1.4, zorder=6,
                    arrowprops=dict(arrowstyle="-", lw=0.5, color=PS.INK,
                                    shrinkA=1, shrinkB=2.5))

    ax.set_xscale("log")
    ax.set_xlim(0.09, 1.4e4)
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlabel(r"pixel density $R$ [px/mm$^2$]")
    ax.set_ylabel("ladder steps [%]")
    ax.set_title("(b)  pixels  —  same decision, input downscaled",
                 fontsize=8.0, loc="left")
    PS.style(ax, grid=None)
    ax.grid(axis="y", alpha=0.22, lw=0.4, color="#ffffff", zorder=3)
    return d


def main():
    fig, axes = plt.subplots(1, 2, figsize=(PS.FULL_W, 2.55))
    gel, rho, p = panel_gel(axes[0])
    px = panel_pixels(axes[1])

    fig.tight_layout(w_pad=2.0, rect=[0, 0.095, 1, 0.965])
    hard = [Line2D([], [], color=HARD3[h], marker=MARKER[h], ms=4.4, lw=1.4,
                   mec="white", mew=0.7, label=h) for h in HARDNESS]
    out = [Patch(fc=c, ec="#9a9a9a", lw=0.4, label=lab)
           for _, lab, c in OUTCOME]
    fig.legend(handles=hard, loc="lower left", ncol=3, frameon=False,
               fontsize=6.8, handlelength=1.8, columnspacing=1.4,
               handletextpad=0.5, bbox_to_anchor=(0.045, -0.012))
    fig.legend(handles=out, loc="lower left", ncol=3, frameon=False,
               fontsize=6.8, handlelength=1.5, columnspacing=1.2,
               handletextpad=0.5, bbox_to_anchor=(0.325, -0.012))

    PS.save(fig, gel[["principle", "unit", "hardness", "thickness_mm",
                      "finest_centre_mm", "depth_lo_mm", "depth_hi_mm",
                      "n_gaps_resolved", "n_gaps_tested"]], "fig_separation")
    px[["width_px", "density_px_per_mm2", "resolved_pct", "merged_pct",
        "contact_lost_pct", "median_dip", "median_dip_sd",
        "median_imprint_lvl"]].to_csv(PS.FIGS / "fig_separation_sweep.csv",
                                      index=False)
    print(f"  (a) 두께 rho {rho:+.3f}  p {p:.3f}  n {len(gel)}")
    print(f"  (b) 최대 분해 {px.resolved_pct.max():.1f} % "
          f"@ R {px.loc[px.resolved_pct.idxmax()].density_px_per_mm2:,.0f}"
          f"  ·  전해상도 {px.iloc[-1].resolved_pct:.1f} %")


if __name__ == "__main__":
    main()
