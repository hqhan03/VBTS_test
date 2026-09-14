#!/usr/bin/env python3
"""겔 설계(두께·경도)가 성능을 얼마나 바꾸나 — MAE 와 R² 를 나란히.

**왜 R² 도 보는가** (2026-09-14, 운전자 요청). MAE 는 "얼마나 틀리나" 이고
R² 는 "그 유닛이 실제로 신호를 따라가나" 다. 둘이 갈릴 수 있다 — 범위가 좁은
유닛은 MAE 가 작아도 R² 가 낮고, 배율만 틀린 유닛은 R² 가 높아도 MAE 가 크다.
형상 쪽에서 이미 본 것이다(상관 0.99 인데 깊이가 참값의 0.61 배).

**해상도를 먼저 없앤다.** 각 유닛에 대해 평탄 구간(가로 80 px 이상, R ≳ 13)의
중앙값을 취해 유닛 하나당 수 하나로 만든 뒤, 그것을 두께·경도로 가른다.
그러지 않으면 해상도 축과 겔 축이 섞인다.

**검정.** 유닛을 단위로 Spearman ρ. 두께·경도는 세 수준뿐이고 원리당 유닛이
아홉이므로 검정력이 낮다 — **q 를 붙이지 않고 ρ 와 p 를 그대로 싣는다.**
5 절의 포화 해상도 검정(20 개 BH 보정)과 **다른 집합**이고, 그 보정에 합치지
않았다는 것을 문서에 적는다.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

import result_common as RC
from palette import HARD3, THICK3

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
AN = ROOT / "data" / "analysis" / "digit_shape"
RES = ROOT / "result" / "single" if RC.SINGLE else ROOT / "result"
FLAT_MIN_W = 80          # 평탄 구간의 시작 — 5 절의 포화 해상도보다 넉넉히 위
PRS = ["9DTact", "DIGIT", "DIGIT_Marker"]


def force_rows():
    out = []
    for pr in PRS:
        f = DS / pr / "force_vs_resolution_axes.csv"
        if not f.exists():
            continue
        d = RC.keep(pd.read_csv(f), pr, "sensor")
        if RC.SINGLE:
            d = d[d.sensor.isin(RC.chosen(pr))]
        d = d[d.width_px >= FLAT_MIN_W].copy()
        d["shear_mae"] = (d.fx_mae + d.fy_mae) / 2
        g = d.groupby("sensor")[["fz_mae", "shear_mae", "fz_r2", "lat_r2"]].median()
        for u, r in g.iterrows():
            out.append(dict(principle=pr, unit=u, task="힘",
                            mae_fz=r.fz_mae, mae_shear=r.shear_mae,
                            r2_fz=r.fz_r2, r2_lat=r.lat_r2))
    return pd.DataFrame(out)


def shape_rows():
    out = []
    f = DS / "9DTact" / "shape_vs_resolution.csv"
    if f.exists():
        d = pd.read_csv(f)
        d = d[d.width_px.notna()].copy()
        d["width_px"] = d.width_px.astype(int)
        d = RC.keep(d, "9DTact", "sensor")
        if RC.SINGLE:
            d = d[d.sensor.isin(RC.chosen("9DTact"))]
        d = d[d.width_px >= FLAT_MIN_W]
        cols = ["cyl4_raw_mae", "cube4_raw_mae", "cyl4_raw_r2", "cube4_raw_r2"]
        g = d.groupby("sensor")[[c for c in cols if c in d]].median()
        for u, r in g.iterrows():
            out.append(dict(principle="9DTact", unit=u, task="형상",
                            mae_cyl4=r.get("cyl4_raw_mae"),
                            mae_cube4=r.get("cube4_raw_mae"),
                            r2_cyl4=r.get("cyl4_raw_r2"),
                            r2_cube4=r.get("cube4_raw_r2")))
    f = AN / "DIGIT_shape_vs_resolution.csv"
    if f.exists():
        d = RC.keep(pd.read_csv(f), "DIGIT", "unit")
        if RC.SINGLE:
            d = d[d.unit.isin(RC.chosen("DIGIT"))]
        d = d[d.width_px >= FLAT_MIN_W]
        rec = {}
        for (u, sh), g in d.groupby(["unit", "shape"]):
            e = (g.depth_pred_mm - g.depth_true_mm).abs().mean()
            ss = ((g.depth_pred_mm - g.depth_true_mm) ** 2).sum()
            st = ((g.depth_true_mm - g.depth_true_mm.mean()) ** 2).sum()
            rec.setdefault(u, {})[f"mae_{sh}"] = float(e)
            rec.setdefault(u, {})[f"r2_{sh}"] = float(1 - ss / st) if st > 0 else np.nan
        for u, r in rec.items():
            out.append(dict(principle="DIGIT", unit=u, task="형상", **r))
    return pd.DataFrame(out)


def tidy(d):
    d = d.copy()
    d["thickness_mm"] = d.unit.str.extract(r"_(\d)mm_")[0].astype(int)
    d["hardness"] = d.unit.str.extract(r"^(soft|medium|hard)_")[0]
    d["hard_n"] = d.hardness.map({"soft": 1, "medium": 2, "hard": 3})
    return d


def tests(d, metrics):
    rows = []
    for pr, g in d.groupby("principle"):
        for m in metrics:
            if m not in g or g[m].notna().sum() < 4:
                continue
            v = g.dropna(subset=[m])
            for fac, col in (("두께", "thickness_mm"), ("경도", "hard_n")):
                rho, p = stats.spearmanr(v[col], v[m])
                rows.append(dict(principle=pr, metric=m, factor=fac,
                                 n=len(v), rho=round(float(rho), 3),
                                 p=round(float(p), 4),
                                 med_1=round(float(v[v[col] == 1][m].median()), 4),
                                 med_2=round(float(v[v[col] == 2][m].median()), 4),
                                 med_3=round(float(v[v[col] == 3][m].median()), 4)))
    return pd.DataFrame(rows)


def panel(ax, g, col, fac, ylab, title):
    """x 는 한 인자, **선은 다른 인자**다 (2026-09-14, 운전자 지시).

    중앙값 선 하나는 "평균이 어디로 가나" 만 보여 주고 같은 겔이 어떻게
    움직이는지는 감춘다. 아홉 유닛이 3 x 3 이므로 칸마다 하나씩이고, 다른
    인자를 고정하면 **정확히 세 점짜리 선 셋**이 나온다 — 예컨대 x 가 두께면
    soft·medium·hard 각각의 두께 곡선이다. 선이 서로 나란하면 두 인자가
    더해지는 것이고, 엇갈리면 상호작용이다.
    """
    x = "thickness_mm" if fac == "두께" else "hard_n"
    other, cmap, lab = (("hard_n", HARD3, {1: "soft", 2: "medium", 3: "hard"})
                        if fac == "두께" else
                        ("thickness_mm", THICK3, {1: "1 mm", 2: "2 mm", 3: "3 mm"}))
    key = {1: "soft", 2: "medium", 3: "hard"} if fac == "두께" else {1: 1, 2: 2, 3: 3}
    for k in (1, 2, 3):
        sub = g[g[other] == k].sort_values(x)
        if not len(sub):
            continue
        c = cmap[key[k]]
        ax.plot(sub[x], sub[col], "-o", c=c, lw=1.6, ms=5, mec="white",
                mew=.7, label=lab[k], zorder=3)
    ax.set_xticks([1, 2, 3])
    ax.set_xticklabels(["1 mm", "2 mm", "3 mm"] if fac == "두께"
                       else ["soft", "medium", "hard"], fontsize=7.5)
    ax.set_ylabel(ylab, fontsize=8)
    ax.set_title(title, fontsize=8.5, loc="left")
    ax.tick_params(labelsize=7)
    ax.grid(alpha=.3, lw=.4, axis="y"); ax.set_axisbelow(True)
    ax.spines[["top", "right"]].set_visible(False)


def figure(d, spec, stem, suptitle):
    """행 = 원리, 열 = (MAE 두께, MAE 경도, R² 두께, R² 경도)."""
    prs = [p for p in PRS if p in set(d.principle)]
    leg = {}
    fig, axes = plt.subplots(len(prs), 4, figsize=(9.6, 2.5 * len(prs)),
                             squeeze=False)
    for i, pr in enumerate(prs):
        g = d[d.principle == pr]
        mcol, rcol, mlab, rlab = spec[pr]
        for j, (col, fac, ylab) in enumerate(
                [(mcol, "두께", mlab), (mcol, "경도", mlab),
                 (rcol, "두께", rlab), (rcol, "경도", rlab)]):
            t = f"{pr} — {ylab} 대 {fac}"
            panel(axes[i][j], g.dropna(subset=[col]), col, fac, ylab, t)
            if i == 0:
                h, l = axes[i][j].get_legend_handles_labels()
                leg.setdefault("경도" if fac == "두께" else "두께",
                               (h, l))
    for k, (x, (h, l)) in enumerate(zip((.27, .76), leg.items())):
        t, (hh, ll) = l if False else (x, leg[list(leg)[k]])
        fig.legend(hh, ll, frameon=False, fontsize=8, ncol=3,
                   title=list(leg)[k], title_fontsize=8,
                   loc="lower center", bbox_to_anchor=(t, -.02))
    fig.suptitle(suptitle, fontsize=10.5, x=.01, ha="left")
    fig.tight_layout(rect=[0, .06, 1, .96])
    p = RES / "extra"
    (p / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(p / "figures" / f"{stem}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"    -> extra/figures/{stem}.png")


def main():
    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    p = RES / "extra" / "data"; p.mkdir(parents=True, exist_ok=True)

    F = tidy(force_rows())
    S = tidy(shape_rows())
    F.to_csv(p / "J_gel_effect_force.csv", index=False)
    S.to_csv(p / "J_gel_effect_shape.csv", index=False)

    tf = tests(F, ["mae_fz", "mae_shear", "r2_fz", "r2_lat"])
    ts = tests(S, ["mae_cyl4", "mae_cube4", "r2_cyl4", "r2_cube4"])
    tf.assign(task="힘").to_csv(p / "J_gel_effect_force_tests.csv", index=False)
    ts.assign(task="형상").to_csv(p / "J_gel_effect_shape_tests.csv", index=False)

    figure(F, {pr: ("mae_fz", "r2_fz", "Fz MAE (N)", "Fz R²") for pr in PRS},
           "J_gel_effect_force", "힘 추정 — 겔 설계에 따른 Fz MAE 와 R² "
           "(평탄 구간 중앙, 유닛 하나가 점 하나)")
    figure(S, {"9DTact": ("mae_cyl4", "r2_cyl4", "cyl4 MAE (mm)", "cyl4 R²"),
               "DIGIT": ("mae_cyl4", "r2_cyl4", "cyl4 MAE (mm)", "cyl4 R²")},
           "J_gel_effect_shape", "형상 복원 — 겔 설계에 따른 원기둥 MAE 와 R² "
           "(평탄 구간 중앙, 유닛 하나가 점 하나)")
    print(tf.to_string(index=False)); print(); print(ts.to_string(index=False))


if __name__ == "__main__":
    main()
