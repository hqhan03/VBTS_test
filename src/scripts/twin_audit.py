#!/usr/bin/env python3
"""쌍둥이 불일치와 경향성 이상치 — 어느 복제를 버릴지 고르기 위한 근거.

두 가지를 따로 잰다.

**1. 쌍둥이 불일치.** 같은 (원리, 경도, 두께) 의 r1 과 r2 는 같은 물건이어야 한다.
`|a-b| / mean` 이 크면 둘 중 하나가 그 규격을 대표하지 못한다. 지표마다 자연스러운
산포가 다르므로(천장은 중앙 6 %, 광학 기울기는 30 % 가 정상) **그 지표 자신의 쌍
분포**와 견준다 — 쌍 아홉 개의 중앙값 대비 몇 배인가.

**2. 경향성 이상치.** 쌍과 무관하게, 한 유닛이 같은 원리의 다른 유닛들과 얼마나
떨어져 있는가. 평균과 표준편차는 이상치 자신에게 끌려가므로 중앙값과 MAD 로 잰다
(robust z = (x - median) / (1.4826 MAD)).

`suspect_hardware` 유닛은 이미 빠져 있다(`result_common`). 여기서 새로 나오는 것은
**빛 누출 말고 다른 이유로** 의심스러운 유닛이다.
"""
from pathlib import Path

import numpy as np
import pandas as pd

import result_common as RC

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "result"
FOLD = {"9DTact": "1_9DTact", "DIGIT": "2_DIGIT", "DIGIT_Marker": "3_DIGIT_Marker"}
PRS = ["9DTact", "DIGIT", "DIGIT_Marker"]


def _key(u):
    """`hard_2mm_r1` -> (hard, 2, 1)"""
    p = u.split("_")
    return p[0], int(p[1][0]), int(p[2][1])


def collect(pr):
    """이 원리의 유닛별 지표를 긴 형식으로 모은다."""
    d = RES / FOLD[pr] / "data"
    out = []

    def add(unit, metric, value):
        if value is None or (isinstance(value, float) and not np.isfinite(value)):
            return
        h, t, r = _key(unit)
        out.append(dict(principle=pr, unit=unit, hardness=h, thickness_mm=t,
                        rep=r, metric=metric, value=float(value)))

    f = d / "table_max_force.csv"
    if f.exists():
        for _, x in pd.read_csv(f).iterrows():
            add(x.unit, "천장 (N)", x.ceiling_N)
            add(x.unit, "포화 깊이 (mm)", x.depth_mm)

    f = d / "table_spatial_resolution.csv"
    if f.exists():
        for _, x in pd.read_csv(f).iterrows():
            add(x.unit, "분해 가능한 최소 간격 (mm)", x.finest_centre_mm)
            add(x.unit, "골 깊이 best_dip", x.get("best_dip"))

    f = d / "optical_slopes.csv"
    if f.exists():
        S = pd.read_csv(f)
        for pb, g in S.groupby("probe"):
            for _, x in g.iterrows():
                add(x.unit, f"자국 지름 기울기 {pb} (px/mm)", x.dia_slope_px_per_mm)
                add(x.unit, f"밝기 기울기 {pb} (lvl/mm)", x.level_slope_per_mm)

    # 힘 추정 — 해상도에 걸친 seed 중앙값의 중앙값. 한 해상도만 보면 잡음을 본다.
    f = d / "force_mae_vs_resolution.csv"
    if f.exists():
        F = RC.drop(pd.read_csv(f), pr, "sensor")
        for u, g in F.groupby("sensor"):
            k = g.groupby("width_px")[["fx_mae", "fy_mae", "fz_mae"]].median()
            for c, nm in (("fz_mae", "Fz"), ("fx_mae", "Fx"), ("fy_mae", "Fy")):
                add(u, f"{nm} MAE 중앙 (N)", k[c].median())
            add(u, "Fz 최솟값 (N)", k.fz_mae.min())

    f = d / "shape_vs_resolution.csv"
    if f.exists() and pr == "9DTact":
        S = RC.drop(pd.read_csv(f), pr, "sensor")
        for u, g in S.groupby("sensor"):
            k = g.groupby("width_px")[["cyl4_raw_mae", "cube4_raw_mae"]].median()
            add(u, "형상 MAE cyl4 최솟값 (mm)", k.cyl4_raw_mae.min())
            add(u, "형상 MAE cube4 최솟값 (mm)", k.cube4_raw_mae.min())
    return pd.DataFrame(out)


def twins(D):
    """쌍둥이 불일치. `ratio` 는 이 지표의 쌍 중앙값 대비 몇 배인가."""
    rows = []
    for (pr, m, h, t), g in D.groupby(["principle", "metric", "hardness",
                                       "thickness_mm"]):
        g = g.drop_duplicates("rep")
        if len(g) != 2:
            continue
        a, b = g.sort_values("rep").value.values
        mu = (abs(a) + abs(b)) / 2
        if mu <= 0:
            continue
        rows.append(dict(principle=pr, metric=m, hardness=h, thickness_mm=t,
                         r1=a, r2=b, rel_diff=abs(a - b) / mu,
                         worse_rep=1 if abs(a) > abs(b) else 2))
    T = pd.DataFrame(rows)
    if not len(T):
        return T
    med = T.groupby(["principle", "metric"]).rel_diff.transform("median")
    T["typical"] = med
    T["ratio"] = T.rel_diff / med.replace(0, np.nan)
    return T.sort_values("ratio", ascending=False)


def polish(M, n=12):
    """중앙값 다듬기 — 3x3 을 grand + 경도효과 + 두께효과 로 분해한다.

    설계가 경도와 두께를 일부러 흔들었으므로, 원리 전체의 중앙값과 견주면
    **설계된 변화가 이상치로 잡힌다**(hard_3mm 의 천장 63 N 이 그랬다 — 두께
    기울기의 정당한 끝점인데 z +6.3 이 나왔다). 행·열 효과를 먼저 빼고 남은
    잔차만 본다. 평균 대신 중앙값을 쓰는 것은 이상치 자신에게 끌려가지 않기
    위해서다(Tukey).
    """
    R = M.copy().astype(float)
    row = pd.Series(0.0, index=R.index)
    col = pd.Series(0.0, index=R.columns)
    grand = 0.0
    for _ in range(n):
        rm = R.median(axis=1)
        R = R.sub(rm, axis=0); row += rm
        d = row.median(); row -= d; grand += d
        cm = R.median(axis=0)
        R = R.sub(cm, axis=1); col += cm
        d = col.median(); col -= d; grand += d
    return grand, row, col, R


def trend(D):
    """경향성 이상치 — 경도·두께 설계를 뺀 **잔차**의 robust z.

    셀(경도x두께)의 중앙값으로 3x3 을 만들어 다듬고, 셀 잔차를 본다. 셀이
    통째로 벗어나면 그 겔 규격이 이상한 것이고(배합·양생 사고), 셀 안에서 한
    유닛만 벗어나면 그것은 쌍 불일치가 이미 잡는다.
    """
    rows = []
    for (pr, m), g in D.groupby(["principle", "metric"]):
        M = g.pivot_table(index="hardness", columns="thickness_mm",
                          values="value", aggfunc="median")
        if M.shape != (3, 3) or M.isna().any().any():
            continue
        grand, row, col, Rr = polish(M)
        # **척도는 재장착 산포다.** 다듬기는 잔차를 여럿 정확히 0 으로 만들어
        # MAD 가 0 에 붙고 z 가 ±100 까지 튄다. 대신 같은 지표의 쌍 반차
        # 중앙값을 쓴다 — "다시 끼웠을 때 생기는 흔들림의 몇 배인가" 가 되어
        # 읽히는 값이 되고, 3x3 의 칸 수에 휘둘리지 않는다.
        sp = []
        for _, gg in g.groupby(["hardness", "thickness_mm"]):
            gg = gg.drop_duplicates("rep")
            if len(gg) == 2:
                a, b = gg.sort_values("rep").value.values
                sp.append(abs(a - b) / 2)
        scale = float(np.median(sp)) if sp else 0.0
        if scale <= 0:
            continue
        for h in M.index:
            for t in M.columns:
                res = float(Rr.loc[h, t])
                z = res / scale
                if abs(z) < 2.5:
                    continue
                rows.append(dict(principle=pr, metric=m, cell=f"{h}_{t}mm",
                                 observed=M.loc[h, t],
                                 expected=grand + row[h] + col[t],
                                 residual=res, remount_spread=scale, z=z))
    Z = pd.DataFrame(rows)
    if not len(Z):
        return Z
    return Z.reindex(Z.z.abs().sort_values(ascending=False).index)


def pick(D, T):
    """셀마다 어느 복제를 남길지 — 설계 추세에 가까운 쪽에 표를 준다.

    지표마다 다듬기로 셀 기댓값을 구하고, 두 복제 중 **기댓값에서 먼 쪽**에
    한 표씩 준다. 표가 크게 갈리는 셀만 권고가 의미 있다 — 표가 비슷하면
    둘 중 아무거나 써도 된다는 뜻이다.
    """
    votes = {}
    for (pr, m), g in D.groupby(["principle", "metric"]):
        M = g.pivot_table(index="hardness", columns="thickness_mm",
                          values="value", aggfunc="median")
        if M.shape != (3, 3) or M.isna().any().any():
            continue
        grand, row, col, _ = polish(M)
        for (h, t), gg in g.groupby(["hardness", "thickness_mm"]):
            gg = gg.drop_duplicates("rep")
            if len(gg) != 2:
                continue
            exp = grand + row[h] + col[t]
            d = {int(x.rep): abs(x.value - exp) for _, x in gg.iterrows()}
            far = max(d, key=d.get)
            if d[far] == min(d.values()):
                continue
            k = (pr, f"{h}_{t}mm")
            votes.setdefault(k, {1: 0, 2: 0, "n": 0})
            votes[k][far] += 1
            votes[k]["n"] += 1
    rows = []
    for (pr, cell), v in votes.items():
        drop = 1 if v[1] > v[2] else 2 if v[2] > v[1] else None
        rows.append(dict(principle=pr, cell=cell, n_metrics=v["n"],
                         votes_r1_far=v[1], votes_r2_far=v[2],
                         suggest_drop=f"r{drop}" if drop else "동률",
                         margin=abs(v[1] - v[2]) / v["n"] if v["n"] else 0))
    return pd.DataFrame(rows).sort_values("margin", ascending=False)


def coverage():
    """자료량 불일치 — 값이 아니라 **얼마나 재었나**가 짝과 다른 경우.

    기울기가 맞아도 점이 절반이면 그 유닛은 같은 것을 재고 있지 않다
    (`DIGIT_Marker_medium_1mm_r2` 는 점 7 개에 깊이 0.11~0.71 mm,
    짝은 21 개에 0.11~1.60 mm 다). 값 비교로는 잡히지 않는다.
    """
    rows = []
    for pr in PRS:
        f = RES / FOLD[pr] / "data" / "optical_slopes.csv"
        if not f.exists():
            continue
        S = pd.read_csv(f)
        for (pb, h, t), g in S.groupby(["probe", "hardness", "thickness_mm"]):
            g = g.drop_duplicates("rep")
            if len(g) != 2:
                continue
            g = g.sort_values("rep")
            n1, n2 = g.n.values
            s1, s2 = (g.depth_hi_mm - g.depth_lo_mm).values
            rows.append(dict(principle=pr, probe=pb, cell=f"{h}_{t}mm",
                             n_r1=n1, n_r2=n2, n_ratio=max(n1, n2) / max(min(n1, n2), 1),
                             span_r1=s1, span_r2=s2,
                             span_ratio=max(s1, s2) / max(min(s1, s2), 1e-9),
                             r2_r1=g.r2.values[0], r2_r2=g.r2.values[1]))
    C = pd.DataFrame(rows)
    if not len(C):
        return C
    C["worst"] = C[["n_ratio", "span_ratio"]].max(axis=1)
    return C.sort_values("worst", ascending=False)


def main():
    D = pd.concat([collect(p) for p in PRS], ignore_index=True)
    out = RES / "extra" / "data"
    out.mkdir(parents=True, exist_ok=True)
    D.to_csv(out / "unit_metrics.csv", index=False)

    T = twins(D)
    T.to_csv(out / "twin_disagreement.csv", index=False)
    Z = trend(D)
    Z.to_csv(out / "trend_outliers.csv", index=False)

    print(f"  유닛 지표 {len(D)} 행, 쌍 {len(T)} 개, 지표 {D.metric.nunique()} 종\n")

    print("  === 지표별 쌍둥이 불일치의 정상 범위 (중앙값) ===")
    for (pr, m), g in T.groupby(["principle", "metric"]):
        print(f"    {pr:<13} {m:<32} {g.rel_diff.median()*100:5.1f} %  "
              f"(최대 {g.rel_diff.max()*100:5.1f} %)")
    print()

    print("  === 쌍둥이 불일치 상위 (자기 지표 중앙값의 3 배 이상) ===")
    bad = T[T.ratio >= 3]
    if not len(bad):
        print("    없음")
    for _, x in bad.iterrows():
        print(f"    {x.principle:<13} {x.hardness}_{x.thickness_mm}mm  "
              f"{x.metric:<32} r1 {x.r1:9.3f}  r2 {x.r2:9.3f}  "
              f"차 {x.rel_diff*100:5.1f} %  (보통 {x.typical*100:4.1f} %, "
              f"{x.ratio:.1f}배)")
    print()

    print("  === 경향성 이상치 — 설계를 뺀 셀 잔차 / 재장착 산포 (>= 2.5 배) ===")
    if not len(Z):
        print("    없음")
    for _, x in Z.iterrows():
        print(f"    {x.principle:<13} {x.cell:<12} {x.metric:<32} "
              f"실측 {x.observed:9.3f}  기대 {x.expected:9.3f}  "
              f"재장착의 {x.z:+.1f} 배")
    print()

    print("  === 셀별 누적 — 몇 개 지표에서 쌍이 크게 어긋났나 ===")
    cnt = {}
    for _, x in bad.iterrows():
        cnt.setdefault((x.principle, f"{x.hardness}_{x.thickness_mm}mm"), 0)
        cnt[(x.principle, f"{x.hardness}_{x.thickness_mm}mm")] += 1
    for (pr, c), n in sorted(cnt.items(), key=lambda kv: -kv[1]):
        if n < 2:
            continue
        print(f"    {pr:<13} {c:<12} {n} 개 지표")
    print()

    C = coverage()
    if len(C):
        C.to_csv(out / "twin_coverage.csv", index=False)
        print("  === 자료량 불일치 — 점 수나 깊이 범위가 짝의 1.5 배 이상 차이 ===")
        bc = C[C.worst >= 1.5]
        if not len(bc):
            print("    없음")
        for _, x in bc.iterrows():
            print(f"    {x.principle:<13} {x.cell:<12} {x.probe:<6} "
                  f"점 {x.n_r1:3.0f} / {x.n_r2:3.0f}   "
                  f"깊이폭 {x.span_r1:.2f} / {x.span_r2:.2f} mm   "
                  f"r2 {x.r2_r1:.3f} / {x.r2_r2:.3f}")
        print()

    # ---- 유닛 하나로 모은다. 증거가 겹치는 것만 의심스럽다 ----
    sus = {}

    def flag(pr, unit, kind, detail):
        sus.setdefault((pr, unit), []).append((kind, detail))

    for _, x in bad.iterrows():                       # 쌍 불일치
        far = f"r{x.worse_rep}"
        # 어느 쪽이 이상한지는 불일치만으로 정해지지 않는다. 두 유닛 모두 적되,
        # 추세 표(pick)와 자료량이 같은 쪽을 가리킬 때만 결론이 선다.
        for r in (1, 2):
            flag(x.principle, f"{x.hardness}_{x.thickness_mm}mm_r{r}",
                 "쌍 불일치", f"{x.metric} {x.rel_diff*100:.0f}% ({x.ratio:.1f}배)")
    if len(C):
        for _, x in C[C.worst >= 1.5].iterrows():
            r = 1 if x.n_r1 < x.n_r2 or x.span_r1 < x.span_r2 else 2
            flag(x.principle, f"{x.cell}_r{r}", "자료량 부족",
                 f"{x.probe} 점 {min(x.n_r1, x.n_r2):.0f} vs {max(x.n_r1, x.n_r2):.0f}, "
                 f"깊이폭 {min(x.span_r1, x.span_r2):.2f} vs {max(x.span_r1, x.span_r2):.2f} mm")

    print("  === 증거가 겹치는 유닛 (서로 다른 종류 2 개 이상) ===")
    S2 = []
    for (pr, u), ev in sus.items():
        kinds = {k for k, _ in ev}
        if len(kinds) < 2:
            continue
        S2.append(dict(principle=pr, unit=u, n_evidence=len(ev),
                       kinds="+".join(sorted(kinds)),
                       detail=" | ".join(f"{k}: {d}" for k, d in ev)))
    S2 = pd.DataFrame(S2).sort_values("n_evidence", ascending=False) \
        if S2 else pd.DataFrame()
    if not len(S2):
        print("    없음 — 어느 유닛도 두 종류의 증거에 동시에 걸리지 않았다")
    for _, x in S2.iterrows():
        print(f"    {x.principle:<13} {x.unit:<16} {x.detail}")
    if len(S2):
        S2.to_csv(out / "suspect_units.csv", index=False)
    print()

    P = pick(D, T)
    P.to_csv(out / "replicate_choice.csv", index=False)
    print("  === 어느 복제를 버릴까 — 추세에서 먼 쪽에 표 (지표 5 개 이상) ===")
    P = P[P.n_metrics >= 5]
    for _, x in P.head(12).iterrows():
        print(f"    {x.principle:<13} {x.cell:<12} 지표 {x.n_metrics:2}  "
              f"r1 먼쪽 {x.votes_r1_far:2}  r2 먼쪽 {x.votes_r2_far:2}  "
              f"-> {x.suggest_drop} 을 버림 (표차 {x.margin*100:.0f} %)")
    print(f"\n  -> {out}/twin_disagreement.csv, trend_outliers.csv, "
          f"replicate_choice.csv, unit_metrics.csv")


if __name__ == "__main__":
    main()
