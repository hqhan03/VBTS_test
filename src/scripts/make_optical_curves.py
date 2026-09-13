#!/usr/bin/env python3
"""깊이에 따른 자국 지름과 밝기 — 유닛별 그래프 + 기울기 3x3 표.

지름은 **픽셀**로 둔다. mm 로 바꾸려면 px/mm 이 필요한데 그 값이 유닛마다
최대 1.5 배 어긋나는 것이 2026-09-12 에 확인됐다(digit_shape.py 의 fit_scale).
픽셀은 측정된 그대로다.

자료는 두 종류에서 온다. 둘 다 깊이·자국·밝기를 한 행에 담는다:
  characterize/steps.csv     램프. 깊이 범위가 넓다 (선호)
  shape_<probe>/ladder.csv   형상 사다리. 얕지만 유닛이 다 있다 (대체)
"""
import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
RES = ROOT / "result"
FOLD = {"9DTact": "1_9DTact", "DIGIT": "2_DIGIT", "DIGIT_Marker": "3_DIGIT_Marker"}
HARD = ["soft", "medium", "hard"]
PC = {"ball4": "#c2553a", "ball8": "#1f6f8b"}

# (원리, 프로브) -> 후보 경로. 앞에서부터 있는 것을 쓴다.
SRC = {
    ("9DTact", "ball4"): ["20260911_passC_ceiling/*/characterize/steps.csv",
                          "20260905_passA_ball4/*/shape_ball4/ladder.csv"],
    ("9DTact", "ball8"): ["20260911_passC_ceiling_ball8/*/characterize/steps.csv",
                          "20260907_passB_ball8/*/characterize/steps.csv"],
    ("DIGIT", "ball4"): ["20260910_passA_calibgrid/*/characterize/steps.csv"],
    ("DIGIT", "ball8"): ["20260912_passC_ceiling_ball8/*/characterize/steps.csv"],
    ("DIGIT_Marker", "ball4"): ["20260910_passA_calibgrid/*/characterize/steps.csv"],
    ("DIGIT_Marker", "ball8"): [],          # 램프가 없다 — passB 는 광학 열이 없다
}


import matplotlib.ticker as mticker
SIZES_WH = [(1920, 1080), (1280, 720), (854, 480), (640, 360), (426, 240),
            (320, 180), (160, 90), (80, 45), (48, 27), (32, 18), (16, 9), (8, 5)]
XT = [w for w, _ in SIZES_WH]
XTL = [f"{w}\u00d7{h}" for w, h in SIZES_WH]


def res_axis(ax, yt=None, fs=7):
    """해상도 축을 가로x세로로 적고 보조선을 켠다."""
    ax.set_xticks(XT); ax.set_xticklabels(XTL, fontsize=fs, rotation=90)
    ax.xaxis.set_minor_locator(mticker.NullLocator())
    if yt is not None:
        ax.set_yticks(yt)
        ax.set_yticklabels([f"{v:g}" for v in yt], fontsize=fs + 1)
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax.grid(True, which="major", axis="both", alpha=.35, lw=.55, color="#b0b0b0")
    ax.set_axisbelow(True)

def plain_log(ax, which="y"):
    """로그 축 눈금을 평범한 숫자로. mathtext 를 쓰지 않게 해 마이너스 깨짐을 없앤다.

    NanumGothic 에 U+2212 글리프가 없어 로그 포매터의 $10^{-1}$ 이 "10<깨짐>1" 로
    나온다. axes.unicode_minus 도 mathtext.fontset 도 이 경로에는 듣지 않았다.
    """
    from matplotlib.ticker import FuncFormatter, NullFormatter
    f = FuncFormatter(lambda v, _: f"{v:g}")
    for a in ([ax.yaxis] if which == "y" else
              [ax.xaxis] if which == "x" else [ax.xaxis, ax.yaxis]):
        a.set_major_formatter(f)
        a.set_minor_formatter(NullFormatter())

def load(pr, probe):
    """(유닛, 깊이, 지름 px, 밝기) 표. 여러 런이 있으면 가장 긴 것."""
    rows = []
    for pat in SRC[(pr, probe)]:
        for f in glob.glob(str(DS / pr / pat)):
            u = Path(f).parents[1].name.replace(pr + "_", "").split("__")[0]
            d = pd.read_csv(f)
            dia = "radius_px"
            lvl = ("img_mean_abs_diff" if "img_mean_abs_diff" in d
                   else "mean_abs_diff_in_region")
            if dia not in d or lvl not in d:
                continue
            rows.append(pd.DataFrame(dict(
                unit=u, probe=probe, source=Path(f).parents[2].name,
                depth_mm=d.depth_mm, diameter_px=2 * d[dia], level=d[lvl])))
    if not rows:
        return pd.DataFrame()
    D = pd.concat(rows)
    # **소스를 하나로 통일한다.** 유닛마다 다른 pass 를 쓰면 깊이 구간이 달라져
    # 기울기가 비교 불가가 된다 — 9DTact ball4 에서 복제 쌍이 119 대 317 로
    # 벌어진 것이 그 때문이었다(8 유닛은 깊은 램프, 9 유닛은 얕은 사다리).
    best = D.groupby("source").unit.nunique().idxmax()
    return D[D.source == best]


def valid_span(g):
    """검출이 살아 있는 구간만. 자국이 시야를 채우면 `contact_region` 이 덩어리를
    놓쳐 지름이 0 으로 무너지고, 그 뒤 0 과 수백 사이를 오간다(면적 감시를 떼어낸
    것과 같은 원인, docs/force_ceiling.md 6.5b). 그 구간을 넣고 직선을 맞추면
    복제 쌍 안에서 119 대 317, 심지어 음수 기울기가 나온다. 누적 최대의 30 %
    밑으로 처음 떨어지는 곳에서 자른다."""
    g = g.sort_values("depth_mm").reset_index(drop=True)
    run = g.diameter_px.cummax()
    bad = (g.diameter_px < 0.30 * run) & (run > 0)
    if bad.any():
        g = g.iloc[:int(bad.idxmax())]
    return g


# 기울기를 맞추는 **공통 깊이 창**. 자료마다 깊이 범위가 다르다 — ball4 사다리는
# 0.07~0.57 mm, 램프는 5 mm 까지 간다. 창을 맞추지 않으면 유닛마다 다른 구간의
# 기울기를 비교하게 되고, 9DTact ball4 의 복제 쌍이 119 대 317 로 벌어진다.
WINDOW = (0.10, 0.50)


def slopes(D, window=WINDOW):
    """유닛·프로브별 기울기 — 지름 px/mm 와 밝기 lvl/mm. 공통 창 안에서만."""
    out = []
    for (u, p), g in D.groupby(["unit", "probe"]):
        g = valid_span(g[g.depth_mm > 0])
        # 창은 각 유닛 자신의 유효 구간이다. 자료마다 깊이 범위가 달라 고정 창을
        # 쓰면 두꺼운 겔이 통째로 빠진다(얕은 깊이에선 자국이 아직 검출되지 않는다).
        # 그래서 구간을 표에 함께 적고, **원리 간 기울기 비교는 하지 않는다.**
        g = g[g.diameter_px > 0]
        if len(g) < 4:
            continue
        sd = np.polyfit(g.depth_mm, g.diameter_px, 1)[0]
        sl = np.polyfit(g.depth_mm, g.level, 1)[0]
        out.append(dict(unit=u, probe=p, hardness=u.split("_")[0],
                        thickness_mm=int(u.split("_")[1][0]), rep=int(u[-1]),
                        n=len(g), depth_lo_mm=g.depth_mm.min(),
                        depth_hi_mm=g.depth_mm.max(),
                        r2=float(np.corrcoef(g.depth_mm, g.diameter_px)[0, 1] ** 2),
                        dia_slope_px_per_mm=sd, level_slope_per_mm=sl))
    return pd.DataFrame(out)


def grid3x3(S, col, fmt="{:.0f}"):
    """3x3. 칸 = 'r1 / r2  (평균)'."""
    rows = []
    for h in HARD:
        r = {"hardness": h}
        for t in (1, 2, 3):
            v = S[(S.hardness == h) & (S.thickness_mm == t)].sort_values("rep")[col].dropna()
            if not len(v):
                r[f"{t}mm"] = "—"
            else:
                e = " / ".join(fmt.format(x) for x in v)
                r[f"{t}mm"] = f"{e}  ({fmt.format(v.mean())})" if len(v) > 1 else e
        rows.append(r)
    return pd.DataFrame(rows)


def panel(pr, D):
    """유닛 18 개 격자. 프로브당 선 하나, 지름과 밝기를 두 축에."""
    units = [f"{h}_{t}mm_r{r}" for h in HARD for t in (1, 2, 3) for r in (1, 2)]
    drawn = []          # 그린 숫자를 그대로 csv 로 남긴다
    fig, axes = plt.subplots(3, 6, figsize=(19, 9), sharex=True)
    for ax, u in zip(axes.ravel(), units):
        g = D[D.unit == u]
        if not len(g):
            ax.text(.5, .5, "자료 없음", ha="center", va="center", fontsize=8,
                    color="#999", transform=ax.transAxes)
            ax.set_title(u, fontsize=8, color="#999"); ax.set_xticks([]); ax.set_yticks([])
            continue
        a2 = ax.twinx()
        for p, gg in g.groupby("probe"):
            gg = gg.sort_values("depth_mm")
            ax.plot(gg.depth_mm, gg.diameter_px, "-o", c=PC[p], lw=1.5, ms=3.6,
                    mec="white", mew=.6, label=p, zorder=3)
            a2.plot(gg.depth_mm, gg.level, "--s", c=PC[p], lw=1.1, ms=2.8,
                    alpha=.65, mec="white", mew=.4)
            drawn.append(gg[["unit", "probe", "depth_mm", "diameter_px",
                             "level"]].copy())
        ax.set_title(u, fontsize=8.5)
        ax.tick_params(labelsize=7); a2.tick_params(labelsize=6, colors="#777")
        ax.spines[["top"]].set_visible(False); a2.spines[["top"]].set_visible(False)
        # 보조선: 눈금마다 가로·세로 모두
        ax.grid(True, which="major", axis="both", alpha=.35, lw=.5,
                color="#b0b0b0")
        ax.set_axisbelow(True)
    for ax in axes[-1]:
        ax.set_xlabel("깊이 (mm)", fontsize=8)
    for ax in axes[:, 0]:
        ax.set_ylabel("자국 지름 (px)", fontsize=8)
    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper right", frameon=False, fontsize=9, ncol=2)
    fig.suptitle(f"{pr} — 깊이에 따른 자국 지름(실선, 왼쪽 축)과 밝기 변화"
                 f"(점선, 오른쪽 축)", fontsize=12, x=.09, ha="left")
    fig.tight_layout(rect=[0, 0, 1, .96])
    d = RES / FOLD[pr]
    (d / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(d / "figures" / "optical_vs_depth_18units.png", dpi=150,
                bbox_inches="tight")
    plt.close(fig)
    (d / "data").mkdir(parents=True, exist_ok=True)
    (pd.concat(drawn) if drawn else pd.DataFrame()).to_csv(
        d / "data" / "optical_vs_depth_18units.csv", index=False)


def main():
    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    # NanumGothic 에 유니코드 마이너스(U+2212) 글리프가 없어 축 라벨이
    # "6 x 10<깨짐>2" 로 나온다. ASCII 하이픈을 쓰게 한다.
    plt.rcParams["axes.unicode_minus"] = False
    # 로그 축 라벨은 mathtext 로 그려지고 그것도 NanumGothic 을 따라가
    # "10<깨짐>1" 이 된다. mathtext 에는 완전한 폰트를 따로 준다.
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
        D = pd.concat([load(pr, p) for p in ("ball4", "ball8")], ignore_index=True)
        d = RES / FOLD[pr] / "data"
        d.mkdir(parents=True, exist_ok=True)
        if not len(D):
            print(f"  {pr}: 광학 자료 없음"); continue
        D.to_csv(d / "optical_vs_depth.csv", index=False)
        S = slopes(D)
        S.to_csv(d / "optical_slopes.csv", index=False)
        for p in S.probe.unique():
            g = S[S.probe == p]
            grid3x3(g, "dia_slope_px_per_mm").to_csv(
                d / f"optical_slope_diameter_{p}_3x3.csv", index=False)
            grid3x3(g, "level_slope_per_mm", "{:.1f}").to_csv(
                d / f"optical_slope_level_{p}_3x3.csv", index=False)
        panel(pr, D)
        got = ", ".join(f"{p} {S[S.probe==p].unit.nunique()}유닛"
                        for p in sorted(S.probe.unique()))
        print(f"  {pr:<13} {len(D):>6} 행  ({got})")
        for p in sorted(S.probe.unique()):
            print(f"     지름 기울기 {p} (px/mm):")
            print(grid3x3(S[S.probe == p], "dia_slope_px_per_mm").to_string(index=False))


if __name__ == "__main__":
    main()
