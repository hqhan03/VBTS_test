#!/usr/bin/env python3
"""논문 그림 — 두 질문. (I 장)

(a) **인접한 두 접촉을 가를 수 있나.** 같은 경도·같은 프로브·같은 압입에서
    두께만 1 mm 와 3 mm 로 다른 실제 영상 둘, 그리고 두 기둥을 가로지른 단면.
(b) **추정기가 화소를 몇 개 필요로 하나.** 접촉 프레임 하나를 면적 평균으로
    줄여 넣고 힘 오차를 본다.

**둘을 잇지 않는다.** 서로 다른 질문이고, 둘이 독립이라는 것은 이 자료로
입증되지 않았다. 화살표를 그리면 입증한 척이 된다. 이 규율이 논문 전체의
주장 강도를 정한다.

(a) 의 두 장을 고른 규칙
    시각 대비가 가장 큰 둘을 임의로 고르면 안 된다. 같은 경도(hard), 같은
    프로브(`pair100`, 기둥 ⌀1.0 mm 둘, 중심 간격 2.00 mm), 같은 압입 단
    (0.30 mm)에서 **두께만** 다른 둘을 쓴다. 그리는 것은 원본이 아니라
    `|접촉 − 기준|` 이고 (σ = 3 평활), **두 장이 같은 표시 범위**를 쓴다.

회색조로 그린다
    영상은 넷 뿐인 팔레트(파랑·초록·빨강·검정) 밖이므로 색 지도를 쓰지 않는다.
    (a) 의 자국과 (b) 의 축소 프레임이 같은 회색조라 나란히 읽힌다.

`data/` 없이 돌아간다
    그림에 들어가는 다섯 장이 `paper/figures/sources/` 에 있고, 화소 밀도는
    `paper/figures/fig2_force_vs_resolution.csv` 에서 읽는다 —
    `pixel_density.density()` 는 `data/analysis/` 를 봐야 해서 쓰지 않는다.

캡션이 져야 할 것
    1. (a) 가 **두께만 다른 두 시편**(hard, 1 mm 대 3 mm)이고 같은 프로브·같은
       압입·**같은 표시 범위**라는 것. 그리는 것은 기준영상 대비 밝기 변화다.
    2. (a) 아래의 **점선이 판정 바닥 2.5 그레이 레벨**이라는 것. 선은 있고
       글자는 없다.
    3. (b) 의 곡선이 **9DTact 아홉 시편의 중앙값**이고, 영상 셋은 그중
       `hard_2mm_r1` 한 장을 줄인 것이라는 것.
    4. **(a) 와 (b) 는 잇지 않는다** — 서로 다른 질문이다.

자료
    영상 `paper/figures/sources/` (다섯 장, 1920×1080 원본)
    곡선 `paper/figures/fig2_force_vs_resolution.csv`
"""
import re

import cv2
import numpy as np
import pandas as pd
import yaml

import paper_style as PS
from paper_style import THICK3

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402

SRC = PS.ROOT / "paper" / "figures" / "sources"
FORCE_CSV = PS.ROOT / "paper" / "figures" / "fig2_force_vs_resolution.csv"

UNITS = [("hard_1mm_r1", 1), ("hard_3mm_r1", 3)]   # 두께만 다르다
STEP = "pair100_d0.30"
SHOW_PX = [320, 80, 16]                            # (b) 가 보여 주는 세 단
SWEEP_UNIT = "hard_2mm_r1"                         # (b) 의 영상이 나온 유닛
DECISION_FLOOR = 2.5                               # 자국 밝기 판정 바닥 (lvl)
HALF = 240                                         # 자국 잘라내는 반폭 (px)

DEPTH_MM = float(re.search(r"_d([\d.]+)", STEP).group(1))


def pair_geometry(pid="pair100"):
    """기둥 지름과 중심 간격 (mm). 손으로 적지 않고 `probes.yaml` 에서 뽑는다."""
    f = PS.ROOT / "src" / "config" / "probes.yaml"
    for pr in yaml.safe_load(f.read_text())["probes"]:
        if pr.get("id") == pid:
            d = float(pr["element_diameter_mm"])
            return d, d + float(pr["gap_mm"])
    return None, None


def imprint(unit):
    """기준영상 대비 밝기 변화와 자국 중심. 두 장이 같은 자로 그려져야 한다."""
    img = cv2.imread(str(SRC / f"fig1b_{unit}_{STEP}.png"), cv2.IMREAD_GRAYSCALE)
    ref = cv2.imread(str(SRC / f"fig1b_{unit}_reference.png"), cv2.IMREAD_GRAYSCALE)
    assert img is not None and ref is not None, f"{unit} 의 원본이 없다"
    d = cv2.GaussianBlur(np.abs(img.astype(np.float32) - ref.astype(np.float32)),
                         (0, 0), 3)
    cy, cx = np.unravel_index(np.argmax(cv2.GaussianBlur(d, (0, 0), 25)), d.shape)
    return d, int(cy), int(cx)


def density_of(width_px, unit=SWEEP_UNIT):
    """그 단의 화소 밀도. `fig2` csv 가 유닛·폭마다 들고 있다."""
    g = pd.read_csv(FORCE_CSV)
    g = g[(g.principle == "9DTact") & (g.sensor == unit) & (g.width_px == width_px)]
    assert len(g), f"{unit} 의 {width_px} px 단이 csv 에 없다"
    return float(g.density_px_per_mm2.median())


def main():
    dat = {t: imprint(u) for u, t in UNITS}
    vmax = max(float(np.percentile(d, 99.9)) for d, _, _ in dat.values())

    fig = plt.figure(figsize=(PS.FULL_W_NARROW, 3.30))
    gs = fig.add_gridspec(2, 2, width_ratios=[1.0, 1.28],
                          height_ratios=[1.0, 1.02], wspace=0.34, hspace=0.42,
                          left=0.085, right=0.995, top=0.90, bottom=0.135)

    # ------------------------------------------- (a) 두 접촉을 가를 수 있나 --
    a_axes, b_axes = [], []
    top = gs[0, 0].subgridspec(1, 2, wspace=0.08)
    for k, (_u, t) in enumerate(UNITS):
        d, cy, cx = dat[t]
        y0 = int(np.clip(cy - HALF, 0, d.shape[0] - 2 * HALF))
        x0 = int(np.clip(cx - HALF, 0, d.shape[1] - 2 * HALF))
        ax = fig.add_subplot(top[0, k])
        # **같은 표시 범위** — 두 장의 밝기를 견줄 수 있어야 한다
        ax.imshow(d[y0:y0 + 2 * HALF, x0:x0 + 2 * HALF], cmap="gray",
                  vmin=0, vmax=vmax)
        ax.set_title(f"{t} mm", pad=3, color=THICK3[t])
        ax.set_xticks([]); ax.set_yticks([])
        a_axes.append(ax)

    ax = fig.add_subplot(gs[1, 0])
    for _u, t in UNITS:
        d, cy, cx = dat[t]
        x0 = int(np.clip(cx - HALF, 0, d.shape[1] - 2 * HALF))
        prof = d[int(np.clip(cy, 0, d.shape[0] - 1)), x0:x0 + 2 * HALF]
        ax.plot(np.arange(len(prof)) - len(prof) / 2, prof, "-", c=THICK3[t],
                lw=1.8, label=f"{t} mm")
    # 판정 바닥 — 선은 두고 글자는 넣지 않는다(캡션이 진다)
    ax.axhline(DECISION_FLOOR, c=PS.MUTED, lw=0.7, ls=(0, (2, 2)), zorder=1)
    ax.set_xlabel("across the two posts [px]")
    ax.set_ylabel(r"$\Delta$ intensity [lvl]")
    ax.legend(loc="upper left", frameon=False, handlelength=1.5,
              handletextpad=0.5, labelspacing=0.25, borderpad=0.1)
    PS.style(ax, grid=None)
    ax.grid(alpha=0.25, lw=0.4, color="#c8c8c8")
    ax.set_axisbelow(True)

    # ------------------------------------------ (b) 화소를 몇 개 필요로 하나 --
    base = cv2.imread(str(SRC / f"fig1c_{SWEEP_UNIT}_ball8_000501.png"),
                      cv2.IMREAD_GRAYSCALE)
    assert base is not None, "(b) 의 원본이 없다"
    top = gs[0, 1].subgridspec(1, len(SHOW_PX), wspace=0.08)
    for k, w in enumerate(SHOW_PX):
        ax = fig.add_subplot(top[0, k])
        h = int(round(w * base.shape[0] / base.shape[1]))
        ax.imshow(cv2.resize(base, (w, h), interpolation=cv2.INTER_AREA),
                  cmap="gray")
        # **밀도가 먼저다.** 픽셀 폭은 그 단을 가리키는 이름일 뿐이고, 묻는 것은
        # 실제 면적당 화소가 몇 개냐다.
        ax.set_title(f"$R$ = {density_of(w):.3g}", pad=3)
        ax.set_xticks([]); ax.set_yticks([])
        ax.set_anchor("N")
        b_axes.append(ax)

    ax = fig.add_subplot(gs[1, 1])
    g = pd.read_csv(FORCE_CSV)
    g = g[(g.principle == "9DTact") & (g.measure == "fz_mae")]
    med = g.groupby("width_px").agg(mae_N=("mae_N", "median"),
                                    R=("density_px_per_mm2", "median"))
    ax.plot(med.R.values, med.mae_N.values, "-o", c=PS.SERIES, lw=1.8, ms=4.6,
            mec="white", mew=0.7)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks([0.1, 10, 1000]); ax.set_xticklabels(["0.1", "10", "1000"])
    ax.minorticks_off()
    ax.set_yticks([0.05, 0.1]); ax.set_yticklabels(["0.05", "0.1"])
    ax.set_xlabel(r"pixel density $R$ [px/mm$^2$]")
    ax.set_ylabel("force MAE [N]")
    PS.style(ax, grid=None)
    ax.grid(alpha=0.25, lw=0.4, color="#c8c8c8")
    ax.set_axisbelow(True)

    # 패널 이름을 같은 높이에, 각 패널이 실제로 차지한 왼쪽 끝에
    fig.canvas.draw()
    for axs, lab in ((a_axes, "(a)"), (b_axes, "(b)")):
        pos = [a.get_position() for a in axs]
        fig.text(min(p.x0 for p in pos) - 0.012,
                 max(p.y1 for p in pos) + 0.055, lab,
                 fontsize=11.0, ha="right", va="bottom", color=PS.INK)

    out = med.reset_index().assign(principle="9DTact", measure="fz_mae",
                                   n_units=g.sensor.nunique())
    PS.save(fig, out, "fig_question")

    dia, pitch = pair_geometry()
    print(f"  (a) hard, {DEPTH_MM:.2f} mm 압입, 기둥 ⌀{dia:.1f} mm 둘 · "
          f"중심 간격 {pitch:.2f} mm — 두께 1 대 3 mm")
    print(f"  (b) {SWEEP_UNIT} 한 장을 " +
          " · ".join(f"{w} px (R {density_of(w):.3g})" for w in SHOW_PX) +
          f"  ·  곡선은 {g.sensor.nunique()} 시편 중앙값")


if __name__ == "__main__":
    main()
