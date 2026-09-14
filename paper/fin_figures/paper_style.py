#!/usr/bin/env python3
"""논문 그림이 함께 쓰는 판형·색·저장 규칙.

`result/` 의 그림은 **자료를 들여다보기 위한 것**이라 한글 라벨에 넉넉한 판이다.
논문 그림은 다르다 — 영문이고, IEEE 두 단 판형에 맞아야 하고, 벡터로 나가야 하고,
축소돼 인쇄돼도 읽혀야 한다. 그 차이를 이 파일 한 곳에 모은다.

**그림과 그것을 그린 코드가 같은 폴더에 있다** (운전자 결정, 2026-09-14) — 이
폴더만 통째로 건네면 누구든 다시 그릴 수 있다. `paper_fig_*.py` 는 전부 이것을
import 한다. 새 그림을 만들 때 rcParams 를 다시 쓰지 말 것 — 여기를 고치면 모든
그림이 함께 움직여야 한다.

돌리는 법:  `cd paper/fin_figures && python3 paper_fig_<이름>.py`

색은 `palette.py` 를 그대로 가져온다. 팔레트 검증기 전 항목 통과를 확인했다
(인접 쌍 최악 ΔE 11.0 deutan, 보통 시야 25.8, 바탕 대비 전부 3:1 이상).
**그래도 색만으로 군을 가르지 않는다** — 표식 모양(MARKER)을 함께 건다.
흑백 인쇄와 색각 이상 양쪽에서 살아남아야 하기 때문이다.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

# 색은 `src/scripts/palette.py` 하나에서만 나온다 — `result/` 의 그림과 같은 색을
# 써야 하므로 여기에 값을 베껴 두지 않는다.
sys.path.insert(0, str(ROOT / "src" / "scripts"))
from palette import HARD3, PRINCIPLE, THICK3      # noqa: E402,F401 — 재수출

# 그림도 코드도 이 폴더다. `paper/figures/` 는 그 전에 만든 것이 들어 있는 곳이라
# 섞지 않는다.
FIGS = HERE

# IEEE 두 단 판형. 한 단 3.50 in, 두 단 걸침 7.16 in.
#
# **두 단 그림은 7.16 보다 좁게 그려도 된다** (운전자 결정, 2026-09-15). 본문에
# `\textwidth` 로 앉히면 그만큼 **확대**되므로 글자도 함께 커진다 — 좁게 그리고
# 크게 앉히는 것이 작은 글자를 키우는 가장 싼 방법이다. 대신 **패널 비율이
# 뭉개지지 않는 선**에서만 줄인다.
COL_W, FULL_W = 3.50, 7.16
FULL_W_NARROW = 6.10        # 두 패널짜리 두 단 그림의 기본

INK = "#1a1a1a"
MUTED = "#707070"
SUSPECT_MARK = "!"          # 빛 누출 의심 유닛

# 순서가 있는 변수라 색만으로는 부족하다. 모양을 함께 건다.
MARKER = {"soft": "o", "medium": "s", "hard": "^"}

# 원리별 표시 이름과 실측 쇼어. **두 계열이 같은 눈금이 아니다** — 9DTact 는 40 점을
# 흔들었고 광도 계열은 6 점이다(부록 B). 그림마다 이것을 적어야 "경도 효과 미검출"
# 이 정직하게 읽힌다.
SHORE = {"9DTact": {"soft": 30, "medium": 50, "hard": 70},
         "DIGIT": {"soft": 51, "medium": 54, "hard": 57},
         "DIGIT_Marker": {"soft": 51, "medium": 54, "hard": 57}}

# [AUTHOR CHECK] 본문의 최종 명칭이 아직 안 정해졌다 (outline 열린문제 7).
# 여기만 고치면 모든 그림이 따라온다.
DISPLAY = {"9DTact": "9DTact", "DIGIT": "DIGIT", "DIGIT_Marker": "DIGIT + markers"}


def use_paper_style():
    """모든 논문 그림에 공통으로 거는 rcParams."""
    plt.rcParams.update({
        "figure.dpi": 200,
        "savefig.dpi": 400,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.01,
        # 글자는 **인쇄에서 읽히는 것**이 기준이다. 7.5 pt 로 그렸더니 두 단에
        # 앉혔을 때 작았다(2026-09-15) — 한 단 올렸다.
        "font.size": 9.0,
        "axes.titlesize": 9.5,
        "axes.labelsize": 9.0,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "legend.fontsize": 8.5,
        "axes.linewidth": 0.6,
        "xtick.major.width": 0.6,
        "ytick.major.width": 0.6,
        "xtick.major.size": 2.6,
        "ytick.major.size": 2.6,
        "lines.linewidth": 1.6,
        "lines.markersize": 4.6,
        "grid.linewidth": 0.4,
        "grid.alpha": 0.30,
        "axes.edgecolor": "#444444",
        "text.color": INK,
        "axes.labelcolor": INK,
        "xtick.color": "#444444",
        "ytick.color": "#444444",
        # 글꼴을 문서에 심는다 — Type 3 은 IEEE PDF eXpress 가 되돌려 보낸다
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def style(ax, grid="y"):
    """위·오른쪽 테두리를 지우고 격자를 뒤로 보낸다."""
    ax.spines[["top", "right"]].set_visible(False)
    if grid:
        ax.grid(axis=grid, alpha=0.30, lw=0.4, color="#b6b6b6")
    ax.set_axisbelow(True)


def save(fig, df, stem):
    """pdf(본문용) · png(문서 미리보기용) · csv(다시 그릴 수 있게) 셋을 함께 낸다.

    **csv 없이 그림을 저장하지 않는다** — `result/` 의 규칙과 같다.
    셋 다 `paper/fin_figures/` 로 간다.
    """
    FIGS.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGS / f"{stem}.pdf")
    fig.savefig(FIGS / f"{stem}.png")
    plt.close(fig)
    df.to_csv(FIGS / f"{stem}.csv", index=False)
    print(f"  -> paper/fin_figures/{stem}.pdf · .png · .csv  ({len(df)} 행)")
