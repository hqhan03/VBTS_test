#!/usr/bin/env python3
"""논문 그림 — 힘 추정 오차 대 화소 밀도. (V.A)

**이 논문의 중심 음성 결과가 이 그림 하나에 있다.** 같은 아홉 시편을 왼쪽에서는
두께로, 오른쪽에서는 경도로 나눴다 — **가는 선은 양쪽이 글자 그대로 똑같고 굵은
선만 달라진다.** 그런데 어느 쪽에서도 굵은 선 셋이 가는 선들의 산포 밖으로
나오지 않는다. 겔 설계의 두 축 어느 것도 이 곡선을 가르지 못한다.

한쪽만 그리면 이 말을 할 수 없다. "두께가 안 가른다" 와 "경도가 안 가른다" 는
서로 다른 주장이고, 둘을 **같은 가는 선 위에** 얹어야 독자가 두 번 확인한다.

판형 (운전자 결정, 2026-09-15)
    **3 행 × 2 열, Fz 만.** 계획서의 3 × 4 (전단 열까지)는 열두 칸을 10.5 pt 로
    그리게 되어 축 글자가 겹친다. 전단은 본문 표(Table VI)로 내린다 — 세 원리와
    두 나눔을 지키는 것이 전단 열을 지키는 것보다 앞선다.

주장의 상한 (`CLAUDE.md` §4)
    이 그림이 보이는 것은 **"무관하다" 가 아니라 "이 설계로는 검출되지 않았다"**
    이다. 유닛별 요구 밀도가 원리 안에서 두세 자릿수로 흩어지므로(1.7 ~ 880
    px/mm², 아래 삼각형의 per-unit 범위) 그보다 작은 겔 효과는 아홉 시편으로
    잡히지 않는다. 검출 실패이지 독립성의 증거가 아니다.

세로 축이 원리마다 다르다
    9DTact 0.024 ~ 0.132 N · DIGIT 0.046 ~ 0.155 · Marker 0.063 ~ 0.254 이라
    셋을 묶으면 9DTact 의 곡선이 눌린다. **행 안에서만** 축을 맞췄다 — 같은
    자료를 두 번 자른 것이므로 왼쪽과 오른쪽은 반드시 같은 축이어야 한다.
    **행을 가로질러 값을 견주면 안 된다.** 세 계열은 입력 표현부터 다르다
    (9DTact `grey` · DIGIT `raw` · Marker `inpaint`).

세로 축을 0 에서 선형으로
    로그로 그리면 낮은 밀도의 붕괴와 평탄 구간이 한 화면에 들어오지만, 평탄
    구간 안의 **군 간 차이가 눌려** 이 그림의 요점이 사라진다. 바닥을 잘라
    올리는 것도 같은 이유로 안 된다 — 요점이 "그 차이가 작다" 이기 때문이다.

삼각형 — 10 % 평탄점
    그 유닛 **자신의** 최솟값의 110 % 안에 드는 가장 낮은 단. `argmin` 은 평탄
    구간에서 seed 잡음을 집으므로 쓰지 않는다. 축 아래 삼각형은 **유닛마다
    구한 뒤 중앙값**(n = 9)이고, 중앙 곡선의 평탄점과는 다른 수다 — 본문·초록이
    끝까지 전자를 쓴다(계획서 §4 불일치 5). 두 패널의 삼각형이 같은 것은 같은
    아홉 유닛을 나누기만 했기 때문이다.

경도 범례는 실측 쇼어로
    9DTact 는 **40 쇼어 점**을 흔들었고 광도 계열은 **6 점**이다. `soft/medium/
    hard` 로만 적으면 "경도 효과 미검출" 이 부정직하게 읽힌다 (`CLAUDE.md` §4).

칸마다 정해진 센서 하나 (`CLAUDE.md` §1) — 원리당 아홉 시편, 군마다 셋.

자료
    `result/single/{1_9DTact,2_DIGIT,3_DIGIT_Marker}/data/
     force_mae_vs_resolution_9units.csv` — 유닛 × 축 × 12 단의 seed 중앙값.
    삼각형은 `result/single/extra/data/knee_force_by_unit.csv` 의 `fz_knee_R`.

    **전단을 이 그림에서 뺀 데에는 자료 쪽 이유도 있다.** 저장소의 csv 는 축별
    중앙값만 담으므로 전단을 `(median Fx + median Fy)/2` 로밖에 못 만드는데,
    분석 파이프라인의 정본은 seed 단위 `(Fx+Fy)/2` 의 중앙값이다. 둘은 27 유닛
    중 10 에서 무릎이 달라진다(Marker 중앙 71.7 대 28.4 px/mm²). Fz 는 27 유닛
    전부 정본과 일치한다 — 이 그림이 그리는 것이 그것이다.

캡션이 져야 할 것
    1. 행이 원리, 열이 나눈 변수((a)(c)(e) 두께 · (b)(d)(f) 경도)이고 **가는 선은
       두 열이 같은 선**이라는 것.
    2. 가는 선 = 시편 하나의 seed 중앙값, 굵은 선 = 군 중앙값(군마다 시편 셋).
    3. 삼각형 = 10 % 평탄 밀도의 **유닛별 값의 중앙값**(n = 9), 유닛별 범위는
       본문 표에.
    4. **세로 축이 행마다 다르고 행을 가로질러 견주면 안 된다** — 세 계열의 입력
       표현이 다르다.
    5. 칸마다 시편 하나라 **오차 막대가 없다**. 제작 간 산포는 한계 절에서 54
       유닛 집합의 숫자로 따로 인용한다.
"""
import numpy as np
import pandas as pd

import paper_style as PS
from paper_style import HARD3, THICK3, SHORE, DISPLAY

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402
import matplotlib.ticker as mticker       # noqa: E402

FOLD = {"9DTact": "1_9DTact", "DIGIT": "2_DIGIT", "DIGIT_Marker": "3_DIGIT_Marker"}
PRINCIPLES = ("9DTact", "DIGIT", "DIGIT_Marker")

# 화소 사다리. csv 에는 밀도만 있고 폭이 없는데, 밀도는 폭의 제곱에 비례하므로
# 유닛 안에서 밀도를 정렬하면 이 열두 단과 일대일로 붙는다. 굵은 선을 그리려면
# **유닛을 가로질러 같은 단끼리** 묶어야 하고(유닛마다 시야가 달라 같은 폭이 같은
# 밀도가 아니다), 그 묶음을 만드는 것이 이 사다리다.
LADDER = [8, 16, 32, 48, 80, 160, 320, 426, 640, 854, 1280, 1920]

# (나누는 변수, 색표, 범례에 적을 이름)
SPLITS = [("thickness_mm", THICK3, lambda pr, v: f"{v} mm"),
          ("hardness", HARD3, lambda pr, v: f"Shore OO-{SHORE[pr][v]}")]
ORDER = {"thickness_mm": [1, 2, 3], "hardness": ["soft", "medium", "hard"]}

XT = [0.1, 1, 10, 100, 1000, 10000]
XTL = ["0.1", "1", "10", r"$10^2$", r"$10^3$", r"$10^4$"]


def load(pr):
    """유닛 × 12 단의 Fz MAE. 밀도 순위로 사다리 단을 되찾는다."""
    f = PS.ROOT / f"result/single/{FOLD[pr]}/data/force_mae_vs_resolution_9units.csv"
    d = pd.read_csv(f)
    d = d[d.axis == "Fz"].rename(columns={"median": "fz_mae"}).copy()
    assert d.sensor.nunique() == 9, f"{pr}: 시편이 아홉이 아니다"
    assert not d.suspect_hardware.any(), f"{pr}: 선택 집합에 의심 유닛이 있다"
    rung = d.groupby("sensor").density_px_per_mm2.rank().astype(int)
    assert d.groupby("sensor").size().eq(len(LADDER)).all(), f"{pr}: 단이 12 가 아니다"
    d["width_px"] = [LADDER[i - 1] for i in rung]
    d["thickness_mm"] = d.sensor.str.extract(r"_(\d)mm_")[0].astype(int)
    d["hardness"] = d.sensor.str.extract(r"^(soft|medium|hard)_")[0]
    d["principle"] = pr
    return d


def knee_median(pr):
    """10 % 평탄 밀도 — **유닛마다 구한 뒤 중앙값**. 정본은 분석 쪽 csv 다."""
    k = pd.read_csv(PS.ROOT / "result/single/extra/data/knee_force_by_unit.csv")
    k = k[(k.principle == pr) & (~k.suspect_hardware)]
    return float(k.fz_knee_R.median())


def main():
    data = {pr: load(pr) for pr in PRINCIPLES}

    tags = iter("abcdef")
    fig, axes = plt.subplots(len(PRINCIPLES), len(SPLITS),
                             figsize=(PS.FULL_W_NARROW, 5.30), sharex=True)

    for row, pr in enumerate(PRINCIPLES):
        d = data[pr]
        knee = knee_median(pr)
        for col, (key, cmap, lab) in enumerate(SPLITS):
            ax = axes[row, col]

            # 가는 선 — 시편 하나. x 는 **그 유닛 자신의** 밀도다. 같은 유닛이 두
            # 열에 모두 나오므로 선은 같고 색만 바뀐다. 그것이 이 그림의 장치다.
            for _, g in d.groupby("sensor"):
                g = g.sort_values("density_px_per_mm2")
                ax.plot(g.density_px_per_mm2, g.fz_mae, "-",
                        c=cmap[g[key].iloc[0]], lw=0.7, alpha=0.45, zorder=2)

            # 굵은 선 — 군 중앙값. **사다리 단으로 묶고** 그 묶음의 중앙 밀도에
            # 찍는다. 유닛마다 x 가 다르므로 밀도로 직접 묶을 수 없다.
            for v in ORDER[key]:
                g = d[d[key] == v]
                med = g.groupby("width_px").fz_mae.median()
                xs = g.groupby("width_px").density_px_per_mm2.median()
                # 가는 선 위에서 굵은 선이 끊기지 않게 흰 테를 먼저 깐다
                ax.plot(xs.values, med.values, "-", c="white", lw=3.4,
                        alpha=0.9, zorder=3)
                ax.plot(xs.values, med.values, "-", c=cmap[v], lw=1.8,
                        label=lab(pr, v), zorder=4)

            # 10 % 평탄점 — 축 아래 삼각형 하나. 두 열이 같은 값이다.
            ax.plot([knee], [0], marker="^", ms=5.0, c=PS.BLACK, clip_on=False,
                    transform=ax.get_xaxis_transform(), zorder=6)

            ax.set_xscale("log")
            ax.set_xticks(XT)
            ax.set_xticklabels(XTL)
            ax.xaxis.set_minor_locator(mticker.NullLocator())
            ax.yaxis.set_major_locator(mticker.MaxNLocator(4))
            ax.set_title(f"({next(tags)})", loc="left")
            if col == 0:
                ax.set_ylabel(f"{DISPLAY[pr]}\n$F_z$ MAE [N]")
            if row == len(PRINCIPLES) - 1:
                ax.set_xlabel("pixel density $R$ [px/mm$^2$]")
            PS.style(ax)

        # **행 안에서 세로 축을 맞춘다.** 같은 자료를 두 번 자른 것이므로 두 열이
        # 다른 축이면 거짓 차이가 보인다. 0 에서 시작한다.
        hi = max(a.get_ylim()[1] for a in axes[row])
        for a in axes[row]:
            a.set_ylim(0, hi)
        axes[row, 1].set_yticklabels([])

        # 범례는 열마다 하나씩만 — 두께는 행을 가로질러 같으므로 (a) 에만,
        # 경도는 **실측 쇼어가 원리마다 다르므로** 행마다 단다.
        axes[row, 1].legend(loc="upper right", frameon=False, handlelength=1.3,
                            handletextpad=0.45, labelspacing=0.20,
                            borderpad=0.1, fontsize=9.0)
    axes[0, 0].legend(loc="upper right", frameon=False, handlelength=1.3,
                      handletextpad=0.45, labelspacing=0.20, borderpad=0.1,
                      fontsize=9.0)

    fig.tight_layout(w_pad=0.8, h_pad=0.9)
    out = pd.concat(data.values())[
        ["principle", "sensor", "hardness", "thickness_mm", "width_px",
         "density_px_per_mm2", "fz_mae", "min", "max"]]
    PS.save(fig, out, "fig_force")

    # 그림이 말하는 것을 숫자로 — 굵은 선 셋이 가는 선들의 산포 안에 있나.
    rows = []
    for pr in PRINCIPLES:
        d = data[pr]
        for key, _c, _l in SPLITS:
            # 각 단에서 군 중앙값의 폭과, 같은 단에서 시편 아홉의 폭
            per = d.groupby(["width_px", key]).fz_mae.median().unstack()
            grp = (per.max(axis=1) - per.min(axis=1))
            unit = d.groupby("width_px").fz_mae.agg(lambda v: v.max() - v.min())
            rows.append(dict(principle=pr, split=key,
                             group_spread=float(grp.median()),
                             unit_spread=float(unit.median()),
                             ratio=float(grp.median() / unit.median())))
        rows[-1]["knee_R_median"] = knee_median(pr)
    S = pd.DataFrame(rows)
    print("\n  군 간 폭 ÷ 시편 간 폭 (단마다 구한 뒤 중앙값) — 1 보다 작아야 "
          "'굵은 선이 산포 안' 이다")
    for _, r in S.iterrows():
        print(f"    {r.principle:<13} {r.split:<13} "
              f"군 {r.group_spread:.4f} N · 시편 {r.unit_spread:.4f} N "
              f"→ {r.ratio:.2f}")
    print("\n  10 % 평탄 밀도 (유닛별 중앙값, n = 9)")
    for pr in PRINCIPLES:
        k = pd.read_csv(PS.ROOT / "result/single/extra/data/knee_force_by_unit.csv")
        k = k[k.principle == pr]
        print(f"    {pr:<13} R = {k.fz_knee_R.median():7.2f} px/mm²   "
              f"유닛별 {k.fz_knee_R.min():.2f} ~ {k.fz_knee_R.max():.1f}")
    S.to_csv(PS.FIGS / "fig_force_stats.csv", index=False)
    print(f"  -> paper/fin_figures/fig_force_stats.csv  ({len(S)} 행)")


if __name__ == "__main__":
    main()
