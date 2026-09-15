#!/usr/bin/env python3
"""영상 응답 포화(ceiling)를 **글자 없이** 설명하는 그림. (IV.C 들머리)

`fig_ceiling` 은 재어 놓은 값을 그린다 — 두께마다의 포화 힘. 그 값이 **무엇을
잰 것인지**는 그림에 없다. 이 그림이 그것을 진다.

읽는 차례
    왼쪽 → 오른쪽   누르는 힘이 커진다 (화살표가 길고 굵어진다)
    위 칸 안         겔 단면 — 공이 파고들고, 자국이 깊어진다
    아래 띠          그때 카메라가 받는 영상 — 자국이 밝고 넓어진다
    오른쪽 곡선      그 영상 응답이 힘을 따라 오르다가 **평평해진다**
    위 줄 대 아래 줄 얇은 겔과 두꺼운 겔 — 평평해지는 자리가 다르다

**세 번째 칸에서 겔은 더 눌리는데 영상은 그대로다.** 그림 전체가 그 한 문장을
위한 것이다 — 그 자리의 힘이 `fig_ceiling` 이 세로축에 찍는 값이다.

**글자가 하나도 없다** (운전자 결정, 2026-09-15). 축 이름도 눈금도 범례도 없다.
방향은 축 끝의 화살촉이 지고, 나머지는 캡션이 진다.

**이것은 개념도다 — 자료가 아니다.**
    곡선도 자국도 **그려 넣은 것**이고 잰 값이 아니다. 두 줄이 다른 자리에서
    평평해지는 것도 "그런 일이 일어난다" 는 뜻이지 **어느 쪽이 더 크다는 주장이
    아니다.** 캡션에 이 말을 반드시 넣을 것 — 넣지 않으면 두께가 두꺼울수록
    포화 힘이 크다는 결과로 읽힌다. 실제로는:

    - 깊이 참조형(9DTact) 은 두꺼울수록 **크다** — 그러나 rho +0.63, 정확 p 0.09 다.
      아홉 점으로는 **못 가른다**.
    - 광도 스테레오(DIGIT) 는 **반대로 간다** — rho −0.90, p 0.0036.

    그림은 두 계열 가운데 어느 쪽도 그리지 않는다. 그리는 것은 **재는 방법**이다.

색 (`CLAUDE.md` §2)
    두께는 순서가 있는 변수라 **얇을수록 파랑 · 두꺼울수록 빨강** 이다
    (`paper_style.THICK3`). 겔 단면 테두리와 곡선이 같은 색을 쓴다.

자료
    없다. 그린 값은 `fig_ceiling_schematic.csv` 에 그대로 남는다 — 이 그림을
    다시 그리는 데 드는 것이 그 표뿐이라는 뜻이다.
"""
import numpy as np
import pandas as pd

import paper_style as PS
from paper_style import THICK3

PS.use_paper_style()
import matplotlib.pyplot as plt                        # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle   # noqa: E402

# 누르는 세 단. 힘은 0 ~ 1 로 규격화한 **그림용** 값이다.
FORCES = (0.16, 0.50, 1.00)

# 두 줄 — 얇은 겔과 두꺼운 겔.
#
# `ceiling` 은 응답이 멈추는 자리다. 얇은 쪽의 천장을 **가운데 칸의 힘에 정확히
# 맞춘다** — 그래야 셋째 칸의 자국이 둘째 칸과 한 점 다르지 않게 나온다. 겔은 더
# 눌리는데 영상은 그대로라는 것이 이 그림의 전부다. 두꺼운 쪽은 셋째 칸에서야
# 닿으므로 아직 자라는 중이다.
#
# `peak` 는 그 천장의 **높이**다. 둘을 같게 두면 오른쪽 곡선판에서 두 평평한
# 구간이 포개져 하나만 보인다. 두꺼운 겔이 변형을 넓게 퍼뜨려 자국이 덜 또렷한
# 것이기도 하다 — 자국 밝기도 같은 값으로 낮춘다.
ROWS = [dict(thickness=1, gel_h=5.5, ceiling=0.50, peak=1.00),
        dict(thickness=3, gel_h=9.0, ceiling=0.82, peak=0.84)]

XC = (13.0, 34.0, 55.0)          # 세 칸의 가운데
HALF_W = 9.5                     # 겔 반폭
BALL_R = 3.6
DEPTH_MAX = 3.2                  # 가장 센 힘에서의 파고든 깊이
STRIP_W, STRIP_H = 14.0, 7.0     # 카메라 영상 띠 (16:9 에 가깝게)

# 줄 하나의 속 배치 (줄 바닥에서 잰다). 위로 갈수록 영상 → 겔 → 공 → 힘 화살표.
STRIP_Y, GEL_Y, ROW_H = 0.0, 10.0, 37.0
ROW_Y = (37.0, 0.0)              # 얇은 줄이 위
PLOT_X = (72.0, 106.0)           # 오른쪽 곡선 판
GEL_FILL = "#ececec"
BALL_FILL = "#ffffff"


def response(f, r):
    """영상 응답. 힘을 따라 오르다가 그 겔의 천장에서 **딱 멈춘다**.

    시정수를 `ceiling / 3` 으로 잡으면 그 자리에서 95 % 에 닿고, 거기서 **잘라
    둔다**. 점근선으로만 두면 곡선이 끝까지 조금씩 올라 "평평하다" 로 읽히지
    않는다 — 그 한 가지가 이 그림이 말해야 하는 전부다.
    """
    ceil = r["ceiling"]
    return r["peak"] * (1.0 - np.exp(-np.minimum(f, ceil) / (ceil / 3.0)))


def gel(ax, xc, y0, h, depth, colour):
    """겔 단면과 파고든 공.

    자국은 **공의 아랫면 그대로**다. 접촉 반폭 a 안에서 겔 표면이 공을 따라가고,
    바깥은 평평하다 — 접촉 끝에서 두 높이가 정확히 맞아떨어진다. 바깥에 아주
    작은 부풀음을 더한다(눌린 것이 어디론가 가야 한다).
    """
    top = y0 + h
    cy = top - depth + BALL_R                       # 공 중심
    a = float(np.sqrt(max(2 * BALL_R * depth - depth ** 2, 1e-9)))
    xs = np.linspace(xc - HALF_W, xc + HALF_W, 500)
    dx = xs - xc
    inside = np.abs(dx) <= a
    surf = np.full_like(xs, top)
    surf[inside] = cy - np.sqrt(np.maximum(BALL_R ** 2 - dx[inside] ** 2, 0.0))
    out = ~inside
    surf[out] = top + 0.18 * depth * np.exp(
        -((np.abs(dx[out]) - a) / (0.7 * BALL_R)) ** 2)

    ring = list(zip(xs, surf)) + [(xc + HALF_W, y0), (xc - HALF_W, y0)]
    ax.add_patch(Polygon(ring, closed=True, facecolor=GEL_FILL,
                         edgecolor=colour, lw=1.5, zorder=2))
    ax.add_patch(Circle((xc, cy), BALL_R, facecolor=BALL_FILL,
                        edgecolor=PS.INK, lw=1.5, zorder=4))
    return cy + BALL_R                              # 공 꼭대기


def push(ax, xc, y_ball_top, f):
    """누르는 힘. **길이와 굵기 둘 다**로 크기를 적는다 — 하나만 쓰면 작은 칸에서
    차이가 안 보인다.

    길이는 **힘만으로** 정한다. 공이 깊이 박힐수록 꼭대기가 내려가므로, 화살표
    꼬리를 한 높이에 고정하면 두 줄의 같은 힘이 다른 길이로 그려진다.
    """
    tip = y_ball_top + 0.9
    ax.annotate("", xy=(xc, tip), xytext=(xc, tip + 5.0 + 6.5 * f),
                arrowprops=dict(arrowstyle="-|>", color=PS.INK,
                                lw=0.9 + 2.2 * f, shrinkA=0, shrinkB=0,
                                mutation_scale=8 + 9 * f))


def strip(ax, xc, y0, s):
    """카메라가 받는 영상. 응답 `s` 가 자국의 **넓이와 밝기**를 함께 정한다."""
    n = 220
    gx = np.linspace(-1.0, 1.0, n) * (STRIP_W / STRIP_H)
    gy = np.linspace(-1.0, 1.0, int(n * STRIP_H / STRIP_W))
    X, Y = np.meshgrid(gx, gy)
    sig = 0.20 + 0.46 * s
    img = (0.10 + 0.86 * s) * np.exp(-(X ** 2 + Y ** 2) / (2 * sig ** 2))
    ax.imshow(np.clip(img, 0, 1), cmap="gray", vmin=0, vmax=1, zorder=2,
              extent=(xc - STRIP_W / 2, xc + STRIP_W / 2, y0, y0 + STRIP_H),
              interpolation="bilinear", aspect="auto")
    ax.add_patch(Rectangle((xc - STRIP_W / 2, y0), STRIP_W, STRIP_H,
                           facecolor="none", edgecolor=PS.INK, lw=1.0, zorder=3))


def look(ax, xc, y_from, y_to):
    """겔에서 영상으로 — 카메라가 아래에서 본다는 것만 가리킨다."""
    ax.annotate("", xy=(xc, y_to), xytext=(xc, y_from),
                arrowprops=dict(arrowstyle="-|>", color=PS.MUTED, lw=1.6,
                                shrinkA=0, shrinkB=0, mutation_scale=13))


def curve_panel(ax, y_lo, y_hi):
    """응답 대 힘. 두 줄이 **다른 자리에서** 평평해진다.

    축은 선 끝의 화살촉이 방향을 진다 — 글자가 없으므로 그것 말고는 길이 없다.
    """
    x0, x1 = PLOT_X
    ax.annotate("", xy=(x1, y_lo), xytext=(x0, y_lo),
                arrowprops=dict(arrowstyle="-|>", color=PS.INK, lw=1.1,
                                shrinkA=0, shrinkB=0, mutation_scale=11))
    ax.annotate("", xy=(x0, y_hi), xytext=(x0, y_lo),
                arrowprops=dict(arrowstyle="-|>", color=PS.INK, lw=1.1,
                                shrinkA=0, shrinkB=0, mutation_scale=11))

    span_x, span_y = (x1 - x0) * 0.84, (y_hi - y_lo) * 0.86
    rows = []
    for r in ROWS:
        c = THICK3[r["thickness"]]
        f = np.linspace(0, 1.06, 400)
        ax.plot(x0 + f / 1.06 * span_x, y_lo + response(f, r) * span_y,
                "-", c=c, lw=2.2, zorder=3)

        xk = x0 + r["ceiling"] / 1.06 * span_x
        yk = y_lo + response(r["ceiling"], r) * span_y
        ax.plot([xk, xk], [y_lo, yk], ls=(0, (2, 2)), c=c, lw=1.1, zorder=2)
        ax.plot([xk], [yk], "o", c=c, ms=7.5, mec="white", mew=1.2, zorder=5)
        # 가로축 위의 **눈금 없는 표식** — 이 힘이 fig_ceiling 의 세로축 값이다.
        ax.plot([xk], [y_lo], "v", c=c, ms=8.0, mec="white", mew=1.0,
                clip_on=False, zorder=5)

        for fi in FORCES:                            # 세 칸이 곡선의 어디인가
            ax.plot([x0 + fi / 1.06 * span_x], [y_lo + response(fi, r) * span_y],
                    "o", c=c, ms=4.6, mec="white", mew=0.9, zorder=4)
            rows.append(dict(thickness_mm=r["thickness"], force_norm=fi,
                             response_norm=float(response(fi, r)),
                             ceiling_norm=r["ceiling"], peak_norm=r["peak"]))
    return pd.DataFrame(rows)


def main():
    fig, ax = plt.subplots(figsize=(PS.FULL_W_NARROW, 4.10))
    fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
    ax.set_xlim(0, 108); ax.set_ylim(0, 2 * ROW_H)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    for r, y0 in zip(ROWS, ROW_Y):
        h, c = r["gel_h"], THICK3[r["thickness"]]
        for xc, f in zip(XC, FORCES):
            top = gel(ax, xc, y0 + GEL_Y, h, DEPTH_MAX * f ** 0.6, c)
            push(ax, xc, top, f)
            strip(ax, xc, y0 + STRIP_Y, response(f, r))
            look(ax, xc, y0 + GEL_Y - 0.4, y0 + STRIP_Y + STRIP_H + 0.4)

    stages = curve_panel(ax, 8.0, 2 * ROW_H - 8.0)
    PS.save(fig, stages, "fig_ceiling_schematic")
    print("  개념도 — 글자 없음. 멈추는 자리: " + " · ".join(
        f"두께 {r['thickness']} mm → {r['ceiling']:.2f}" for r in ROWS))


if __name__ == "__main__":
    main()
