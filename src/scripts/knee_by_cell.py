#!/usr/bin/env python3
"""성능이 포화하는 해상도 — 경도·두께 칸별로.

**포화 해상도의 정의.** 그 유닛 자신의 최솟값의 110 % 안에 드는 **가장 낮은** 해상도.
`argmin` 은 곡선이 평평한 구간에서 흔들리므로 쓰지 않는다 — 같은 유닛을 seed 만
바꿔 돌려도 argmin 이 한두 단 움직이는데, 포화 해상도는 움직이지 않는다.

**칸마다 유닛이 둘뿐이다.** 그래서 칸 값은 두 복제의 중앙값이고, 경향은 칸이 아니라
**유닛 18 개**로 검정한다(Spearman). 칸 표는 눈으로 보라고 있는 것이지 검정의
단위가 아니다.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import pixel_density as PD
import result_common as RC

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
RES = ROOT / "result" / "single" if RC.SINGLE else ROOT / "result"
FOLD = {"9DTact": "1_9DTact", "DIGIT": "2_DIGIT", "DIGIT_Marker": "3_DIGIT_Marker"}
HARD = ["soft", "medium", "hard"]


def knee(v, tol=1.10):
    """최솟값의 110 % 안에 드는 가장 낮은 해상도(픽셀 폭)."""
    v = v.dropna()
    if len(v) < 4:
        return np.nan
    return int(v.index[v <= v.min() * tol].min())


def knee_R(v, pr, unit, tol=1.10):
    """같은 것을 **화소 밀도** R (px/mm²) 로. 유닛마다 시야가 다르므로 같은 픽셀
    폭이 같은 물리 밀도가 아니다 — 원리·유닛을 가로질러 견주려면 이쪽이다."""
    w = knee(v, tol)
    return np.nan if not np.isfinite(w) else PD.density(pr, unit, w)


def force_knees(pr):
    f = DS / pr / "force_vs_resolution_axes.csv"
    if not f.exists():
        return pd.DataFrame()
    d = RC.mark(pd.read_csv(f), pr, "sensor")
    d["shear_mae"] = (d.fx_mae + d.fy_mae) / 2
    out = []
    for u, g in d.groupby("sensor"):
        k = g.groupby("width_px")[["fz_mae", "shear_mae"]].median()
        h, t, r = u.split("_")[0], int(u.split("_")[1][0]), int(u[-1])
        out.append(dict(principle=pr, unit=u, hardness=h, thickness_mm=t, rep=r,
                        suspect_hardware=RC.is_suspect(pr, u),
                        fz_knee_px=knee(k.fz_mae), fz_best=k.fz_mae.min(),
                        shear_knee_px=knee(k.shear_mae),
                        shear_best=k.shear_mae.min(),
                        fz_knee_R=knee_R(k.fz_mae, pr, u),
                        shear_knee_R=knee_R(k.shear_mae, pr, u)))
    return pd.DataFrame(out)


def shape_knees():
    out = []
    f = RES / FOLD["9DTact"] / "data" / "shape_vs_resolution.csv"
    if f.exists():
        d = RC.keep(pd.read_csv(f), "9DTact", "sensor")
        for u, g in d.groupby("sensor"):
            k = g.groupby("width_px")[["cyl4_raw_mae", "cube4_raw_mae"]].median()
            h, t, r = u.split("_")[0], int(u.split("_")[1][0]), int(u[-1])
            out.append(dict(principle="9DTact", unit=u, hardness=h, thickness_mm=t,
                            rep=r, suspect_hardware=RC.is_suspect("9DTact", u),
                            cyl4_knee_px=knee(k.cyl4_raw_mae),
                            cyl4_best_mm=k.cyl4_raw_mae.min(),
                            cube4_knee_px=knee(k.cube4_raw_mae),
                            cube4_best_mm=k.cube4_raw_mae.min(),
                            cyl4_knee_R=knee_R(k.cyl4_raw_mae, "9DTact", u),
                            cube4_knee_R=knee_R(k.cube4_raw_mae, "9DTact", u)))
    f = ROOT / "data" / "analysis" / "digit_shape" / "DIGIT_shape_vs_resolution.csv"
    if f.exists():
        d = RC.keep(pd.read_csv(f), "DIGIT", "unit")
        d["err"] = (d.depth_pred_mm - d.depth_true_mm).abs()
        w = d.groupby(["unit", "width_px", "shape"]).err.mean().unstack("shape")
        for u, g in w.groupby(level=0):
            g = g.droplevel(0)
            h, t, r = u.split("_")[0], int(u.split("_")[1][0]), int(u[-1])
            out.append(dict(principle="DIGIT", unit=u, hardness=h, thickness_mm=t,
                            rep=r, suspect_hardware=False,
                            cyl4_knee_px=knee(g.get("cyl4")),
                            cyl4_best_mm=g.get("cyl4").min(),
                            cube4_knee_px=knee(g.get("cube4")),
                            cube4_best_mm=g.get("cube4").min(),
                            cyl4_knee_R=knee_R(g.get("cyl4"), "DIGIT", u),
                            cube4_knee_R=knee_R(g.get("cube4"), "DIGIT", u)))
    return pd.DataFrame(out)


def cell(D, col):
    """3x3. 칸에 **두 복제를 그대로** 적는다.

    한때 중앙값을 적었는데, 80 과 640 의 중앙값 360 은 **사다리에 없는 해상도**라
    읽는 사람을 속인다. 둘이 같으면 하나만, 다르면 둘 다 적는다.
    """
    rows = []
    for h in HARD:
        r = {"hardness": h}
        for t in (1, 2, 3):
            v = D[(D.hardness == h) & (D.thickness_mm == t)][col].dropna()
            if not len(v):
                r[f"{t}mm"] = "—"
            elif v.nunique() == 1:
                r[f"{t}mm"] = PD.fmt(v.iloc[0])
            else:
                r[f"{t}mm"] = " / ".join(PD.fmt(x) for x in sorted(v))
        rows.append(r)
    return pd.DataFrame(rows)


def trend(D, col):
    """포화 해상도가 두께·경도를 따라가나 — 검정 단위는 유닛이다."""
    d = D.dropna(subset=[col])
    if len(d) < 6:
        return None
    hz = {"soft": 0, "medium": 1, "hard": 2}
    rt, pt = spearmanr(d.thickness_mm, d[col])
    rh, ph = spearmanr(d.hardness.map(hz), d[col])
    return dict(n=len(d), rho_thickness=rt, p_thickness=pt,
                rho_hardness=rh, p_hardness=ph)


def main():
    out = RES / "extra" / "data"
    out.mkdir(parents=True, exist_ok=True)

    F = pd.concat([force_knees(p) for p in FOLD], ignore_index=True)
    S = shape_knees()
    F.to_csv(out / "knee_force_by_unit.csv", index=False)
    S.to_csv(out / "knee_shape_by_unit.csv", index=False)

    tabs = []
    for pr, D in list(F.groupby("principle")) + list(S.groupby("principle")):
        cols = [c for c in ("fz_knee_px", "shear_knee_px",
                            "cyl4_knee_px", "cube4_knee_px") if c in D]
        for c in cols:
            g = cell(D, c.replace("_px", "_R"))
            g.insert(0, "metric", c.replace("_knee_px", ""))
            g.insert(0, "principle", pr)
            tabs.append(g)
            tr = trend(D, c.replace("_px", "_R"))
            print(f"\n  === {pr} · {c} ===")
            print(g.to_string(index=False))
            if tr:
                print(f"    유닛 {tr['n']} 개 — 두께 rho {tr['rho_thickness']:+.3f} "
                      f"p {tr['p_thickness']:.3f} | 경도 rho {tr['rho_hardness']:+.3f} "
                      f"p {tr['p_hardness']:.3f}")
    pd.concat(tabs).to_csv(out / "knee_by_cell_3x3.csv", index=False)

    rows = []
    for pr, D in list(F.groupby("principle")) + list(S.groupby("principle")):
        for c in [x for x in ("fz_knee_px", "shear_knee_px",
                              "cyl4_knee_px", "cube4_knee_px") if x in D]:
            tr = trend(D, c.replace("_px", "_R"))
            if tr:
                rows.append(dict(principle=pr,
                                 metric=c.replace("_knee_px", ""), **tr))
    T = pd.DataFrame(rows)
    # **다중검정 보정.** 두께와 경도를 원리 x 지표 10 조합에 걸어 20 번 검정한다.
    # 20 번 중 하나가 p < 0.05 인 것은 우연으로 나오는 수다. Benjamini-Hochberg 로
    # 거짓발견율을 통제한 q 를 함께 싣고, **판정은 q 로 한다.**
    from scipy.stats import false_discovery_control
    ps = np.r_[T.p_thickness.values, T.p_hardness.values]
    q = false_discovery_control(ps, method="bh")
    T["q_thickness"] = q[:len(T)]
    T["q_hardness"] = q[len(T):]
    T.to_csv(out / "knee_trends.csv", index=False)
    print(f"\n  다중검정 보정: 검정 {len(q)} 개 중 q < 0.05 인 것 {(q < .05).sum()} 개")

    # 전체 중앙 포화 해상도 — 칸을 나누지 않은 요약. 실무적으로 쓸 숫자는 이것이다.
    srow = []
    for pr, D in list(F.groupby("principle")) + list(S.groupby("principle")):
        for c in [x for x in ("fz_knee_px", "shear_knee_px",
                              "cyl4_knee_px", "cube4_knee_px") if x in D]:
            v = D[c].dropna()
            vR = D[c.replace("_px", "_R")].dropna()
            if not len(v):
                continue
            srow.append(dict(principle=pr, metric=c.replace("_knee_px", ""),
                             n=len(v),
                             median_R=round(float(np.median(vR)), 3),
                             min_R=round(float(vR.min()), 3),
                             max_R=round(float(vR.max()), 3),
                             median_px=float(np.median(v)),
                             min_px=int(v.min()), max_px=int(v.max())))
    pd.DataFrame(srow).to_csv(out / "knee_summary.csv", index=False)
    print("\n  === 전체 중앙 포화 해상도 (칸을 나누지 않고) ===")
    for x in srow:
        print(f"    {x['principle']:<13} {x['metric']:<7} 중앙 "
              f"{x['median_R']:8.3g} px/mm²  범위 {x['min_R']:.3g} ~ "
              f"{x['max_R']:.3g}  (폭 {x['median_px']:.0f} px)  n={x['n']}")
    print(f"\n  -> {out}/knee_by_unit*.csv, knee_by_cell_3x3.csv, knee_trends.csv")


if __name__ == "__main__":
    main()
