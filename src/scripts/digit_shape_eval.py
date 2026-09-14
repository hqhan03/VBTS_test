#!/usr/bin/env python3
"""DIGIT 형상 평가를 18 유닛 x 12 해상도로 낸다 — `digit_shape.py` 의 구동부.

**이 파일이 없었다.** `digit_shape.py` 의 `main()` 은 빈 껍데기였고 원래 결과를
낸 구동부가 저장소에 남아 있지 않았다(2026-09-14). 그래서 두 가지가 늦게
드러났다:

* `eval_unit` 이 `load_ref()` 를 건너뛰고 `reference.png` 를 직접 읽고 있었다.
  바로 위 docstring 이 "쓰면 안 된다" 고 적어 둔 파일이다.
* 접촉 마스크의 3x3 열림이 픽셀 단위로 고정돼 저해상도에서 자국을 통째로
  지웠다 — 16x9 에서 깊이가 0 으로 나왔다.

모델(LUT)은 그대로 쓴다. 바뀐 것은 복원 단계뿐이다. 기존 CSV 는
`..._maskbug.csv` 로 백업한다.

    python3 src/scripts/digit_shape_eval.py
""" 
import sys, pickle, time, warnings
from pathlib import Path
sys.path.insert(0, 'src/scripts'); warnings.filterwarnings("ignore")
import pandas as pd
import digit_shape as D

ROOT = Path('.')
AN = ROOT/'data'/'analysis'/'digit_shape'
DS = ROOT/'data'/'20260911_VBTSresolution_dataset'/'DIGIT'
rows = []
luts = sorted(AN.glob('DIGIT_*_lut.pkl'))
print(f"{len(luts)} 유닛", flush=True)
for i, f in enumerate(luts, 1):
    unit = f.name[len('DIGIT_'):-len('_lut.pkl')]
    M = pickle.load(open(f, 'rb'))
    t0 = time.time()
    n = 0
    for shape in ('cyl4', 'cube4'):
        run = DS/f'20260910_passA_{shape}'/f'DIGIT_{unit}'
        if not run.exists():
            continue
        r = D.eval_unit(run, M['model'], M['px_per_mm'], shape=shape)
        for x in r:
            x['unit'] = unit
        rows += r; n += len(r)
    print(f"  [{i:2}/{len(luts)}] {unit:<16} {n:>4} 행  {time.time()-t0:.0f}s",
          flush=True)
d = pd.DataFrame(rows)
out = AN/'DIGIT_shape_vs_resolution.csv'
if out.exists():
    out.rename(AN/'DIGIT_shape_vs_resolution.maskbug.csv')
cols = ['unit', 'shape', 'width_px', 'depth_true_mm', 'depth_pred_mm']
extra = [c for c in d.columns if c not in cols]
d[cols + extra].to_csv(out, index=False)
print(f"-> {out}  ({len(d)} 행)")
