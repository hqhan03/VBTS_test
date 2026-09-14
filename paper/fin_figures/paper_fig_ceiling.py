#!/usr/bin/env python3
"""논문 그림 — 영상 응답 포화 힘(천장) 대 겔 두께, 경도별. (IV.C)

이 그림이 말하는 것은 **부호가 뒤집힌다**는 것이다. 9DTact 는 두께를 따라 오르고
DIGIT 은 내려간다. 한쪽만 그리면 그 관찰이 사라지므로 둘을 나란히 놓는다.

**DIGIT_Marker 는 뺐다** (운전자 결정, 2026-09-15). 마커 유닛에는 `ball8` 램프가
없어 `ball4` 로 잰 값이고, 힘은 프로브 사이에서 환산되지 않으므로(비 1.50 ~ 3.26,
CV 21 % — 부록 C) 애초에 나머지 둘과 세로로 견줄 수 없는 패널이었다. 값은
`fig_ceiling_stats.csv` 와 `B_ceiling_vs_thickness.csv` 에 그대로 있다
(두께 ρ −0.53, p 0.145).

세로 축을 묶지 않는다
    9DTact 가 63 N 까지 가는데 DIGIT 계열은 6 ~ 23 N 이다. 축을 묶으면 DIGIT 과
    Marker 의 기울기가 아래에 눌려 보이지 않는다. 대신 **칸마다 y 라벨과 눈금을
    달아** 축이 따로라는 것이 눈에 보이게 한다.

세로로 견주면 안 되는 값이다
    (1) 판정 문턱이 **그 유닛 자신의 최대 응답의 15 %** 인 상대 기준이라 응답이
        약한 유닛일수록 천장이 높게 나온다(부록 A). 한 유닛의 운용 한계로만 쓴다.
    (2) Marker 는 `ball8` 램프가 없어 `ball4` 로 쟀다. 힘은 프로브 사이에서
        환산되지 않는다(비 1.50 ~ 3.26, CV 21 % — 부록 C).
    그래서 **한 원리 안에서의 두께·경도 방향**만 읽는 그림이다.

칸마다 정해진 센서 하나만 쓴다
    운전자 결정(2026-09-14, `CLAUDE.md` §1). 칸마다 복제를 둘씩 만들었지만
    **고른 시편 하나**만 분석하고 그린다 — 원리당 9, 합 27. 고르는 것은
    `result_common.chosen()` 이고(확정 불량 → 독립 증거 → 파괴 → 그 밖에는 r1),
    고르지 않은 복제는 **그림에 겹쳐 찍지 않는다.**

    그래서 이 그림에는 오차 막대가 없다 — 칸마다 점이 하나다. **선을 정밀한
    것으로 읽으면 안 된다.** 제작 간 산포(9DTact Fz 요구 밀도가 복제 쌍 안에서
    중앙 6.7 배)는 54 유닛 집합에서만 나오므로 **한계 절의 숫자로** 인용한다.

    선택 규칙이 빛 누출 유닛을 이미 걸렀으므로 이 집합에는 의심 유닛이 없다
    (`suspect_hardware` 전부 False). 표식을 따로 두지 않는다.

표식은 전부 동그라미다 (운전자 결정, 2026-09-15)
    경도는 **색만으로** 갈린다. 팔레트가 색각 검증을 통과하므로(인접 쌍 최악
    ΔE 11.0 deutan) 색각 이상에서는 읽히고, 남는 위험은 **흑백 인쇄**다.

캡션이 져야 할 것
    1. **어느 패널이 무엇인가** — 제목의 `(a)` `(b)` `(c)` 와 원리 이름.
    2. **세로 축이 패널마다 다르고 값을 가로로 견주면 안 된다**는 것
       (상대 기준 + Marker 는 프로브가 다름).
    3. **두께 경향** — 9DTact ρ +0.63 (p 0.068) 대 DIGIT −0.90 (p 0.001),
       Marker −0.53 (p 0.145). 그림에서 뺐고 `fig_ceiling_stats.csv` 에 있다.
       경도는 세 원리 모두 비유의(+0.37 / +0.05 / −0.11).

자료
    `result/single/extra/data/B_ceiling_vs_thickness.csv`  (분석 집합 27)
"""
from itertools import combinations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from matplotlib.lines import Line2D

import paper_style as PS
from paper_style import HARD3, SHORE, DISPLAY

PS.use_paper_style()                      # rcParams 를 pyplot 을 쓰기 전에 건다
import matplotlib.pyplot as plt           # noqa: E402

HARDNESS = ("soft", "medium", "hard")
# DIGIT_Marker 는 뺀다 (운전자 결정, 2026-09-15). 애초에 `ball8` 램프가 없어
# `ball4` 로 잰 값이라 나머지 둘과 세로로 견줄 수 없는 패널이었다.
PRINCIPLES = ("9DTact", "DIGIT")
DODGE = dict(zip(HARDNESS, (-0.055, 0.0, 0.055)))   # 정해진 어긋냄 — 난수 흔들기가 아니다


def exact_p(th, y):
    """두께 라벨을 바꿔 달아 보는 정확 순열 검정.

    n = 9 에 수준이 셋이라 점근 p 를 믿기 어렵다. 값을 세 칸에 나눠 담는 서로 다른
    방법이 9!/(3!)³ = 1 680 가지뿐이므로 **전부 세어** 정확 p 를 낸다.
    본문의 다른 절이 쓰는 `spearmanr` 의 p 도 함께 내어 캡션에 어느 쪽을 적을지
    고를 수 있게 한다.
    """
    y = np.asarray(y, float)
    rho0 = spearmanr(th, y).statistic
    idx, hit, n = range(len(y)), 0, 0
    for a in combinations(idx, 3):
        rest = [i for i in idx if i not in a]
        for b in combinations(rest, 3):
            c = [i for i in rest if i not in b]
            lab = np.empty(len(y))
            lab[list(a)], lab[list(b)], lab[c] = 1, 2, 3
            n += 1
            if abs(spearmanr(lab, y).statistic) >= abs(rho0) - 1e-12:
                hit += 1
    return rho0, hit / n


def main():
    single = pd.read_csv(PS.ROOT / "result/single/extra/data/B_ceiling_vs_thickness.csv")
    assert not single.suspect_hardware.any(), "선택 규칙이 거른 유닛이 남아 있다"

    fig, axes = plt.subplots(1, len(PRINCIPLES),
                             figsize=(PS.FULL_W_NARROW, 2.70))
    stats = []

    for tag, ax, pr in zip("abc", axes, PRINCIPLES):
        one = single[single.principle == pr]

        for h in HARDNESS:
            col, dx = HARD3[h], DODGE[h]
            g = one[one.hardness == h].sort_values("thickness_mm")
            ax.plot(g.thickness_mm + dx, g.ceiling_N, "-", c=col, lw=1.4, zorder=3)
            ax.plot(g.thickness_mm + dx, g.ceiling_N, "o", c=col,
                    ms=5.6, mec="white", mew=0.7, ls="none", zorder=4)


        rho, p_ex = exact_p(one.thickness_mm.values, one.ceiling_N.values)
        p_as = spearmanr(one.thickness_mm, one.ceiling_N).pvalue
        rho_h, p_h = spearmanr(
            one.hardness.map({h: i for i, h in enumerate(HARDNESS)}), one.ceiling_N)
        stats.append(dict(principle=pr, rho_thickness=rho, p_exact=p_ex,
                          p_asymptotic=p_as, rho_hardness=rho_h, p_hardness=p_h,
                          n_units=len(one)))

        sh = SHORE[pr]
        probe = one.probe.iloc[0]
        ax.set_title(f"({tag})  {DISPLAY[pr]}", loc="left", pad=13)
        ax.annotate(f"{probe}  ·  Shore OO {sh['soft']}/{sh['medium']}/{sh['hard']}",
                    xy=(0, 1.015), xycoords="axes fraction",
                    fontsize=9.0, color=PS.MUTED)
        ax.set_xticks([1, 2, 3])
        ax.set_xlim(0.72, 3.46)
        ax.set_ylim(0, None)
        ax.set_xlabel("gel thickness [mm]")
        ax.set_ylabel("image saturation force [N]")
        PS.style(ax)

    fig.tight_layout(w_pad=1.3, rect=[0, 0.075, 1, 1])
    hs = [Line2D([], [], color=HARD3[h], marker="o", ms=5.6, lw=1.8,
                 mec="white", mew=0.7, label=h) for h in HARDNESS]
    fig.legend(handles=hs, loc="lower center", ncol=3, frameon=False,
               handlelength=1.8, columnspacing=2.0,
               handletextpad=0.5, bbox_to_anchor=(0.5, -0.008))
    out = single[single.principle.isin(PRINCIPLES)][
        ["principle", "probe", "unit", "hardness", "thickness_mm", "ceiling_N"]]
    PS.save(fig, out, "fig_ceiling")

    st = pd.DataFrame(stats)
    st.to_csv(PS.FIGS / "fig_ceiling_stats.csv", index=False)
    print(st.to_string(index=False))


if __name__ == "__main__":
    main()
