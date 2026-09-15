#!/usr/bin/env python3
"""논문 그림 — 두 접촉 분리: 겔이 정하는 것과 화소가 정하는 것. (IV.B)

네 칸이 한 질문의 네 얼굴이다 — **인접한 두 접촉을 가를 수 있나.**

(a)(b) 자국을 눈으로 — 같은 경도·같은 프로브·같은 압입에서 **두께만** 1 mm 와
       3 mm 로 다른 실제 영상. 1 mm 는 두 덩어리가 보이고 3 mm 는 뭉개진다.
(c)    겔이 정하는 것 — 전해상도에서 분해된 가장 좁은 간격 대 두께.
(d)    화소가 정하는 것 — 판정을 그대로 두고 입력만 줄인다.

위 줄이 아래 줄의 **눈으로 보는 판**이다. (a)(b) 는 따로 있던 `fig_two_contacts`
였고 2026-09-15 에 여기로 합쳤다(운전자 결정) — 같은 질문을 재는 그림이라
한 판에 있는 것이 맞다. 그때 단면 패널은 뺐다. 그 자료는
`fig_two_contacts.csv` 에 남아 있다.

(a)(b) 의 두 장을 고른 규칙
    시각 대비가 가장 큰 둘을 임의로 고르면 안 된다. 같은 경도(hard), 같은
    프로브(`pair100`, 기둥 ⌀1.0 mm 둘, 중심 간격 2.00 mm), 같은 압입 단
    (0.30 mm)에서 **두께만** 다른 둘이다. 그리는 것은 원본이 아니라
    `|접촉 − 기준|` 이고 (σ = 3 평활), **두 장이 같은 표시 범위**를 쓴다.
    영상은 회색조다 — 색 지도는 넷뿐인 팔레트 밖이다.

(c) 에서 광도 스테레오는 점으로 찍지 않는다
    여덟 시편 **모두** 가장 좁은 압자(중심 간격 1.10 mm)를 갈랐다. **값이 아니라
    바닥이다** — 점을 찍으면 "1.10 mm 가 그 센서의 분해능" 으로 읽힌다.
    (광도의 `hard_2mm` 는 두 기둥 램프가 없어 여덟이다.)

(c) 의 범례는 **실측 쇼어**다
    soft / medium / hard 는 계열마다 다른 물건이라(9DTact OO-30 ~ 70 은 40 점,
    광도 계열 OO-51 ~ 57 은 6 점) 이름만으로는 무엇을 얼마나 흔들었는지 보이지
    않는다. 이 패널은 9DTact 뿐이므로 눈금을 그대로 적는다.

(d) 는 시편 하나, 압입 하나다
    아홉을 묶어 분해 **비율**로 그렸다가 뺐다(2026-09-15) — **겔 한계와 화소
    한계가 섞이기 때문**이다. `hard_3mm_r1` 은 전해상도 한계가 2.50 mm 라 어느
    밀도에서도 2.00 mm 를 가르지 못하는데(36 단 중 0), 그 실패가 모든 막대에
    들어가 곡선의 천장을 70 % 로 눌렀다. 화소가 아니라 겔이 정한 천장이다.

    그래서 **`soft_2mm_r1` 하나**만 그린다. 전해상도 한계가 1.75 mm 로 2.00 mm
    보다 여유가 있고, 전해상도에서 세 깊이 단을 모두 분해하는 아홉 중 유일한
    시편이다. 겔이 못 하는 것이 섞이지 않으므로 **남는 것은 화소 이야기뿐**이다.
    압입은 **0.30 mm 하나**만 그린다 — (a)(b) 와 같은 압입이다.

    이 시편에서는 관문 셋 중 둘만 문다 — 골이 Rayleigh 를 넘긴 단은 밝기·잡음
    관문에 한 번도 걸리지 않는다(아래 `assert`). **Rayleigh 와 접촉 검출**만 남는다.

캡션이 져야 할 것 — 그림 안의 글자를 걷어냈으므로(운전자 결정) 여섯을 캡션이 진다
    1. **어느 패널이 무엇인가.** 제목이 `(a)` ~ `(d)` 뿐이다 —
       (a)(b) `9DTact_hard_1mm_r1` 과 `_3mm_r1`, 압입 0.30 mm, 기둥 중심 간격
       2.00 mm, **같은 표시 범위**의 `|접촉 − 기준|`.
       (c) 깊이 참조형 아홉 시편, 전해상도.
       (d) `soft_2mm_r1`, 압입 0.30 mm, 같은 프로브.
    2. **가장 좁은 압자가 중심 간격 1.10 mm** 라는 것, 그리고 **광도 스테레오는
       여덟 시편 모두 그 바닥에 있어 한계를 못 봤다**는 것. (c) 에 그 바닥을
       가리키는 선이 없다.
    3. (d) 의 **파선이 Rayleigh 문턱 dip = 0.265** 라는 것. 선은 있고 글자는 없다.
       판정은 **선 위/아래**로 읽는다 — 표식은 전부 같게 찍었다.
    4. (d) 왼쪽 끝의 `×` 는 **접촉 덩어리 자체를 못 찾은 단**이다 — 골이 얕아
       못 가른 것(파선 아래의 점)과 다른 실패다.
    5. (c) 의 **두께 경향** — Spearman rho +0.75 (p 0.02, n 9). 경도는 −0.13
       (p 0.73). 스크립트가 표준출력으로 낸다.
    6. **`fig_input_resolution` 과 잇지 않는다** — 그것은 다른 질문이다.

말하지 않는 것
    **"두 점을 가르는 데 R ≈ 387 px/mm² 가 든다" 를 쓰지 않는다.** 387 은 아홉을
    묶었을 때 분해 비율이 최대였던 밀도이고, 힘·형상에서 쓴 10 % 평탄 기준과
    다른 자다. 같은 기준을 세우기 전에는 그 둘을 나눈 배수도 말하지 않는다.

칸마다 정해진 센서 하나 (`CLAUDE.md` §1)

자료
    (a)(b) `paper/figures/sources/` (원본 넉 장, 1920×1080)
    (c) `result/single/extra/data/G_spatial_resolution.csv`
    (d) `result/extra/data/resolution_sweep_9DTact_pair100.csv`
        (경로만 `extra` 다 — `resolution_sweep.py` 의 `OUT` 이 하드코딩돼 있고,
         실제로 돈 것은 선택된 아홉 개뿐이다. §1 위반이 아니다.)
"""
import cv2
import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import paper_style as PS
from paper_style import HARD3, THICK3, DISPLAY, SHORE

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402

SRC = PS.ROOT / "paper" / "figures" / "sources"

HARDNESS = ("soft", "medium", "hard")
DODGE = dict(zip(HARDNESS, (-0.055, 0.0, 0.055)))
NARROWEST_MM = 1.10                       # 우리가 만든 가장 좁은 압자 (중심 간격)

IMPRINTS = [("hard_1mm_r1", 1), ("hard_3mm_r1", 3)]   # 두께만 다르다
IMPRINT_STEP = "pair100_d0.30"
HALF = 240                                # 자국 잘라내는 반폭 (px)

SWEEP_UNIT = "soft_2mm_r1"                # 전해상도에서 세 깊이 단 모두 분해
SWEEP_DEPTH_MM = 0.3
SEP_MM = 2.00                             # pair100 — 기둥 ⌀1.0 mm, 중심 간격
RAYLEIGH = 0.265
LOST_Y = -0.20                            # 접촉을 못 찾은 단을 찍는 자리


def imprint(unit):
    """기준영상 대비 밝기 변화와 자국 중심. 두 장이 같은 자로 그려져야 한다."""
    img = cv2.imread(str(SRC / f"fig1b_{unit}_{IMPRINT_STEP}.png"),
                     cv2.IMREAD_GRAYSCALE)
    ref = cv2.imread(str(SRC / f"fig1b_{unit}_reference.png"),
                     cv2.IMREAD_GRAYSCALE)
    assert img is not None and ref is not None, f"{unit} 의 원본이 없다"
    d = cv2.GaussianBlur(np.abs(img.astype(np.float32) - ref.astype(np.float32)),
                         (0, 0), 3)
    cy, cx = np.unravel_index(np.argmax(cv2.GaussianBlur(d, (0, 0), 25)), d.shape)
    return d, int(cy), int(cx)


def panel_imprints(axes):
    """(a)(b) 자국을 눈으로. 두 장이 **같은 표시 범위**를 쓴다."""
    dat = {t: imprint(u) for u, t in IMPRINTS}
    vmax = max(float(np.percentile(d, 99.9)) for d, _, _ in dat.values())
    for ax, (_u, t) in zip(axes, IMPRINTS):
        d, cy, cx = dat[t]
        y0 = int(np.clip(cy - HALF, 0, d.shape[0] - 2 * HALF))
        x0 = int(np.clip(cx - HALF, 0, d.shape[1] - 2 * HALF))
        ax.imshow(d[y0:y0 + 2 * HALF, x0:x0 + 2 * HALF], cmap="gray",
                  vmin=0, vmax=vmax)
        ax.set_title(f"{t} mm", pad=3, color=THICK3[t])
        ax.set_xticks([]); ax.set_yticks([])


def panel_gel(ax):
    """(c) 분해된 가장 좁은 간격 대 두께."""
    d = pd.read_csv(PS.ROOT / "result/single/extra/data/G_spatial_resolution.csv")
    assert not d.suspect_hardware.any(), "선택 규칙이 거른 유닛이 남아 있다"
    nine, digit = d[d.principle == "9DTact"], d[d.principle == "DIGIT"]
    assert (digit.finest_centre_mm == NARROWEST_MM).all()

    for h in HARDNESS:
        g = nine[nine.hardness == h].sort_values("thickness_mm")
        ax.plot(g.thickness_mm + DODGE[h], g.finest_centre_mm, "-",
                c=HARD3[h], lw=1.8, label=f"Shore OO-{SHORE['9DTact'][h]}",
                zorder=3)
        ax.plot(g.thickness_mm + DODGE[h], g.finest_centre_mm, "o",
                c=HARD3[h], ms=5.6, mec="white", mew=0.7, ls="none", zorder=4)

    rho, p = spearmanr(nine.thickness_mm, nine.finest_centre_mm)
    ax.legend(loc="upper left", frameon=False, handlelength=1.5,
              handletextpad=0.45, labelspacing=0.25, borderpad=0.1, fontsize=9.0)
    ax.set_xticks([1, 2, 3])
    ax.set_xlim(0.72, 3.30)
    ax.set_ylim(0.86, 2.98)
    ax.set_xlabel("gel thickness [mm]")
    ax.set_ylabel("finest resolved\nseparation [mm]")
    PS.style(ax)
    return nine.assign(rho_thickness=rho, p_thickness=p), rho, p


def panel_pixels(ax):
    """(d) 한 시편·한 압입의 골 대 화소 밀도."""
    d = pd.read_csv(PS.ROOT / "result/extra/data/resolution_sweep_9DTact_pair100.csv")
    u = d[(d.unit == SWEEP_UNIT) & (d.depth_mm == SWEEP_DEPTH_MM)] \
        .sort_values("width_px")
    assert len(u), f"{SWEEP_UNIT} 의 {SWEEP_DEPTH_MM} mm 단이 없다"
    # **Rayleigh 를 넘긴 단은 나머지 두 관문에 한 번도 걸리지 않는다** — 이 패널이
    # 골과 접촉 검출만 그리는 근거다.
    seen = u.dropna(subset=["dip"])
    passed = seen[seen.dip >= RAYLEIGH]
    assert (passed.imprint_lvl >= 2.5).all(), "밝기 관문이 물었다 — 그림에 넣어야 한다"
    assert (passed.dip > 3 * passed.dip_sd).all(), "잡음 관문이 물었다 — 그림에 넣어야 한다"
    assert (passed.verdict == "분해").all(), "Rayleigh 를 넘겼는데 분해가 아니다"

    c = PS.SERIES
    ax.axhline(RAYLEIGH, c=PS.MUTED, lw=0.7, ls=(0, (4, 2)), zorder=1)
    ax.plot(seen.density_px_per_mm2, seen.dip, "-", c=c, lw=1.8, zorder=3)
    ax.plot(seen.density_px_per_mm2, seen.dip, "o", c=c, ms=5.6, mec="white",
            mew=0.7, ls="none", zorder=4)
    # 접촉 덩어리 자체를 못 찾은 단 — 값이 없으므로 축 바닥에 따로 찍는다.
    # 글자는 넣지 않는다(운전자 결정) — 캡션이 말해야 한다.
    lost = u[u.dip.isna()]
    ax.plot(lost.density_px_per_mm2, [LOST_Y] * len(lost), "x", c=c, ms=5.2,
            mew=1.3, ls="none", zorder=4)

    ax.set_xscale("log")
    ax.set_xlim(0.09, 1.4e4)
    ax.set_ylim(-0.27, 0.62)
    ax.set_xlabel(r"pixel density $R$ [px/mm$^2$]")
    ax.set_ylabel("dip  $(P-T)/P$")
    PS.style(ax, grid=None)
    ax.grid(alpha=0.25, lw=0.4, color="#c8c8c8")
    ax.set_axisbelow(True)
    return u, seen[seen.verdict == "분해"].density_px_per_mm2.min()


def letters(fig, rows):
    """패널 이름을 줄마다 **같은 높이**에. 영상 칸은 비율이 고정돼 그려진 높이가
    그래프 칸과 다르므로, 각자의 y1 을 쓰면 글자가 어긋난다."""
    fig.canvas.draw()
    tags = iter("abcdefgh")
    for axs in rows:
        pos = [a.get_position() for a in axs]
        y = max(p.y1 for p in pos) + 0.012
        for p in pos:
            fig.text(p.x0 - 0.008, y, f"({next(tags)})", fontsize=11.0,
                     ha="right", va="bottom", color=PS.INK)


def main():
    fig = plt.figure(figsize=(PS.FULL_W_NARROW, 4.25))
    gs = fig.add_gridspec(2, 2, height_ratios=[1.30, 1.25],
                          wspace=0.42, hspace=0.42,
                          left=0.115, right=0.988, top=0.950, bottom=0.105)
    top = [fig.add_subplot(gs[0, k]) for k in (0, 1)]
    bot = [fig.add_subplot(gs[1, k]) for k in (0, 1)]

    panel_imprints(top)
    gel, rho, p = panel_gel(bot[0])
    sweep, first = panel_pixels(bot[1])
    letters(fig, [top, bot])

    PS.save(fig, gel[["principle", "unit", "hardness", "thickness_mm",
                      "finest_centre_mm", "depth_lo_mm", "depth_hi_mm",
                      "n_gaps_resolved", "n_gaps_tested"]], "fig_separation")
    sweep[["unit", "probe", "depth_mm", "width_px", "density_px_per_mm2",
           "dip", "dip_sd", "imprint_lvl", "verdict"]].to_csv(
        PS.FIGS / "fig_separation_sweep.csv", index=False)
    print(f"  (a)(b) hard, {SWEEP_DEPTH_MM:.2f} mm 압입, 중심 간격 "
          f"{SEP_MM:.2f} mm — 두께 1 대 3 mm")
    print(f"  (c) 두께 rho {rho:+.3f}  p {p:.3f}  n {len(gel)}")
    print(f"  (d) {SWEEP_UNIT} @ {SWEEP_DEPTH_MM} mm — "
          f"분해되는 가장 낮은 밀도 R {first:.2f}"
          f"   (접촉 못 찾은 단 {int(sweep.dip.isna().sum())})")


if __name__ == "__main__":
    main()
