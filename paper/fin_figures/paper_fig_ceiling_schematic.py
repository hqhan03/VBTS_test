#!/usr/bin/env python3
"""시편 판 — 무엇을 만들어 무엇을 했는지 그림 하나로. (III 장 / IV.C 들머리)

**곡선판을 뺐다 (운전자 결정, 2026-09-15).** 그래서 이 그림은 더 이상 포화를
설명하지 않는다 — **흔든 것 둘**과 **거는 것 하나**를 보여 준다.

    윗줄   겔 **두께**를 흔든다 — 1 · 2 · 3 mm. 색은 하나(파랑)다.
    아랫줄 겔 **경도**를 흔든다 — OO-30 · 50 · 70. 두께는 2 mm 로 묶는다.
    둘 다  **같은 프로브 · 같은 힘** — 화살표가 여섯 다 같은 크기다.
    칸 아래 그때 카메라가 받는 영상.

**화살표를 같게 그리는 것이 이 그림의 규율이다.** 크기를 달리 하면 "힘을 키웠다"
로 읽히는데, 여기서 흔든 것은 힘이 아니라 **겔**이다. 힘은 통제된 쪽이다.

**가운데 칸 둘은 같은 시편이다** — 2 mm · OO-50. 윗줄에서는 두께 계열의 가운데로,
아랫줄에서는 경도 계열의 가운데로 한 번씩 나온다. 색만 다르다(무엇을 흔드는
줄인지가 색이다). 겹치는 것이 아니라 **십자로 만나는 자리**다.

색 (`CLAUDE.md` §2)
    윗줄은 **한 색**이다 — 흔드는 것이 색이 아니라 **두께(모양)** 이므로 색을
    쓰면 두 자로 같은 것을 두 번 적는 셈이다.

    아랫줄은 경도가 순서 있는 변수라 **무를수록 파랑 · 단단할수록 빨강** 으로
    간다(`paper_style.HARD3`) — OO-30 파랑 · OO-50 초록 · OO-70 빨강. 셋을 쓰되
    **왼쪽부터 빨·파·초 가 아니다.** 순서를 뒤집으면 논문의 다른 그림
    (`fig_ceiling` · `fig_growth` · `fig_separation`)과 경도 색이 어긋난다.

파고드는 깊이는 겔마다 다르게 그린다
    같은 힘이면 **두꺼울수록 · 무를수록 더 들어간다.** 평범한 역학이고, §4 가
    막는 주장(경도가 영상 응답을 가른다)과는 다른 이야기다. 자국 크기는 그
    깊이를 따라간다 — **기하학이지 잰 값이 아니다.**

글자
    아랫줄 겔 안의 `OO-30` · `OO-50` · `OO-70` 셋뿐이다. 다른 데는 없다.
    윗줄의 두께는 **모양이 지므로** 적지 않는다.

**이것은 개념도다 — 자료가 아니다.** 자국도 깊이도 그려 넣은 것이다. 캡션이
그렇게 적어야 한다.

자료
    없다. 그린 값은 `fig_ceiling_schematic.csv` 에 그대로 남는다.
"""
import numpy as np
import pandas as pd

import paper_style as PS
from paper_style import BLUE, HARD3

PS.use_paper_style()
import matplotlib.pyplot as plt                        # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle   # noqa: E402

# 윗줄 — 두께만 흔든다. 높이는 **1 : 2 : 3 그대로** 그린다.
TOP = [dict(thickness=1, gel_h=3.5, depth=1.2),
       dict(thickness=2, gel_h=7.0, depth=1.8),
       dict(thickness=3, gel_h=10.5, depth=2.2)]

# 아랫줄 — 두께를 2 mm 로 묶고 경도만 흔든다. 무를수록 더 들어간다.
BOT = [dict(hardness="soft", shore=30, gel_h=7.0, depth=2.3),
       dict(hardness="medium", shore=50, gel_h=7.0, depth=1.8),
       dict(hardness="hard", shore=70, gel_h=7.0, depth=1.4)]

XC = (15.0, 44.0, 73.0)          # 세 칸의 가운데
HALF_W = 12.5                    # 겔 반폭
BALL_R = 3.4
STRIP_W, STRIP_H = 16.0, 9.0     # 카메라 영상 띠 (16:9)

# 줄 하나의 속 배치 (줄 바닥에서 잰다). 아래에서 위로 영상 → 겔 → 공 → 힘 화살표.
STRIP_Y, GEL_Y = 0.0, 11.5
ROW_Y = (33.0, 0.0)              # 두께 줄이 위
ARROW_LEN = 4.5                  # **여섯이 다 같다** — 힘은 통제된 쪽이다
DEPTH_REF = 2.3                  # 자국 크기를 깊이에 맞추는 기준
LABEL_PT = 9.0                   # 겔 안의 쇼어 표기 (본문 글자보다 작게)
GEL_FILL = "#ececec"
BALL_FILL = "#ffffff"


def imprint_level(depth):
    """자국의 세기. **깊이를 따라가는 기하학**이지 잰 값이 아니다."""
    return 0.34 + 0.56 * depth / DEPTH_REF


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
                         edgecolor=colour, lw=1.6, zorder=2))
    ax.add_patch(Circle((xc, cy), BALL_R, facecolor=BALL_FILL,
                        edgecolor=PS.INK, lw=1.6, zorder=4))
    return cy + BALL_R                              # 공 꼭대기


def push(ax, xc, y_ball_top):
    """누르는 힘. **여섯이 다 같다.** 크기를 달리 하면 힘을 흔든 것으로 읽힌다 —
    여기서 흔든 것은 겔이고 힘은 통제된 쪽이다.

    꼬리를 한 높이에 고정하지 않고 **공 꼭대기에서 재어** 올린다. 공이 깊이 박힐
    수록 꼭대기가 내려가므로, 고정하면 같은 힘이 다른 길이로 그려진다.
    """
    tip = y_ball_top + 0.9
    ax.annotate("", xy=(xc, tip), xytext=(xc, tip + ARROW_LEN),
                arrowprops=dict(arrowstyle="-|>", color=PS.INK, lw=2.0,
                                shrinkA=0, shrinkB=0, mutation_scale=13))


def strip(ax, xc, y0, s):
    """카메라가 받는 영상. `s` 가 자국의 **넓이와 밝기**를 함께 정한다."""
    n = 240
    gx = np.linspace(-1.0, 1.0, n) * (STRIP_W / STRIP_H)
    gy = np.linspace(-1.0, 1.0, int(n * STRIP_H / STRIP_W))
    X, Y = np.meshgrid(gx, gy)
    sig = 0.20 + 0.46 * s
    img = (0.10 + 0.86 * s) * np.exp(-(X ** 2 + Y ** 2) / (2 * sig ** 2))
    ax.imshow(np.clip(img, 0, 1), cmap="gray", vmin=0, vmax=1, zorder=2,
              extent=(xc - STRIP_W / 2, xc + STRIP_W / 2, y0, y0 + STRIP_H),
              interpolation="bilinear", aspect="auto")
    ax.add_patch(Rectangle((xc - STRIP_W / 2, y0), STRIP_W, STRIP_H,
                           facecolor="none", edgecolor=PS.INK, lw=1.1, zorder=3))


def look(ax, xc, y_from, y_to):
    """겔에서 영상으로 — 카메라가 아래에서 본다는 것만 가리킨다."""
    ax.annotate("", xy=(xc, y_to), xytext=(xc, y_from),
                arrowprops=dict(arrowstyle="-|>", color=PS.MUTED, lw=1.6,
                                shrinkA=0, shrinkB=0, mutation_scale=13))


def cell(ax, xc, y0, spec, colour, label=None):
    """한 칸 — 힘 · 겔 · 공 · 영상, 그리고 아랫줄이면 쇼어 표기."""
    top = gel(ax, xc, y0 + GEL_Y, spec["gel_h"], spec["depth"], colour)
    push(ax, xc, top)
    s = imprint_level(spec["depth"])
    strip(ax, xc, y0 + STRIP_Y, s)
    look(ax, xc, y0 + GEL_Y - 0.4, y0 + STRIP_Y + STRIP_H + 0.4)
    if label:
        # **겔 안, 아래쪽**에 적는다. 겔 밖에 두면 어느 겔의 것인지 한 번 더
        # 따져야 하고, 영상 띠로 가는 화살표와도 자리를 다툰다.
        ax.text(xc, y0 + GEL_Y + 0.7, label, ha="center", va="bottom",
                fontsize=LABEL_PT, color=PS.INK, zorder=5)
    return s


def main():
    fig, ax = plt.subplots(figsize=(PS.FULL_W_NARROW, 4.35))
    fig.subplots_adjust(left=0.005, right=0.995, top=0.995, bottom=0.005)
    ax.set_xlim(0, 88); ax.set_ylim(0, 67.0)
    ax.set_aspect("equal")
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    rows = []
    for xc, spec in zip(XC, TOP):                    # 윗줄 — 두께, 한 색
        s = cell(ax, xc, ROW_Y[0], spec, BLUE)
        rows.append(dict(row="thickness", thickness_mm=spec["thickness"],
                         shore_oo=50, colour=BLUE, depth_units=spec["depth"],
                         gel_h_units=spec["gel_h"], imprint_level=s))

    for xc, spec in zip(XC, BOT):                    # 아랫줄 — 경도, 세 색
        c = HARD3[spec["hardness"]]
        s = cell(ax, xc, ROW_Y[1], spec, c, f"OO-{spec['shore']}")
        rows.append(dict(row="hardness", thickness_mm=2, shore_oo=spec["shore"],
                         colour=c, depth_units=spec["depth"],
                         gel_h_units=spec["gel_h"], imprint_level=s))

    PS.save(fig, pd.DataFrame(rows), "fig_ceiling_schematic")
    print("  시편 판 — 윗줄 두께 1·2·3 mm (한 색) · 아랫줄 OO-30/50/70 (2 mm)")
    print(f"  화살표는 여섯 다 같은 크기 ({ARROW_LEN:.1f}) — 흔든 것은 겔이다")


if __name__ == "__main__":
    main()
