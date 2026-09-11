#!/usr/bin/env python3
"""재현성의 바닥 — 같은 유닛을 다시 앉히고 다시 재면 숫자가 얼마나 달라지는가.

캠페인은 유닛마다 한 번씩 쟀으므로, 두 유닛의 차이가 겔의 차이인지 그날 겔을
앉힌 방식의 차이인지 가릴 잣대가 없었다. `<원리>/repeated_data/<데이터셋>/` 에 있는 런들이
그 잣대다: 같은 유닛, 같은 프로토콜, 다시 앉히고 다시 영점 잡고 다시 잰 것.

각 유닛의 모든 런에서 사다리를 읽어 **공통 깊이**(가장 얕은 최대 ~ 가장 깊은 최소,
5 점)에서 힘을 선형 보간하고, 런들 사이의 표준편차를 낸다. 보고하는 것은

  sd_N        그 깊이에서 런 사이 힘의 표준편차
  cv          sd / 평균 — 힘이 유닛마다 10 배 다르므로 이쪽이 비교 가능하다
  range_N     최대 - 최소

그리고 유닛 사이의 차이와 나란히 놓는다. 재현성의 sd 가 유닛 사이의 sd 와 비슷하면
그 데이터셋으로는 유닛을 구별할 수 없다.

    python3 scripts/repeat_spread.py
"""
import re
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
N_AT = 5


def ladder(run):
    """(depth_mm, force_N) — Pass A 는 사다리에서, Pass B 는 눌러 들어가는 스트림에서."""
    for p in sorted(run.glob("shape_*/ladder.csv")):
        L = pd.read_csv(p)
        if len(L) >= 3 and {"depth_mm", "force_N"} <= set(L.columns):
            return L.assign(force_N=L.force_N.abs()).sort_values("depth_mm")
    f = run / "stream" / "frames.csv"
    if f.exists():
        S = pd.read_csv(f)
        if {"depth_mm", "Fz_s_corr", "segment"} <= set(S.columns):
            S = S[(S.segment == "normal_load") & (S.depth_mm > 0.02)]
            if len(S) >= 20:
                # 깊이로 0.02 mm 칸에 모아 칸마다 중앙값 — 프레임 잡음을 걷는다
                b = (S.depth_mm / 0.02).round() * 0.02
                G = (S.assign(depth_mm=b, force_N=S.Fz_s_corr.abs())
                       .groupby("depth_mm", as_index=False).force_N.median())
                if len(G) >= 3:
                    return G.sort_values("depth_mm")
    return None


def at(L, d):
    return np.interp(d, L.depth_mm.values, L.force_N.values)


def unit_of(name):
    return re.sub(r"__\d+$", "", name)


rows, notes = [], []
for rep in sorted(ROOT.glob("data/20260911_VBTSresolution_dataset/*/repeated_data/2026*")):
    ds = rep.parent.parent / rep.name
    groups = {}
    for r in sorted(p for p in rep.iterdir() if p.is_dir()):
        groups.setdefault(unit_of(r.name), []).append(r)
    for unit, reps in sorted(groups.items()):
        runs = [ds / unit] + reps if (ds / unit).is_dir() else reps
        L = [(r.name, ladder(r)) for r in runs]
        L = [(n, x) for n, x in L if x is not None]
        if len(L) < 2:
            notes.append(f"{rep.name}/{unit}: 사다리 있는 런 {len(L)} — 건너뜀")
            continue
        lo = max(x.depth_mm.min() for _, x in L)
        hi = min(x.depth_mm.max() for _, x in L)
        if hi <= lo:
            notes.append(f"{rep.name}/{unit}: 깊이 구간이 겹치지 않는다")
            continue
        for d in np.linspace(lo, hi, N_AT):
            f = np.array([at(x, d) for _, x in L])
            rows.append(dict(principle=rep.parent.parent.name, dataset=ds.name,
                             unit=unit.split("_", 1)[1] if "_" in unit else unit,
                             n_runs=len(L), depth_mm=round(float(d), 3),
                             mean_N=round(float(f.mean()), 4),
                             sd_N=round(float(f.std(ddof=1)), 4),
                             range_N=round(float(np.ptp(f)), 4),
                             cv=round(float(f.std(ddof=1) / max(f.mean(), 1e-9)), 4)))

D = pd.DataFrame(rows)
out = ROOT / "data" / "analysis" / "repeat_spread.csv"
D.to_csv(out, index=False)
for n in notes:
    print("  " + n)
print(f"\n  -> {out}: {len(D)} 행, {D.groupby(['principle','dataset','unit']).ngroups} 유닛\n")

for (pr, ds), g in D.groupby(["principle", "dataset"]):
    print(f"## {pr}/{ds}")
    for unit, u in g.groupby("unit"):
        print(f"   {unit:16s} {int(u.n_runs.iloc[0])} 런  "
              f"cv 중앙 {u.cv.median():.3f}  sd {u.sd_N.median():.4f} N  "
              f"범위 {u.range_N.median():.4f} N")
    # 유닛 사이의 차이와 비교: 같은 데이터셋의 모든 유닛을 공통 깊이에서
    cands = sorted((ds_p for ds_p in (ROOT / "data" / "20260911_VBTSresolution_dataset" / pr / ds).iterdir()
                    if ds_p.is_dir()))
    ll = [(p.name, ladder(p)) for p in cands]
    ll = [(n, x) for n, x in ll if x is not None]
    if len(ll) >= 3:
        lo = max(x.depth_mm.min() for _, x in ll)
        hi = min(x.depth_mm.max() for _, x in ll)
        if hi > lo:
            mid = 0.5 * (lo + hi)
            f = np.array([at(x, mid) for _, x in ll])
            b = float(f.std(ddof=1) / max(f.mean(), 1e-9))
            w = float(g.cv.median())
            print(f"   ── 유닛 사이 cv {b:.3f} (깊이 {mid:.3f} mm, {len(ll)} 유닛) "
                  f"vs 반복 cv {w:.3f} → 구별력 {b / max(w, 1e-9):.1f}배")
    print()
