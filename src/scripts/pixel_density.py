#!/usr/bin/env python3
"""입력 해상도를 **화소 밀도** R (px/mm²) 로 옮긴다.

**왜 픽셀 폭이 아니라 밀도인가.** 세 원리의 카메라는 총 픽셀 수가 같아도 **보는
면적이 다르다.** 같은 "80 px 폭" 이 어떤 유닛에서는 겔의 더 좁은 조각을, 다른
유닛에서는 더 넓은 조각을 담는다. 폭을 x 축에 두면 그 차이가 숨고, 원리 간·유닛
간 비교가 카메라 화소 수의 비교가 되어 버린다. 밀도로 옮기면 **겔 표면 1 mm²
당 몇 화소로 보고 있는가** 라는 물리량이 된다.

**유도.** 원 해상도의 축척을 `s` (px/mm) 라 하면 시야 면적은
`A = (W/s) × (H/s) = W·H / s²` 이다. 가로를 `w` 로 줄이면 배율 `k = w/W` 이므로
총 화소는 `k²·W·H`, 따라서

    R = k²·W·H / A = k²·s²  =  (s·k)²

즉 **그 해상도에서의 px/mm 를 제곱한 값**이고, 세로/가로 비가 유지되므로 별도의
세로 항이 필요 없다.

**축척의 출처.**

* 9DTact · DIGIT — `data/analysis/derived_variables.csv` 의 `px_per_mm`.
* DIGIT_Marker — `data/analysis/marker_geometry.csv` 의 `px_per_mm_grid`.
  마커 유닛은 표면-높이 회귀 축척이 **20 % 낮다**는 것이 2026-09-13 에 확인됐다
  (`docs/cross_principle.md` §3.5b). 격자가 프레임마다 누워 있는 자이므로 그것을
  쓴다. 회귀값을 쓰면 마커 팔의 밀도가 통째로 1.4 배 낮게 나온다.
"""
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
AN = ROOT / "data" / "analysis"
NATIVE_W = 1920

_CACHE = {}


def _table():
    if _CACHE:
        return _CACHE
    d = pd.read_csv(AN / "derived_variables.csv")
    for _, r in d.iterrows():
        if r.principle in ("9DTact", "DIGIT") and np.isfinite(r.px_per_mm):
            _CACHE[(r.principle, r.unit)] = float(r.px_per_mm)
    g = pd.read_csv(AN / "marker_geometry.csv")
    for _, r in g.iterrows():
        u = str(r.unit).replace("DIGIT_Marker_", "")
        if np.isfinite(r.px_per_mm_grid):
            _CACHE[("DIGIT_Marker", u)] = float(r.px_per_mm_grid)
    return _CACHE


def ppm(pr, unit):
    """원 해상도(1920 px 폭)에서의 px/mm. 없으면 그 원리의 중앙값."""
    t = _table()
    u = str(unit).replace(f"{pr}_", "")
    if (pr, u) in t:
        return t[(pr, u)]
    vals = [v for (p, _), v in t.items() if p == pr]
    return float(np.median(vals)) if vals else np.nan


def density(pr, unit, width_px):
    """화소 밀도 R (px/mm²) — 그 유닛을 `width_px` 로 줄였을 때."""
    s = ppm(pr, unit)
    return np.nan if not np.isfinite(s) else (s * width_px / NATIVE_W) ** 2


def median_density(pr, width_px):
    """원리 전체의 중앙 밀도. 축 눈금에만 쓴다 — 유닛별 값은 `density()`."""
    t = _table()
    vals = [v for (p, _), v in t.items() if p == pr]
    if not vals:
        return np.nan
    return (float(np.median(vals)) * width_px / NATIVE_W) ** 2


def add(d, pr, width_col="width_px", unit_col="sensor", out="density_px_per_mm2"):
    """데이터프레임에 밀도 열을 붙인다."""
    d = d.copy()
    d[out] = [density(pr, u, w) for u, w in zip(d[unit_col], d[width_col])]
    return d


def fmt(v):
    """밀도를 사람이 읽는 자릿수로. 지수 표기는 쓰지 않는다 — 세 자리 수와 네 자리
    수가 같은 표에 섞이므로, `%g` 의 `1.69e+03` 보다 `1690` 이 견주기 쉽다."""
    v = float(v)
    if not np.isfinite(v):
        return "—"
    if v >= 100:
        return f"{v:,.0f}"
    if v >= 10:
        return f"{v:.1f}"
    return f"{v:.2f}"
