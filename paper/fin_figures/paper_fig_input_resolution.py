#!/usr/bin/env python3
"""논문 Figure 1 — 과제마다 드는 화소가 다르다. (I 장)

**핵심 한 장이다** (운전자 결정, 2026-09-15). 같은 접촉 프레임을 면적 평균으로
줄여 넣고, **두 과제**의 오차가 어디서 평평해지는지 본다.

    (a)(b)(c)  같은 프레임, R = 220 / 13.8 / 0.55 px/mm² — 눈으로 보는 축
    (d)        힘 추정 — 수직력 MAE 대 화소 밀도
    (e)        형상 복원 — 깊이 MAE 대 화소 밀도, 압자 둘

**이 그림이 지는 주장은 하나다.** 같은 센서·같은 접촉인데 **평평해지는 자리가
과제마다 다르다** — 힘은 R ≈ 5, 원기둥은 ≈ 47, 정육면체는 ≈ 188 이다. 40 배다.
"해상도가 높을수록 좋다"도 "해상도는 상관없다"도 아니라는 것이 논문의 출발점이고,
Figure 1 이 그것을 먼저 보여 준다.

(e) 의 오른쪽 끝이 다시 오른다
    화소를 더 주면 오차가 **커진다**. 잡음이 함께 들어오기 때문이고, 힘 (d) 에서도
    같은 모양이 약하게 보인다. 이 그림은 **관찰만 적는다** — 까닭은 본문이 진다.

▲ 가 가리키는 것 = **그 과제의 요구 밀도**
    제 바닥의 110 % 안에 드는 **가장 낮은 밀도**다. 셋을 같은 자로 잰다.
    임의의 절대 문턱(예: "0.1 mm 이하")을 쓰지 않는다 — 과제마다 단위가 달라
    (N 과 mm) 견줄 수 없고, 잰 것은 **평평해지는 자리**이지 합격선이 아니다.

    | 과제 | 요구 밀도 R | 그 자리의 오차 | 바닥 |
    |---|---:|---:|---:|
    | 힘 (수직력) | **4.9** | 0.051 N | 0.047 N |
    | 형상, 원기둥 ⌀4 | **47** | 0.062 mm | 0.061 mm |
    | 형상, 정육면체 4 mm | **188** | 0.081 mm | 0.075 mm |

    **배수를 본문에 쓸 때는 단이 성긴 것을 함께 적을 것** — 밀도 단이 대략 ×4 씩
    뛰므로 47 대 188 은 **한 단 차이**다. "4 배" 가 아니라 "한 단 높다" 가 정직하다.

(e) 의 압자 둘은 색과 **선 모양**으로 함께 가른다
    팔레트 넷 가운데 파랑·빨강이고, 실선·파선을 겹쳐 건다 — 흑백 인쇄와 색각
    이상에서 둘 다 살아남는 값싼 길이다(`paper_style` 머리글).

`data/` 없이 돌아간다
    원본이 `paper/figures/sources/` 에 있고, 밀도는 csv 가 들고 있다 —
    `pixel_density.density()` 는 `data/analysis/` 를 봐야 해서 쓰지 않는다.

캡션이 져야 할 것 — 그림 안에 설명 글자를 넣지 않으므로 다섯을 캡션이 진다
    1. **어느 패널이 무엇인가.** (a)(b)(c) 는 같은 프레임(`hard_2mm_r1`, ball ⌀8)
       을 R = 220 / 13.8 / 0.55 로 줄인 것, (d) 힘, (e) 형상.
    2. **곡선은 9DTact 선택 아홉 시편의 중앙값**이고 띠는 사분범위다.
    3. **▲ 는 요구 밀도** — 제 바닥의 110 % 안에 드는 가장 낮은 밀도.
       힘 4.9 · 원기둥 47 · 정육면체 188.
    4. (e) 의 **파랑 실선이 원기둥 ⌀4, 빨강 파선이 정육면체 4 mm** 라는 것.
    5. **`fig_separation` 과 잇지 않는다** — 그것은 "두 접촉을 가를 수 있나" 로
       다른 질문이고, 같은 x 축을 쓴다고 이어지는 것이 아니다.

칸마다 정해진 센서 하나 (`CLAUDE.md` §1)

자료
    영상 `paper/figures/sources/fig1c_hard_2mm_r1_ball8_000501.png`
    (d)  `paper/figures/fig2_force_vs_resolution.csv`
    (e)  `result/single/1_9DTact/data/shape_mae_vs_resolution_9units.csv`
"""
import cv2
import pandas as pd

import paper_style as PS
from paper_style import BLUE, RED, letters

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402

SRC = PS.ROOT / "paper" / "figures" / "sources"
FORCE_CSV = PS.ROOT / "paper" / "figures" / "fig2_force_vs_resolution.csv"
SHAPE_CSV = (PS.ROOT / "result/single/1_9DTact/data"
             / "shape_mae_vs_resolution_9units.csv")

SHOW_PX = [320, 80, 16]                            # 보여 주는 세 단
SWEEP_UNIT = "hard_2mm_r1"                         # 영상이 나온 유닛
PLATEAU = 1.10                                     # 제 바닥의 110 % 안
PROBES = [("cyl4", r"cylinder $\varnothing$4", BLUE, "-"),
          ("cube4", "cube 4 mm", RED, (0, (4.5, 2.0)))]


def plateau_R(t):
    """제 바닥의 110 % 안에 드는 **가장 낮은 밀도**. 셋을 같은 자로 잰다."""
    return float(t[t.med <= PLATEAU * t.med.min()].R.iloc[0])


def mark(ax, R, c, m="^"):
    """요구 밀도를 축 **아래**에 찍는다. 곡선 위에 얹으면 자료처럼 읽힌다."""
    ax.plot([R], [0], m, c=c, ms=6.0, mec="white", mew=0.6,
            transform=ax.get_xaxis_transform(), clip_on=False, zorder=6)


def force_curve():
    """(d) 아홉 시편의 수직력 MAE 중앙값. 단은 `width_px`, x 는 실제 밀도다."""
    g = pd.read_csv(FORCE_CSV)
    g = g[(g.principle == "9DTact") & (g.measure == "fz_mae")]
    assert g.sensor.nunique() == 9, "선택 아홉이 아니다"
    t = (g.groupby("width_px")
          .agg(R=("density_px_per_mm2", "median"), med=("mae_N", "median"),
               lo=("mae_N", lambda s: s.quantile(.25)),
               hi=("mae_N", lambda s: s.quantile(.75)),
               n=("mae_N", "size"))
          .sort_values("R"))
    return t


def shape_curves():
    """(e) 압자마다의 깊이 MAE 중앙값.

    이 csv 에는 `width_px` 가 없고 **밀도만** 있다. 밀도는 유닛마다 다르므로
    (겔 폭이 달라 mm 당 화소가 다르다) 밀도로 묶으면 칸마다 한 시편만 들어간다 —
    그래서 **축소 단의 차례**로 묶고 x 는 그 단의 밀도 중앙값으로 둔다.
    """
    d = pd.read_csv(SHAPE_CSV)
    assert not d.suspect_hardware.any(), "선택 규칙이 거른 유닛이 남아 있다"
    assert d.sensor.nunique() == 9, "선택 아홉이 아니다"
    d = d.sort_values(["probe", "sensor", "density_px_per_mm2"])
    d["rung"] = d.groupby(["probe", "sensor"]).cumcount()
    # 마지막 단은 원영상이 큰 넷에만 있다 — 아홉이 모두 가진 단까지만 그린다.
    full = d.groupby(["probe", "rung"]).sensor.nunique().eq(9)
    keep = full[full].reset_index().rung.max()
    d = d[d.rung <= keep]
    out = {}
    for probe, g in d.groupby("probe"):
        out[probe] = (g.groupby("rung")
                       .agg(R=("density_px_per_mm2", "median"),
                            med=("mae_mm", "median"),
                            lo=("mae_mm", lambda s: s.quantile(.25)),
                            hi=("mae_mm", lambda s: s.quantile(.75)),
                            n=("mae_mm", "size")))
    return out


def panel_frames(axes):
    """(a)(b)(c) 같은 프레임을 면적 평균으로 줄인 것.

    제목은 **밀도**다. 픽셀 폭은 그 단을 가리키는 이름일 뿐이고, 묻는 것은 면적당
    화소가 몇 개냐다 — 유닛마다 겔 폭이 달라 같은 폭이 같은 밀도가 아니다.
    """
    base = cv2.imread(str(SRC / f"fig1c_{SWEEP_UNIT}_ball8_000501.png"),
                      cv2.IMREAD_GRAYSCALE)
    assert base is not None, "축소 시연에 쓸 원본이 없다"
    g = pd.read_csv(FORCE_CSV)
    g = g[(g.principle == "9DTact") & (g.sensor == SWEEP_UNIT)]
    rows = []
    for ax, w in zip(axes, SHOW_PX):
        r = g[g.width_px == w]
        assert len(r), f"{SWEEP_UNIT} 의 {w} px 단이 csv 에 없다"
        R = float(r.density_px_per_mm2.median())
        h = int(round(w * base.shape[0] / base.shape[1]))
        ax.imshow(cv2.resize(base, (w, h), interpolation=cv2.INTER_AREA),
                  cmap="gray")
        ax.set_title(f"$R$ = {R:.3g}", pad=3)
        ax.set_xticks([]); ax.set_yticks([])
        rows.append(dict(unit=SWEEP_UNIT, width_px=w, density_px_per_mm2=R))
    return pd.DataFrame(rows)


def panel_force(ax):
    """(d) 힘 — 로그·로그. 값이 좁은 띠 안에서 움직여 선형 축이면 눌린다."""
    t = force_curve()
    ax.fill_between(t.R, t.lo, t.hi, color=PS.SERIES, alpha=0.13, lw=0)
    ax.plot(t.R, t.med, "-o", c=PS.SERIES, lw=1.8, ms=4.4, mec="white", mew=0.7)
    R = plateau_R(t)
    mark(ax, R, PS.SERIES)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(0.09, 1.4e4)
    ax.set_ylim(0.033, 0.118)
    ax.set_xticks([0.1, 10, 1000]); ax.set_xticklabels(["0.1", "10", "1000"])
    ax.set_yticks([0.05, 0.1]); ax.set_yticklabels(["0.05", "0.1"])
    ax.minorticks_off()
    ax.set_xlabel(r"pixel density $R$ [px/mm$^2$]")
    ax.set_ylabel("force MAE [N]")
    PS.style(ax, grid=None)
    ax.grid(alpha=0.25, lw=0.4, color="#c8c8c8")
    ax.set_axisbelow(True)
    return t.assign(task="force_fz", probe="ball8", required_R=R), R


def panel_shape(ax):
    """(e) 형상 — y 는 선형이다. 0 이 뜻을 갖는 값이라 밑동을 보여야 한다."""
    cur = shape_curves()
    rows, req = [], {}
    for probe, label, c, ls in PROBES:
        t = cur[probe]
        ax.fill_between(t.R, t.lo, t.hi, color=c, alpha=0.13, lw=0)
        ax.plot(t.R, t.med, ls=ls, c=c, lw=1.8, label=label)
        req[probe] = plateau_R(t)
        mark(ax, req[probe], c)
        rows.append(t.assign(task="shape_depth", probe=probe,
                             required_R=req[probe]))
    ax.set_xscale("log")
    ax.set_xlim(0.09, 1.4e4)
    ax.set_ylim(0.0, 0.365)
    ax.set_xticks([0.1, 10, 1000]); ax.set_xticklabels(["0.1", "10", "1000"])
    ax.minorticks_off()
    ax.set_yticks([0.0, 0.1, 0.2, 0.3])
    ax.set_xlabel(r"pixel density $R$ [px/mm$^2$]")
    ax.set_ylabel("depth MAE [mm]")
    ax.legend(loc="upper right", frameon=False, handlelength=1.9,
              handletextpad=0.45, labelspacing=0.22, borderpad=0.1,
              borderaxespad=0.1, fontsize=9.0)
    PS.style(ax, grid=None)
    ax.grid(alpha=0.25, lw=0.4, color="#c8c8c8")
    ax.set_axisbelow(True)
    return pd.concat(rows), req


def main():
    # 줄마다 격자를 따로 건다 — 윗줄 셋과 아랫줄 둘은 칸 너비가 다르다.
    # 왼쪽·오른쪽 끝만 맞추면 두 줄이 그대로 줄이 선다.
    L, R = 0.108, 0.988
    fig = plt.figure(figsize=(PS.FULL_W_NARROW, 3.55))
    # 윗줄 높이는 **영상이 제 비율로 다 들어가는 높이**다. 원본이 16:9 라
    # 칸 너비의 0.5625 배면 된다.
    g_top = fig.add_gridspec(1, 3, wspace=0.26,
                             left=L, right=R, top=0.945, bottom=0.703)
    g_bot = fig.add_gridspec(1, 2, wspace=0.40,
                             left=L, right=R, top=0.600, bottom=0.135)
    top = [fig.add_subplot(g_top[0, i]) for i in range(3)]
    bot = [fig.add_subplot(g_bot[0, i]) for i in range(2)]

    frames = panel_frames(top)
    force, force_R = panel_force(bot[0])
    shape, shape_R = panel_shape(bot[1])
    letters(fig, [top, bot])

    tidy = pd.concat([
        force.reset_index().rename(columns={"width_px": "rung"})
             .assign(unit_measure="N"),
        shape.reset_index().assign(unit_measure="mm"),
    ])[["task", "probe", "rung", "R", "med", "lo", "hi", "n",
        "required_R", "unit_measure"]]
    PS.save(fig, tidy, "fig_input_resolution")
    frames.to_csv(PS.FIGS / "fig_input_resolution_frames.csv", index=False)
    print("  (a)(b)(c) " + " · ".join(
        f"{r.width_px} px (R {r.density_px_per_mm2:.3g})"
        for r in frames.itertuples()) + f"  —  {SWEEP_UNIT}")
    print(f"  (d) 힘   요구 밀도 R {force_R:.3g}")
    print("  (e) 형상 요구 밀도 " + " · ".join(
        f"{p} R {shape_R[p]:.3g}" for p, *_ in PROBES) + "   (9 시편 중앙값)")


if __name__ == "__main__":
    main()
