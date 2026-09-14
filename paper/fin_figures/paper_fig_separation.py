#!/usr/bin/env python3
"""논문 그림 — 두 접촉 분리는 겔 두께를 따라간다. (IV.B)

전해상도에서 두 기둥(⌀1.0 mm)을 여러 간격으로 눌러, 골이 보이는지 판정한다.
세 관문을 모두 넘어야 *분해*다 — dip ≥ 0.265 (Rayleigh), 자국 ≥ 2.5 그레이 레벨,
dip > 잡음의 3 배.

광도 스테레오는 점으로 찍지 않는다
    여덟 시편 **모두** 가장 좁은 압자(중심 간격 1.10 mm)를 갈랐다. **값이 아니라
    바닥이다** — 점을 찍으면 "1.10 mm 가 그 센서의 분해능" 으로 읽힌다. 띠와
    한 줄로 적는다. 광도의 `hard_2mm` 는 두 기둥 램프가 없어 여덟이다.

화소 밀도 패널은 뺐다 (운전자 결정, 2026-09-15)
    같은 판정을 12 단으로 줄인 스윕을 (b) 로 붙였다가 뺐다. 되살린다면 그때의
    규칙이 그대로 적용된다 — 판정을 셋으로 가를 것(분해 / 접촉은 찾았으나 못
    가름 / 접촉 검출 실패), **"두 점을 가르는 데 R ≈ 387 px/mm² 가 든다" 를 쓰지
    말 것**(387 은 분해 비율이 최대였던 밀도이고 힘·형상의 10 % 평탄 기준과 다른
    자다), 그것을 힘·형상 밀도와 나눈 배수도 말하지 말 것.
    자료는 `result/single/extra/data/H_resolution_sweep.csv` 에 그대로 있다.

칸마다 정해진 센서 하나 (`CLAUDE.md` §1)

자료
    `result/single/extra/data/G_spatial_resolution.csv`
"""
import pandas as pd
from scipy.stats import spearmanr

import paper_style as PS
from paper_style import HARD3, MARKER, DISPLAY

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402

HARDNESS = ("soft", "medium", "hard")
DODGE = dict(zip(HARDNESS, (-0.055, 0.0, 0.055)))
NARROWEST_MM = 1.10                       # 우리가 만든 가장 좁은 압자 (중심 간격)


def main():
    d = pd.read_csv(PS.ROOT / "result/single/extra/data/G_spatial_resolution.csv")
    assert not d.suspect_hardware.any(), "선택 규칙이 거른 유닛이 남아 있다"
    nine, digit = d[d.principle == "9DTact"], d[d.principle == "DIGIT"]
    assert (digit.finest_centre_mm == NARROWEST_MM).all()

    fig, ax = plt.subplots(figsize=(PS.COL_W, 2.45))

    ax.axhspan(0.86, NARROWEST_MM, color="#eeeeee", lw=0, zorder=0)
    ax.axhline(NARROWEST_MM, c=PS.MUTED, lw=0.7, ls=(0, (4, 2)), zorder=1)
    ax.annotate(f"narrowest probe {NARROWEST_MM:.2f} mm  —  "
                f"{DISPLAY['DIGIT']} {len(digit)}/{len(digit)}",
                xy=(0.985, 0.012), xycoords="axes fraction", ha="right",
                va="bottom", fontsize=6.0, color=PS.MUTED)

    for h in HARDNESS:
        g = nine[nine.hardness == h].sort_values("thickness_mm")
        ax.plot(g.thickness_mm + DODGE[h], g.finest_centre_mm, "-",
                c=HARD3[h], lw=1.4, label=h, zorder=3)
        ax.plot(g.thickness_mm + DODGE[h], g.finest_centre_mm, MARKER[h],
                c=HARD3[h], ms=4.4, mec="white", mew=0.7, ls="none", zorder=4)

    rho, p = spearmanr(nine.thickness_mm, nine.finest_centre_mm)
    rho_h, p_h = spearmanr(
        nine.hardness.map({h: i for i, h in enumerate(HARDNESS)}),
        nine.finest_centre_mm)
    ax.annotate(rf"$\rho_{{\rm thickness}}$ = {rho:+.2f}  (p = {p:.2f}, n = {len(nine)})",
                xy=(0.985, 0.955), xycoords="axes fraction", ha="right",
                va="top", fontsize=6.5, color=PS.MUTED)

    ax.legend(loc="upper left", frameon=False, fontsize=6.8, handlelength=1.7,
              handletextpad=0.5, labelspacing=0.32, borderpad=0.1)
    ax.set_xticks([1, 2, 3])
    ax.set_xlim(0.72, 3.30)
    ax.set_ylim(0.86, 2.98)
    ax.set_xlabel("gel thickness [mm]")
    ax.set_ylabel("finest resolved separation [mm]")
    ax.set_title(f"{DISPLAY['9DTact']}, full resolution", fontsize=8.0, loc="left")
    PS.style(ax)

    fig.tight_layout(pad=0.3)
    PS.save(fig, nine[["principle", "unit", "hardness", "thickness_mm",
                       "finest_centre_mm", "depth_lo_mm", "depth_hi_mm",
                       "n_gaps_resolved", "n_gaps_tested"]], "fig_separation")
    print(f"  두께 rho {rho:+.3f}  p {p:.3f}   경도 rho {rho_h:+.3f}  p {p_h:.3f}"
          f"   n {len(nine)}   (광도 {len(digit)} 시편 전부 바닥)")


if __name__ == "__main__":
    main()
