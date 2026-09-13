#!/usr/bin/env python3
"""축별 힘·토크 MAE 대 해상도 — 유닛 18 개 격자 + 원리 요약.

모델은 ResNet-18 의 fc 를 6 출력으로 바꾼 것이라 Fx, Fy, Fz, Tx, Ty, Tz 를 모두
예측한다. 2026-09-12 이전에는 Fx, Fy 를 CSV 에 쓰지 않고 hypot 으로 합친
`lat_mae` 만 남겼다 — 방향별 성능이 보이지 않았다.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

import result_common as RC

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
RES = ROOT / "result"
FOLD = {"9DTact": "1_9DTact", "DIGIT": "2_DIGIT", "DIGIT_Marker": "3_DIGIT_Marker"}
REP = {"9DTact": "grey", "DIGIT": "raw", "DIGIT_Marker": "inpaint"}
AX = [("fx_mae", "Fx", "#c2553a"), ("fy_mae", "Fy", "#d9a441"),
      ("fz_mae", "Fz", "#1f6f8b")]
TQ = [("tx_mae", "Tx", "#c2553a"), ("ty_mae", "Ty", "#d9a441"),
      ("tz_mae", "Tz", "#1f6f8b")]
HARD = ["soft", "medium", "hard"]
from palette import HARD3 as CH_TITLE   # 경도 제목 색 — 뚜렷이 갈리는 셋


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

def res_axis(ax, yt, fs=6.2):
    """해상도 눈금을 **측정한 12 단만** 가로x세로로 적고, 눈금마다 보조선을 켠다.

    로그 포매터가 찍는 10 / 100 / 1000 은 어느 해상도를 쟀는지 보여주지 못한다.
    """
    ax.set_xticks(XT); ax.set_xticklabels(XTL, fontsize=fs, rotation=90)
    ax.xaxis.set_minor_locator(mticker.NullLocator())
    ax.set_yticks(yt); ax.set_yticklabels([f"{v:g}" for v in yt], fontsize=fs + .8)
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax.grid(True, which="major", axis="both", alpha=.35, lw=.5, color="#b0b0b0")
    ax.grid(True, which="minor", axis="y", alpha=.15, lw=.4)
    ax.set_axisbelow(True)


def load(pr):
    f = DS / pr / "force_vs_resolution_axes.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    d["hardness"] = d.sensor.str.split("_").str[0]
    d["thickness_mm"] = d.sensor.str.extract(r"_(\d)mm_").astype(int)
    d["rep"] = d.sensor.str[-1].astype(int)
    return RC.mark(d, pr, "sensor")


def panel(pr, d, cols, stem, ylab, yt):
    units = [f"{h}_{t}mm_r{r}" for h in HARD for t in (1, 2, 3) for r in (1, 2)]
    drawn = []          # 그린 숫자를 그대로 csv 로 남긴다 — 그림과 표가 어긋나지 않게
    fig, axes = plt.subplots(3, 6, figsize=(19, 9), sharex=True, sharey=True)
    for ax, u in zip(axes.ravel(), units):
        g = d[d.sensor == u]
        if not len(g):
            why = RC.reason(pr, u) or "자료 없음"
            ax.text(.5, .5, why, ha="center", va="center", fontsize=8,
                    color="#999", transform=ax.transAxes)
            ax.set_title(u, fontsize=8, color="#999")
            continue
        ls, lw = RC.style(pr, u)
        for c, lab, col in cols:
            k = g.groupby("width_px")[c].agg(["median", "min", "max"])
            ax.plot(k.index, k["median"], ls, c=col, lw=lw, ms=4.2,
                    mec="white", mew=.7, label=lab, zorder=3)
            ax.fill_between(k.index, k["min"], k["max"], color=col, alpha=.16, lw=0)
            drawn.append(k.reset_index().assign(
                sensor=u, axis=lab, suspect_hardware=RC.is_suspect(pr, u)))
        ax.set_xscale("log"); ax.set_yscale("log"); res_axis(ax, yt)
        tt, tc = RC.title(pr, u)
        ax.set_title(tt, fontsize=8.5 if tc == "black" else 7.4, color=tc)
        ax.tick_params(labelsize=7)
        ax.spines[["top", "right"]].set_visible(False)
    for ax in axes[-1]:
        ax.set_xlabel("해상도 (가로 × 세로, px)", fontsize=8, labelpad=6)
    for ax in axes[:, 0]:
        ax.set_ylabel(ylab, fontsize=8)
    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper right", frameon=False, fontsize=9.5, ncol=3)
    fig.suptitle(f"{pr} — {ylab} 대 해상도 (입력 표현 `{REP[pr]}`, seed 3 개의 "
                 f"중앙값과 범위)", fontsize=12, x=.09, ha="left")
    fig.tight_layout(rect=[0, 0, 1, .96])
    p = RES / FOLD[pr] / "figures"
    p.mkdir(parents=True, exist_ok=True)
    fig.savefig(p / f"{stem}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    q = RES / FOLD[pr] / "data"; q.mkdir(parents=True, exist_ok=True)
    (pd.concat(drawn)[["sensor", "axis", "width_px", "median", "min", "max",
                       "suspect_hardware"]]
     if drawn else pd.DataFrame()).to_csv(q / f"{stem}.csv", index=False)
    n = sum(1 for u in units if RC.is_suspect(pr, u))
    if n:
        print(f"    {stem}: {RC.LABEL} {n} 유닛을 포함해 그렸다 (점선 + {RC.MARK})")


def summary(pr, d):
    """원리 하나의 축별 중앙값 — 무릎이 어디인지 한눈에."""
    fig, ax = plt.subplots(figsize=(5.6, 3.8))
    rows = []
    for c, lab, col in AX:
        k = d.groupby("width_px")[c].median()
        ax.plot(k.index, k.values, "-o", c=col, lw=1.8, ms=5, mec="white",
                mew=.7, label=lab)
        b = k.idxmin()
        ax.plot(b, k[b], "*", c=col, ms=14, mec="white", mew=.8, zorder=5)
        rows.append(pd.DataFrame(dict(axis=lab, width_px=k.index, mae=k.values)))
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xticks(XT); ax.set_xticklabels(XTL, fontsize=7, rotation=90)
    ax.xaxis.set_minor_locator(mticker.NullLocator())
    ax.set_yticks(YT); ax.set_yticklabels([f"{v:g}" for v in YT], fontsize=8)
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax.set_xlabel("해상도 (가로 × 세로, px)", labelpad=6); ax.set_ylabel("MAE (N)")
    ax.set_title(f"{pr} — 축별 힘 오차 대 해상도 (★ = 최소)", fontsize=10.5, loc="left")
    ax.legend(frameon=False, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, which="major", axis="both", alpha=.35, lw=.55, color="#b0b0b0")
    ax.set_axisbelow(True)
    p = RES / FOLD[pr]
    (p / "figures").mkdir(parents=True, exist_ok=True)
    (p / "data").mkdir(parents=True, exist_ok=True)
    fig.savefig(p / "figures" / "force_mae_summary.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    pd.concat(rows).to_csv(p / "data" / "force_mae_summary.csv", index=False)


def main():
    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    # NanumGothic 에 유니코드 마이너스(U+2212) 글리프가 없어 축 라벨이
    # "6 x 10<깨짐>2" 로 나온다. ASCII 하이픈을 쓰게 한다.
    plt.rcParams["axes.unicode_minus"] = False
    # 로그 축 라벨은 mathtext 로 그려지고 그것도 NanumGothic 을 따라가
    # "10<깨짐>1" 이 된다. mathtext 에는 완전한 폰트를 따로 준다.
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
        d = load(pr)
        if d is None or not len(d):
            print(f"  {pr}: 아직 자료 없음"); continue
        p = RES / FOLD[pr] / "data"
        p.mkdir(parents=True, exist_ok=True)
        d.to_csv(p / "force_mae_vs_resolution.csv", index=False)
        panel(pr, d, AX, "force_mae_vs_resolution_18units", "힘 MAE (N)", YT_F)
        panel(pr, d, TQ, "torque_mae_vs_resolution_18units", "토크 MAE (N·m)", YT_T)
        summary(pr, d)
        doc_panel(pr, d)
        k = d.groupby("width_px")[[c for c, _, _ in AX]].median()
        print(f"  {pr:<13} {len(d)} 행, {d.sensor.nunique()} 유닛  "
              f"최소: Fx {k.fx_mae.idxmin()}px  Fy {k.fy_mae.idxmin()}px  "
              f"Fz {k.fz_mae.idxmin()}px")



# --------------------------------------------- docs/figures 용 패널 --
SIZES_WH = [(1920, 1080), (1280, 720), (854, 480), (640, 360), (426, 240),
            (320, 180), (160, 90), (80, 45), (48, 27), (32, 18), (16, 9), (8, 5)]
XT = [w for w, _ in SIZES_WH]
XTL = [f"{w}\u00d7{h}" for w, h in SIZES_WH]
YT = [0.01, 0.02, 0.05, 0.1, 0.2]
# 유닛별 격자는 중앙값이 아니라 개별 유닛이라 폭이 넓다 (힘 0.013 ~ 0.356 N,
# 토크 0.0001 ~ 0.0044 N·m). 두 자릿수 떨어져 있어 눈금을 따로 준다.
YT_F = [0.01, 0.02, 0.05, 0.1, 0.2, 0.4]
YT_T = [0.0001, 0.0002, 0.0005, 0.001, 0.002, 0.004]


def doc_panel(pr, d):
    """`force_estimation.md` §2.4 와 같은 배치 — 열 = 경도, 행 = 두께 × 복제.

    축은 모두 공유(로그)하고 선은 Fx·Fy·Fz 셋. seed 3 개의 중앙값과 범위를 그린다.
    """
    rows = [(t, r) for t in (1, 2, 3) for r in (1, 2)]
    fig, axes = plt.subplots(len(rows), 3, figsize=(11.5, 13.5),
                             sharex=True, sharey=True)
    for i, (t, rep) in enumerate(rows):
        for j, h in enumerate(HARD):
            ax = axes[i, j]
            u = f"{h}_{t}mm_r{rep}"
            g = d[d.sensor == u]
            if not len(g):
                ax.text(.5, .5, "—", ha="center", va="center", fontsize=13,
                        color="#bbb", transform=ax.transAxes)
            else:
                for c, lab, col in AX:
                    k = g.groupby("width_px")[c].agg(["median", "min", "max"])
                    ax.plot(k.index, k["median"], "-o", c=col, lw=1.4, ms=3.4,
                            mec="white", mew=.6, label=lab, zorder=3)
                    ax.fill_between(k.index, k["min"], k["max"], color=col,
                                    alpha=.15, lw=0, zorder=2)
            ax.set_xscale("log"); ax.set_yscale("log")
            # 해상도는 측정한 12 단만 눈금으로 찍고 가로x세로로 적는다.
            ax.set_xticks(XT); ax.set_xticklabels(XTL, fontsize=6.2, rotation=90)
            ax.xaxis.set_minor_locator(mticker.NullLocator())
            ax.set_yticks(YT); ax.set_yticklabels([f"{v:g}" for v in YT], fontsize=7)
            ax.yaxis.set_minor_formatter(mticker.NullFormatter())
            ax.tick_params(labelsize=7)
            ax.spines[["top", "right"]].set_visible(False)
            # 보조선: 눈금마다 가로·세로 모두
            ax.grid(True, which="major", axis="both", alpha=.35, lw=.5,
                    color="#b0b0b0")
            ax.grid(True, which="minor", axis="y", alpha=.15, lw=.4)
            ax.set_axisbelow(True)
            if i == 0:
                ax.set_title(h, fontsize=11, color=CH_TITLE[h])
            if j == 0:
                ax.set_ylabel(f"{t} mm · r{rep}\nMAE (N)", fontsize=8.5)
            if i == len(rows) - 1:
                ax.set_xlabel("해상도 (가로 × 세로, px)", fontsize=8.5, labelpad=6)
            else:
                ax.set_xticklabels([])
    h_, l_ = axes[0, 0].get_legend_handles_labels()
    fig.legend(h_, l_, loc="upper right", frameon=False, fontsize=10, ncol=3,
               bbox_to_anchor=(.99, .985))
    fig.suptitle(f"{pr} — 축별 힘 추정 오차 대 해상도 (입력 `{REP[pr]}`)",
                 fontsize=12.5, x=.06, ha="left", y=.985)
    fig.tight_layout(rect=[0, 0, 1, .965])
    p = ROOT / "docs" / "figures"
    p.mkdir(parents=True, exist_ok=True)
    fig.savefig(p / f"force_axes_{pr}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    print(f"    -> docs/figures/force_axes_{pr}.png")


if __name__ == "__main__":
    main()
