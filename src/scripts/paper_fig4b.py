#!/usr/bin/env python3
"""Figure 4b — Figure 2b 와 같은 배치로 그린 **형상 복원 오차**.

Figure 4 는 한 유닛의 복원 예시와 전체 중앙값 곡선을 보인다. 이 그림은 그것을
**겔 설계로 갈라** 놓는다 (2026-09-14, 운전자 지시): 가는 선이 시편 하나,
굵은 선이 군 중앙값, 왼쪽은 두께로 오른쪽은 경도로 같은 자료를 두 번 나눈다.
힘 쪽 Figure 2·2b 와 같은 질문을 형상에 던지는 것이다 — *겔 설계가 곡선을
가르는가.*

행은 **원리 x 압자** 넷이다. 압자를 합치지 않는 이유는 둘이 다르게 움직이기
때문이다 — 정육면체는 모서리가 있어 평면 압자처럼 굴고, 원기둥은 곡면이다.

**y 축은 원리끼리만 공유한다.** 두 파이프라인의 절대 오차로 우열을 매기면 안
된다 — 광도 스테레오는 0.010 ~ 0.578 mm 를, 밝기→깊이는 그보다 깊은 구간을
평가한다(`shape_reconstruction.md` §4). 같은 자가 아니므로 세로로 견주지 말 것.
행 묶음 안에서 **해상도에 따른 모양**만 읽는다.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

import pixel_density as PD
import result_common as RC
from palette import HARD3, THICK3

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
AN = ROOT / "data" / "analysis" / "digit_shape"
OUT = ROOT / "paper" / "figures"
GROUPS = [("thickness_mm", THICK3, "Gel thickness", lambda v: f"{v} mm"),
          ("hardness", HARD3, "Gel hardness", lambda v: v)]
XT = [0.1, 1, 10, 100, 1000, 10000]
XTL = ["0.1", "1", "10", "100", "1000", "10⁴"]


def tidy(d, pr):
    d = d.copy()
    d["thickness_mm"] = d.sensor.str.extract(r"_(\d)mm_")[0].astype(int)
    d["hardness"] = d.sensor.str.extract(r"^(soft|medium|hard)_")[0]
    return PD.add(d, pr)


def load(pr, probe, single=True):
    """한 원리·한 압자의 (시편, 폭) -> MAE."""
    if pr == "9DTact":
        f = DS / "9DTact" / "shape_vs_resolution.csv"
        if not f.exists():
            return None
        d = pd.read_csv(f)
        d = d[d.width_px.notna()].copy()
        d["width_px"] = d.width_px.astype(int)
        d = d.rename(columns={f"{probe}_raw_mae": "mae"})
        d = d[["sensor", "width_px", "mae"]].dropna()
    else:
        f = AN / "DIGIT_shape_vs_resolution.csv"
        if not f.exists():
            return None
        d = pd.read_csv(f)
        d = d[d["shape"] == probe].copy()
        d["mae"] = (d.depth_pred_mm - d.depth_true_mm).abs()
        d = (d.groupby(["unit", "width_px"]).mae.mean().reset_index()
               .rename(columns={"unit": "sensor"}))
    d = RC.keep(d, pr, "sensor")
    if single:
        d = d[d.sensor.isin(RC.chosen(pr))]
    return tidy(d, pr) if len(d) else None


ROWS = [("9DTact", "cyl4", "Depth-referenced\ncylinder ⌀4 mm"),
        ("9DTact", "cube4", "Depth-referenced\ncube 4 mm"),
        ("DIGIT", "cyl4", "Photometric\ncylinder ⌀4 mm"),
        ("DIGIT", "cube4", "Photometric\ncube 4 mm")]


def main():
    plt.rcParams["font.family"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, axes = plt.subplots(len(ROWS), 2, figsize=(7.16, 7.6), sharex=True)

    hi_by_pr, handles, keep = {}, {}, {}
    for i, (pr, probe, nice) in enumerate(ROWS):
        d = load(pr, probe)
        keep[i] = d
        if d is None:
            continue
        for j, (gcol, cmap, gtitle, glab) in enumerate(GROUPS):
            ax = axes[i, j]
            for u, g in d.groupby("sensor"):
                g = g.sort_values("density_px_per_mm2")
                ax.plot(g.density_px_per_mm2, g.mae, "-",
                        c=cmap[g[gcol].iloc[0]], lw=.8, alpha=.45, zorder=2)
            for v in cmap:
                g = d[d[gcol] == v]
                if not len(g):
                    continue
                med = g.groupby("width_px").mae.median()
                xs = g.groupby("width_px").density_px_per_mm2.median()
                xs = xs.reindex(med.index)
                ax.plot(xs.values, med.values, "-", c="white", lw=3.6,
                        alpha=.9, zorder=3)
                ln, = ax.plot(xs.values, med.values, "-", c=cmap[v], lw=2.0,
                              label=glab(v), zorder=4)
                handles.setdefault(j, {}).setdefault(glab(v), ln)
            ax.set_xscale("log")
            ax.set_xticks(XT); ax.set_xticklabels(XTL, fontsize=5.8)
            ax.xaxis.set_minor_locator(mticker.NullLocator())
            ax.tick_params(labelsize=6.5)
            ax.grid(True, which="major", alpha=.3, lw=.4, color="#b8b8b8")
            ax.set_axisbelow(True)
            ax.spines[["top", "right"]].set_visible(False)
            if i == 0:
                ax.set_title("Shape reconstruction error", fontsize=7.5)
            if j == 0:
                ax.set_ylabel(f"{nice}\ndepth MAE [mm]", fontsize=7.2)
        hi_by_pr.setdefault(pr, []).append(float(np.nanmax(
            d.groupby(["sensor", "width_px"]).mae.median())))

    # y 는 **원리끼리만** 공유한다 — 두 파이프라인의 절대 오차를 세로로 견주면 안 된다
    for i, (pr, probe, _) in enumerate(ROWS):
        if keep.get(i) is None:
            continue
        hi = max(hi_by_pr[pr]) * 1.05
        for j in (0, 1):
            axes[i, j].set_ylim(0, hi)
            axes[i, j].yaxis.set_major_locator(mticker.MaxNLocator(5))
            axes[i, j].tick_params(axis="y", labelleft=(j == 0), labelsize=6.5)

    for (x, txt) in ((.295, "Split by gel thickness"),
                     (.775, "Split by gel hardness")):
        fig.text(x, 1.004, txt, fontsize=8.5, weight="bold", ha="center")
        fig.text(x, .062, "Pixel density $R$ [px/mm$^2$]", fontsize=8,
                 ha="center")
    for g, x in ((0, .295), (1, .775)):
        h = handles.get(g, {})
        if h:
            fig.legend(h.values(), h.keys(), frameon=False, fontsize=7.5,
                       title=GROUPS[g][2], title_fontsize=7.5, ncol=3,
                       loc="lower center", bbox_to_anchor=(x, -.008))
    fig.tight_layout(rect=[0, .072, 1, .987])
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig4b_shape_by_gel.{ext}", dpi=300,
                    bbox_inches="tight")
    plt.close(fig)

    rows = []
    for i, (pr, probe, _) in enumerate(ROWS):
        if keep.get(i) is not None:
            rows.append(keep[i].assign(principle=pr, probe=probe))
    pd.concat(rows).to_csv(OUT / "fig4b_shape_by_gel.csv", index=False)
    print("  -> paper/figures/fig4b_shape_by_gel.{png,pdf,csv}")


if __name__ == "__main__":
    main()
