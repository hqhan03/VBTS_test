#!/usr/bin/env python3
"""data/analysis/ceiling_summary.csv — 유닛마다 이미지 포화로 잰 최대 측정 가능 힘.

`--phase characterize` 가 램프를 돌면서 이미 판정한 것을 `characterize/steps.csv`
에서 **다시 재생**한다. 새로 정의하지 않는다: 같은 규칙, 같은 기본값
(`--sat-frac 0.15 --sat-hits 2 --sat-min-force 0.3 --fit-floor 0.10`), 같은
"최대는 상위 세 창 기울기의 중앙값" 이다. 그래서 이 스크립트가 내는 천장은
`config/sensor_registry.yaml` 에 적힌 천장과 일치해야 하고, 일치하지 않으면
그것 자체가 보고할 일이다 (`--check`).

문서는 docs/force_ceiling.md. 데이터셋은 2026-09-11 정리 뒤 유닛당 폴더 하나이고,
격자와 램프가 다른 런에서 나온 12 유닛은 램프 옆 PROVENANCE.yaml 이 출처를 담는다.

    python3 scripts/ceiling_summary.py            # 표를 다시 쓴다
    python3 scripts/ceiling_summary.py --check    # 등록부와 맞춰만 본다
"""
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parent.parent
DS = "20260910_passA_calibgrid"
SAT_FRAC, SAT_HITS, SAT_MIN_F, FIT_FLOOR = 0.15, 2, 0.3, 0.10
EXP_WINDOW, EXP_MIN_F, EXP_MIN_DEPTH_FRAC, EXP_ALARM = 4, 0.5, 0.25, 2.0


def ceiling(S, thickness_mm, strict=False):
    """(천장 N, 깊이 mm, 최대 응답 lvl/N, 두 단이 붙어 있었나) — 런과 같은 규칙.

    `strict=False` 는 런이 실제로 한 대로다. 런의 판정은 if/elif 사슬이고 연속
    카운터를 되돌리는 것은 **마지막 else** 뿐이다(run_indentation.py 3591). 그 앞의
    지수 경보 가지(깊이가 두께의 25 % 를 넘고 국소 지수가 2.0 을 넘는 단)를 타면
    카운터가 그대로 남으므로, 그 구간에서는 "두 단 연속" 이 실제로는 "두 단" 이다 —
    붙어 있지 않아도 된다. `strict=True` 는 붙어 있기를 요구한다.
    """
    f = S.force_N.values
    d = S.depth_mm.values
    sl = S.slope_levels_per_N.values
    seen, peak, hits, first = [], 0.0, 0, None
    for i in range(len(S)):
        if np.isfinite(sl[i]) and f[i] > FIT_FLOOR:
            seen.append(sl[i])
            peak = float(np.median(sorted(seen, reverse=True)[:3]))
        armed = f[i] >= SAT_MIN_F and peak > 0 and np.isfinite(sl[i])
        low = armed and sl[i] < SAT_FRAC * peak
        if low:
            hits += 1
            if first is None:
                first = i
            if hits >= SAT_HITS:
                # 런은 `f_hist[-sat_hits]` 를 쓴다 — 두 단이 붙어 있다고 가정하고
                # 현재 단에서 두 칸 뒤를 집는다. 붙어 있지 않았으면 그 칸은 첫
                # 적중과 무관한 단이 된다(아래 two_steps_adjacent 가 그것을 표시).
                j = i - SAT_HITS + 1
                return float(f[j]), float(d[j]), peak, (i - first == SAT_HITS - 1)
        else:
            # 런이 카운터를 되돌리는 조건: 지수 경보 창이 무장되지 않은 단
            exp_kept = False
            if (i + 1 > EXP_WINDOW
                    and min(f[max(0, i - EXP_WINDOW):i + 1]) > EXP_MIN_F
                    and d[i] >= EXP_MIN_DEPTH_FRAC * thickness_mm):
                w = slice(max(0, i - EXP_WINDOW), i + 1)
                if (d[w] > 0).all() and (f[w] > 0).all():
                    exp = float(np.polyfit(np.log(d[w]), np.log(f[w]), 1)[0])
                    exp_kept = np.isfinite(exp) and exp > EXP_ALARM
            if strict or not exp_kept:
                hits, first = 0, None
    return np.nan, np.nan, peak, True


ap = argparse.ArgumentParser()
ap.add_argument("--check", action="store_true", help="표를 쓰지 않고 등록부와만 비교")
a = ap.parse_args()

reg = yaml.safe_load((ROOT / "config" / "sensor_registry.yaml").open())
BY_ID = {e["id"]: e for e in reg["sensors"]}
rows, bad = [], []
for pr in ("DIGIT", "DIGIT_Marker"):
    base = ROOT / "data" / "20260911_VBTSresolution_dataset" / pr / DS
    if not base.exists():
        continue
    for run in sorted(p for p in base.iterdir() if p.is_dir()):
        st = run / "characterize" / "steps.csv"
        if not st.exists():
            bad.append(f"{pr}/{run.name}: characterize/steps.csv 없음")
            continue
        S = pd.read_csv(st).sort_values("step")
        unit = run.name
        g = re.search(r"(soft|medium|hard)_(\d)mm_r(\d)", unit)
        th = int(g.group(2))
        ceil, depth, peak, adjacent = ceiling(S, th)
        s_ceil, _, _, _ = ceiling(S, th, strict=True)
        # `peak` 는 포화를 선언한 순간까지 본 최대다 — 판정이 쓴 값. 램프 전체를 다 본
        # 최대는 그보다 크거나 같고, 그쪽이 **유닛의 성질**로서의 응답이다 (등록부의
        # peak_slope_levels_per_N 과 같은 값). 4.1 의 교란 분석은 이쪽을 쓴다.
        fin = S[(S.force_N > FIT_FLOOR) & S.slope_levels_per_N.notna()].slope_levels_per_N
        peak_final = float(np.median(sorted(fin, reverse=True)[:3])) if len(fin) else np.nan
        prov = run / "characterize" / "PROVENANCE.yaml"
        ir = (BY_ID.get(unit) or {}).get("image_response") or {}
        r_ceil = ir.get("max_measurable_force_N") if ir.get("reached") else None
        err = abs(ceil - r_ceil) if (r_ceil and np.isfinite(ceil)) else np.nan
        if np.isfinite(err) and err > 1e-4:
            bad.append(f"{unit}: 재생 {ceil:.4f} N vs 등록부 {r_ceil:.4f} N")
        rows.append(dict(
            unit=unit, pr=pr, hard=g.group(1), th=th, rep=int(g.group(3)),
            ceil=ceil, depth=depth, peak=peak, peak_final=peak_final, steps=len(S),
            fmax=float(S.force_N.max()), dmax=float(S.depth_mm.max()),
            img0=float(S.img_mean_abs_diff.iloc[0]), img1=float(S.img_mean_abs_diff.iloc[-1]),
            d_over_t=depth / th, two_steps_adjacent=adjacent, ceil_strict=s_ceil,
            registry_ceil=r_ceil, match_err=err,
            ramp_from=(yaml.safe_load(prov.open()).get("moved_from") if prov.exists() else ""),
        ))

D = pd.DataFrame(rows)
print(f"  {len(D)} 유닛, 천장 잡힌 것 {D.ceil.notna().sum()}, "
      f"등록부와 최대 차이 {np.nanmax(D.match_err.values):.6f} N")
for b in bad:
    print("  ! " + b)
if not a.check:
    out = ROOT / "data" / "analysis" / "ceiling_summary.csv"
    D.to_csv(out, index=False)
    print(f"  -> {out}")
    print(D.groupby(["pr", "hard"]).ceil.median().round(2).to_string())
