#!/usr/bin/env python3
"""논문 그림 — 합력 오차와 옌센 하한. (V.A)

사용자가 정작 알고 싶은 것은 축별 오차가 아니라 **합력 오차** E‖F̂ − F‖ 인 경우가
많다. 스윕이 축별 MAE 만 저장해 처음에는 그것을 계산할 수 없었고, 그래서 옌센
부등식으로 **하한** L = √(MAE_x² + MAE_y² + MAE_z²) 만 보고했다. 그 뒤 선택 27
유닛을 다시 학습해 **실측했다**.

**하한이 얼마나 잘 버텼는지가 그 자체로 방법에 대한 결과다.** 크기는 실측의
0.86 ~ 0.90 배로 10 % 쯤 낮게 잡았고, 36 칸 중 **35 칸에서 성립**했다. 그래서
하한을 지우지 않고 함께 그린다 — 축별만 재고 합력을 하한으로 보고하는 후속
연구가 그 하한을 얼마나 믿어도 되는지를 이 그림이 말해 준다.

**어긋난 칸이 하나 있다** — Marker 의 160 px 단에서 하한(0.1105)이 실측(0.1058)을
넘는다. 옌센 부등식이 틀린 것이 아니라 두 값이 **다른 학습 판**에서 나왔기
때문이다(축별은 판 A, 실측 합력은 재학습). 그림에서 실선이 그 한 단에서 파선
아래로 내려가는 것이 그것이고, 하한을 "반드시 아래" 로 읽으면 안 된다는 표시다.

**평탄점까지 같지는 않았다** (2026-09-15 에 확인, `figure_plan.md` §3.1 정정)
    계획서는 "평탄점의 위치는 하한과 실측이 같았다" 고 적었는데, 같은 규칙
    (최솟값의 110 %)으로 다시 내면 **깊이 참조형만 맞는다**:

    | 원리 | 실측 평탄점 R | 하한 평탄점 R |
    |---|---:|---:|
    | 9DTact | 13.65 | 13.65 |
    | DIGIT | **2.93** | 18.33 |
    | DIGIT_Marker | **22.57** | 361.15 |

    광도 두 계열에서는 **실측 곡선이 바닥 근처에서 더 평평해** 평탄점이 하한보다
    낮은 밀도에서 잡힌다. 하한은 크기뿐 아니라 **요구 밀도도 보수적으로** 잡는
    셈이다. 본문이 "하한이 평탄점을 제대로 짚었다" 고 쓰면 안 된다.

띠는 부등식의 폭이다
    옅은 띠의 아래가 옌센 하한, 위가 삼각부등식의 상한(축별 MAE 의 합)이다.
    참값은 그 사이 어디에든 있을 수 있다 — 실선이 실제로 어디에 있었는지를
    보여 주는 것이 이 그림의 두 번째 임무다.

합력은 사실상 Fz 다
    제곱합에서 Fz 의 몫이 밀도마다 **51 ~ 82 %** 라, 합력 곡선은 Fz 곡선의 모양을
    그대로 물려받는다. 그래서 `fig_force` 와 이 그림은 **같은 이야기를 두 번**
    한다 — 지면이 모자라면 이쪽이 보충자료로 갈 자리다 (`figure_plan.md` §3.1).

**여기의 평탄점은 `fig_force` 의 삼각형과 다른 수다**
    이 자료는 원리마다 **곡선이 하나**뿐이라(유닛을 이미 합친 것) 평탄점도
    **합친 곡선의 평탄점**이다. `fig_force` 의 삼각형은 **유닛마다 구한 뒤
    중앙값**이다. 계획서 §4 불일치 5 가 이 둘이고, 본문·초록은 후자로 통일한다.
    섞어 쓰면 같은 양이 두 값으로 나온다 — 캡션이 어느 쪽인지 밝혀야 한다.

세로 축은 원리마다 따로
    세 계열은 입력 표현부터 다르다(grey / raw / inpaint). 행을 가로질러 견줄 수
    없다는 것은 `fig_force` 와 같다.

칸마다 정해진 센서 하나 (`CLAUDE.md` §1) — 원리당 아홉 시편을 합친 곡선.

캡션이 져야 할 것
    1. 실선 = 실측 합력 MAE, 파선 = 옌센 하한, 띠 = 하한과 삼각부등식 상한 사이.
    2. **평탄점이 합친 곡선의 것**이고 Fig. 5 의 삼각형(유닛별 중앙값)과 다른
       수라는 것.
    3. 하한이 실측의 **0.86 ~ 0.90 배**였고 36 칸 중 35 칸에서 성립했다는 것.
       평탄점은 **깊이 참조형에서만** 하한과 일치한다 — 광도 두 계열에서는
       실측 쪽이 더 낮은 밀도에서 평탄해진다.
    4. 세로 축이 칸마다 다르고 원리끼리 견주면 안 된다는 것.

자료
    `result/single/extra/data/I_resultant_force.csv` (원리 × 12 단)
    · 요약 `I_resultant_force_summary.csv`
"""
import pandas as pd

import paper_style as PS
from paper_style import DISPLAY

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402
import matplotlib.ticker as mticker       # noqa: E402

PRINCIPLES = ("9DTact", "DIGIT", "DIGIT_Marker")
XT = [0.1, 1, 10, 100, 1000, 10000]
XTL = ["0.1", "1", "10", r"$10^2$", r"$10^3$", r"$10^4$"]


def plateau(g, col, tol=1.10):
    """최솟값의 110 % 안에 드는 가장 낮은 밀도. `fig_force` 와 같은 규칙이되
    **여기서는 합친 곡선 하나**에 걸므로 나오는 수가 다르다."""
    g = g.sort_values("density_px_per_mm2")
    return float(g[g[col] <= g[col].min() * tol].density_px_per_mm2.iloc[0])


def main():
    d = pd.read_csv(PS.ROOT / "result/single/extra/data/I_resultant_force.csv")
    assert set(d.principle) == set(PRINCIPLES), "원리가 셋이 아니다"
    assert not d.res_mae_exact.isna().any(), "실측 합력에 빈 칸이 있다"

    fig, axes = plt.subplots(1, len(PRINCIPLES),
                             figsize=(PS.FULL_W_NARROW, 2.55))
    rows = []
    for tag, ax, pr in zip("abc", axes, PRINCIPLES):
        g = d[d.principle == pr].sort_values("density_px_per_mm2")
        ax.fill_between(g.density_px_per_mm2, g.lo, g.hi, color=PS.MUTED,
                        alpha=0.18, lw=0, zorder=2)
        ax.plot(g.density_px_per_mm2, g.lo, "--", c=PS.BLACK, lw=1.3,
                zorder=3, label="Jensen bound")
        ax.plot(g.density_px_per_mm2, g.res_mae_exact, "-", c=PS.BLACK, lw=1.9,
                zorder=4, label="measured")

        pe, pl = plateau(g, "res_mae_exact"), plateau(g, "lo")
        ax.plot([pe], [0], marker="^", ms=5.0, c=PS.BLACK, clip_on=False,
                transform=ax.get_xaxis_transform(), zorder=6)
        rows.append(dict(principle=pr, plateau_R_measured=pe,
                         plateau_R_bound=pl,
                         best_measured_N=g.res_mae_exact.min(),
                         best_bound_N=g.lo.min(),
                         bound_over_measured=(g.lo / g.res_mae_exact).median(),
                         fz_share_min=g.fz_share.min(),
                         fz_share_max=g.fz_share.max()))

        ax.set_xscale("log")
        ax.set_xticks(XT)
        ax.set_xticklabels(XTL)
        ax.xaxis.set_minor_locator(mticker.NullLocator())
        ax.yaxis.set_major_locator(mticker.MaxNLocator(4))
        ax.set_ylim(0, ax.get_ylim()[1])
        ax.set_title(f"({tag}) {DISPLAY[pr]}", loc="left")
        # 세 칸에 x 이름을 셋 쓰면 칸 사이에서 글자가 부딪친다 — 가운데 하나만
        if tag == "b":
            ax.set_xlabel("pixel density $R$ [px/mm$^2$]")
        if tag == "a":
            ax.set_ylabel("resultant force MAE [N]")
            ax.legend(loc="upper right", frameon=False, handlelength=1.9,
                      handletextpad=0.5, labelspacing=0.20, borderpad=0.1,
                      fontsize=9.0)
        PS.style(ax)

    fig.tight_layout(w_pad=0.8)
    PS.save(fig, d[["principle", "width_px", "density_px_per_mm2",
                    "lo", "hi", "res_mae_exact", "fz_share"]], "fig_resultant")

    S = pd.DataFrame(rows)
    print("\n  하한이 얼마나 잘 버텼나")
    for _, r in S.iterrows():
        print(f"    {r.principle:<13} 실측 최소 {r.best_measured_N:.4f} N · "
              f"하한 {r.best_bound_N:.4f} N → {r.bound_over_measured:.2f} 배   "
              f"평탄점 실측 R {r.plateau_R_measured:7.2f} · 하한 R "
              f"{r.plateau_R_bound:7.2f}")
    print(f"  Fz 의 제곱합 몫: {S.fz_share_min.min():.0%} ~ {S.fz_share_max.max():.0%}"
          "  — 합력은 사실상 Fz 다")
    print("  ** 이 평탄점은 **합친 곡선**의 것이다. fig_force 의 삼각형"
          "(유닛별 중앙값)과 다른 수다")
    S.to_csv(PS.FIGS / "fig_resultant_stats.csv", index=False)
    print(f"  -> paper/fin_figures/fig_resultant_stats.csv  ({len(S)} 행)")


if __name__ == "__main__":
    main()
