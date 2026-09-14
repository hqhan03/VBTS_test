#!/usr/bin/env python3
"""Figure 2b — Figure 2 와 같은 배치로 그린 **합력 오차**.

Figure 2 는 Fz 와 전단을 따로 보인다. 이 그림은 그 둘을 하나로 합친 힘 벡터의
오차를 같은 축·같은 배치로 그려 **바로 아래에 놓고 견줄 수 있게** 한다
(2026-09-14, 운전자 지시).

**y 는 하한이다.** 정확한 E‖F_pred − F_true‖ 는 프레임마다 세 오차를 함께 봐야
나오는데 스윕은 축별 MAE 만 내보낸다. L2 노름이 볼록하므로 옌센 부등식으로
√(MAEx² + MAEy² + MAEz²) ≤ E‖ΔF‖ 이고, 세 축이 프레임마다 함께 틀릴 때 같아진다
— 압입이 세 축을 동시에 흔드는 이 실험이 그 경우에 가깝다. 자세한 것은
`resultant_force.py` 와 results 문서의 해당 절.

Figure 2 와 **같은 규칙**을 지킨다: 가는 선 = 시편 하나, 굵은 선 = 군 중앙값,
왼쪽은 두께로 오른쪽은 경도로 같은 자료를 두 번 나눈다, 평탄 구간은 축 아래
작은 표식으로만, y 축 이름에 센서 이름을 괄호로.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

import paper_fig2 as F2
import pixel_density as PD
import pixel_density as PD
from palette import HARD3, THICK3

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "paper" / "figures"
AX = ["fx_mae", "fy_mae", "fz_mae"]
GROUPS = [("thickness_mm", THICK3, "Gel thickness", lambda v: f"{v} mm"),
          ("hardness", HARD3, "Gel hardness", lambda v: v)]


def load(pr):
    """실측 `res_mae` 가 있으면 그것을, 없으면 옌센 하한을 쓴다.

    2026-09-15 에 선택 27 유닛을 다시 학습해 실측값을 얻었다. 하한은 9DTact
    0.881, DIGIT 0.863, 마커 0.900 배로 참값을 낮춰 잡고 있었다 — 평탄점의
    위치는 같았지만 크기는 달랐다.
    """
    ex = ROOT / "data" / "20260911_VBTSresolution_dataset" / pr \
        / "force_vs_resolution_res.csv"
    if ex.exists():
        import result_common as _RC
        e = _RC.keep(pd.read_csv(ex), pr, "sensor")
        if "res_mae" in e and len(e):
            e = e[e.sensor.isin(_RC.chosen(pr))].copy()
            e["thickness_mm"] = e.sensor.str.extract(r"_(\d)mm_")[0].astype(int)
            e["hardness"] = e.sensor.str.extract(r"^(soft|medium|hard)_")[0]
            e = PD.add(e, pr)
            k = (e.groupby(["sensor", "hardness", "thickness_mm", "width_px",
                            "density_px_per_mm2"]).res_mae.median().reset_index())
            return k.rename(columns={"res_mae": "res"})
    d = F2.load(pr)
    if d is None:
        return None
    # seed 를 먼저 접고 축을 합친다. 순서를 뒤집으면 seed 잡음이 노름 안으로
    # 들어가 하한이 부풀려진다.
    k = (d.groupby(["sensor", "hardness", "thickness_mm", "width_px",
                    "density_px_per_mm2"])[AX].median().reset_index())
    k["res"] = np.sqrt((k[AX] ** 2).sum(axis=1))
    return k


def main():
    plt.rcParams["font.family"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(len(F2.ROWS), 2, figsize=(7.16, 6.4), sharex=True)

    ylim, handles = [], {}
    for i, (pr, nice) in enumerate(F2.ROWS):
        d = load(pr)
        if d is None:
            continue
        for j, (gcol, cmap, gtitle, glab) in enumerate(GROUPS):
            ax = axes[i, j]
            for u, g in d.groupby("sensor"):
                g = g.sort_values("density_px_per_mm2")
                ax.plot(g.density_px_per_mm2, g.res, "-",
                        c=cmap[g[gcol].iloc[0]], lw=.8, alpha=.45, zorder=2)
            for v in cmap:
                g = d[d[gcol] == v]
                if not len(g):
                    continue
                med = g.groupby("width_px").res.median()
                xs = g.groupby("width_px").density_px_per_mm2.median()
                xs = xs.reindex(med.index)
                ax.plot(xs.values, med.values, "-", c="white", lw=3.6,
                        alpha=.9, zorder=3)
                ln, = ax.plot(xs.values, med.values, "-", c=cmap[v], lw=2.0,
                              label=glab(v), zorder=4)
                handles.setdefault(j, {}).setdefault(glab(v), ln)
            pl = F2.plateau(d.groupby("width_px").res.median())
            if pl:
                xp = float(d[d.width_px == pl].density_px_per_mm2.median())
                ax.plot([xp], [0], marker="^", ms=4.5, c="#1a1a1a",
                        clip_on=False, transform=ax.get_xaxis_transform(),
                        zorder=6)
            # y 는 선형 — Figure 2 와 같아야 위아래로 견줄 수 있다.
            ax.set_xscale("log")
            ax.set_xticks(F2.XT); ax.set_xticklabels(F2.XTL, fontsize=5.8)
            ax.xaxis.set_minor_locator(mticker.NullLocator())
            ax.tick_params(labelsize=6.5)
            ax.grid(True, which="major", alpha=.3, lw=.4, color="#b8b8b8")
            ax.set_axisbelow(True)
            ax.spines[["top", "right"]].set_visible(False)
            if i == 0:
                ax.set_title("Resultant force error  $\\|\\Delta F\\|$",
                             fontsize=7.5)
            if j == 0:
                ax.set_ylabel(f"{nice}\nMAE [N]", fontsize=7.5)
            ylim.append(ax.get_ylim())

    hi = max(b for _, b in ylim)
    for i in range(len(F2.ROWS)):
        for j in (0, 1):
            ax = axes[i, j]
            ax.set_ylim(0, hi)
            ax.yaxis.set_major_locator(mticker.MaxNLocator(5))
            ax.tick_params(axis="y", labelleft=(j == 0), labelsize=6.5)

    for (x, txt) in ((.295, "Split by gel thickness"),
                     (.775, "Split by gel hardness")):
        fig.text(x, 1.005, txt, fontsize=8.5, weight="bold", ha="center")
        fig.text(x, .072, "Pixel density $R$ [px/mm$^2$]", fontsize=8,
                 ha="center")
    for g, x in ((0, .295), (1, .775)):
        h = handles.get(g, {})
        if h:
            fig.legend(h.values(), h.keys(), frameon=False, fontsize=7.5,
                       title=GROUPS[g][2], title_fontsize=7.5, ncol=3,
                       loc="lower center", bbox_to_anchor=(x, -.012))
    fig.tight_layout(rect=[0, .085, 1, .985])
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig2b_resultant_force.{ext}", dpi=300,
                    bbox_inches="tight")
    plt.close(fig)

    rows = []
    for pr, _ in F2.ROWS:
        d = load(pr)
        if d is not None:
            rows.append(d.assign(principle=pr))
    pd.concat(rows).to_csv(OUT / "fig2b_resultant_force.csv", index=False)
    print("  -> paper/figures/fig2b_resultant_force.{png,pdf,csv}")


if __name__ == "__main__":
    main()
