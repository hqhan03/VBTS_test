#!/usr/bin/env python3
"""논문 그림 — 평탄 밀도는 겔을 따르지 않는다. (V.A · V.B, 표 V 를 받친다)

**왜 필요한가** (2026-09-15). "힘·형상의 평탄 밀도가 두께·경도를 따르지 않는다"
는 이 논문의 결론 중 하나인데, 그것을 받치는 표도 그림도 논문에 없었다. 괄호
안의 `(|rho| <= 0.58, q >= 0.53)` 넷이 전부였다. 표 V 를 만들어 검정을 실었고,
이 그림이 그 표를 눈으로 보여 준다.

무엇을 보이나
    한 줄이 한 과업·한 구성이다. 줄마다
      - 회색 가로 막대 = 그 구성 아홉 시편의 평탄 밀도 **최소 ~ 최대**
      - 회색 점 아홉 = 시편 하나씩
      - 색 점 셋 = **군 중앙값** (왼쪽 칸은 두께 1 · 2 · 3 mm, 오른쪽 칸은
        경도 soft · medium · hard)
    읽는 법은 하나다 — **색 점 셋이 회색 막대의 어디쯤 모여 있나.** 겔이
    요구량을 정한다면 셋이 막대를 따라 벌어져야 한다. 벌어지지 않는다.

색만으로 군을 가르지 않는다 (`CLAUDE.md` §2)
    표식 모양은 쓰지 않기로 되어 있으므로(`paper_style` 의 운전자 결정) **자리**로
    가른다 — 군 중앙값 셋을 줄 안에서 위·가운데·아래로 어긋나게 찍고 그 차례를
    1 · 2 · 3 mm (또는 soft · medium · hard) 로 고정한다. 흑백 인쇄에서도,
    색각 이상에서도 위아래 자리로 읽힌다.

말하지 않는 것 (`CLAUDE.md` §4)
    **"무관하다" 가 아니다.** 구성당 시편이 아홉이고 시편 사이 산포가 두세
    자릿수라, 그보다 작은 겔 효과는 이 설계로 **검출되지 않았다**. 캡션이 그렇게
    적어야 한다. 경도 칸은 계열마다 흔든 폭이 다르다는 것도 함께 적는다 —
    9DTact 는 Shore OO 40 점, 광도 계열은 6 점이다.

합력 평탄 밀도를 여기서 계산하는 이유
    `knee_force_by_unit.csv` 는 축별(Fz · 전단) 평탄 밀도만 담고 있다. 표 IV 가
    합력 기준으로 바뀌었으므로 합력 평탄 밀도가 필요한데, 유닛별 `res_mae` 가
    저장소에 없다. 그래서 축별 MAE 에서 Jensen 하한
    `sqrt(MAEx^2 + MAEy^2 + MAEz^2)` 를 **유닛마다** 만들고 그 곡선에서 평탄
    밀도를 잡는다 — 본문·표 IV 와 같은 값이 나온다.

자료 (전부 csv 라 어느 기계에서나 다시 그린다, `CLAUDE.md` §3)
    힘   `result/single/<원리>/data/force_mae_vs_resolution_9units.csv`
    형상 `result/single/extra/data/knee_shape_by_unit.csv`
"""
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import paper_style as PS
from paper_style import HARD3, THICK3, SHORE

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402

FOLD = {"9DTact": "1_9DTact", "DIGIT": "2_DIGIT", "DIGIT_Marker": "3_DIGIT_Marker"}
AX = ["Fx", "Fy", "Fz"]
TOL = 0.10                                # 본문 기준 허용치
HARDNESS = ("soft", "medium", "hard")
THICKNESS = (1, 2, 3)
DODGE = (0.20, 0.0, -0.20)                # 군 중앙값을 줄 안에서 어긋나게

# 줄의 차례 — 위에서 아래로. (과업 이름, 원리, 값이 든 열)
ROWS = [("Force $\\|\\Delta F\\|$", "9DTact", "res"),
        ("Force $\\|\\Delta F\\|$", "DIGIT", "res"),
        ("Force $\\|\\Delta F\\|$", "DIGIT_Marker", "res"),
        ("Depth, $\\varnothing$4 mm cyl.", "9DTact", "cyl4_knee_R"),
        ("Depth, $\\varnothing$4 mm cyl.", "DIGIT", "cyl4_knee_R"),
        ("Depth, 4 mm cube", "9DTact", "cube4_knee_R"),
        ("Depth, 4 mm cube", "DIGIT", "cube4_knee_R")]


def knee(v):
    """평탄 밀도 — 그 유닛 자신의 최솟값의 (1 + TOL) 안에 드는 **가장 낮은** 단.

    `argmin` 은 곡선이 평평한 구간에서 시드 잡음에 흔들리므로 쓰지 않는다.
    """
    return int(np.argmax(np.asarray(v) <= min(v) * (1 + TOL)))


def resultant(pr):
    """구성 하나의 유닛별 합력(하한) 평탄 밀도."""
    f = PS.ROOT / "result" / "single" / FOLD[pr] / "data" / \
        "force_mae_vs_resolution_9units.csv"
    d = pd.read_csv(f)
    d = d[d.axis.isin(AX)]
    assert not d.suspect_hardware.any(), "선택 규칙이 거른 유닛이 남아 있다"
    w = d.pivot_table(index=["sensor", "density_px_per_mm2"],
                      columns="axis", values="median").reset_index()
    w["res"] = np.sqrt((w[AX] ** 2).sum(axis=1))
    out = []
    for u, g in w.groupby("sensor"):
        g = g.sort_values("density_px_per_mm2")
        i = knee(g.res.values)
        out.append(dict(principle=pr, unit=u,
                        hardness=u.split("_")[0],
                        thickness_mm=int(u.split("_")[1].replace("mm", "")),
                        metric="res", knee_R=float(g.density_px_per_mm2.iloc[i]),
                        best=float(g.res.min())))
    assert len(out) == 9, f"{pr}: 유닛이 {len(out)} 개다"
    return pd.DataFrame(out)


def shape():
    d = pd.read_csv(PS.ROOT / "result/single/extra/data/knee_shape_by_unit.csv")
    assert not d.suspect_hardware.any()
    out = []
    for col in ("cyl4_knee_R", "cube4_knee_R"):
        for _, r in d.iterrows():
            out.append(dict(principle=r.principle, unit=r.unit,
                            hardness=r.hardness, thickness_mm=int(r.thickness_mm),
                            metric=col, knee_R=float(r[col]),
                            best=float(r[col.replace("knee_R", "best_mm")])))
    return pd.DataFrame(out)


def panel(ax, dat, factor):
    """한 칸 — 줄마다 산포 막대 + 시편 점 + 군 중앙값 셋."""
    levels = THICKNESS if factor == "thickness_mm" else HARDNESS
    cmap = THICK3 if factor == "thickness_mm" else HARD3
    for y, (_task, pr, met) in enumerate(ROWS):
        g = dat[(dat.principle == pr) & (dat.metric == met)]
        assert len(g) == 9, f"{pr}/{met}: {len(g)} 행"
        ax.plot([g.knee_R.min(), g.knee_R.max()], [y, y], "-",
                c="#c0c0c0", lw=3.4, solid_capstyle="round", zorder=1)
        ax.plot(g.knee_R, [y] * len(g), "o", c="#8c8c8c", ms=3.0,
                ls="none", zorder=2)
        for lev, dy in zip(levels, DODGE):
            med = g[g[factor] == lev].knee_R.median()
            ax.plot([med], [y + dy], "o", c=cmap[lev], ms=5.6,
                    mec="white", mew=0.7, ls="none", zorder=4)
    ax.set_xscale("log")
    ax.set_xlim(0.12, 1.6e4)
    ax.set_ylim(len(ROWS) - 0.45, -0.55)
    ax.set_yticks(range(len(ROWS)))
    PS.style(ax, grid=None)
    ax.grid(axis="x", alpha=0.25, lw=0.4, color="#c8c8c8")
    ax.set_axisbelow(True)
    # 과업이 바뀌는 자리에 옅은 가로줄 — 줄 이름만으로는 묶음이 읽히지 않는다.
    for y in [i - 0.5 for i in range(1, len(ROWS))
              if ROWS[i][0] != ROWS[i - 1][0]]:
        ax.axhline(y, c="#dcdcdc", lw=0.6, zorder=0)


def main():
    dat = pd.concat([resultant(p) for p in FOLD] + [shape()], ignore_index=True)

    fig, axes = plt.subplots(1, 2, figsize=(PS.FULL_W_NARROW, 3.15),
                             sharey=True)
    fig.subplots_adjust(left=0.238, right=0.988, top=0.855, bottom=0.175,
                        wspace=0.08)
    panel(axes[0], dat, "thickness_mm")
    panel(axes[1], dat, "hardness")

    # 줄 이름은 왼쪽 칸에만. 같은 과업이 두세 줄이면 첫 줄에만 적고 나머지는
    # 원리 이름만 적어 세로 공간을 아낀다.
    labels, seen = [], None
    for task, pr, _met in ROWS:
        labels.append(f"{task}\n{PS.DISPLAY[pr]}" if task != seen
                      else PS.DISPLAY[pr])
        seen = task
    axes[0].set_yticklabels(labels, fontsize=8.6, linespacing=1.15)
    axes[1].tick_params(labelleft=False)

    for ax, ttl, levels, cmap, names in (
            (axes[0], "(a)", THICKNESS, THICK3,
             [f"{t} mm" for t in THICKNESS]),
            (axes[1], "(b)", HARDNESS, HARD3,
             list(HARDNESS))):
        # 제목은 패널 이름뿐이다 — 어느 칸이 두께이고 어느 칸이 경도인지는
        # 범례와 캡션이 진다(`fig_separation` 과 같은 규칙).
        ax.set_title(ttl, fontsize=11.0, loc="left", pad=7)
        for lev, nm in zip(levels, names):
            ax.plot([], [], "o", c=cmap[lev], ms=5.6, mec="white", mew=0.7,
                    ls="none", label=nm)
        # 범례는 칸 **밖**, 제목과 같은 줄 오른쪽에 — 안에 두면 마지막 줄을 덮는다.
        ax.legend(loc="lower right", bbox_to_anchor=(1.005, 0.995), frameon=False,
                  ncol=3, columnspacing=0.55, handletextpad=0.15, borderpad=0.0,
                  fontsize=8.0)
    # x 이름은 두 칸이 함께 쓴다 — 칸마다 달면 가운데에서 겹친다.
    fig.supxlabel(r"plateau density $R$ at $\tau=10\,\%$ [px/mm$^2$]",
                  fontsize=10.5, y=0.015)

    PS.save(fig, dat[["principle", "unit", "hardness", "thickness_mm",
                      "metric", "knee_R", "best"]], "fig_plateau_gel")

    # 표 V 가 이 수치를 쓴다 — 표준출력으로 내서 맞춰 볼 수 있게 한다.
    print(f"  tau = {TOL:.0%},  Shore OO  "
          + " · ".join(f"{p} {SHORE[p]['soft']}-{SHORE[p]['hard']}" for p in FOLD))
    for task, pr, met in ROWS:
        g = dat[(dat.principle == pr) & (dat.metric == met)]
        rt, pt = spearmanr(g.thickness_mm, g.knee_R)
        rh, ph = spearmanr([HARDNESS.index(h) for h in g.hardness], g.knee_R)
        print(f"  {task[:22]:<24s} {PS.DISPLAY[pr]:<14s} "
              f"median R {g.knee_R.median():8.1f}  "
              f"range {g.knee_R.min():6.1f}-{g.knee_R.max():8.1f}  "
              f"rho_thick {rt:+.2f} (p {pt:.2f})  rho_hard {rh:+.2f} (p {ph:.2f})")


if __name__ == "__main__":
    main()
