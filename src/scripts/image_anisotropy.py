#!/usr/bin/env python3
"""픽셀이 정사각인가 — `cyl4` 자국의 축 비로 결정한다.

`probes.yaml` 의 `image_scale.UNRESOLVED`: 설계 FOV 25.51 x 11.97 mm 의 종횡비는
2.131 인데 프레임은 1920 x 1080 = 1.778 이다. 20 % 어긋난다. 둘 중 하나다.

  정사각 픽셀      → ⌀4.00 mm 평면 원기둥의 자국이 **원**으로 찍힌다 (축 비 1.00)
  설계 FOV 가 옳다 → 가로가 세로보다 1.199 배 더 눌러 담기므로 자국이 **타원**,
                     긴 축이 세로이고 축 비 1.199

한 프레임이면 답이 나오지만, 겔이 기울거나 프로브가 조금 기울어도 자국은 타원이 된다.
그래서 **모든 유닛의 모든 단**을 재고 유닛 사이에 공통으로 남는 성분을 본다: 축 비의
중앙값과 긴 축 방향의 분포. 방향이 한쪽으로 몰리면 광학이고, 흩어지면 장착이다.

    python3 src/scripts/image_anisotropy.py
"""
import re
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DSROOT = ROOT / "data" / "20260911_VBTSresolution_dataset"
DATASETS = {"9DTact": "20260905_passA_cyl4", "DIGIT": "20260910_passA_cyl4",
            "DIGIT_Marker": "20260910_passA_cyl4"}
PROBE_MM = 4.00
DESIGN_RATIO = 25.51 / 11.97 / (1920 / 1080)     # 1.199
MIN_AREA_PX = 4000


def reference(run):
    for n in ("reference_working.png", "reference_collect.png", "reference.png"):
        p = run / n
        if p.exists():
            g = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if g is not None:
                return g.astype(np.int16), n
    return None, None


def filled_blob(mask, near=None):
    """가장 큰 덩어리를 구멍까지 메워 돌려준다.

    DIGIT 자국은 가장자리에 밝은 고리가 서고 가운데가 비어 보일 때가 있으며, 마커
    겔은 점이 자국을 조각낸다. 바깥 윤곽만 잡아 타원을 맞추면 조각 하나에 맞춰진다
    (첫 판에서 DIGIT 의 타원 채움이 0.11 이었다). 그래서 (1) 기대 위치 근처의
    덩어리들만 남기고 (2) 볼록 껍질로 메운 뒤 (3) 그 위에 타원을 맞춘다.
    """
    n, lab, stats_, cent = cv2.connectedComponentsWithStats(mask, 8)
    if n <= 1:
        return None
    keep = []
    for i in range(1, n):
        if stats_[i, cv2.CC_STAT_AREA] < 300:
            continue
        if near is not None and np.hypot(*(cent[i] - near)) > 260:
            continue
        keep.append(i)
    if not keep:
        return None
    m = np.isin(lab, keep).astype(np.uint8) * 255
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    hull = cv2.convexHull(np.vstack(cs))
    out = np.zeros_like(m)
    cv2.drawContours(out, [hull], -1, 255, -1)
    return out, hull


def ellipse(frame, ref, near, level):
    """자국에 타원을 맞춘다 -> (장축 px, 단축 px, 장축 각도 deg, 면적 px, 채움)."""
    g = cv2.imread(str(frame), cv2.IMREAD_GRAYSCALE)
    if g is None:
        return None
    d = np.abs(g.astype(np.int16) - ref).astype(np.uint8)
    d = cv2.GaussianBlur(d, (5, 5), 0)
    # 그 런이 스스로 쓴 문턱(diff_level)을 쓴다. 없으면 Otsu.
    if level and level > 0:
        m = (d >= int(level)).astype(np.uint8) * 255
    else:
        _, m = cv2.threshold(d, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((7, 7), np.uint8))
    fb = filled_blob(m, near)
    if fb is None:
        return None
    filled, hull = fb
    a = float(filled.sum()) / 255.0
    if a < MIN_AREA_PX or len(hull) < 5:
        return None
    (_, _), (ax1, ax2), ang = cv2.fitEllipse(hull)
    major, minor = max(ax1, ax2), min(ax1, ax2)
    if ax1 < ax2:
        ang += 90.0
    fill = a / (np.pi * major * minor / 4.0)
    return major, minor, ang % 180.0, a, fill


rows = []
for pr, ds in DATASETS.items():
    base = DSROOT / pr / ds
    if not base.is_dir():
        continue
    for run in sorted(p for p in base.iterdir() if p.is_dir()):
        ref, refname = reference(run)
        if ref is None:
            continue
        lad = run / "shape_cyl4" / "ladder.csv"
        if not lad.exists():
            continue
        L = pd.read_csv(lad).sort_values("depth_mm")
        for _, r in L.iterrows():
            f = run / "shape_cyl4" / str(r.file)
            if not f.exists():
                continue
            try:
                cx, cy = [float(x) for x in
                          re.findall(r"-?\d+\.?\d*", str(r.get("centroid_px", "")))[:2]]
                near = np.array([cx, cy])
            except Exception:
                near = None
            e = ellipse(f, ref, near, r.get("diff_level"))
            if e is None:
                continue
            major, minor, ang, area, fill = e
            rows.append(dict(principle=pr, unit=run.name.replace(pr + "_", ""),
                             depth_mm=round(float(r.depth_mm), 3),
                             force_N=round(abs(float(r.force_N)), 3),
                             major_px=round(major, 1), minor_px=round(minor, 1),
                             axis_ratio=round(major / minor, 4),
                             major_angle_deg=round(ang, 1),
                             area_px=int(area), ellipse_fill=round(fill, 3),
                             px_per_mm_minor=round(minor / PROBE_MM, 1),
                             reference=refname))

D = pd.DataFrame(rows)
out = ROOT / "data" / "analysis" / "image_anisotropy.csv"
D.to_csv(out, index=False)
print(f"  {len(D)} 프레임, {D.groupby(['principle','unit']).ngroups} 유닛  -> {out}\n")

# 깊은 단일수록 자국이 또렷하다. 유닛마다 가장 깊은 단으로 판정한다.
deep = D.sort_values("depth_mm").groupby(["principle", "unit"], as_index=False).last()
print("== 유닛마다 가장 깊은 단 ==")
for pr, g in deep.groupby("principle"):
    a = g.axis_ratio
    print(f"  {pr:13s} n {len(g):2d}  축 비 중앙 {a.median():.3f} "
          f"(사분위 {a.quantile(.25):.3f}–{a.quantile(.75):.3f})  "
          f"장축 각도 중앙 {g.major_angle_deg.median():5.1f}°  "
          f"타원 채움 {g.ellipse_fill.median():.3f}")
a = deep.axis_ratio
print(f"\n  전체 n {len(deep)}  축 비 중앙 {a.median():.4f}  "
      f"평균 {a.mean():.4f} ± {a.std():.4f}")
print(f"  정사각 픽셀이면 1.000, 설계 FOV 가 옳으면 {DESIGN_RATIO:.3f}")

# 장축 방향: 광학이면 한쪽으로 몰린다 (0/180° = 가로, 90° = 세로)
ang = np.deg2rad(2 * deep.major_angle_deg.values)     # 축 데이터 -> 각도 2배
R = np.hypot(np.cos(ang).mean(), np.sin(ang).mean())
mean_ang = (np.rad2deg(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())) / 2) % 180
print(f"  장축 방향 집중도 R {R:.3f} (1 이면 완전히 한 방향, 0 이면 무작위), "
      f"평균 {mean_ang:.1f}°")

from scipy import stats
t = stats.wilcoxon(deep.axis_ratio - 1.0)
t2 = stats.wilcoxon(deep.axis_ratio - DESIGN_RATIO)
print(f"\n  H0 축 비 = 1.000 (정사각):    Wilcoxon p {t.pvalue:.2ე}".replace("ე", "e")
      if False else f"\n  H0 축 비 = 1.000 (정사각):     p {t.pvalue:.3g}")
print(f"  H0 축 비 = {DESIGN_RATIO:.3f} (설계 FOV): p {t2.pvalue:.3g}")
