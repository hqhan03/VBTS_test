#!/usr/bin/env python3
"""Figure 1 — 연구 질문과 비교 방법. 세 패널.

**제목:** Separating contact resolvability from task-specific input resolution.

(a) 겔 설계 — 경도 3 x 두께 3, 두 감지 원리에 같은 하드웨어를 돌려 쓴다.
(b) 두 접촉을 구분하는 능력 — **같은 경도·같은 프로브·같은 압입**의 실제 영상 둘.
(c) 과제가 요구하는 입력 해상도 — 접촉 영상 하나를 줄여 추정기에 넣는다.

**(b) 와 (c) 는 서로 다른 질문이다.** (b) 는 "인접한 두 접촉을 가를 수 있나",
(c) 는 "추정기가 픽셀을 몇 개 필요로 하나". 이 그림은 그 둘을 **잇지 않는다** —
둘이 독립이라는 것은 이 자료로 입증되지 않았고, 화살표를 그리면 입증한 척이 된다.

**배치** (2026-09-14 에 다시 짰다). 그림 수준의 2 x 3 격자 하나를 쓴다 — (a) 가
왼쪽 열을 세로로 다 쓰고, (b) 와 (c) 는 **같은 격자의 같은 행**에 얹힌다. 그래야
영상 줄과 그래프 줄이 패널 사이에서 나란해진다. 전에는 패널마다 자기 격자를 따로
만들어 영상과 그래프의 높이가 어긋났고, 패널 이름 셋의 높이도 제각각이었다.
패널 이름은 **그린 뒤 축의 실제 위치에서** x 를 구해 같은 높이에 놓는다.

**(b) 의 두 장을 고른 규칙.** 시각 대비가 가장 큰 둘을 임의로 고르면 안 된다.
같은 경도(hard), 같은 프로브(pair100, 중심 간격 2.0 mm), 같은 압입 단(0.3 mm)
에서 두께만 1 mm 와 3 mm 로 다른 둘을 쓴다. **표시 범위와 대비 배율도 공유한다.**
"""
import re
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mp
import numpy as np
import pandas as pd
import cv2
import yaml

import pixel_density as PD
from palette import HARD3

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset" / "9DTact"
OUT = ROOT / "paper" / "figures"
PAIR = "20260905_passA_pair100"
STEP = "pair100_d0.30_r1.png"
UNITS = [("9DTact_hard_1mm_r1", "1 mm"), ("9DTact_hard_3mm_r1", "3 mm")]
SHOW = [320, 80, 16]

# (b) 의 조건은 **파일 이름과 probes.yaml 에서 뽑는다.** 손으로 적으면 STEP 이나
# 프로브를 바꿀 때 캡션만 옛날 값으로 남는다.
DEPTH_MM = float(re.search(r"_d([\d.]+)_", STEP).group(1))


def pair_geometry(pid=PAIR.split("_")[-1]):
    """기둥 지름과 중심 간격 (mm). 중심 간격 = 지름 + 틈."""
    f = ROOT / "src" / "config" / "probes.yaml"
    for pr in yaml.safe_load(f.read_text())["probes"]:
        if pr.get("id") == pid:
            d = float(pr["element_diameter_mm"])
            return d, d + float(pr["gap_mm"])
    return None, None


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
    fig = plt.figure(figsize=(7.16, 3.9))
    gs = fig.add_gridspec(2, 3, width_ratios=[.95, 1.18, 1.36],
                          height_ratios=[.88, 1.0], wspace=.40, hspace=.38,
                          left=.065, right=.995, top=.745, bottom=.125)

    # ---------------------------------------------------------- (a) 설계 --
    # 왼쪽 열을 세로로 다 쓴다. 위쪽이 3x3 그림, 아래쪽이 설명 두 줄이다.
    axa = ax = fig.add_subplot(gs[:, 0])
    # 세로로 긴 칸을 쓰므로 **행 간격을 벌려** 그림이 칸을 채우게 한다. 전에는
    # 블록이 위쪽에 몰리고 아래 절반이 비어 (b)·(c) 와 무게가 맞지 않았다.
    ax.set_xlim(-.66, 3.04); ax.set_ylim(-1.30, 3.05); ax.axis("off")
    for i, h in enumerate(["soft", "medium", "hard"]):
        for j, t in enumerate([1, 2, 3]):
            ax.add_patch(mp.Rectangle((j * 1.0, 2.30 - i * 1.0), .82,
                                      .10 + t * .13, fc=HARD3[h], ec="none",
                                      alpha=.9))
            ax.add_patch(mp.Rectangle((j * 1.0, 2.22 - i * 1.0), .82, .08,
                                      fc="#444", ec="none"))
        ax.text(-.16, 2.40 - i * 1.0, h, fontsize=7, ha="right", va="bottom")
    for j, t in enumerate([1, 2, 3]):
        ax.text(j * 1.0 + .41, -.16, f"{t} mm", fontsize=7, ha="center")
    # 한 줄로 두면 칸보다 넓어 왼쪽으로 삐져나간다 — 두 줄로 끊는다.
    ax.text(1.2, -.66, "3 hardness × 3 thickness\n× 2 replicates",
            fontsize=6.8, ha="center", linespacing=1.45)
    ax.text(1.2, -1.20, "same body reused: depth-referenced ·\n"
                        "photometric (+ marker variant)", fontsize=6.2,
            ha="center", color="#555", linespacing=1.45)

    # -------------------------------------- (b) 두 접촉을 가를 수 있는가 --
    sub = gs[0, 1].subgridspec(1, 2, wspace=.10)
    bx, cx_ = [], []
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
        ax.set_title(f"{lab} gel", fontsize=7.5, pad=3)
        ax.set_xticks([]); ax.set_yticks([])
        bx.append(ax)

    ax = fig.add_subplot(gs[1, 1]); bx.append(ax)
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
    sub = gs[0, 2].subgridspec(1, 3, wspace=.10)
    run = DS / "20260907_passB_ball8" / "9DTact_hard_2mm_r1"
    cand = sorted((run / "stream").glob("*.png")) if (run / "stream").exists() else []
    base = cv2.imread(str(cand[len(cand) // 2]), cv2.IMREAD_GRAYSCALE) if cand else None
    for k, w in enumerate(SHOW):
        ax = fig.add_subplot(sub[0, k]); cx_.append(ax)
        if base is not None:
            h = int(round(w * base.shape[0] / base.shape[1]))
            sm = cv2.resize(base, (w, h), interpolation=cv2.INTER_AREA)
            ax.imshow(sm, cmap="gray")
        # **제목은 밀도가 먼저다.** 픽셀 폭은 그 단을 가리키는 이름일 뿐이고,
        # 이 패널이 묻는 것은 "실제 면적당 화소가 몇 개냐" 다.
        R = PD.density("9DTact", "hard_2mm_r1", w)
        ax.set_title(f"$R$ = {PD.fmt(R)}\n{w} px wide", fontsize=6.6,
                     linespacing=1.35, pad=3)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_anchor("N")

    ax = fig.add_subplot(gs[1, 2]); cx_.append(ax)
    f2 = OUT / "fig2_force_vs_resolution.csv"
    if f2.exists():
        g = pd.read_csv(f2)
        g = g[(g.principle == "9DTact") & (g.measure == "fz_mae")]
        # x 는 화소 밀도다 — 픽셀 폭은 유닛마다 다른 물리 샘플링이라 견줄 수 없다.
        med = g.groupby("width_px").agg(
            mae_N=("mae_N", "median"),
            R=("density_px_per_mm2", "median"))
        ax.plot(med.R.values, med.mae_N.values, "-o", c="#1a1a1a", lw=1.5, ms=3)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks([0.1, 10, 1000])
    ax.set_xticklabels(["0.1", "10", "1000"], fontsize=6.5)
    ax.minorticks_off()
    ax.set_xlabel("pixel density $R$ [px/mm$^2$]", fontsize=7.5)
    # 로그 y 축에서 minorticks_off 가 눈금을 전부 지워 버렸다 — 되살린다.
    ax.set_yticks([0.05, 0.1])
    ax.set_yticklabels(["0.05", "0.1"], fontsize=6.5)
    ax.set_ylabel("force MAE [N]", fontsize=7.5)
    ax.tick_params(labelsize=6.5)
    ax.spines[["top", "right"]].set_visible(False); ax.grid(alpha=.3, lw=.4)

    # 패널 이름 셋을 **같은 높이**에, 각 패널이 실제로 차지한 x 범위의 가운데에.
    # 손으로 찍은 x 는 열 너비를 바꿀 때마다 어긋난다.
    fig.canvas.draw()
    dia, pitch = pair_geometry()
    bsub = (f"hard gel, {DEPTH_MM:.2f} mm indentation\n"
            f"two {dia:.1f} mm posts, {pitch:.2f} mm apart"
            if dia else f"hard gel, {DEPTH_MM:.2f} mm indentation")
    groups = [([axa], "(a) Elastomer design", None),
              (bx, "(b) Two distinct contacts", bsub),
              (cx_, "(c) Task input resolution",
               "one contact frame, area-averaged down\n"
               "$R$ = pixels per mm² of gel surface")]
    for axs, lab, sub_ in groups:
        pos = [a.get_position() for a in axs if a is not None]
        if not pos:
            continue
        xc = (min(p.x0 for p in pos) + max(p.x1 for p in pos)) / 2
        fig.text(xc, .915, lab, fontsize=8.5, ha="center", weight="bold")
        if sub_:
            # 축 위쪽이 .745 이고 그 위를 이미지 제목이 쓰므로, 조건 줄은 그보다
            # 더 위에 둔다. 전에는 .845 라 제목과 겹쳤다.
            fig.text(xc, .878, sub_, fontsize=6.0, ha="center", va="top",
                     color="#555", linespacing=1.4)
    fig.suptitle("Separating contact resolvability from task-specific input "
                 "resolution", fontsize=9.5, y=.975)
    OUT.mkdir(parents=True, exist_ok=True)
    for ext in ("png", "pdf"):
        fig.savefig(OUT / f"fig1_question_and_design.{ext}", dpi=300,
                    bbox_inches="tight")
    plt.close(fig)
    print("  -> paper/figures/fig1_question_and_design.{png,pdf}")


if __name__ == "__main__":
    main()
