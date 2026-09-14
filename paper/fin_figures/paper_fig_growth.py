#!/usr/bin/env python3
"""논문 그림 — 자국 성장: 무엇을 고정하느냐가 어느 변수를 가른다. (IV.A)

**왼쪽 절반과 오른쪽 절반이 서로 거울이다.** 같은 자국, 같은 램프, 바뀐 것은
x 축뿐인데 — `깊이 × 경도` 에서는 세 곡선이 포개지고 `힘 × 경도` 에서는 벌어진다.
`깊이 × 두께` 는 벌어지는데 `힘 × 두께` 는 포개진다.

물리로는 그럴 만하다. **같은 깊이**에서는 기재가 얼마나 가까운지가 변형을 정하므로
두께가 이기고, **같은 힘**에서는 겔이 얼마나 무른지가 얼마나 들어가는지를 정하므로
경도가 이긴다. 두 축은 같은 램프의 두 얼굴이지만 **서로 다른 질문**이다.

독자에게 주는 것: *겔 특성을 해석할 때 무엇을 고정해야 하는가.*

**두 가지 잰 것을 다 그려야 한다** (2026-09-15 에 확인)
    지름만 그리면 거울의 절반이 사라진다. 잰 것마다 **다른 변수가 이긴다**:

    | 잰 것 | 깊이 × 경도 | 깊이 × 두께 | 힘 × 경도 | 힘 × 두께 |
    |---|---:|---:|---:|---:|
    | 지름 | 1.16 (순서 없음) | **1.33** | 1.15 | 1.04 |
    | 밝기 | 1.24 | 1.22 (순서 없음) | **2.00** | 1.71 (순서 없음) |

    **지름이 두께 이야기를 하고 밝기가 경도 이야기를 한다.** 같은 깊이에서 두께가
    지름을 1.33 배 가르고(단조), 같은 힘에서는 1.04 배로 무너진다. 경도는 지름을
    거의 못 가르는데(1.15 ~ 1.16) 같은 힘에서 밝기를 **2.00 배**(단조) 가른다.

    **배수만 보고 읽으면 안 된다.** 순서가 없는 칸이 셋이다 — 깊이 × 경도의 지름
    (soft 427 · medium 367 · hard 405), 깊이 × 두께의 밝기, 힘 × 두께의 밝기
    (1.71 이지만 1 mm 가 가장 어둡다). **단조인 칸만 경향으로 인용할 것.**

9DTact 뿐이다
    DIGIT 계열에서는 **뒤집히지 않는다**(두께가 두 기준 모두에서 가르고 경도는
    힘 기준에서도 거의 올라오지 않는다). 그 판을 내려면 원영상이 필요하다 —
    `make_optical_curves.py:501` 의 `if pr == "9DTact"` 를 풀고 실험 기계에서
    돌려야 한다. 본문 문장은 그때까지 "DIGIT 계열에서는 뒤집히지 않는다" 까지만.

같은 색이 패널마다 다른 뜻이다
    (a)(c) 의 파랑·주황·초록은 **경도**, (b)(d) 의 같은 색은 **두께**다. 칸마다
    범례를 달아 갈랐다 — 한 패널 안에서는 한 뜻뿐이다.

칸마다 정해진 센서 하나 (`CLAUDE.md` §1) — 9DTact 아홉 시편, 군마다 셋.

캡션이 져야 할 것
    1. **어느 패널이 무엇인가** — (a) 깊이 · 경도별, (b) 깊이 · 두께별,
       (c) 힘 · 경도별, (d) 힘 · 두께별. 잰 것은 넷 다 **자국 지름**이다.
    2. **선은 중앙값, 띠는 사분위 범위**, 군마다 시편 셋.
    3. 지름을 **픽셀로 둔 이유** — mm 환산에 쓰는 px/mm 이 유닛마다 최대 1.5 배
       어긋난다. 픽셀은 측정된 그대로다.
    4. **원리 간 기울기를 비교하면 안 된다** — 자료마다 깊이 구간이 다르다.

자료
    `result/single/extra/data/H_reversal_9DTact_ball8.csv`
    (`make_optical_curves.py` 의 `reversal()` 이 낸 중앙값·사분위)
"""
import pandas as pd

import paper_style as PS
from paper_style import HARD3, THICK3, SHORE, DISPLAY

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402

MEASURES = [("diameter_px", "imprint diameter [px]"),
            ("level", "intensity change [lvl]")]
PRINCIPLE, PROBE = "9DTact", "ball8"

# (x 축, 나눈 변수, x 라벨, 색, 범례 이름)
PANELS = [
    ("depth_mm", "hardness", "depth [mm]"),
    ("depth_mm", "thickness_mm", "depth [mm]"),
    ("force_N", "hardness", "force [N]"),
    ("force_N", "thickness_mm", "force [N]"),
]
ORDER = {"hardness": ["soft", "medium", "hard"],
         "thickness_mm": ["1", "2", "3"]}


def colour_and_label(key, g):
    """군의 색과 범례 이름. 경도는 **실측 쇼어**로 적는다."""
    if key == "hardness":
        return HARD3[g], f"Shore OO-{SHORE[PRINCIPLE][g]}"
    return THICK3[int(float(g))], f"{int(float(g))} mm"


def main():
    d = pd.read_csv(PS.ROOT / "result/single/extra/data/H_reversal_9DTact_ball8.csv")
    d = d[(d.principle == PRINCIPLE) & (d.probe == PROBE)]
    assert len(d), "자료가 비었다"

    tags = iter("abcdefgh")
    fig, axes = plt.subplots(len(MEASURES), len(PANELS),
                             figsize=(PS.FULL_W, 4.05), sharex="col")
    for row, (meas, ylab) in enumerate(MEASURES):
        dm = d[d.measure == meas]
        for col_i, (xcol, key, xlab) in enumerate(PANELS):
            ax = axes[row, col_i]
            g0 = dm[(dm.x_name == xcol) & (dm.group_by == key)]
            for gname in ORDER[key]:
                g = g0[g0.group.astype(str) == gname].sort_values("x")
                if not len(g):
                    continue
                c, lab = colour_and_label(key, gname)
                ax.fill_between(g.x, g.q1, g.q3, color=c, alpha=0.16, lw=0,
                                zorder=2)
                ax.plot(g.x, g["median"], "-", c=c, lw=1.8, label=lab, zorder=3)

            ax.set_title(f"({next(tags)})", loc="left")
            if row == len(MEASURES) - 1:
                ax.set_xlabel(xlab)
            if col_i == 0:
                ax.set_ylabel(ylab)
            if row == 0:
                ax.legend(loc="upper left", frameon=False, handlelength=1.4,
                          handletextpad=0.45, labelspacing=0.22, borderpad=0.1,
                          fontsize=8.0)
            PS.style(ax)
        # **행 안에서 세로 축을 맞춘다** — 열을 가로질러 읽어야 하기 때문이다
        lo = min(a.get_ylim()[0] for a in axes[row])
        hi = max(a.get_ylim()[1] for a in axes[row])
        for a in axes[row]:
            a.set_ylim(lo, hi)
        for a in axes[row, 1:]:
            a.set_yticklabels([])

    # **짝지은 두 칸의 x 범위를 맞춘다.** 같은 램프를 경도로 한 번, 두께로 한 번
    # 나눈 것이라 x 가 다르면 거울이 읽히지 않는다. 군마다 자료가 닿은 구간이
    # 달라 그냥 두면 (a) 는 0.6 에서, (b) 는 0.2 에서 시작한다.
    for lo_col, hi_col in ((0, 1), (2, 3)):
        lo = min(axes[0, c].get_xlim()[0] for c in (lo_col, hi_col))
        hi = max(axes[0, c].get_xlim()[1] for c in (lo_col, hi_col))
        for c in (lo_col, hi_col):
            for r in range(len(MEASURES)):
                axes[r, c].set_xlim(lo, hi)

    fig.tight_layout(w_pad=0.9, h_pad=0.9)
    PS.save(fig, d[["measure", "x_name", "group_by", "group", "n_units",
                    "x", "median", "q1", "q3"]], "fig_growth")

    # 그림이 말하는 것을 숫자로 — 벌어진 배수와 **순서가 있는지**
    tags = iter("abcdefgh")
    for meas, _ in MEASURES:
        for xcol, key, _x in PANELS:
            g0 = d[(d.measure == meas) & (d.x_name == xcol) & (d.group_by == key)]
            common = g0.groupby("x").group.nunique()
            common = common[common == 3].index
            at = common[len(common) // 2]
            v = g0[g0.x == at].set_index("group")["median"].reindex(ORDER[key])
            mono = v.is_monotonic_increasing or v.is_monotonic_decreasing
            print(f"  ({next(tags)}) {meas:<11} {xcol.split('_')[0]:>5} "
                  f"{at:6.2f} · {key:<12} {v.max() / v.min():.2f} 배"
                  f"   {'단조' if mono else '순서 없음'}")


if __name__ == "__main__":
    main()
