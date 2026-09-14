#!/usr/bin/env python3
"""두 점 분해능의 **입력 해상도 스윕** — 힘·형상과 같은 x 축에 올린다.

**무엇을 묻는가.** "이 겔이 두 접촉을 가를 수 있나" 가 아니라 **"그 판정에 픽셀이
몇 개 필요한가"** 다. 그래서 원본 프레임을 12 단으로 줄여 넣고, **판정 격자와
판정 기준은 손대지 않는다.**

* 영상과 기준영상을 `INTER_AREA` 로 (w, h) 로 줄인다.
* 축척 야코비안을 같은 배율로 줄인다 — 안 그러면 mm 축이 틀어져 dip 이 가짜로
  움직인다.
* **등방 격자를 물리 단위로 고정한다.** 700x700 픽셀만 고정하는 것으로는
  부족하다 — 축척이 함께 줄면 같은 캔버스가 더 넓은 mm 범위를 덮어 0.02 mm
  구간마다 픽셀이 모자라고, 프로파일이 통째로 사라진다. 출력 ppm 을 원 해상도
  값으로 못박아 **입력만 나빠지고 자는 같게** 한다.
* dip >= 0.265, 자국 >= 2.5 레벨, dip > 잡음의 3 배 — `analyse_resolution.py`
  와 같은 세 관문을 그대로 쓴다.
* **검출기의 형태학 커널만 해상도를 따라 줄인다.** 그것은 판정 기준이 아니라
  청소 반경이고 픽셀 단위다. 고정해 두면 160 px 폭에서 커널이 화면의 1/14 가 돼
  덩어리를 지운다 — 첫 스윕이 426 px 아래를 전부 "접촉 없음" 으로 보고한 것이
  그 때문이었다. 겔이 못 가른 것이 아니라 검출기가 포기한 것이다.
"""
import json
import re
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analyse_resolution as A
import pixel_density as PD

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "result" / "extra" / "data"
SIZES = [(1920, 1080), (1280, 720), (854, 480), (640, 360), (426, 240),
         (320, 180), (160, 90), (80, 45), (48, 27), (32, 18), (16, 9), (8, 5)]
_RERUN = re.compile(r"__\d+$")


def judge(raw, J, sep, ksize, ppm0):
    """한 프레임의 dip·자국·잡음. `analyse_resolution` 의 절차 그대로.

    **형태학 커널만 해상도를 따라 줄인다.** 그것은 판정 기준이 아니라 검출기의
    청소 반경이고, 픽셀 단위라 고정하면 낮은 해상도에서 덩어리를 지운다.
    """
    c = A.blob_centre(raw, ksize=ksize)
    if c is None:
        return None
    dw, ppm = A.isotropic(raw.astype(np.float32), J, c, ppm_out=ppm0)
    got = A.axis_and_profile(dw, ppm)
    if got is None:
        return None
    x, prof, _ = got
    f, peak, sd, mtf, sym = A.dip_fraction(x, prof, sep)
    return None if not np.isfinite(f) else (f, peak, sd, mtf, sym)


def main():
    dataset = sys.argv[1] if len(sys.argv) > 1 else "20260911_VBTSresolution_dataset/9DTact/20260905_passA_pair100"
    probe = sys.argv[2] if len(sys.argv) > 2 else "pair100"
    cfg = yaml.safe_load(open(ROOT / "src" / "config" / "probes.yaml"))
    gaps = {p["id"]: p["gap_mm"] for p in cfg["probes"]
            if p["tip"] == "cylinder_pair"}
    sep = A.ELEMENT_MM + gaps[probe]
    droot = ROOT / "data" / dataset
    rows = []
    for run in sorted(d for d in droot.iterdir() if d.is_dir()):
        if _RERUN.search(run.name) or not (run / f"shape_{probe}" / "ladder.csv").exists():
            continue
        unit = run.name.split("_", 1)[1] if "_" in run.name else run.name
        st = json.loads((run / "state.json").read_text())
        J0 = A.jacobian(st, run.name)
        if J0 is None:
            print(f"  {unit}: 축척 없음 — 건너뜀"); continue
        ref0 = cv2.cvtColor(cv2.imread(str(run / "reference.png")),
                            cv2.COLOR_BGR2GRAY)
        # **출력 격자는 원 해상도의 ppm 으로 고정한다.** 입력만 나빠지고 자는 같다.
        ppm0 = float(np.sqrt(abs(np.linalg.det(J0))))
        lad = pd.read_csv(run / f"shape_{probe}" / "ladder.csv")
        for w, h in SIZES:
            k = w / ref0.shape[1]
            # **야코비안도 같은 배율로.** 픽셀이 커졌으므로 mm/px 가 커진다.
            J = J0 * k
            ref = cv2.resize(ref0, (w, h), interpolation=cv2.INTER_AREA)
            ksize = max(3, int(round(11 * k)) | 1)
            for dep, grp in lad.groupby(lad.target_depth_mm):
                got = []
                for _, r in grp.iterrows():
                    img0 = cv2.cvtColor(
                        cv2.imread(str(run / f"shape_{probe}" / r.file)),
                        cv2.COLOR_BGR2GRAY)
                    img = cv2.resize(img0, (w, h), interpolation=cv2.INTER_AREA)
                    raw = np.clip(ref.astype(np.int32) - img.astype(np.int32),
                                  0, 255).astype(np.uint8)
                    q = judge(raw, J, sep, ksize, ppm0)
                    if q:
                        got.append(q)
                if not got:
                    rows.append(dict(unit=unit, probe=probe, width_px=w,
                                     depth_mm=float(dep), dip=np.nan,
                                     imprint_lvl=np.nan, verdict="접촉 없음"))
                    continue
                fs = np.array([q[0] for q in got])
                pk = float(np.mean([q[1] for q in got]))
                own = float(np.nanmean([q[2] for q in got]))
                across = (fs.std(ddof=1) / np.sqrt(len(fs))
                          if len(fs) > 1 else np.nan)
                sd = np.nanmax([own, across])
                weak = not np.isfinite(pk) or pk < A.MIN_PEAK
                ok = (not weak and fs.mean() >= A.RAYLEIGH
                      and np.isfinite(sd) and fs.mean() > A.NOISE_K * sd)
                rows.append(dict(
                    unit=unit, probe=probe, width_px=w, depth_mm=float(dep),
                    dip=float(fs.mean()), dip_sd=float(sd), imprint_lvl=pk,
                    mtf=float(np.nanmean([q[3] for q in got])),
                    verdict=("신호부족" if weak else "분해" if ok else
                             "잡음" if fs.mean() >= A.RAYLEIGH else "미분해")))
        n = sum(1 for r in rows if r["unit"] == unit and r["verdict"] == "분해")
        print(f"  {unit:<16} 분해 {n:2} / {len(SIZES)*lad.target_depth_mm.nunique()}",
              flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    D = pd.DataFrame(rows)
    # 픽셀 폭은 이 카메라만의 숫자다. 유닛·원리를 가로질러 견주려면 시야 면적으로
    # 나눈 화소 밀도여야 한다 — 문서와 그림이 쓰는 x 축이 이 열이다.
    D = PD.add(D, "9DTact", unit_col="unit")
    f = OUT / f"resolution_sweep_{probe}.csv"
    D.to_csv(f, index=False)
    print(f"\n  -> {f}  ({len(D)} 행)")
    piv = (D.assign(res=D.verdict.eq("분해"))
             .groupby("width_px").res.mean() * 100)
    print("  해상도별 '분해' 비율 (%):")
    print("   " + "  ".join(f"{w}:{piv.get(w, 0):.0f}" for w, _ in SIZES))


if __name__ == "__main__":
    main()
