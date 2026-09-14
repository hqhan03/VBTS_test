#!/usr/bin/env python3
"""공간 분해능을 그림으로 — 3x3 표와 같은 숫자를 눈으로 볼 수 있게.

표는 칸마다 두 값을 적을 수 있어 정확하지만, **어느 쪽으로 기우는지**가 보이지
않는다. 같은 숫자를 두 장으로 그린다:

1. **분해된 가장 좁은 간격** 대 두께 — 선은 복제 평균, 점은 유닛 하나하나.
2. **분해된 깊이 범위** — 유닛마다 lo~hi 를 막대 하나로.

`result/extra/data/resolution_verdicts.csv` 와 원리별 `table_spatial_resolution.csv`
를 읽고, 그린 숫자를 그대로 csv 로 남긴다.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import pixel_density as PD
import result_common as RC

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "result" / "single" if RC.SINGLE else ROOT / "result"
FOLD = {"9DTact": "1_9DTact", "DIGIT": "2_DIGIT", "DIGIT_Marker": "3_DIGIT_Marker"}
HARD = ["soft", "medium", "hard"]
from palette import HARD3 as CH        # 뚜렷이 갈리는 셋 — palette.py
C = {"9DTact": "#1f6f8b", "DIGIT": "#c2553a"}


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(True, which="major", alpha=.3, lw=.55, color="#b0b0b0")
    ax.set_axisbelow(True)


def load(pr):
    f = RES / FOLD[pr] / "data" / "table_spatial_resolution.csv"
    g = RES / FOLD[pr] / "data" / "table_resolved_depth_range.csv"
    if not f.exists():
        return None
    d = pd.read_csv(f)
    if g.exists():
        gg = pd.read_csv(g)[["unit", "depth_lo_mm", "depth_hi_mm"]]
        d = d.drop(columns=[c for c in ("depth_lo_mm", "depth_hi_mm") if c in d])
        d = d.merge(gg, on="unit", how="left")
    d["suspect_hardware"] = d.unit.map(lambda u: RC.is_suspect(pr, u))
    return RC.keep(d, pr, "unit")


def main():
    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    prs = [p for p in ("9DTact", "DIGIT") if load(p) is not None]
    if not prs:
        print("  공간 분해능 자료 없음"); return

    fig, axes = plt.subplots(2, len(prs), figsize=(5.4 * len(prs), 7.2),
                             squeeze=False)
    rng = np.random.default_rng(0)
    out = []
    for j, pr in enumerate(prs):
        d = load(pr)
        out.append(d.assign(principle=pr))

        # ---- 위: 분해된 가장 좁은 간격 대 두께 ----
        ax = axes[0, j]
        for h in HARD:
            g = d[d.hardness == h]
            if not len(g):
                continue
            k = g.groupby("thickness_mm").finest_centre_mm.agg(["mean", "min", "max"])
            ax.plot(k.index, k["mean"], "-", c=CH[h], lw=1.8, label=h, zorder=3)
            ax.vlines(k.index, k["min"], k["max"], color=CH[h], lw=1.0,
                      alpha=.55, zorder=2)
            jit = (rng.random(len(g)) - .5) * .14
            ok = ~g.suspect_hardware.values
            ax.scatter(g.thickness_mm.values[ok] + jit[ok],
                       g.finest_centre_mm.values[ok], s=26, c=CH[h],
                       edgecolor="white", lw=.6, zorder=4)
            if (~ok).any():
                ax.scatter(g.thickness_mm.values[~ok] + jit[~ok],
                           g.finest_centre_mm.values[~ok], s=48, c=CH[h],
                           edgecolor=RC.INK, lw=1.6, zorder=5)
        ax.set_xticks([1, 2, 3]); ax.set_xlim(.7, 3.3)
        ax.set_xlabel("겔 두께 (mm)")
        ax.set_title(f"{pr} — 분해된 가장 좁은 간격", fontsize=10.5, loc="left",
                     color=C.get(pr, "black"))
        # y 축은 두 원리가 공유한다. DIGIT 은 아홉 칸이 전부 1.10 이라 자기 범위로
        # 그리면 축이 1.04~1.16 으로 확대돼 **평평하다는 사실 자체가 안 보인다.**
        ax.set_ylim(1.0, 2.65)
        if d.finest_centre_mm.nunique() == 1:
            v = float(d.finest_centre_mm.iloc[0])
            ax.annotate(f"18 / 18 유닛이 가장 좁은 프로브({v:.2f} mm)를 분해했다\n"
                        "— 값이 아니라 **상한**이다",
                        (2, v), fontsize=8.5, ha="center", va="bottom",
                        xytext=(0, 14), textcoords="offset points", color="#666")
        style(ax)
        if j == 0:
            ax.set_ylabel("중심 간격 (mm) — 낮을수록 좋다")
            ax.legend(frameon=False, fontsize=8.5, title="경도", title_fontsize=8.5)

        # ---- 아래: 분해된 깊이 범위, 유닛마다 막대 하나 ----
        ax = axes[1, j]
        e = d.dropna(subset=["depth_lo_mm", "depth_hi_mm"]).copy()
        e["key"] = e.hardness.map({h: i for i, h in enumerate(HARD)}) * 100 \
            + e.thickness_mm * 10 + e.rep
        e = e.sort_values("key")
        y = np.arange(len(e))
        for yy, (_, x) in zip(y, e.iterrows()):
            if x.depth_hi_mm <= x.depth_lo_mm:
                # 한 깊이에서만 분해됐다 — 막대로는 폭이 0 이라 보이지 않는다
                ax.plot([x.depth_lo_mm], [yy], "o", ms=7, color=CH[x.hardness],
                        mec="white", mew=.8, zorder=4)
                continue
            ax.plot([x.depth_lo_mm, x.depth_hi_mm], [yy, yy],
                    lw=5, solid_capstyle="butt", color=CH[x.hardness],
                    alpha=.95, zorder=3)
            if x.suspect_hardware:
                ax.plot([x.depth_lo_mm, x.depth_hi_mm], [yy, yy], lw=7.0,
                        solid_capstyle="butt", color=RC.INK, alpha=.9, zorder=2)
        ax.set_yticks(y)
        ax.set_yticklabels([f"{'! ' if s else ''}{u}"
                            for u, s in zip(e.unit, e.suspect_hardware)], fontsize=7)
        for t, s in zip(ax.get_yticklabels(), e.suspect_hardware):
            if s:
                t.set_color(RC.INK)
        ax.invert_yaxis()
        ax.set_xlabel("깊이 (mm)")
        ax.set_title(f"{pr} — 분해된 깊이 범위", fontsize=10.5, loc="left",
                     color=C.get(pr, "black"))
        style(ax); ax.grid(axis="y", alpha=0)

    fig.suptitle("공간 분해능 — 3×3 표와 같은 숫자 (점은 유닛 하나하나, "
                 f"{RC.MARK} = {RC.LABEL})", fontsize=11.5, x=.04, ha="left")
    fig.tight_layout(rect=[0, 0, 1, .96])
    d = RES / "extra"
    (d / "figures").mkdir(parents=True, exist_ok=True)
    (d / "data").mkdir(parents=True, exist_ok=True)
    fig.savefig(d / "figures" / "G_spatial_resolution.png", dpi=200,
                bbox_inches="tight")
    plt.close(fig)
    D = pd.concat(out)[["principle", "unit", "hardness", "thickness_mm", "rep",
                        "finest_centre_mm", "finest_edge_mm", "depth_lo_mm",
                        "depth_hi_mm", "best_dip", "n_gaps_resolved",
                        "n_gaps_tested", "suspect_hardware"]]
    D.to_csv(d / "data" / "G_spatial_resolution.csv", index=False)
    print(f"  -> extra/figures/G_spatial_resolution.png  +  "
          f"extra/data/G_spatial_resolution.csv  ({len(D)} 행)")


def sweep_figure():
    """공간 분해능의 입력 해상도 스윕 — 힘·형상과 같은 x 축.

    세 칸: 분해 비율, dip 과 Rayleigh 문턱, 자국 밝기와 판정 바닥. 판정이 어디서
    무너지는지와 **왜** 무너지는지를 함께 보여야 한다 — 골이 얕아져서인지, 자국이
    옅어져서인지, 검출기가 접촉을 놓쳐서인지가 다른 이야기다.
    """
    f = RES / "extra" / "data" / "resolution_sweep_pair100.csv"
    if not f.exists():
        return
    import analyse_resolution as AR
    d = pd.read_csv(f)
    # 유닛마다 시야가 다르므로 x 를 화소 밀도로 옮긴다. 이 스윕은 9DTact 뿐이다.
    d["R"] = [PD.density("9DTact", u, w) for u, w in zip(d.unit, d.width_px)]
    xr = d.groupby("width_px").R.median()
    W = sorted(d.width_px.unique())
    fig, axes = plt.subplots(1, 3, figsize=(7.16, 2.5))

    ax = axes[0]
    frac = d.assign(r=d.verdict.eq("분해")).groupby("width_px").r.mean() * 100
    lost = d.assign(r=d.verdict.eq("접촉 없음")).groupby("width_px").r.mean() * 100
    ax.plot(xr.reindex(frac.index).values, frac.values, "-o", c="#0072B2", lw=1.8, ms=4,
            label="resolved")
    ax.plot(xr.reindex(lost.index).values, lost.values, "--s", c="#1a1a1a", lw=1.2, ms=3,
            alpha=.6, label="contact lost")
    ax.set_ylabel("share of ladder steps [%]", fontsize=8)
    ax.legend(frameon=False, fontsize=6.8)

    ax = axes[1]
    m = d.groupby("width_px").dip.median()
    ax.plot(xr.reindex(m.index).values, m.values, "-o", c="#D55E00", lw=1.8, ms=4)
    ax.axhline(AR.RAYLEIGH, c="#1a1a1a", ls=":", lw=1.1)
    ax.text(.97, .06, f"Rayleigh {AR.RAYLEIGH}", transform=ax.transAxes,
            fontsize=6.2, ha="right")
    ax.set_ylabel("median dip", fontsize=8)

    ax = axes[2]
    m = d.groupby("width_px").imprint_lvl.median()
    ax.plot(xr.reindex(m.index).values, m.values, "-o", c="#009E73", lw=1.8, ms=4)
    ax.axhline(AR.MIN_PEAK, c="#1a1a1a", ls=":", lw=1.1)
    ax.text(.97, .06, f"floor {AR.MIN_PEAK}", transform=ax.transAxes,
            fontsize=6.2, ha="right")
    ax.set_ylabel("median imprint [levels]", fontsize=8)

    for ax in axes:
        ax.set_xscale("log")
        ax.set_xticks([0.1, 1, 10, 100, 1000, 10000])
        ax.set_xticklabels(["0.1", "1", "10", "100", "1000", "10⁴"], fontsize=6.8)
        ax.minorticks_off()
        ax.set_xlabel("Pixel density $R$ [px/mm$^2$]", fontsize=8)
        ax.tick_params(labelsize=7); style(ax)
    fig.suptitle("Two-point judgement against input resolution "
                 "(9DTact, pair100, centre gap 2.0 mm)", fontsize=9, x=.02,
                 ha="left")
    fig.tight_layout(rect=[0, 0, 1, .92])
    p = RES / "extra"
    fig.savefig(p / "figures" / "H_resolution_sweep.png", dpi=200,
                bbox_inches="tight")
    plt.close(fig)
    # 그림이 그린 숫자를 그대로 — 원자료는 resolution_sweep_pair100.csv 다
    pd.DataFrame(dict(
        width_px=frac.index, density_px_per_mm2=xr.reindex(frac.index).values,
        resolved_pct=frac.values,
        contact_lost_pct=lost.reindex(frac.index).values,
        median_dip=d.groupby("width_px").dip.median().reindex(frac.index).values,
        median_imprint_lvl=d.groupby("width_px").imprint_lvl.median()
                            .reindex(frac.index).values,
        median_dip_sd=d.groupby("width_px").dip_sd.median()
                       .reindex(frac.index).values,
        rayleigh=AR.RAYLEIGH, imprint_floor=AR.MIN_PEAK,
    )).to_csv(p / "data" / "H_resolution_sweep.csv", index=False)
    print("    -> extra/figures/H_resolution_sweep.png")


if __name__ == "__main__":
    main()
    sweep_figure()
