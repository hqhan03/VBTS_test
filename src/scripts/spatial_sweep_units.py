#!/usr/bin/env python3
"""센서마다 — 어느 화소 밀도에서 어느 중심 간격까지 분해되나.

`resolution_sweep.py` 를 **모든 간격**(pair010 ~ pair150, 중심 간격 1.10 ~
2.50 mm)에 대해 돌린 결과를 센서별 한 판으로 모은다 (2026-09-14, 운전자 요청).

**판정을 세는 규칙.** 한 (유닛, 간격, 폭) 칸에는 깊이 사다리가 여러 단 들어
있다. 그 중 **하나라도 분해되면 그 칸을 분해로 센다** — 묻는 것이 "이 간격을
가를 수 있는가" 이지 "모든 깊이에서 가르는가" 가 아니기 때문이다. 대신 몇
단에서 갈렸는지를 점 크기로 보인다: 작은 점은 한 단만 간신히 갈린 것이다.

**읽는 법.** 굵은 계단선이 그 밀도에서 **분해되는 가장 좁은 간격**이다. 아래로
내려갈수록 좋다. 선이 끊긴 구간은 어느 간격도 분해되지 않은 곳이다.

**DIGIT_Marker 는 없다** — 공간 분해능을 재지 않았다(운전자 결정, 2026-09-11).
DIGIT 은 pair010 과 pair025 만 있다.
"""
import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
import yaml

import result_common as RC

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "result" / "single" if RC.SINGLE else ROOT / "result"
XT = [0.1, 1, 10, 100, 1000, 10000]
XTL = ["0.1", "1", "10", "100", "1000", "10⁴"]


def sep_mm():
    cfg = yaml.safe_load((ROOT / "src" / "config" / "probes.yaml").read_text())
    return {p["id"]: float(p["element_diameter_mm"]) + float(p["gap_mm"])
            for p in cfg["probes"] if p["tip"] == "cylinder_pair"}


def load(pr):
    rows = []
    for f in sorted(glob.glob(str(RES.parent / "extra" / "data"
                                  / f"resolution_sweep_{pr}_pair*.csv"))):
        rows.append(pd.read_csv(f))
    if not rows:
        return None
    d = pd.concat(rows, ignore_index=True)
    d = RC.keep(d, pr, "unit")
    if RC.SINGLE:
        d = d[d.unit.isin(RC.chosen(pr))]
    S = sep_mm()
    d["sep_mm"] = d.probe.map(S)
    return d.dropna(subset=["sep_mm", "density_px_per_mm2"])


def panel(ax, g, title):
    """x = 화소 밀도, y = 중심 간격. 점 = 그 칸에서 갈린 깊이 단의 수."""
    cell = (g.assign(ok=g.verdict.eq("분해"))
             .groupby(["sep_mm", "width_px", "density_px_per_mm2"])
             .agg(n_ok=("ok", "sum"), n=("ok", "size")).reset_index())
    bad = cell[cell.n_ok == 0]
    ax.scatter(bad.density_px_per_mm2, bad.sep_mm, s=9, marker="x",
               c="#c9c9c9", lw=.8, zorder=2)
    good = cell[cell.n_ok > 0]
    ax.scatter(good.density_px_per_mm2, good.sep_mm,
               s=16 + 34 * good.n_ok / good.n.clip(lower=1),
               c="#0072B2", alpha=.85, ec="white", lw=.5, zorder=3)
    # 굵은 계단선 — 그 밀도에서 분해되는 가장 좁은 간격
    best = good.groupby("width_px").agg(
        R=("density_px_per_mm2", "median"), s=("sep_mm", "min")).sort_values("R")
    if len(best):
        ax.step(best.R, best.s, where="mid", c="#D55E00", lw=2.0, zorder=4)
    ax.set_xscale("log")
    ax.set_xticks(XT); ax.set_xticklabels(XTL, fontsize=6.5)
    ax.xaxis.set_minor_locator(mticker.NullLocator())
    ax.set_yticks(sorted(cell.sep_mm.unique()))
    ax.set_yticklabels([f"{v:.2f}" for v in sorted(cell.sep_mm.unique())],
                       fontsize=6.5)
    ax.set_title(title, fontsize=8.5)
    ax.tick_params(labelsize=6.5)
    ax.grid(alpha=.3, lw=.4); ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def main():
    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    out = []
    for pr in ("9DTact", "DIGIT"):
        d = load(pr)
        if d is None or not len(d):
            continue
        units, ncol = RC.grid(pr)
        units = [u for u in units if u in set(d.unit)]
        ncol = min(ncol, 3) if len(units) <= 9 else ncol
        nrow = int(np.ceil(len(units) / ncol))
        fig, axes = plt.subplots(nrow, ncol, figsize=(3.3 * ncol, 2.6 * nrow),
                                 squeeze=False, sharex=True, sharey=True)
        for ax, u in zip(axes.ravel(), units):
            tt, tc = RC.title(pr, u)
            panel(ax, d[d.unit == u], tt)
            ax.title.set_color(tc)
        for ax in axes.ravel()[len(units):]:
            ax.axis("off")
        for ax in axes[-1]:
            ax.set_xlabel("화소 밀도 R (px/mm²)", fontsize=8)
        for ax in axes[:, 0]:
            ax.set_ylabel("중심 간격 (mm)", fontsize=8)
        fig.suptitle(f"{pr} — 어느 화소 밀도에서 어느 간격까지 분해되나 "
                     "(파랑 = 그 칸에서 갈린 깊이 단이 있다, 크기 = 몇 단, "
                     "주황 계단 = 분해되는 가장 좁은 간격)", fontsize=9.5,
                     x=.01, ha="left")
        fig.tight_layout(rect=[0, 0, 1, .97])
        p = RES / "extra"
        (p / "figures").mkdir(parents=True, exist_ok=True)
        (p / "data").mkdir(parents=True, exist_ok=True)
        stem = f"K_spatial_sweep_{pr}"
        fig.savefig(p / "figures" / f"{stem}.png", dpi=200, bbox_inches="tight")
        plt.close(fig)
        cell = (d.assign(ok=d.verdict.eq("분해"))
                 .groupby(["unit", "sep_mm", "width_px", "density_px_per_mm2"])
                 .agg(n_ok=("ok", "sum"), n=("ok", "size")).reset_index())
        cell.assign(principle=pr).to_csv(p / "data" / f"{stem}.csv", index=False)
        out.append((pr, len(units), cell))
        print(f"    -> extra/figures/{stem}.png  ({len(units)} 유닛)")
    for pr, n, cell in out:
        g = cell[cell.n_ok > 0]
        if len(g):
            b = g.groupby("width_px").agg(R=("density_px_per_mm2", "median"),
                                          s=("sep_mm", "min"))
            i = b.s.idxmin()
            print(f"  {pr}: 가장 좁게 갈린 간격 {b.s.min():.2f} mm "
                  f"@ R {b.loc[i, 'R']:.0f} px/mm² ({i} px)")


if __name__ == "__main__":
    main()
