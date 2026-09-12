#!/usr/bin/env python3
"""형상 복원 정확도 대 해상도 — 유닛 18 개 격자 + 요약.

9DTact 는 밝기->깊이 조회표를 ball4 로 보정하고 **held-out 형상** cyl4 / cube4 로
평가한다. ball4 는 보정 프로브이므로 점수에 쓰지 않는다.

`raw` 는 조회표 그대로, `corrected` 는 해상도에 따른 회색조 손실을 보정한 것이다.
"""
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
PROBE = [("cyl4", "원기둥 ⌀4 mm", "#c2553a"), ("cube4", "정육면체 4 mm", "#1f6f8b")]


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

def load9():
    f = DS / "9DTact" / "shape_vs_resolution.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    d = d[d.width_px.notna()].copy()
    d["width_px"] = d.width_px.astype(int)
    return d


def panel(d, col_tmpl, stem, ylab, title):
    units = [f"{h}_{t}mm_r{r}" for h in HARD for t in (1, 2, 3) for r in (1, 2)]
    fig, axes = plt.subplots(3, 6, figsize=(19, 9), sharex=True, sharey=True)
    for ax, u in zip(axes.ravel(), units):
        g = d[d.sensor == u]
        if not len(g):
            ax.text(.5, .5, "자료 없음", ha="center", va="center", fontsize=8,
                    color="#999", transform=ax.transAxes)
            ax.set_title(u, fontsize=8, color="#999"); continue
        for probe, lab, c in PROBE:
            col = col_tmpl.format(probe)
            if col not in g:
                continue
            k = g.groupby("width_px")[col].median().dropna()
            if not len(k):
                continue
            ax.plot(k.index, k.values, "-o", c=c, lw=1.5, ms=3.2, mec="white",
                    mew=.5, label=lab)
        ax.set_xscale("log"); ax.set_yscale("log"); plain_log(ax, "both")
        ax.set_title(u, fontsize=8.5); ax.tick_params(labelsize=7)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=.22, lw=.5, which="both"); ax.set_axisbelow(True)
    for ax in axes[-1]:
        ax.set_xlabel("가로 해상도 (px)", fontsize=8)
    for ax in axes[:, 0]:
        ax.set_ylabel(ylab, fontsize=8)
    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper right", frameon=False, fontsize=9.5, ncol=2)
    fig.suptitle(title, fontsize=12, x=.09, ha="left")
    fig.tight_layout(rect=[0, 0, 1, .96])
    p = RES / FOLD["9DTact"] / "figures"
    p.mkdir(parents=True, exist_ok=True)
    fig.savefig(p / f"{stem}.png", dpi=150, bbox_inches="tight")
    plt.close(fig)


def summary(d):
    fig, ax = plt.subplots(figsize=(5.8, 3.8))
    rows = []
    for probe, lab, c in PROBE:
        for kind, ls, al in (("raw", "-", 1.0), ("corrected", "--", .75)):
            col = f"{probe}_{kind}_mae"
            if col not in d:
                continue
            k = d.groupby("width_px")[col].median().dropna()
            ax.plot(k.index, k.values, ls, c=c, lw=1.9, alpha=al,
                    label=f"{lab} · {kind}")
            b = k.idxmin()
            ax.plot(b, k[b], "*", c=c, ms=13, mec="white", mew=.7, zorder=5)
            rows.append(pd.DataFrame(dict(probe=probe, kind=kind,
                                          width_px=k.index, mae_mm=k.values)))
    ax.set_xscale("log"); ax.set_yscale("log"); plain_log(ax, "both")
    ax.set_xlabel("가로 해상도 (px)"); ax.set_ylabel("깊이 MAE (mm)")
    ax.set_title("9DTact — 형상 복원 오차 대 해상도 (★ = 최소)",
                 fontsize=10.5, loc="left")
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=.25, lw=.6, which="both"); ax.set_axisbelow(True)
    p = RES / FOLD["9DTact"]
    fig.savefig(p / "figures" / "shape_mae_summary.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    pd.concat(rows).to_csv(p / "data" / "shape_mae_summary.csv", index=False)


# ------------------------------------------------------------- DIGIT --
def load_digit():
    """digit_shape.py 가 낸 held-out 평가. 긴 형식 -> 9DTact 와 같은 넓은 형식."""
    f = ROOT / "data" / "analysis" / "digit_shape" / "DIGIT_shape_vs_resolution.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    d["err_mm"] = (d.depth_pred_mm - d.depth_true_mm).abs()
    w = (d.groupby(["unit", "width_px", "shape"]).err_mm.mean()
         .unstack("shape").reset_index())
    w = w.rename(columns={c: f"{c}_raw_mae" for c in ("cyl4", "cube4")})
    return w.rename(columns={"unit": "sensor"})


def digit_summary(d, raw):
    """요약 + 예측-참값 산점도. 상관이 이 파이프라인의 핵심 증거다."""
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.8))
    ax = axes[0]
    rows = []
    for probe, lab, c in PROBE:
        col = f"{probe}_raw_mae"
        if col not in d:
            continue
        k = d.groupby("width_px")[col].median().dropna()
        ax.plot(k.index, k.values, "-o", c=c, lw=1.9, ms=5, mec="white",
                mew=.7, label=lab)
        b = k.idxmin()
        ax.plot(b, k[b], "*", c=c, ms=13, mec="white", mew=.7, zorder=5)
        rows.append(pd.DataFrame(dict(probe=probe, width_px=k.index,
                                      mae_mm=k.values)))
    ax.set_xscale("log"); ax.set_yscale("log"); plain_log(ax, "both")
    ax.set_xlabel("가로 해상도 (px)"); ax.set_ylabel("깊이 MAE (mm)")
    ax.set_title("DIGIT — 형상 복원 오차 대 해상도 (★ = 최소)",
                 fontsize=10, loc="left")
    ax.legend(frameon=False, fontsize=8.5)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=.25, lw=.6, which="both"); ax.set_axisbelow(True)

    ax = axes[1]
    g = raw[raw.width_px == 426]
    for probe, lab, c in PROBE:
        s = g[g["shape"] == probe]
        if not len(s):
            continue
        ax.scatter(s.depth_true_mm, s.depth_pred_mm, s=26, c=c, alpha=.65,
                   edgecolor="white", lw=.5,
                   label=f"{lab}  r={np.corrcoef(s.depth_true_mm, s.depth_pred_mm)[0,1]:+.3f}")
    lim = [0, max(g.depth_true_mm.max(), g.depth_pred_mm.max()) * 1.05]
    ax.plot(lim, lim, ":", c="#888", lw=1.2, zorder=1)
    ax.set_xlim(lim); ax.set_ylim(lim)
    ax.set_xlabel("참 깊이 (mm)"); ax.set_ylabel("복원 깊이 (mm)")
    ax.set_title("426 px 에서의 전이 (점선 = 이상)", fontsize=10, loc="left")
    ax.legend(frameon=False, fontsize=8)
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=.25, lw=.6); ax.set_axisbelow(True)

    fig.tight_layout()
    p = RES / FOLD["DIGIT"]
    (p / "figures").mkdir(parents=True, exist_ok=True)
    (p / "data").mkdir(parents=True, exist_ok=True)
    fig.savefig(p / "figures" / "shape_mae_summary.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    pd.concat(rows).to_csv(p / "data" / "shape_mae_summary.csv", index=False)


def main():
    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    # 로그 축 라벨은 mathtext 로 그려지고 그것도 NanumGothic 을 따라가
    # "10<깨짐>1" 이 된다. mathtext 에는 완전한 폰트를 따로 준다.
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    d = load9()
    if d is None:
        print("  9DTact: 자료 없음"); return
    p = RES / FOLD["9DTact"] / "data"
    p.mkdir(parents=True, exist_ok=True)
    d.to_csv(p / "shape_vs_resolution.csv", index=False)
    panel(d, "{}_raw_mae", "shape_mae_vs_resolution_18units", "깊이 MAE (mm)",
          "9DTact — 형상 복원 오차 대 해상도 (조회표 그대로)")
    panel(d, "{}_corrected_mae", "shape_mae_corrected_18units", "깊이 MAE (mm)",
          "9DTact — 형상 복원 오차 대 해상도 (회색조 손실 보정)")
    summary(d)
    k = d.groupby("width_px")[["cyl4_raw_mae", "cube4_raw_mae"]].median()
    print(f"  9DTact  {len(d)} 행, {d.sensor.nunique()} 유닛  "
          f"최소: cyl4 {k.cyl4_raw_mae.idxmin()}px ({k.cyl4_raw_mae.min():.4f} mm)  "
          f"cube4 {k.cube4_raw_mae.idxmin()}px ({k.cube4_raw_mae.min():.4f} mm)")

    dd = load_digit()
    if dd is None or not len(dd):
        print("  DIGIT: 형상 평가 아직 없음"); return
    raw = pd.read_csv(ROOT / "data" / "analysis" / "digit_shape"
                      / "DIGIT_shape_vs_resolution.csv")
    pD = RES / FOLD["DIGIT"] / "data"; pD.mkdir(parents=True, exist_ok=True)
    dd.to_csv(pD / "shape_vs_resolution.csv", index=False)
    raw.to_csv(pD / "shape_predictions.csv", index=False)
    panel_d = panel
    globals()["RES_FOLD_OVERRIDE"] = "DIGIT"
    digit_summary(dd, raw)
    k2 = dd.groupby("width_px")[["cyl4_raw_mae", "cube4_raw_mae"]].median()
    print(f"  DIGIT   {len(dd)} 행, {dd.sensor.nunique()} 유닛  "
          f"최소: cyl4 {k2.cyl4_raw_mae.idxmin()}px ({k2.cyl4_raw_mae.min():.4f} mm)  "
          f"cube4 {k2.cube4_raw_mae.idxmin()}px ({k2.cube4_raw_mae.min():.4f} mm)")


if __name__ == "__main__":
    main()
