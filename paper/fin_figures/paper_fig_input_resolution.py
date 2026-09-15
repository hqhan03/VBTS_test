#!/usr/bin/env python3
"""논문 그림 — 추정기가 화소를 몇 개 필요로 하나. (I 장)

접촉 프레임 하나를 면적 평균으로 줄여 넣고 힘 오차를 본다. 한 줄(가로 배치)이다.

**두 접촉 영상은 여기 없다.** `fig_separation` 의 위 줄로 옮겼다(운전자 결정,
2026-09-15) — 같은 질문(두 접촉을 가를 수 있나)을 재는 그림과 한 판에 있는 것이
맞다. 이 그림은 **다른 질문**이고, 둘을 잇지 않는 것이 논문 전체의 주장 강도를
정한다.

`data/` 없이 돌아간다
    원본이 `paper/figures/sources/` 에 있고, 화소 밀도는
    `paper/figures/fig2_force_vs_resolution.csv` 에서 읽는다 —
    `pixel_density.density()` 는 `data/analysis/` 를 봐야 해서 쓰지 않는다.

캡션이 져야 할 것
    1. **어느 패널이 무엇인가** — (a)(b)(c) 는 같은 프레임을 R = 220 / 13.8 / 0.55
       로 줄인 것, (d) 는 힘 오차 곡선.
    2. 곡선이 **9DTact 아홉 시편의 중앙값**이고, 영상 셋은 그중 `hard_2mm_r1`
       한 장이라는 것.
    3. **`fig_separation` 과 잇지 않는다** — 서로 다른 질문이다.

자료
    영상 `paper/figures/sources/fig1c_hard_2mm_r1_ball8_000501.png`
    곡선 `paper/figures/fig2_force_vs_resolution.csv`
"""
import cv2
import pandas as pd

import paper_style as PS

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402

SRC = PS.ROOT / "paper" / "figures" / "sources"
FORCE_CSV = PS.ROOT / "paper" / "figures" / "fig2_force_vs_resolution.csv"

SHOW_PX = [320, 80, 16]                            # 보여 주는 세 단
SWEEP_UNIT = "hard_2mm_r1"                         # 영상이 나온 유닛


def density_of(width_px, unit=SWEEP_UNIT):
    """그 단의 화소 밀도. `fig2` csv 가 유닛·폭마다 들고 있다."""
    g = pd.read_csv(FORCE_CSV)
    g = g[(g.principle == "9DTact") & (g.sensor == unit) & (g.width_px == width_px)]
    assert len(g), f"{unit} 의 {width_px} px 단이 csv 에 없다"
    return float(g.density_px_per_mm2.median())


def letters(fig, axes):
    """패널 이름을 각 축의 왼쪽 위에. 축 제목으로 달면 좁은 영상 칸에서 가운데
    제목과 부딪힌다 — 그려진 뒤 실제 자리에서 x 를 구해 놓는다."""
    fig.canvas.draw()
    pos = [a.get_position() for a in axes]
    y = max(p.y1 for p in pos) + 0.03
    for tag, p in zip("abcdefgh", pos):
        fig.text(p.x0 - 0.008, y, f"({tag})", fontsize=11.0,
                 ha="right", va="bottom", color=PS.INK)


def fig_input_resolution():
    """요구 해상도 — 줄인 영상 셋과 힘 오차 곡선, 한 줄."""
    base = cv2.imread(str(SRC / f"fig1c_{SWEEP_UNIT}_ball8_000501.png"),
                      cv2.IMREAD_GRAYSCALE)
    assert base is not None, "축소 시연에 쓸 원본이 없다"

    fig, raw = plt.subplots(1, len(SHOW_PX) + 2,
                            figsize=(PS.FULL_W_NARROW, 1.85),
                            gridspec_kw=dict(width_ratios=[1, 1, 1, 0.34, 1.9]))
    raw[len(SHOW_PX)].axis("off")          # 영상과 그래프 사이의 빈 칸
    axes = [*raw[:len(SHOW_PX)], raw[-1]]
    fig.subplots_adjust(left=0.015, right=0.988, top=0.80, bottom=0.30,
                        wspace=0.30)
    for ax, w in zip(axes, SHOW_PX):
        h = int(round(w * base.shape[0] / base.shape[1]))
        ax.imshow(cv2.resize(base, (w, h), interpolation=cv2.INTER_AREA),
                  cmap="gray")
        # **밀도가 먼저다.** 픽셀 폭은 그 단을 가리키는 이름일 뿐이고, 묻는 것은
        # 실제 면적당 화소가 몇 개냐다.
        ax.set_title(f"$R$ = {density_of(w):.3g}", pad=3)
        ax.set_xticks([]); ax.set_yticks([])

    ax = axes[-1]
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

    letters(fig, axes)
    PS.save(fig, med.reset_index().assign(principle="9DTact",
                                          measure="fz_mae",
                                          n_units=g.sensor.nunique()),
            "fig_input_resolution")
    print("  요구 해상도 — " +
          " · ".join(f"{w} px (R {density_of(w):.3g})" for w in SHOW_PX) +
          f"  ·  곡선은 {g.sensor.nunique()} 시편 중앙값")


def main():
    fig_input_resolution()


if __name__ == "__main__":
    main()
