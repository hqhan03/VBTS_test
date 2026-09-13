#!/usr/bin/env python3
"""Figure 1 — 연구 질문과 비교 방법. 세 패널.

**제목:** Separating contact resolvability from task-specific input resolution.

(a) 겔 설계 — 경도 3 x 두께 3, 두 감지 원리에 같은 하드웨어를 돌려 쓴다.
(b) 두 접촉을 구분하는 능력 — **같은 경도·같은 프로브·같은 압입**의 실제 영상 둘.
(c) 과제가 요구하는 입력 해상도 — 접촉 영상 하나를 줄여 추정기에 넣는다.

**(b) 와 (c) 는 서로 다른 질문이다.** (b) 는 "인접한 두 접촉을 가를 수 있나",
(c) 는 "추정기가 픽셀을 몇 개 필요로 하나". 이 그림은 그 둘을 **잇지 않는다** —
둘이 독립이라는 것은 이 자료로 입증되지 않았고, 화살표를 그리면 입증한 척이 된다.

**(b) 의 두 장을 고른 규칙.** 시각 대비가 가장 큰 둘을 임의로 고르면 안 된다.
같은 경도(hard), 같은 프로브(pair100, 중심 간격 2.0 mm), 같은 압입 단(0.3 mm)
에서 두께만 1 mm 와 3 mm 로 다른 둘을 쓴다. **표시 범위와 대비 배율도 공유한다.**
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mp
import numpy as np
import pandas as pd
import cv2

from palette import HARD3

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset" / "9DTact"
OUT = ROOT / "paper" / "figures"
PAIR = "20260905_passA_pair100"
STEP = "pair100_d0.30_r1.png"
UNITS = [("9DTact_hard_1mm_r1", "1 mm"), ("9DTact_hard_3mm_r1", "3 mm")]
SHOW = [320, 80, 16]


def imprint(unit):
    """기준영상 대비 밝기 변화. 두 장이 같은 자로 그려져야 한다."""
    run = DS / PAIR / unit
    img = cv2.imread(str(run / "shape_pair100" / STEP), cv2.IMREAD_GRAYSCALE)
    ref = cv2.imread(str(run / "reference.png"), cv2.IMREAD_GRAYSCALE)
    if img is None or ref is None:
        return None
    d = np.abs(img.astype(np.float32) - ref.astype(np.float32))
    d = cv2.GaussianBlur(d, (0, 0), 3)
    yx = np.unravel_index(np.argmax(cv2.GaussianBlur(d, (0, 0), 25)), d.shape)
    return d, yx


def main():
    plt.rcParams["font.family"] = ["DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    fig = plt.figure(figsize=(7.16, 3.6))
    gs = fig.add_gridspec(1, 3, width_ratios=[1, 1.25, 1.3], wspace=.38)

    # ---------------------------------------------------------- (a) 설계 --
    ax = fig.add_subplot(gs[0, 0])
    ax.set_xlim(-.55, 3.0); ax.set_ylim(-.85, 3.5); ax.axis("off")
    ax.text(1.35, 3.35, "(a) Elastomer design", fontsize=8.5, ha="center",
            weight="bold")
    for i, h in enumerate(["soft", "medium", "hard"]):
        for j, t in enumerate([1, 2, 3]):
            ax.add_patch(mp.Rectangle((j * 1.0, 2.3 - i * .78), .82,
                                      .10 + t * .13, fc=HARD3[h], ec="none",
                                      alpha=.9))
            ax.add_patch(mp.Rectangle((j * 1.0, 2.22 - i * .78), .82, .08,
                                      fc="#444", ec="none"))
        ax.text(-.12, 2.4 - i * .78, h, fontsize=7, ha="right", va="bottom")
    for j, t in enumerate([1, 2, 3]):
        ax.text(j * 1.0 + .41, -.12, f"{t} mm", fontsize=7, ha="center")
    ax.text(1.15, -.40, "3 hardness × 3 thickness × 2 replicates",
            fontsize=6.5, ha="center")
    ax.text(1.15, -.66, "same body reused: depth-referenced ·\n"
                        "photometric (+ marker variant)", fontsize=6.0,
            ha="center", color="#555")

    # -------------------------------------- (b) 두 접촉을 가를 수 있는가 --
    sub = gs[0, 1].subgridspec(2, 2, height_ratios=[1.15, 1], hspace=.32,
                               wspace=.12)
    dat, vmax = {}, 0
    for u, lab in UNITS:
        r = imprint(u)
        if r is None:
            continue
        dat[lab] = r
        vmax = max(vmax, float(np.percentile(r[0], 99.9)))
    for k, (u, lab) in enumerate(UNITS):
        if lab not in dat:
            continue
        d, (cy, cx) = dat[lab]
        half = 240
        y0 = int(np.clip(cy - half, 0, d.shape[0] - 2 * half))
        x0 = int(np.clip(cx - half, 0, d.shape[1] - 2 * half))
        sl = d[y0:y0 + 2 * half, x0:x0 + 2 * half]
        ax = fig.add_subplot(sub[0, k])
        ax.imshow(sl, cmap="magma", vmin=0, vmax=vmax)   # **같은 표시 범위**
        ax.set_title(f"{lab} gel", fontsize=8)
        ax.set_xticks([]); ax.set_yticks([])

    ax = fig.add_subplot(sub[1, :])
    for (u, lab), c in zip(UNITS, ("#0072B2", "#D55E00")):
        if lab not in dat:
            continue
        d, (cy, cx) = dat[lab]
        x0p = int(np.clip(cx - 240, 0, d.shape[1] - 480))
        prof = d[int(np.clip(cy, 0, d.shape[0] - 1)), x0p:x0p + 480]
        ax.plot(np.arange(len(prof)) - len(prof) / 2, prof, "-", c=c, lw=1.4,
                label=f"{lab}")
    ax.axhline(2.5, c="#1a1a1a", ls=":", lw=1.0)
    ax.text(.98, .93, "decision floor 2.5", transform=ax.transAxes,
            fontsize=6.2, ha="right", va="top", color="#1a1a1a")
    ax.set_xlabel("across the two posts [px]", fontsize=7.5)
    ax.set_ylabel("Δ intensity", fontsize=7.5)
    ax.tick_params(labelsize=6.5)
    ax.legend(frameon=False, fontsize=6.5, loc="upper left")
    ax.spines[["top", "right"]].set_visible(False); ax.grid(alpha=.3, lw=.4)

    # ------------------------------------- (c) 과제가 요구하는 입력 해상도 --
    sub = gs[0, 2].subgridspec(2, 3, height_ratios=[1.15, 1], hspace=.32,
                               wspace=.12)
    run = DS / "20260907_passB_ball8" / "9DTact_hard_2mm_r1"
    cand = sorted((run / "stream").glob("*.png")) if (run / "stream").exists() else []
    base = cv2.imread(str(cand[len(cand) // 2]), cv2.IMREAD_GRAYSCALE) if cand else None
    for k, w in enumerate(SHOW):
        ax = fig.add_subplot(sub[0, k])
        if base is not None:
            h = int(round(w * base.shape[0] / base.shape[1]))
            sm = cv2.resize(base, (w, h), interpolation=cv2.INTER_AREA)
            ax.imshow(sm, cmap="gray")
        ax.set_title(f"{w} px", fontsize=7.5)
        ax.set_xticks([]); ax.set_yticks([])

    ax = fig.add_subplot(sub[1, :])
    f2 = OUT / "fig2_force_vs_resolution.csv"
    if f2.exists():
        g = pd.read_csv(f2)
        g = g[(g.principle == "9DTact") & (g.measure == "fz_mae")]
        med = g.groupby("width_px").mae_N.median()
        ax.plot(med.index, med.values, "-o", c="#1a1a1a", lw=1.5, ms=3)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks([8, 80, 1920]); ax.set_xticklabels(["8", "80", "1920"],
                                                     fontsize=6.5)
    ax.minorticks_off()
    ax.set_xlabel("input width [px]", fontsize=7.5)
    ax.set_ylabel("force MAE [N]", fontsize=7.5)
    ax.tick_params(labelsize=6.5)
    ax.spines[["top", "right"]].set_visible(False); ax.grid(alpha=.3, lw=.4)

    fig.text(.455, .985, "(b) Two distinct contacts", fontsize=8.5,
             ha="center", weight="bold")
    fig.text(.83, .985, "(c) Task input resolution", fontsize=8.5,
             ha="center", weight="bold")
    fig.suptitle("Separating contact resolvability from task-specific input "
                 "resolution", fontsize=9.5, y=1.09)
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig1_question_and_design.{ext}", dpi=300,
                    bbox_inches="tight")
    plt.close(fig)
    print("  -> paper/figures/fig1_question_and_design.{png,pdf}")


if __name__ == "__main__":
    main()
