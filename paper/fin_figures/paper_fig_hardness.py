#!/usr/bin/env python3
"""논문 그림 — 두 계열이 흔든 경도 폭. (III.B)

**이 그림이 없으면 V 장의 "경도 효과가 검출되지 않았다" 가 부정직하게 읽힌다.**
경도가 무관한 것이 아니라 **한쪽 계열은 거의 흔들지 않았다** — 깊이 참조형은
Shore OO **40 점**(30 → 70, Ecoflex 에서 Dragon Skin 으로 제품군을 건너뛴다),
광도 계열은 **6 점**(51 → 57, Slacker 비율만 바꾼 한 배합)이다. **6.7 배**다.

부록이 아니라 방법에 있어야 한다 (계획서 F2 (c)). 독자가 이 폭을 먼저 보고
V 장에 들어가야 "미검출" 을 검정력의 문제로 읽는다. 뒤에 두면 순서가 뒤집힌다.

왜 수직선 하나짜리 그림인가
    두 계열을 **같은 축**에 올리는 것이 이 그림의 전부다. 3 × 3 표로는 40 대 6 이
    보이지 않는다 — 표는 `soft / medium / hard` 라는 같은 이름 아래 아주 다른
    물건을 넣어 두기 때문이다. 배수를 글자로 적지 않았다. 같은 자 위에 얹으면
    눈이 먼저 본다.

마커 계열은 따로 그리지 않는다
    광도 계열과 **같은 배합**에서 뜬 겔이다(III.B). 다만 구 압자 아래에서
    측정상 더 단단했다(Hertz 강성비 1.64) — 그것은 경도 눈금의 문제가 아니라
    마커 자체의 문제이므로 본문이 따로 적는다.

캡션이 져야 할 것
    1. 점이 **실측 Shore OO** 라는 것(제조사 공칭이 아니라 경화된 재료에서 잰 값).
    2. **40 점 대 6 점, 6.7 배.** 그림이 보여 주지만 숫자는 캡션이 적는다.
    3. 깊이 참조형은 **제품군을 건너뛴다**(Ecoflex → Dragon Skin). 광도 계열은
       한 배합의 가소제 비율만 바꾼 것이다 — 같은 "경도 3 수준" 이 아니다.
    4. 마커 겔은 광도 계열과 같은 배합이라 따로 그리지 않았다.

자료
    `result/single/extra/data/D_hardness_range_imbalance.csv`
"""
import pandas as pd

import paper_style as PS
from paper_style import HARD3, DISPLAY

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402

ORDER = ["soft", "medium", "hard"]
# 아래에서 위로 — 깊이 참조형을 위에 둔다(본문의 차례와 같다)
ROWS = ["DIGIT", "9DTact"]
# 마커 겔은 같은 배합이라 같은 줄이다 — 캡션이 그것을 적는다
LABEL = {"9DTact": DISPLAY["9DTact"], "DIGIT": DISPLAY["DIGIT"]}


def main():
    d = pd.read_csv(PS.ROOT / "result/single/extra/data/D_hardness_range_imbalance.csv")
    assert set(d.principle) == {"9DTact", "DIGIT"}, "계열이 둘이 아니다"

    fig, ax = plt.subplots(figsize=(PS.COL_W, 1.60))
    for y, pr in enumerate(ROWS):
        g = d[d.principle == pr].set_index("hardness").shore_OO
        # 흔든 폭을 선 하나로 — 이 선의 길이 차이가 그림의 전부다
        ax.plot([g.min(), g.max()], [y, y], "-", c=PS.MUTED, lw=2.0, zorder=2,
                solid_capstyle="round")
        for h in ORDER:
            ax.plot([g[h]], [y], marker="o", ms=8.0, c=HARD3[h], zorder=3,
                    clip_on=False)

    ax.set_yticks(range(len(ROWS)))
    ax.set_yticklabels([LABEL[p] for p in ROWS])
    ax.set_ylim(-0.6, len(ROWS) - 0.4)
    ax.set_xlim(25, 75)
    ax.set_xticks([30, 40, 50, 60, 70])
    ax.set_xlabel("measured Shore OO hardness")
    PS.style(ax, grid="x")
    ax.spines["left"].set_visible(False)
    ax.tick_params(axis="y", length=0)

    fig.tight_layout()
    PS.save(fig, d, "fig_hardness")

    spans = d.groupby("principle").shore_OO.agg(lambda v: v.max() - v.min())
    print(f"\n  흔든 폭 — 깊이 참조형 {spans['9DTact']} 점 · 광도 계열 "
          f"{spans['DIGIT']} 점 → {spans['9DTact'] / spans['DIGIT']:.1f} 배")


if __name__ == "__main__":
    main()
