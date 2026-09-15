#!/usr/bin/env python3
"""마커 팔의 세 전처리를 나란히 — 지운 것 하나, 남긴 것 둘.

**왜 필요한가** (2026-09-14 운전자 지적, 2026-09-15 학습). 머리 결과의 마커
팔은 `inpaint`, 곧 마커 점을 **지운** 표현이다. 그런데 마커 기반 센서의 표준은
Marker Displacement Method 로 마커를 **추적**해 전단을 읽고, FEATS 는 GelSight
Mini 원본 이미지를 그대로 넣는다. 우리는 그 신호를 지우고 학습한 뒤 그 위에서
H9 을 판정했다.

그래서 마커를 남긴 `colour`·`grey` 로 선택 아홉 유닛을 축분리로 다시 학습했다.
세 전처리는 **같은 프레임, 같은 설정, 같은 학습 판**이고 입력 표현만 다르다.

자료도 함께 내보낸다 — `result/single/3_DIGIT_Marker/data/` 로 옮겨 두면 다른
그림이 바로 읽을 수 있다.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd
from scipy import stats

import pixel_density as PD
import result_common as RC

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset" / "DIGIT_Marker"
RES = ROOT / "result" / "single" if RC.SINGLE else ROOT / "result"
PR = "DIGIT_Marker"
# (파일, 이름, 색) — 색은 운전자가 정한 팔레트
REPS = [("force_vs_resolution_res.csv", "inpaint — 마커 지움", "#D40000"),
        ("force_vs_resolution_colour_axes.csv", "colour — 마커 남김", "#0047B3"),
        ("force_vs_resolution_grey_axes.csv", "grey — 마커 남김", "#007A29")]
MET = [("sh", "전단 (Fx·Fy 평균)"), ("fz_mae", "Fz"), ("res", "합력 ‖ΔF‖")]
XT = [0.1, 1, 10, 100, 1000, 10000]
XTL = ["0.1", "1", "10", "100", "1000", "10⁴"]


def load(fname):
    f = DS / fname
    if not f.exists():
        return None
    d = RC.keep(pd.read_csv(f), PR, "sensor")
    d = d[d.sensor.isin(RC.chosen(PR))].copy()
    if not len(d) or "fx_mae" not in d:
        return None
    d["sh"] = (d.fx_mae + d.fy_mae) / 2
    # 합력: 실측이 있으면 그것, 없으면 옌센 하한. 열 이름을 나눠 둔다.
    if "res_mae" in d:
        d["res"] = d.res_mae
        d["res_kind"] = "실측"
    else:
        d["res"] = np.sqrt(d.fx_mae ** 2 + d.fy_mae ** 2 + d.fz_mae ** 2)
        d["res_kind"] = "하한"
    return PD.add(d, PR)


def main():
    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    got = [(f, lab, c, load(f)) for f, lab, c in REPS]
    got = [g for g in got if g[3] is not None]
    if not got:
        print("  자료 없음"); return
    fig, axes = plt.subplots(1, len(MET), figsize=(11.0, 3.4))
    rows, kinds = [], set()
    for j, (m, mlab) in enumerate(MET):
        ax = axes[j]
        for f, lab, c, d in got:
            k = (d.groupby("width_px")
                   .agg(v=(m, "median"), R=("density_px_per_mm2", "median"))
                   .dropna().sort_values("R"))
            ax.plot(k.R, k.v, "-o", c=c, lw=2.0, ms=4, mec="white", mew=.6,
                    label=lab)
            rows.append(k.assign(rep=lab, metric=m).reset_index())
            if m == "res":
                kinds |= set(d.res_kind.unique())
        ax.set_xscale("log")
        ax.set_xticks(XT); ax.set_xticklabels(XTL, fontsize=7)
        ax.xaxis.set_minor_locator(mticker.NullLocator())
        ax.set_ylim(0, None)
        ax.set_xlabel("화소 밀도 R (px/mm²)", fontsize=8.5)
        ax.set_ylabel(f"{mlab} MAE (N)", fontsize=8.5)
        ax.tick_params(labelsize=7.5)
        ax.grid(alpha=.3, lw=.4); ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
        if j == 0:
            ax.legend(frameon=False, fontsize=7.5, loc="upper right")
    fig.suptitle("DIGIT_Marker — 같은 프레임·같은 설정, 입력 표현만 다르다 "
                 f"(선택 9 유닛, 합력은 {'·'.join(sorted(kinds))})",
                 fontsize=10, x=.01, ha="left")
    fig.tight_layout(rect=[0, 0, 1, .94])
    fd = RES / FOLD_FIG; fd.mkdir(parents=True, exist_ok=True)
    fig.savefig(fd / "marker_reps.png", dpi=200, bbox_inches="tight")
    plt.close(fig)

    dd = RES / FOLD_DATA; dd.mkdir(parents=True, exist_ok=True)
    pd.concat(rows).to_csv(dd / "marker_reps.csv", index=False)
    # 원자료도 결과 폴더로 — 다른 그림이 바로 읽는다
    for f, lab, _, d in got:
        d.to_csv(dd / f.replace("force_vs_resolution_", "reps_"), index=False)

    print(f"    -> {FOLD_FIG}/marker_reps.png")
    print(f"\n  H9 — 1920 px 가 80 px 보다 나은 유닛 (축분리 전단)")
    for f, lab, _, d in got:
        k = d.groupby(["sensor", "width_px"]).sh.median().unstack()
        b = int((k[1920] < k[80]).sum())
        p = stats.wilcoxon(k[1920], k[80]).pvalue
        print(f"    {lab:<22} {b}/{len(k)}  p {p:.4f}  "
              f"비 {(k[1920] / k[80]).median():.2f}")


FOLD_FIG = "3_DIGIT_Marker/figures"
FOLD_DATA = "3_DIGIT_Marker/data"

if __name__ == "__main__":
    main()
