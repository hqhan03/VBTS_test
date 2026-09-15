#!/usr/bin/env python3
"""논문 그림 — 두 접촉 분리: 겔이 정하는 것과 화소가 정하는 것. (IV.B)

두 패널이 **서로 다른 질문**이다.

(a) 겔  — 두 기둥을 얼마나 가까이 붙여도 갈리는가. 전해상도에서 잰다.
(b) 화소 — 그 판정에 화소가 몇 개 드는가. 판정을 그대로 두고 입력만 줄인다.

(b) 는 힘·형상과 **같은 x 축**(화소 밀도 R)에 두 접촉 판정을 올리는 자리다.

(a) 에서 광도 스테레오는 점으로 찍지 않는다
    여덟 시편 **모두** 가장 좁은 압자(중심 간격 1.10 mm)를 갈랐다. **값이 아니라
    바닥이다** — 점을 찍으면 "1.10 mm 가 그 센서의 분해능" 으로 읽힌다.
    (광도의 `hard_2mm` 는 두 기둥 램프가 없어 여덟이다.)

(a) 의 범례는 **실측 쇼어**다
    soft / medium / hard 는 계열마다 다른 물건이라(9DTact OO-30 ~ 70 은 40 점,
    광도 계열 OO-51 ~ 57 은 6 점) 이름만으로는 무엇을 얼마나 흔들었는지 보이지
    않는다. 이 패널은 9DTact 뿐이므로 눈금을 그대로 적는다.

(b) 는 시편 하나, 압입 하나다
    아홉을 묶어 분해 **비율**로 그렸다가 뺐다(2026-09-15) — **겔 한계와 화소
    한계가 섞이기 때문**이다. `hard_3mm_r1` 은 전해상도 한계가 2.50 mm 라 어느
    밀도에서도 2.00 mm 를 가르지 못하는데(36 단 중 0), 그 실패가 모든 막대에
    들어가 곡선의 천장을 70 % 로 눌렀다. 화소가 아니라 겔이 정한 천장이다.

    그래서 **`soft_2mm_r1` 하나**만 그린다. 전해상도 한계가 1.75 mm 로 2.00 mm
    보다 여유가 있고, 전해상도에서 세 깊이 단을 모두 분해하는 아홉 중 유일한
    시편이다. 겔이 못 하는 것이 섞이지 않으므로 **남는 것은 화소 이야기뿐**이다.
    압입은 **0.30 mm 하나**만 그린다(운전자 결정).

    이 시편에서는 관문 셋 중 둘만 문다 — 골이 Rayleigh 를 넘긴 단은 밝기·잡음
    관문에 한 번도 걸리지 않는다(아래 `assert`). **Rayleigh 와 접촉 검출**만 남는다.

(b) 의 음영 — 잡음 관문을 **잴 수 없는** 구간 (2026-09-15, `spatial_resolution.md` §5.1a)
    160 px(R ≈ 55) 아래에서는 단면의 0.02 mm 칸이 카메라 화소보다 잘아, 이웃 칸
    여럿이 같은 화소에서 값을 길어 온다. `profile_noise` 의 이웃 차분은 그래서
    잡음이 아니라 **골의 기울기**를 잰다 — 옛 추정은 낮게(dip_sd 중앙이 1920 px
    0.0514 에서 8 px 0.0034 로 15 배 하락), 한 화소 간격으로 고친 추정은 높게
    (32 px 에서 sd 가 골의 3.7 배) 잡는다. **둘 다 틀리다.**

    **이 시편의 분해 판정 둘이 그 안에 있다** — R 4.9 (48 px) 와 R 13.6 (80 px).
    공표된(옛) 추정으로는 잡음 관문에 여유가 3.8 ~ 11.9 배라 물지 않지만, 문서가
    고친 추정의 폭별 중앙(48 px sd 0.214 · 80 px 0.130)을 그대로 대면 둘 다
    탈락하고 분해 시작이 **R 55** 로 올라간다. 그 중앙값은 아홉 유닛·세 깊이를
    묶은 것이지 이 시편의 값이 아니므로 **그렇게 된다고 적으면 안 된다** — 이
    시편의 고친 sd 는 원영상이 있어야 나온다(실험 기계).

    **기본값을 바꾸지 않았다**(운전자 결정)는 것을 따라, 점과 판정은 공표된
    추정 그대로 두고 **음영으로 구간만 표시**한다. 캡션이 그것을 말한다.

    고해상도 쪽 역전(854 → 1920 px 에서 분해 비율이 떨어지는 것)은 이것과
    **무관하다** — 그 구간은 건너뛰기가 1 이라 두 추정의 계산이 같다.

캡션이 져야 할 것 — 그림 안의 글자를 걷어냈으므로(운전자 결정) 다섯을 캡션이 진다
    1. **어느 패널이 무엇인가.** 제목이 `(a)` · `(b)` 뿐이다 —
       (a) 깊이 참조형 아홉 시편, 전해상도.
       (b) `soft_2mm_r1`, 압입 0.30 mm, 두 기둥 중심 간격 2.00 mm.
    2. **가장 좁은 압자가 중심 간격 1.10 mm** 라는 것, 그리고 **광도 스테레오는
       아홉 시편 모두 그 바닥에 있어 한계를 못 봤다**는 것 (본문 [IV-B2] 가
       "every specimen" 이라고 적는다 — 한때 여덟로 적혀 있었다). (a) 에 그 바닥을
       가리키는 선이 없다.
    3. (b) 의 **파선이 Rayleigh 문턱 dip = 0.265** 라는 것. 선은 있고 글자는 없다.
       판정은 **선 위/아래**로 읽는다 — 표식은 전부 같게 찍었다.
    4. (b) 왼쪽 끝의 `×` 는 **접촉 덩어리 자체를 못 찾은 단**이다 — 골이 얕아
       못 가른 것(파선 아래의 점)과 다른 실패다.
    5. (a) 의 **두께 경향** — Spearman rho +0.75 (p 0.02, n 9). 경도는 −0.13
       (p 0.73). 스크립트가 표준출력으로 낸다.

말하지 않는 것
    **"두 점을 가르는 데 R ≈ 387 px/mm² 가 든다" 를 쓰지 않는다.** 387 은 아홉을
    묶었을 때 분해 비율이 최대였던 밀도이고, 힘·형상에서 쓴 10 % 평탄 기준과
    다른 자다. 같은 기준을 세우기 전에는 그 둘을 나눈 배수도 말하지 않는다.

칸마다 정해진 센서 하나 (`CLAUDE.md` §1)

자료
    (a) `result/single/extra/data/G_spatial_resolution.csv`
    (b) `result/extra/data/resolution_sweep_9DTact_pair100.csv`
        (경로만 `extra` 다 — `resolution_sweep.py` 의 `OUT` 이 하드코딩돼 있고,
         실제로 돈 것은 선택된 아홉 개뿐이다. §1 위반이 아니다.)
"""
import pandas as pd
from scipy.stats import spearmanr

import paper_style as PS
from paper_style import HARD3, DISPLAY, SHORE

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402

HARDNESS = ("soft", "medium", "hard")
DODGE = dict(zip(HARDNESS, (-0.055, 0.0, 0.055)))
NARROWEST_MM = 1.10                       # 우리가 만든 가장 좁은 압자 (중심 간격)

SWEEP_UNIT = "soft_2mm_r1"                # 전해상도에서 세 깊이 단 모두 분해
SWEEP_DEPTH_MM = 0.3
SEP_MM = 2.00                             # pair100 — 기둥 ⌀1.0 mm, 중심 간격
RAYLEIGH = 0.265
LOST_Y = -0.20                            # 접촉을 못 찾은 단을 찍는 자리


def panel_gel(ax):
    """분해된 가장 좁은 간격 대 두께."""
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

    ax.legend(loc="upper left", frameon=False, handlelength=1.6,
              handletextpad=0.5, labelspacing=0.3, borderpad=0.1)
    ax.set_xticks([1, 2, 3])
    ax.set_xlim(0.72, 3.30)
    ax.set_ylim(0.86, 2.98)
    ax.set_xlabel("gel thickness [mm]")
    ax.set_ylabel("finest resolved separation [mm]")
    ax.set_title("(a)", loc="left")
    PS.style(ax)
    return nine.assign(rho_thickness=rho, p_thickness=p), rho, p


# 잡음 추정이 서는 가장 낮은 폭 (`spatial_resolution.md` §5.1a). 이 아래는
# 음영으로만 표시하고 값은 공표된 추정 그대로 둔다.
NOISE_FLOOR_PX = 160


def panel_pixels(ax):
    """한 시편·한 압입의 골 대 화소 밀도."""
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

    # **잡음 관문을 잴 수 없는 구간** (`spatial_resolution.md` §5.1a, 2026-09-15).
    # 160 px 아래에서는 단면의 0.02 mm 칸이 카메라 화소보다 잘아 이웃 차분이
    # 잡음이 아니라 골의 기울기를 잰다 — 옛 추정은 낮게, 고친 추정은 높게 잡고
    # **둘 다 틀리다.** 이 시편의 판정은 공표된(옛) 추정으로 낸 것이므로 값은
    # 그대로 두되, 어디부터 그 추정이 서지 않는지는 보여야 한다.
    floor_R = float(u[u.width_px == NOISE_FLOOR_PX].density_px_per_mm2.iloc[0])
    ax.axvspan(0.09, floor_R, color=PS.MUTED, alpha=0.07, lw=0, zorder=0)

    c = PS.SERIES
    ax.axhline(RAYLEIGH, c=PS.MUTED, lw=0.7, ls=(0, (4, 2)), zorder=1)
    ax.plot(seen.density_px_per_mm2, seen.dip, "-", c=c, lw=1.4, zorder=3)
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
    ax.set_title("(b)", loc="left")
    PS.style(ax, grid=None)
    ax.grid(alpha=0.25, lw=0.4, color="#c8c8c8")
    ax.set_axisbelow(True)
    return u, seen[seen.verdict == "분해"].density_px_per_mm2.min(), floor_R


def main():
    fig, axes = plt.subplots(1, 2, figsize=(PS.FULL_W_NARROW, 2.60))
    gel, rho, p = panel_gel(axes[0])
    sweep, first, floor_R = panel_pixels(axes[1])

    fig.tight_layout(w_pad=2.0)
    PS.save(fig, gel[["principle", "unit", "hardness", "thickness_mm",
                      "finest_centre_mm", "depth_lo_mm", "depth_hi_mm",
                      "n_gaps_resolved", "n_gaps_tested"]], "fig_separation")
    sweep[["unit", "probe", "depth_mm", "width_px", "density_px_per_mm2",
           "dip", "dip_sd", "imprint_lvl", "verdict"]].to_csv(
        PS.FIGS / "fig_separation_sweep.csv", index=False)
    print(f"  (a) 두께 rho {rho:+.3f}  p {p:.3f}  n {len(gel)}")
    print(f"  (b) {SWEEP_UNIT} @ {SWEEP_DEPTH_MM} mm — "
          f"분해되는 가장 낮은 밀도 R {first:.2f}"
          f"   (접촉 못 찾은 단 {int(sweep.dip.isna().sum())})")
    # 잡음 관문이 실제로 얼마나 여유 있었나 — 공표된 추정으로
    ok = sweep.dropna(subset=["dip"])
    ok = ok[ok.dip >= RAYLEIGH]          # 관문은 Rayleigh 를 넘긴 단에만 건다
    ratio = ok.dip / (3 * ok.dip_sd)
    print(f"      잡음 관문 여유 dip/(3 sd) {ratio.min():.1f} ~ {ratio.max():.1f} 배 "
          "— 공표된 추정으로는 한 단도 물지 않는다")
    print(f"      음영 = R < {floor_R:.1f} (§5.1a: 이 아래에서는 잡음 추정이 서지 "
          f"않는다). **분해되는 두 단(R {first:.1f} · 13.6)이 그 안에 있다**")


if __name__ == "__main__":
    main()
