#!/usr/bin/env python3
"""유닛 x 간격의 분해 판정을 하나의 표로 — `analyse_resolution.py` 를 전수 재생.

각 행은 (원리, 유닛, 프로브, 깊이) 하나이고, 세 관문(dip >= 0.265, 자국 >= 2.5
레벨, 잡음의 3 배)의 판정과 DIGIT 360 의 MTF >= 0.5 판정을 함께 담는다.
여기서 3x3 표의 두 칸 -- "분해된 가장 좁은 간격" 과 "분해된 깊이 범위" -- 이 나온다.
"""
import re
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
PY = sys.executable
# (원리, 데이터셋, 프로브, 중심간격 mm). 기둥 지름 1.0 mm 이므로 가장자리 = 중심 - 1.0
SRC = [("9DTact", "20260911_passA_pair010", "pair010", 1.10),
       ("9DTact", "20260905_passA_pair025", "pair025", 1.25),
       ("9DTact", "20260905_passA_pair050", "pair050", 1.50),
       ("9DTact", "20260905_passA_pair075", "pair075", 1.75),
       ("9DTact", "20260905_passA_pair100", "pair100", 2.00),
       ("9DTact", "20260911_passA_pair150", "pair150", 2.50),
       ("DIGIT",  "20260909_passA_pair010", "pair010", 1.10),
       ("DIGIT",  "20260909_passA_pair025", "pair025", 1.25)]
UNITS = [f"{h}_{t}mm_r{r}" for h in ("soft", "medium", "hard")
         for t in (1, 2, 3) for r in (1, 2)]
ROW = re.compile(r"^\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+"
                 r"(\S+)\s+([\d.]+)\s+(\S+)")


def main():
    out = []
    for pr, ds, probe, gap in SRC:
        for u in UNITS:
            r = subprocess.run([PY, str(ROOT / "src" / "scripts" / "analyse_resolution.py"),
                                ds, f"{pr}_{u}", probe],
                               capture_output=True, text=True, cwd=ROOT)
            for ln in r.stdout.splitlines():
                m = ROW.match(ln)
                if not m:
                    continue
                out.append(dict(principle=pr, unit=u, probe=probe, centre_gap_mm=gap,
                                edge_gap_mm=round(gap - 1.0, 2),
                                hardness=u.split("_")[0], thickness_mm=int(u.split("_")[1][0]),
                                rep=int(u[-1]), depth_mm=float(m.group(1)),
                                dip=float(m.group(2)), dip_sd=float(m.group(3)),
                                imprint_lvl=float(m.group(4)), symmetry=float(m.group(5)),
                                verdict=m.group(6), mtf=float(m.group(7)),
                                verdict_mtf=m.group(8)))
        print(f"  {pr} {probe}: 누적 {len(out)} 행", flush=True)
    D = pd.DataFrame(out)
    p = ROOT / "result" / "extra" / "data" / "resolution_verdicts.csv"
    p.parent.mkdir(parents=True, exist_ok=True)
    D.to_csv(p, index=False)
    print(f"-> {p} ({len(D)} 행, {D.unit.nunique()} 유닛)")


if __name__ == "__main__":
    main()
