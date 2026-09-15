#!/usr/bin/env python3
"""논문 그림 — 광도 계열의 복원 깊이는 유닛마다 기울기가 다르다. (V.B)

**본문이 이미 이 그림을 부르고 있다** ([V-B2] 의 `Fig. 3b`) — 지금 가리킬 패널이
없다.

유닛 **안에서는** 복원 깊이가 참 깊이를 잘 따라간다(r 0.93 ~ 1.00). 그런데
**유닛 사이에서는 기울기가 세 배 넘게 갈린다.** 보이는 접촉 캡이 프로브가 실제로
들어간 깊이보다 얕기 때문이고, 그 얕은 정도가 유닛마다 다르다. 그래서 **광도
계열의 절대 깊이는 유닛 고유의 값**이고, 유닛을 가로질러 견줄 수 있는 것은
오차–밀도 곡선의 **모양**뿐이다. V.B 의 다른 그림이 절대값을 세로로 견주지
않는 이유가 이것이다.

1 대 1 선을 함께 긋는다
    기울기가 1 에서 얼마나 떨어져 있는지가 요점이므로 기준선이 있어야 한다.
    아홉 선이 전부 그 아래에 있다 — **한 유닛도 프로브 이동량만큼 깊게 복원하지
    않는다.**

두께로 색을 나눈 것에 대하여
    기울기가 두께를 따라간다 — 원기둥 Spearman ρ **+0.69** (p 0.042, n 9),
    정육면체 +0.63 (p 0.068). 얇을수록 기울기가 낮다. **다중검정 보정 전이고
    본문이 지금 다루지 않는 관찰**이므로, 색은 자료를 있는 그대로 나눈 것이지
    주장이 아니다. 인용한다면 `CLAUDE.md` §4 의 상한을 그대로 건다 — 경향이지
    기전이 아니다. 숫자는 `fig_slope_stats.csv` 에 있다.

    물리로 읽자면 얇은 겔일수록 기재가 가까워 프로브 이동량 중 더 많은 몫이
    눌림이 아니라 기재 쪽으로 가고, 보이는 캡은 그만큼 더 얕아진다. **이 자료로
    검증한 것이 아니다.**

전해상도만 그린다
    축소가 이 기울기에 어떻게 작용하는지는 다른 질문이고 `fig_shape` 가 답한다.
    여기서 묻는 것은 **원본에서조차 유닛끼리 견줄 수 없다**는 것이다.

**본문의 "0.16 ~ 0.92" 가 저장소에서 재현되지 않는다** (2026-09-15 확인)
    분석 집합 아홉 시편의 전해상도 자유적합은 **원기둥 0.23 ~ 0.78** ·
    정육면체 0.17 ~ 0.73 이다. 원점을 지나게 맞추면 0.49 ~ 1.02, 54 유닛 집합
    (`result/2_DIGIT/`) 으로 내면 0.05 ~ 0.88 — 어느 쪽도 0.16 ~ 0.92 가 아니다.
    본문 [V-B2] 의 그 값은 저장소 밖에서 온 것이므로, **그림을 실으려면 문장을
    이 그림의 값으로 고쳐야 한다.** 같은 양이 두 값으로 나오면 안 된다.

x 축은 로봇 깊이다
    사다리(`ladder.csv`)가 기록한 `depth_mm`, 곧 그 유닛의 적합된 영점에 대한
    로봇 압입량이다. 명령값이 아니라 **실측 도달 깊이**다.

원기둥만 그린다
    프로브마다 선 아홉이면 열여덟이라 못 읽는다. 정육면체도 같은 이야기를
    하고(0.17 ~ 0.73), 두 프로브의 기울기는 `fig_slope_stats.csv` 에 함께 있다.

칸마다 정해진 센서 하나 (`CLAUDE.md` §1) — 광도 계열 아홉 시편.

캡션이 져야 할 것
    1. 광도 계열 아홉 시편, **전해상도**, ⌀4 mm 원기둥.
    2. 점선이 **1 대 1** 이라는 것.
    3. 유닛 안의 상관은 r **0.93 ~ 1.00**, 유닛 사이의 기울기는 **0.23 ~ 0.78**.
    4. 그래서 **광도 계열의 절대 깊이는 유닛끼리 견줄 수 없다.**
    5. 색은 겔 두께다. 기울기가 두께를 따라가지만(ρ +0.69, p 0.042, 보정 전)
       이 논문은 그것을 주장으로 쓰지 않는다.

자료
    `result/single/2_DIGIT/data/shape_predictions.csv` (전해상도 · `cyl4`)
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import paper_style as PS
from paper_style import THICK3

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402

PROBE, FULL = "cyl4", 1920


def load():
    d = pd.read_csv(PS.ROOT / "result/single/2_DIGIT/data/shape_predictions.csv")
    d = d[(d.width_px == FULL) & (d["shape"] == PROBE)].copy()
    assert d.unit.nunique() == 9, "시편이 아홉이 아니다"
    d["thickness_mm"] = d.unit.str.extract(r"_(\d)mm_")[0].astype(int)
    return d.sort_values(["unit", "depth_true_mm"])


def fits(d):
    """유닛마다 기울기 · 절편 · 상관."""
    out = []
    for (u, sh), g in d.groupby(["unit", "shape"]):
        if len(g) < 3:
            continue
        s, i = np.polyfit(g.depth_true_mm, g.depth_pred_mm, 1)
        out.append(dict(unit=u, probe=sh, n=len(g), slope=s, intercept=i,
                        r=np.corrcoef(g.depth_true_mm, g.depth_pred_mm)[0, 1],
                        thickness_mm=int(u.split("_")[1][0]),
                        hardness=u.split("_")[0]))
    return pd.DataFrame(out)


def main():
    d = load()
    fig, ax = plt.subplots(figsize=(PS.COL_W, 2.55))

    hi = max(d.depth_true_mm.max(), d.depth_pred_mm.max()) * 1.05
    # 1 대 1 — 기울기가 1 에서 얼마나 떨어졌는지가 요점이므로 기준선이 필요하다
    ax.plot([0, hi], [0, hi], ":", c=PS.MUTED, lw=1.0, zorder=1)

    seen = set()
    for u, g in d.groupby("unit"):
        t = int(g.thickness_mm.iloc[0])
        ax.plot(g.depth_true_mm, g.depth_pred_mm, "-", c=THICK3[t], lw=1.4,
                alpha=0.85, zorder=3,
                label=f"{t} mm" if t not in seen else None)
        seen.add(t)

    ax.set_xlim(0, hi)
    ax.set_ylim(0, hi)
    ax.set_xlabel("indentation depth, robot [mm]")
    ax.set_ylabel("reconstructed depth [mm]")
    h, l = ax.get_legend_handles_labels()
    order = np.argsort([int(x.split()[0]) for x in l])
    ax.legend([h[i] for i in order], [l[i] for i in order], loc="upper left",
              frameon=False, handlelength=1.3, handletextpad=0.45,
              labelspacing=0.20, borderpad=0.1, fontsize=9.0)
    PS.style(ax, grid="both")

    fig.tight_layout()
    PS.save(fig, d[["unit", "shape", "width_px", "thickness_mm",
                    "depth_true_mm", "depth_pred_mm"]], "fig_slope")

    # 두 프로브 전부에 대해 기울기를 낸다 — 그림은 원기둥만 그린다
    allp = pd.read_csv(PS.ROOT / "result/single/2_DIGIT/data/shape_predictions.csv")
    S = fits(allp[allp.width_px == FULL])
    print("\n  유닛별 기울기 (전해상도)")
    for probe in ("cyl4", "cube4"):
        g = S[S.probe == probe]
        rho, p = spearmanr(g.thickness_mm, g.slope)
        print(f"    {probe:<6} 기울기 {g.slope.min():.2f} ~ {g.slope.max():.2f} · "
              f"r {g.r.min():.2f} ~ {g.r.max():.2f} · "
              f"두께와 ρ {rho:+.2f} (p {p:.3f}, n {len(g)})")
    print("  ** 한 유닛도 1 을 넘지 않는다 — 보이는 캡이 프로브 이동량보다 얕다")
    S.to_csv(PS.FIGS / "fig_slope_stats.csv", index=False)
    print(f"  -> paper/fin_figures/fig_slope_stats.csv  ({len(S)} 행)")


if __name__ == "__main__":
    main()
