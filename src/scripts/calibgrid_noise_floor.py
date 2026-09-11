"""같은 유닛을 두 번 잰 격자의 상관 = 전이 상관의 잡음 바닥."""
import sys; sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np, pandas as pd
from pathlib import Path
from calibgrid_transfer import response_map, CH, MATCH_PX
B=Path("data/20260911_VBTSresolution_dataset/DIGIT/20260910_passA_calibgrid")
# 2026-09-11 폴더 정리 뒤: 같은 유닛의 두 번째 격자는 _discarded/ 로 갔다.
# 잡음 바닥을 다시 세우려면 깨끗한 유닛 몇을 일부러 두 번 재야 한다
# (photometric_calibration.md 3.1).
PAIRS=[]
def match(a,b,tol=MATCH_PX):
    out=[]
    for dep,ga in a.groupby("dep"):
        gb=b[b.dep==dep]
        if not len(gb): continue
        for _,ra in ga.iterrows():
            d=np.hypot(gb.cx-ra.cx, gb.cy-ra.cy); j=d.idxmin()
            if d[j]<=tol:
                out.append({**{f"{c}_a":ra[c] for c in CH},
                            **{f"{c}_b":gb.loc[j,c] for c in CH}, "dist":float(d[j])})
    return pd.DataFrame(out)
print(f"{'유닛':22s} {'n':>3s} {'dB':>7s} {'dG':>7s} {'dR':>7s}")
res=[]
for unit,r1,r2 in PAIRS:
    a=response_map(B/r1,unit); b=response_map(B/r2,unit)
    if a is None or b is None: print(f"{unit}: 없음"); continue
    a=a[a.clear>=30]; b=b[b.clear>=30]
    m=match(a,b)
    if len(m)<6: print(f"{unit}: 겹치는 점 {len(m)}"); continue
    r={c: float(np.corrcoef(m[f'{c}_a'],m[f'{c}_b'])[0,1]) for c in CH}
    res.append(r); print(f"{unit:22s} {len(m):3d} " + " ".join(f"{r[c]:+7.3f}" for c in CH))
if res:
    print("\n  같은 유닛 재측정 (잡음 바닥):")
    for c in CH: print(f"    {c} 중앙 {np.median([r[c] for r in res]):+.3f}")
    print("\n  비교 — 복제 쌍 18: dB +0.690  dG +0.553  dR +0.573")
    print("        비복제 612: dB +0.332  dG +0.460  dR +0.314")
