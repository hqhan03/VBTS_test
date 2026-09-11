#!/usr/bin/env python3
"""데이터셋 재고 조사 — 원리 × 프로브 × 겔 유닛이 다 있는지, 무엇이 비어 있는지.

셋 다 같은 설계를 따른다: 경도 3 × 두께 3 × 반복 2 = **유닛 18 개**. 9DTact 는
`medium_2mm_r1` 이 파괴돼 17 개다. pass 마다 프로브가 다르고, pass 가 남겨야 하는
파일도 다르다. 이 스크립트는 **디스크만 보고** 그 격자를 채워 md 로 쓴다 —
어느 원리에 어느 프로브가 없는지, 있는 pass 안에서 어느 유닛이 비어 있는지.

    python3 src/scripts/dataset_audit.py
    python3 src/scripts/dataset_audit.py --out <경로>.md
"""
import argparse
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DSROOT = ROOT / "data" / "20260911_VBTSresolution_dataset"
PRS = ["9DTact", "DIGIT", "DIGIT_Marker"]
HARD = ["soft", "medium", "hard"]
THICK = [1, 2, 3]
REPS = [1, 2]
DESTROYED = {("9DTact", "medium_2mm_r1")}

# pass 이름 -> (사람이 읽는 프로브, 그 pass 가 남겨야 하는 파일들)
PROBE = {
    "passA_ball4":    ("구 ⌀4 mm",              ["shape_ball4/ladder.csv", "scale_ball4/scale.yaml"]),
    "passA_cube4":    ("정육면체 4 mm",          ["shape_cube4/ladder.csv"]),
    "passA_cyl4":     ("원기둥 ⌀4 mm",           ["shape_cyl4/ladder.csv"]),
    "passA_pair010":  ("두 기둥, 간격 0.10 mm",  ["shape_pair010/ladder.csv"]),
    "passA_pair025":  ("두 기둥, 간격 0.25 mm",  ["shape_pair025/ladder.csv"]),
    "passA_pair050":  ("두 기둥, 간격 0.50 mm",  ["shape_pair050/ladder.csv"]),
    "passA_pair075":  ("두 기둥, 간격 0.75 mm",  ["shape_pair075/ladder.csv"]),
    "passA_pair100":  ("두 기둥, 간격 1.00 mm",  ["shape_pair100/ladder.csv"]),
    "passA_calibgrid": ("구 ⌀4 mm 격자 + 램프",  ["calibgrid_ball4/grid.csv", "characterize/steps.csv"]),
    "passB_ball8":    ("구 ⌀8 mm",              ["stream/frames.csv"]),
    "passC_ceiling":  ("구 ⌀4 mm 램프",          ["characterize/steps.csv"]),
    "passC_ceiling_ball8": ("구 ⌀8 mm 램프",     ["characterize/steps.csv"]),
    "passC_surfacecheck":  ("표면 재측정 (zero 만)", ["zero/zero.yaml"]),
}

# 일부러 일부 유닛만 잰 pass. 재지 않은 유닛은 결함이 아니므로 "빈 유닛" 으로 세지
# 않고 이유와 함께 따로 적는다.
PARTIAL = {
    ("9DTact", "passA_pair010"):
        "1.25 mm 를 이미 분해해 한계가 미결이던 유닛에만 의미가 있다. 나머지는 "
        "1.25 도 분해하지 못하므로 더 좁은 간격은 결과가 정해져 있다.",
    ("9DTact", "passC_ceiling"):
        "ball4 로 돈 첫 시도다. 선언된 천장 다섯 개가 전부 자루 구간(깊이 4.0 mm "
        "밖)에서 나와 무효이고, passC_ceiling_ball8 이 대체한다. "
        "docs/force_ceiling.md 6.3.",
    ("9DTact", "passC_ceiling_ball8"):
        "9DTact_medium_2mm_r1 은 2026-09-04 의 초기 램프가 파괴해 잴 수 없다. "
        "나머지 17 유닛은 모두 포화까지 갔다. docs/force_ceiling.md 6.5c.",
    ("9DTact", "passC_surfacecheck"):
        "깊은 램프를 돌린 유닛만 손상 확인용으로 잰다. 램프 전후의 zero 가 같은 "
        "역할을 하므로 별도 실행은 필요할 때만 한다.",
    ("DIGIT", "passC_ceiling_ball8"):
        "18 / 18 전수. 9DTact 와 같은 프로브로 놓기 위한 pass 다 — 두 프로브의 힘 "
        "비가 1.50 ~ 3.26 으로 흩어져 환산이 불가능하다. docs/force_ceiling.md 6.7.",
}


def units(pr):
    return [f"{h}_{t}mm_r{r}" for h in HARD for t in THICK for r in REPS
            if (pr, f"{h}_{t}mm_r{r}") not in DESTROYED]


def rows(path, n_header=1):
    try:
        with path.open() as fh:
            return max(sum(1 for _ in fh) - n_header, 0)
    except OSError:
        return 0


def scan():
    out = []
    for pr in PRS:
        base = DSROOT / pr
        if not base.is_dir():
            continue
        for ds in sorted(base.glob("2026*")):
            key = re.sub(r"^\d{8}_", "", ds.name)
            probe, need = PROBE.get(key, ("?", []))
            for u in units(pr):
                run = ds / f"{pr}_{u}"
                r = dict(principle=pr, dataset=ds.name, pass_key=key, probe=probe,
                         unit=u, hardness=u.split("_")[0],
                         thickness_mm=int(u.split("_")[1][0]), rep=int(u[-1]),
                         folder=run.is_dir())
                for f in need:
                    r[f] = rows(run / f) if run.is_dir() else 0
                r["ok"] = bool(r["folder"]) and all(r.get(f, 0) > 0 for f in need)
                r["need"] = ";".join(need)
                out.append(r)
    return pd.DataFrame(out)


ap = argparse.ArgumentParser()
ap.add_argument("--out", default=str(DSROOT / "DATA_INVENTORY.md"))
a = ap.parse_args()
D = scan()

# ---------------------------------------------------------------- 프로브 격자 --
order = [k for k in PROBE if any(D.pass_key == k)]
grid = {}
for k in order:
    row = {}
    for pr in PRS:
        g = D[(D.pass_key == k) & (D.principle == pr)]
        row[pr] = (int(g.ok.sum()), len(g)) if len(g) else None
    grid[k] = row

L = []
W = L.append
W("# 데이터 재고 — 원리 × 프로브 × 겔 유닛\n")
W("`src/scripts/dataset_audit.py` 가 디스크만 보고 만든다. 기준은 설계값 **경도 3 × 두께 3 ×")
W("반복 2 = 유닛 18 개**이고, 9DTact 는 `medium_2mm_r1` 이 파괴돼 **17 개**다")
W("(`docs/force_ceiling.md` §7). 칸의 숫자는 **그 pass 가 남겨야 하는 파일까지 갖춘 유닛 수**")
W("/ 기대값이다 — 폴더만 있고 사다리가 비었으면 세지 않는다.\n")
W("## 폴더 구조\n")
W("```")
W("data/20260911_VBTSresolution_dataset/")
W("├── <원리>/                        9DTact | DIGIT | DIGIT_Marker")
W("│   ├── <YYYYMMDD>_<pass>/         프로브 하나 = pass 하나, 유닛당 폴더 하나")
W("│   │   └── <원리>_<경도>_<두께>mm_r<반복>/")
W("│   │       ├── state.json meta.yaml summary.yaml   그 런이 무엇을 했나")
W("│   │       ├── zero/                              영점 표면 찾기")
W("│   │       ├── shape_<프로브>/ladder.csv           깊이 사다리 (Pass A)")
W("│   │       ├── scale_<프로브>/scale.yaml           mm -> px 축척")
W("│   │       ├── stream/frames.csv                  프레임당 힘·자세 (Pass B)")
W("│   │       ├── calibgrid_ball4/grid.csv           광도 보정 격자")
W("│   │       └── characterize/steps.csv             최대 측정 가능 힘 램프")
W("│   ├── repeated_data/<pass>/<런>/  같은 유닛 두 번째·세 번째 측정")
W("│   └── *.csv                       그 원리의 스윕 결과")
W("└── DATA_INVENTORY.md               이 문서")
W("```")
W("")
W("버린 런은 여기 없다 — `data/_discarded/<원리>/<pass>/` 에 이유와 함께 있다.")
W("유닛당 폴더를 하나로 줄인 기록은 `data/analysis/DATASET_CLEANUP.md` 다.\n")
W("## 프로브 격자\n")
W("| pass | 프로브 | 9DTact | DIGIT | DIGIT_Marker |")
W("|---|---|---|---|---|")
for k in order:
    c = []
    for pr in PRS:
        v = grid[k][pr]
        if v is None or v[1] == 0:
            c.append("—")
        else:
            got, exp = v
            c.append(f"**{got} / {exp}**" if got == exp else f"⚠ {got} / {exp}")
    W(f"| `{k}` | {PROBE[k][0]} | {c[0]} | {c[1]} | {c[2]} |")
W("")
W("`—` 는 그 원리에 그 pass 가 **없다**는 뜻이다. 빈 칸이 이 표의 요점이다.\n")

# ------------------------------------------------ 시작만 한 pass 를 구분한다 --
STARTED = 2          # 채운 유닛이 이 수 이하면 "구멍" 이 아니라 "시작만 한 pass"
started = [(k, pr, grid[k][pr][0], grid[k][pr][1]) for k in order for pr in PRS
           if grid[k][pr] and grid[k][pr][1] and 0 < grid[k][pr][0] <= STARTED]
if started:
    W("## 시작만 한 pass\n")
    W("유닛 하나둘만 재고 멈춘 pass 다. 아래 \"비어 있는 유닛\" 표에서는 빼고 센다 —")
    W("거기 넣으면 재지 않은 유닛 열여섯 줄이 결함처럼 보인다. 이것은 결함이 아니라")
    W("**수집이 안 된 것**이고, 없는 pass 와 같은 성격이다.\n")
    W("| pass | 원리 | 채운 유닛 | 기대 |")
    W("|---|---|---:|---:|")
    for k, pr, got, exp in started:
        W(f"| `{k}` | {pr} | {got} | {exp} |")
    W("")

# ------------------------------------------------------------------- 빈 칸들 --
W("## 없는 pass — 설계에는 있고 디스크에는 없는 것\n")
miss = [(k, pr) for k in order for pr in PRS if (grid[k][pr] or (0, 0))[1] == 0]
if miss:
    W("| pass | 프로브 | 없는 원리 |")
    W("|---|---|---|")
    for k in order:
        gone = [pr for pr in PRS if (grid[k][pr] or (0, 0))[1] == 0]
        if gone:
            W(f"| `{k}` | {PROBE[k][0]} | {', '.join(gone)} |")
    W("")
else:
    W("없다.\n")

# --------------------------------------------------- 있는 pass 안의 빈 유닛 --
if PARTIAL:
    W("## 일부러 일부만 잰 pass\n")
    W("| pass | 원리 | 채운 유닛 | 기대 | 왜 |")
    W("|---|---|---:|---:|---|")
    for (pr, k), why in PARTIAL.items():
        g = D[(D.principle == pr) & (D.pass_key == k)]
        if len(g):
            W(f"| `{k}` | {pr} | {int(g.ok.sum())} | {len(g)} | {why} |")
    W("")

W("## 있는 pass 안에서 비어 있는 유닛\n")
started_keys = ({(k, pr) for k, pr, _, _ in started}
                | {(k, pr) for (pr, k) in PARTIAL})
holes = D[(~D.ok) & ~D.apply(lambda r: (r.pass_key, r.principle) in started_keys, axis=1)]
if len(holes):
    W("| 원리 | pass | 유닛 | 폴더 | 무엇이 없나 |")
    W("|---|---|---|---|---|")
    for _, r in holes.sort_values(["principle", "pass_key", "unit"]).iterrows():
        what = [f for f in r["need"].split(";") if not r.get(f, 0)]
        W(f"| {r.principle} | `{r.pass_key}` | `{r.unit}` | "
          f"{'있음' if r.folder else '**없음**'} | {', '.join(f'`{x}`' for x in what)} |")
    W("")
else:
    W("**없다 — 끝까지 돌린 pass 는 모두 기대한 유닛을 다 채웠다.**\n")

# ------------------------------------------------------------- 원리별 합계 --
W("## 원리별 합계\n")
W("| 원리 | pass | 기대 유닛 | 채운 유닛 | 프로브 종류 |")
W("|---|---:|---:|---:|---:|")
for pr in PRS:
    g = D[D.principle == pr]
    W(f"| {pr} | {g.pass_key.nunique()} | {len(g)} | {int(g.ok.sum())} | "
      f"{g.probe.nunique()} |")
W("")

# ------------------------------------------------------- 겔 규격별 교차 확인 --
W("## 겔 규격이 세 원리에 고르게 있나\n")
W("한 규격이 어느 원리에서 빠지면 그 규격은 원리 비교에 못 쓴다.\n")
W("| 겔 | 9DTact | DIGIT | DIGIT_Marker |")
W("|---|---:|---:|---:|")
for h in HARD:
    for t in THICK:
        for rp in REPS:
            u = f"{h}_{t}mm_r{rp}"
            c = []
            for pr in PRS:
                g = D[(D.principle == pr) & (D.unit == u)]
                c.append("파괴" if (pr, u) in DESTROYED
                         else (f"{int(g.ok.sum())} / {len(g)}" if len(g) else "—"))
            W(f"| `{u}` | {c[0]} | {c[1]} | {c[2]} |")
W("")
W("숫자는 **그 유닛이 채운 pass 수 / 그 원리가 가진 pass 수**다. 분모가 원리마다 다른 것이")
W("위 첫 표의 빈 칸이고, 분자가 분모보다 작은 것이 두 번째 표다.\n")

# ------------------------------------------------- characterize 가 어디 있나 --
W("## `characterize` (최대 측정 가능 힘) 는 원리마다 다른 pass 에 있다\n")
ch = []
for pr in PRS:
    for ds in sorted((DSROOT / pr).glob("2026*")):
        runs = [r for r in ds.iterdir() if r.is_dir()]
        n = sum(1 for r in runs if rows(r / "characterize" / "steps.csv") > 0)
        if n:
            ch.append(f"| {pr} | `{ds.name}` | {n} / {len(units(pr))} |")
if ch:
    W("| 원리 | 어느 데이터셋 안에 | 램프가 있는 유닛 |")
    W("|---|---|---:|")
    L.extend(ch)
    W("")
    W("`20260907_passB_ball8` 과 `20260910_passA_calibgrid` 의 램프는 힘 상한에 잘려")
    W("**천장이 아니라 하한**이다. 실측 천장은 `passC_ceiling_ball8` 두 개뿐이다 —")
    W("9DTact 17 / 17, DIGIT 18 / 18 (`docs/force_ceiling.md` §6.8).")
    W("`20260911_passC_ceiling` 은 `ball4` 로 돈 첫 시도인데, 선언된 다섯 개가 전부")
    W("자루 구간에서 나와 **무효**다 (§6.3).\n")
    W("`passC_ceiling_ball8` 의 9DTact 가 **분모보다 큰** 것은 결함이 아니다. 힘 상한을")
    W("20 → 30 → 40 → 60 → 80 N 으로 올려 가며 같은 유닛을 여러 번 돌렸고, **\"그 상한에서는")
    W("포화하지 않았다\" 는 것 자체가 결과**이므로 짧은 램프도 버리지 않는다. 분석은 유닛당")
    W("가장 멀리 간 램프를 쓴다 (`absolute_ceiling.py` 가 `__N` 접미사를 떼어 묶는다).\n")

# ---------------------------------------------------------------- 반복 측정 --
W("## 같은 유닛을 두 번 이상 잰 것\n")
rep_rows = []
for pr in PRS:
    rb = DSROOT / pr / "repeated_data"
    if rb.is_dir():
        for ds in sorted(x for x in rb.iterdir() if x.is_dir()):
            runs = [x for x in ds.iterdir() if x.is_dir()]
            uu = sorted({re.sub(r"__\d+$", "", x.name) for x in runs})
            rep_rows.append(f"| {pr} | `{ds.name}` | {len(uu)} | {len(runs)} |")
if rep_rows:
    W("분석이 쓰는 런은 데이터셋 안에 하나뿐이고, 두 번째·세 번째 측정은")
    W("`<원리>/repeated_data/<데이터셋>/` 에 있다. 재현성의 바닥은 여기서만 나온다")
    W("(`docs/campaign_protocol.md` §4.15).\n")
    W("| 원리 | 데이터셋 | 유닛 | 반복 런 |")
    W("|---|---|---:|---:|")
    L.extend(rep_rows)
    W("")

W("---\n")
W(f"유닛-pass 칸 {len(D)} 개 중 {int(D.ok.sum())} 개가 채워져 있다 "
  f"({100 * D.ok.mean():.1f} %). 표 데이터는 `data/analysis/dataset_audit.csv`.")

Path(a.out).write_text("\n".join(L), encoding="utf-8")
D.to_csv(ROOT / "data" / "analysis" / "dataset_audit.csv", index=False)
print(f"  {len(D)} 칸, 채움 {int(D.ok.sum())}, 빈 칸 {int((~D.ok).sum())}")
print(f"  -> {a.out}")
print(f"  -> {ROOT / 'data' / 'analysis' / 'dataset_audit.csv'}")
