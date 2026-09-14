#!/usr/bin/env python3
"""후보 그림 — 시편 **하나**의 두 접촉 판정 대 화소 밀도. (IV.B 보조)

**[대기] 실을지 안 실을지 정해지지 않았다.** F4 에서 화소 패널을 뺀 뒤
(운전자 결정, 2026-09-15) "전해상도에서 2.00 mm 를 가를 수 있는 시편 하나만
보자" 는 요청으로 만든 것이다.

왜 아홉을 묶으면 안 됐나
    묶은 판은 **겔 한계와 화소 한계가 섞여** 있었다. 같은 간격 2.00 mm 를 아홉
    시편에 걸었는데 `hard_3mm_r1` 은 전해상도 한계가 2.50 mm 라 어느 밀도에서도
    가르지 못한다(36 단 중 0). 그 실패가 모든 막대에 들어가 곡선의 천장을
    70 % 로 눌렀다 — 화소가 아니라 겔이 정한 천장이다.

왜 이 시편인가
    `soft_2mm_r1` 은 전해상도 분해 한계가 **1.75 mm** 로 2.00 mm 보다 여유가
    있고, 전해상도에서 **세 깊이 단 모두** 분해한다(9DTact 아홉 중 유일). 겔이
    못 하는 것이 섞이지 않으므로 **남는 것은 화소 이야기뿐**이다.

이 시편에서는 관문 셋 중 하나만 문다
    **골이 Rayleigh 를 넘긴 단은 나머지 두 관문에 한 번도 걸리지 않는다.** 자국
    밝기는 3.3 ~ 8.5 레벨로 판정 바닥 2.5 를 밑돈 적이 없다. 그래서 남는 것은
    **Rayleigh 와 접촉 검출** 둘뿐이고, 이 그림은 그 둘만 그린다.
    (0.3 mm · 16 px 한 단에서 잡음 관문이 물지만 그 단은 골이 음수라 Rayleigh
    에서 이미 떨어진다 — 그림에서 회색 띠 아래 빈 표식으로 보인다.)

읽히는 것
    **요구 밀도가 압입 깊이에 달려 있다** — 0.3 mm 는 R ≈ 4.9, 0.2 mm 는
    R ≈ 13.6, 0.1 mm 는 R ≈ 54.6 부터 갈린다. 같은 겔, 같은 압자, 같은 판정이다.

    **다만 기전이 둘로 갈린다.** 0.2 · 0.3 mm 는 골이 Rayleigh 를 넘느냐로
    갈리는데(두 곡선은 R ≲ 50 에서 거의 포개져 있어 문턱을 스치는 자리만 다르다),
    0.1 mm 는 **그 아래에서 접촉 덩어리를 아예 못 찾는다** — 골의 문제가 아니라
    검출의 문제다. 배수를 인용할 때 이 차이를 함께 적을 것.

    그리고 **이 시편에서는 전해상도가 손해가 아니다** — 묶은 판의 그 현상은
    다른 시편들의 신호부족에서 온 것이다.

자료
    `result/extra/data/resolution_sweep_9DTact_pair100.csv`
    (경로만 `extra` 다 — `resolution_sweep.py` 의 `OUT` 이 하드코딩돼 있고,
     실제로 돈 것은 선택된 아홉 개뿐이다. `CLAUDE.md` §1 위반이 아니다.)
"""
import pandas as pd
from matplotlib.lines import Line2D

import paper_style as PS

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402

UNIT = "soft_2mm_r1"          # 전해상도에서 세 깊이 단 모두 분해하는 유일한 시편
SEP_MM = 2.00                 # pair100 — 기둥 ⌀1.0 mm, 중심 간격
RAYLEIGH = 0.265

# 압입 깊이는 **순서가 있는 변수**다. 경도·두께에 쓰는 범주 셋(파랑·주황·초록)을
# 여기에 다시 쓰면 같은 색이 그림마다 다른 뜻이 된다. 한 색의 농담으로 간다.
DEPTH_RAMP = {0.1: "#9dc3d0", 0.2: "#4a90a8", 0.3: "#14556b"}
DEPTH_MARK = {0.1: "o", 0.2: "s", 0.3: "^"}


def main():
    d = pd.read_csv(PS.ROOT / "result/extra/data/resolution_sweep_9DTact_pair100.csv")
    u = d[d.unit == UNIT].sort_values(["depth_mm", "width_px"])
    assert len(u), f"{UNIT} 가 없다"
    # **Rayleigh 를 넘긴 단은 나머지 두 관문에 한 번도 걸리지 않는다** — 이 그림이
    # 골과 접촉 검출만 그리는 근거다. (0.3 mm · 16 px 에서 잡음 관문이 물지만 그
    # 단은 골이 음수라 Rayleigh 에서 이미 떨어진다.)
    ok = u.dropna(subset=["dip"])
    passed = ok[ok.dip >= RAYLEIGH]
    assert (passed.imprint_lvl >= 2.5).all(), "밝기 관문이 물었다 — 그림에 넣어야 한다"
    assert (passed.dip > 3 * passed.dip_sd).all(), "잡음 관문이 물었다 — 그림에 넣어야 한다"
    assert (passed.verdict == "분해").all(), "Rayleigh 를 넘겼는데 분해가 아니다"

    fig, ax = plt.subplots(figsize=(PS.COL_W, 2.45))

    ax.axhspan(-0.25, RAYLEIGH, color="#f2f2f2", lw=0, zorder=0)
    ax.axhline(RAYLEIGH, c=PS.MUTED, lw=0.7, ls=(0, (4, 2)), zorder=1)
    ax.annotate(f"Rayleigh {RAYLEIGH}", xy=(0.985, RAYLEIGH), xytext=(0, -7),
                textcoords="offset points", xycoords=("axes fraction", "data"),
                ha="right", va="top", fontsize=6.0, color=PS.MUTED)

    for dep, g in u.groupby("depth_mm"):
        c, m = DEPTH_RAMP[dep], DEPTH_MARK[dep]
        seen = g.dropna(subset=["dip"])
        ax.plot(seen.density_px_per_mm2, seen.dip, "-", c=c, lw=1.4, zorder=3)
        res = seen[seen.verdict == "분해"]
        no = seen[seen.verdict != "분해"]
        ax.plot(res.density_px_per_mm2, res.dip, m, c=c, ms=4.2, mec="white",
                mew=0.7, ls="none", zorder=4)
        ax.plot(no.density_px_per_mm2, no.dip, m, mfc="none", mec=c, mew=0.9,
                ms=4.2, ls="none", zorder=4)
        # 접촉 덩어리 자체를 못 찾은 단 — 값이 없으므로 축 바닥에 따로 찍는다
        lost = g[g.dip.isna()]
        ax.plot(lost.density_px_per_mm2, [-0.20] * len(lost), "x", c=c,
                ms=3.6, mew=1.0, ls="none", zorder=4)

    ax.annotate("contact not detected", xy=(0.025, -0.20),
                xycoords=("axes fraction", "data"), xytext=(0, 12),
                textcoords="offset points", fontsize=6.0, color=PS.MUTED)

    lo, hi = ax.get_ylim() if False else (-0.27, 0.73)
    for dep, g in u.groupby("depth_mm"):
        r = g[g.verdict == "분해"]
        if not len(r):
            continue
        ax.plot(r.density_px_per_mm2.min(), lo, "^", c=DEPTH_RAMP[dep], ms=4.6,
                mec="white", mew=0.6, clip_on=False, zorder=6)
    # 범례가 오른쪽 아래를 쓰므로 라벨은 첫 삼각형 **왼쪽**에 둔다
    ax.annotate("first density\nthat resolves", xy=(3.6, lo), ha="right",
                va="center", fontsize=6.0, color=PS.MUTED, linespacing=1.4)

    hs = [Line2D([], [], color=DEPTH_RAMP[k], marker=DEPTH_MARK[k], ms=4.2,
                 lw=1.4, mec="white", mew=0.7, label=f"{k:.1f} mm")
          for k in DEPTH_RAMP]
    leg = ax.legend(handles=hs, loc="lower right", frameon=False, fontsize=6.6,
                    handlelength=1.7, handletextpad=0.5, labelspacing=0.3,
                    borderpad=0.1, title="indentation", title_fontsize=6.6)
    leg._legend_box.align = "left"

    ax.set_xscale("log")
    ax.set_xlim(0.09, 1.4e4)
    ax.set_ylim(-0.27, 0.73)
    ax.set_xlabel(r"pixel density $R$ [px/mm$^2$]")
    ax.set_ylabel("dip  $(P-T)/P$")
    ax.set_title(f"{UNIT.replace('_', ' ')}  ·  two posts {SEP_MM:.2f} mm apart",
                 fontsize=8.0, loc="left")
    PS.style(ax, grid=None)
    ax.grid(alpha=0.25, lw=0.4, color="#c8c8c8")
    ax.set_axisbelow(True)

    fig.tight_layout(pad=0.3)
    PS.save(fig, u[["unit", "probe", "depth_mm", "width_px",
                    "density_px_per_mm2", "dip", "dip_sd", "imprint_lvl",
                    "verdict"]], "fig_separation_sweep_one_unit")

    for dep, g in u.groupby("depth_mm"):
        r = g[g.verdict == "분해"]
        lo = r.density_px_per_mm2.min() if len(r) else float("nan")
        print(f"  압입 {dep:.1f} mm — 분해되는 가장 낮은 밀도 R {lo:>8.2f}"
              f"   (분해 {len(r)}/{len(g)} 단)")


if __name__ == "__main__":
    main()
