#!/usr/bin/env python3
"""축별 힘·토크 MAE 대 해상도 — 유닛 18 개 격자 + 원리 요약.

모델은 ResNet-18 의 fc 를 6 출력으로 바꾼 것이라 Fx, Fy, Fz, Tx, Ty, Tz 를 모두
예측한다. 2026-09-12 이전에는 Fx, Fy 를 CSV 에 쓰지 않고 hypot 으로 합친
`lat_mae` 만 남겼다 — 방향별 성능이 보이지 않았다.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
RES = ROOT / "result"
FOLD = {"9DTact": "1_9DTact", "DIGIT": "2_DIGIT", "DIGIT_Marker": "3_DIGIT_Marker"}
REP = {"9DTact": "grey", "DIGIT": "raw", "DIGIT_Marker": "inpaint"}
AX = [("fx_mae", "Fx", "#c2553a"), ("fy_mae", "Fy", "#d9a441"),
      ("fz_mae", "Fz", "#1f6f8b")]
TQ = [("tx_mae", "Tx", "#c2553a"), ("ty_mae", "Ty", "#d9a441"),
      ("tz_mae", "Tz", "#1f6f8b")]
HARD = ["soft", "medium", "hard"]


def load(pr):
    f = DS / pr / "force_vs_resolution_axes.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    d["hardness"] = d.sensor.str.split("_").str[0]
    d["thickness_mm"] = d.sensor.str.extract(r"_(\d)mm_").astype(int)
    d["rep"] = d.sensor.str[-1].astype(int)
    return d


def panel(pr, d, cols, stem, ylab):
    units = [f"{h}_{t}mm_r{r}" for h in HARD for t in (1, 2, 3) for r in (1, 2)]
    fig, axes = plt.subplots(3, 6, figsize=(19, 9), sharex=True, sharey=True)
    for ax, u in zip(axes.ravel(), units):
        g = d[d.sensor == u]
        if not len(g):
            ax.text(.5, .5, "자료 없음", ha="center", va="center", fontsize=8,
                    color="#999", transform=ax.transAxes)
            ax.set_title(u, fontsize=8, color="#999")
            continue
        for c, lab, col in cols:
            k = g.groupby("width_px")[c].agg(["median", "min", "max"])
            ax.plot(k.index, k["median"], "-o", c=col, lw=1.5, ms=3.2,
                    mec="white", mew=.5, label=lab)
            ax.fill_between(k.index, k["min"], k["max"], color=col, alpha=.16, lw=0)
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set_title(u, fontsize=8.5); ax.tick_params(labelsize=7)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=.22, lw=.5, which="both"); ax.set_axisbelow(True)
    for ax in axes[-1]:
        ax.set_xlabel("가로 해상도 (px)", fontsize=8)
    for ax in axes[:, 0]:
        ax.set_ylabel(ylab, fontsize=8)
    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper right", frameon=False, fontsize=9.5, ncol=3)
    fig.suptitle(f"{pr} — {ylab} 대 해상도 (입력 표현 `{REP[pr]}`, seed 3 개의 "
                 f"중앙값과 범위)", fontsize=12, x=.09, ha="left")
    fig.tight_layout(rect=[0, 0, 1, .96])
    p = RES / FOLD[pr] / "figures"
    p.mkdir(parents=True, exist_ok=True)
    fig.savefig(p / f"{stem}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def summary(pr, d):
    """원리 하나의 축별 중앙값 — 무릎이 어디인지 한눈에."""
    fig, ax = plt.subplots(figsize=(5.6, 3.8))
    rows = []
    for c, lab, col in AX:
        k = d.groupby("width_px")[c].median()
        ax.plot(k.index, k.values, "-o", c=col, lw=1.8, ms=5, mec="white",
                mew=.7, label=lab)
        b = k.idxmin()
        ax.plot(b, k[b], "*", c=col, ms=14, mec="white", mew=.8, zorder=5)
        rows.append(pd.DataFrame(dict(axis=lab, width_px=k.index, mae=k.values)))
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("가로 해상도 (px)"); ax.set_ylabel("MAE (N)")
    ax.set_title(f"{pr} — 축별 힘 오차 대 해상도 (★ = 최소)", fontsize=10.5, loc="left")
    ax.legend(frameon=False, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=.25, lw=.6, which="both"); ax.set_axisbelow(True)
    p = RES / FOLD[pr]
    (p / "figures").mkdir(parents=True, exist_ok=True)
    (p / "data").mkdir(parents=True, exist_ok=True)
    fig.savefig(p / "figures" / "force_mae_summary.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    pd.concat(rows).to_csv(p / "data" / "force_mae_summary.csv", index=False)


def main():
    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    # NanumGothic 에 유니코드 마이너스(U+2212) 글리프가 없어 축 라벨이
    # "6 x 10<깨짐>2" 로 나온다. ASCII 하이픈을 쓰게 한다.
    plt.rcParams["axes.unicode_minus"] = False
    for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
        d = load(pr)
        if d is None or not len(d):
            print(f"  {pr}: 아직 자료 없음"); continue
        p = RES / FOLD[pr] / "data"
        p.mkdir(parents=True, exist_ok=True)
        d.to_csv(p / "force_mae_vs_resolution.csv", index=False)
        panel(pr, d, AX, "force_mae_vs_resolution_18units", "힘 MAE (N)")
        panel(pr, d, TQ, "torque_mae_vs_resolution_18units", "토크 MAE (N·m)")
        summary(pr, d)
        k = d.groupby("width_px")[[c for c, _, _ in AX]].median()
        print(f"  {pr:<13} {len(d)} 행, {d.sensor.nunique()} 유닛  "
              f"최소: Fx {k.fx_mae.idxmin()}px  Fy {k.fy_mae.idxmin()}px  "
              f"Fz {k.fz_mae.idxmin()}px")


if __name__ == "__main__":
    main()
