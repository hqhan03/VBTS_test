#!/usr/bin/env python3
"""result/ 의 3x3 표 — 경도 x 두께. 한 칸에 두 복제값과 평균을 함께 적는다.

표마다 두 가지를 남긴다:
  <이름>.csv     기계가 읽는 긴 형식 (유닛 한 줄)
  <이름>_3x3.csv 사람이 보는 3x3 (칸 = "r1 / r2  (평균)")
"""
from pathlib import Path

import numpy as np
import pandas as pd

import result_common as RC
import yaml

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "result"
REG = yaml.safe_load(open(ROOT / "src" / "config" / "sensor_registry.yaml"))
HARD = ["soft", "medium", "hard"]
FOLD = {"9DTact": "1_9DTact", "DIGIT": "2_DIGIT", "DIGIT_Marker": "3_DIGIT_Marker"}


def grid(df, value, fmt="{:.2f}", note=None, dropped=None):
    """긴 형식 -> 3x3. 칸은 'r1 / r2  (평균)'.

    `dropped` 에 든 유닛은 이미 `df` 에서 빠져 있다. 그 유닛이 속한 칸에 `e` 를 붙여
    **복제가 하나뿐인 칸**임을 읽을 수 있게 한다 — 값 하나짜리 칸을 두 값의 평균과
    구별하지 못하면 표가 거짓말을 한다.
    """
    dropped = dropped or set()
    rows = []
    for h in HARD:
        r = {"hardness": h}
        for t in (1, 2, 3):
            g = df[(df.hardness == h) & (df.thickness_mm == t)].sort_values("rep")
            v = g[value].dropna()
            if not len(v):
                r[f"{t}mm"] = "—"
                continue
            each = " / ".join(fmt.format(x) for x in v)
            # 문자열 칸(깊이 범위 등)은 평균이 없다
            num = pd.api.types.is_numeric_dtype(v)
            r[f"{t}mm"] = (f"{each}  ({fmt.format(v.mean())})"
                           if len(v) > 1 and num else each)
            if note is not None and note in g:
                flag = "".join("!" for x in g[note] if x)
                if flag:
                    r[f"{t}mm"] += " " + flag
            if any(u.startswith(f"{h}_{t}mm_") for u in dropped):
                r[f"{t}mm"] += " e"
        rows.append(r)
    return pd.DataFrame(rows)


def save(df, g, stem, pr):
    d = RES / FOLD[pr] / "data"
    d.mkdir(parents=True, exist_ok=True)
    df.to_csv(d / f"{stem}.csv", index=False)
    g.to_csv(d / f"{stem}_3x3.csv", index=False)
    print(f"  {pr:<13} {stem}")
    print(g.to_string(index=False))
    print()


def units_of(pr):
    return pd.DataFrame([dict(unit=s["id"].replace(pr + "_", ""), hardness=s["hardness"],
                              thickness_mm=s["thickness_mm"], rep=s["replicate"])
                         for s in REG["sensors"] if s.get("principle") == pr
                         and not s.get("suspect_hardware")])


# ------------------------------------------------------ 1. 최대 측정 가능 힘 --
TAG = {"9DTact": "20260911_passC_ceiling_ball8", "DIGIT": "20260912_passC_ceiling_ball8"}


def table_ceiling(pr):
    tag = TAG.get(pr)
    rows = []
    for s in REG["sensors"]:
        if s.get("principle") != pr or s.get("suspect_hardware"):
            continue      # 빛 누출 유닛 — result_common 참조
        ir = s.get("image_response") or {}
        run = s.get("run") or ""
        # ball8 pass 의 값만 쓴다. 9DTact_medium_2mm_r1 은 2026-09-03 의 프로토콜
        # 확정 전 런에서 reached=True 가 남아 있는데(그 램프가 겔을 파괴했다),
        # 프로브도 설정도 다르므로 표에 넣으면 안 된다.
        ok = bool(ir.get("reached")) and bool(tag) and tag in run
        b4 = bool(ir.get("reached")) and "calibgrid" in run
        use = ok or (b4 and pr == "DIGIT_Marker")
        rows.append(dict(unit=s["id"].replace(pr + "_", ""), hardness=s["hardness"],
                         thickness_mm=s["thickness_mm"], rep=s["replicate"],
                         probe=("ball8" if ok else "ball4" if use else "—"),
                         ceiling_N=ir["max_measurable_force_N"] if use else np.nan,
                         depth_mm=ir.get("max_measurable_depth_mm") if use else np.nan,
                         status=s.get("status", ""),
                         suspect=bool(s.get("suspect_hardware"))))
    D = pd.DataFrame(rows)
    save(D, grid(D, "ceiling_N", "{:.1f}", note="suspect",
                 dropped=RC.excluded(pr)), "table_max_force", pr)


# ------------------------------------------------------ 2. 공간 분해능 --
def table_resolution(pr):
    V = pd.read_csv(RES / "extra" / "data" / "resolution_verdicts.csv")
    V = RC.drop(V[V.principle == pr], pr, "unit")
    if not len(V):
        print(f"  {pr}: 분해능 자료 없음 — 표 생략\n")
        return
    ok = V[V.verdict == "분해"]
    rows = []
    for u, g in V.groupby("unit"):
        s = ok[ok.unit == u]
        rows.append(dict(unit=u, hardness=g.hardness.iloc[0],
                         thickness_mm=g.thickness_mm.iloc[0], rep=g.rep.iloc[0],
                         finest_centre_mm=s.centre_gap_mm.min() if len(s) else np.nan,
                         finest_edge_mm=s.edge_gap_mm.min() if len(s) else np.nan,
                         n_gaps_resolved=s.centre_gap_mm.nunique(),
                         n_gaps_tested=g.centre_gap_mm.nunique(),
                         depth_lo_mm=s.depth_mm.min() if len(s) else np.nan,
                         depth_hi_mm=s.depth_mm.max() if len(s) else np.nan,
                         best_dip=s.dip.max() if len(s) else np.nan))
    D = pd.DataFrame(rows)
    save(D, grid(D, "finest_centre_mm", "{:.2f}", dropped=RC.excluded(pr)),
         "table_spatial_resolution", pr)
    D2 = D.assign(depth_range=D.depth_lo_mm.round(2).astype(str) + "–"
                  + D.depth_hi_mm.round(2).astype(str))
    D2.loc[D2.depth_lo_mm.isna(), "depth_range"] = "—"
    save(D2, grid(D2, "depth_range", "{}", dropped=RC.excluded(pr)),
         "table_resolved_depth_range", pr)


def main():
    for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
        table_ceiling(pr)
        table_resolution(pr)


if __name__ == "__main__":
    main()
