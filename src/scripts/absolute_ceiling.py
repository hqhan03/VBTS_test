#!/usr/bin/env python3
"""절대 기준의 천장 — 원리를 건너 비교할 수 있는 자.

`force_ceiling.md` 5 가 적어 둔 한계: 지금의 천장은 **유닛 자신의 최대 응답의
15 %** 라는 상대 기준으로 잡는다. 문턱이 유닛마다 다르므로 두 센서의 천장은 같은
자로 잰 값이 아니고, 4.1 에서 "마커가 더 멀리 읽는다" 는 결론이 그렇게 만들어졌다가
철회됐다.

여기서는 문턱을 모든 유닛에 **같은 물리량**으로 둔다:

    응답이 THRESH lvl/N 아래로 떨어지는 힘

새 수집은 필요 없다. `characterize/steps.csv` 가 단마다 force_N 과
slope_levels_per_N 을 이미 갖고 있고, 이 스크립트는 그 열을 다시 훑을 뿐이다.

**기준값 자체에 근거가 없다는 것이 이 계산의 약점이다.** 0.5 lvl/N 은 문서가 예시로
적은 숫자다. 그래서 하나를 고르기 전에 여러 기준에서 **원리 간 순위가 유지되는지**
부터 본다. 흔들리면 그것은 기준을 잘못 골랐다는 뜻이 아니라 이 자료로는 두 원리를
가를 수 없다는 뜻이고, 그것도 보고할 결과다.

    python3 src/scripts/absolute_ceiling.py
    python3 src/scripts/absolute_ceiling.py --thresholds 0.2,0.5,1.0
"""
import argparse
import re
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
from ceiling_summary import SOURCES, SPHERE_LIMIT_MM, SAT_HITS, SAT_MIN_F   # noqa: E402

# ball8 로 두 원리를 같은 자에 놓는다. ball4 램프는 프로브가 달라 비교에 못 쓴다
# (같은 유닛에서 ball8/ball4 힘 비가 1.50 ~ 3.26 으로 흩어진다, force_ceiling.md 6.7).
DS_ALL = [("9DTact", "20260911_passC_ceiling_ball8"),
          ("DIGIT", "20260912_passC_ceiling_ball8")]


def absolute_ceiling(S, thresh, sphere_limit_mm=None):
    """(힘 N, 깊이 mm, 잘렸나) — 응답이 thresh 아래로 SAT_HITS 단 연속 내려간 힘.

    상대 기준과 같은 연속 규칙을 쓴다(한 단은 잡음이다 — 9DTact 의 단별 기울기
    잡음이 ±2 lvl/N 이다). 구 접촉 한계 밖은 천장이 아니므로 거부한다.
    반환의 세 번째 값은 "끝까지 문턱 위였다" 는 뜻으로, 그 유닛은 천장이 아니라
    **하한**만 갖는다.

    **응답이 한 번은 문턱을 넘은 뒤부터 본다.** 램프 초반은 접촉 면적이 아직 작아
    응답이 낮고, 그 구간을 그냥 훑으면 "이미지가 답하기를 멈춘 힘" 대신 "이미지가
    아직 답하기 전인 힘" 이 잡힌다 — 이 가드가 없으면 9DTact 의 중앙값이 0.37 N 으로
    나온다(30 N 에서도 2.45 lvl/N 로 변하고 있는 센서다). 상대 기준 쪽은 문턱이
    그때까지 본 최대의 15 % 라 초반에는 문턱도 같이 낮아 이 함정이 없었다.
    """
    f, d, sl = S.force_N.values, S.depth_mm.values, S.slope_levels_per_N.values
    hits, armed = 0, False
    for i in range(len(S)):
        if not (f[i] >= SAT_MIN_F and np.isfinite(sl[i])):
            continue
        if not armed:
            armed = sl[i] >= thresh      # 응답이 문턱을 넘은 적이 있어야 한다
            continue
        if sl[i] < thresh:
            hits += 1
            if hits >= SAT_HITS:
                j = i - SAT_HITS + 1
                if sphere_limit_mm is not None and d[j] > sphere_limit_mm:
                    return np.nan, float(d[j]), False    # 자루 구간 — 무효
                return float(f[j]), float(d[j]), False
        else:
            hits = 0
    if not armed:
        return np.nan, np.nan, False     # 응답이 한 번도 문턱을 넘지 않았다
    return np.nan, np.nan, True                          # 끝까지 문턱 위 = 잘림


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--thresholds", default="0.2,0.5,1.0",
                    help="lvl/N, 쉼표로 (기본 0.2,0.5,1.0)")
    a = ap.parse_args()
    TH = [float(x) for x in a.thresholds.split(",")]

    rows = []
    for pr, DS in DS_ALL:
        base = ROOT / "data" / "20260911_VBTSresolution_dataset" / pr / DS
        if not base.exists():
            continue
        for run in sorted(p for p in base.iterdir() if p.is_dir()):
            st = run / "characterize" / "steps.csv"
            if not st.exists():
                continue
            S = pd.read_csv(st).sort_values("step")
            g = re.search(r"(soft|medium|hard)_(\d)mm_r(\d)", run.name)
            if not g:
                continue
            lim = SPHERE_LIMIT_MM.get(DS)
            # 한 유닛을 여러 번 돌린 재실행은 `__2`, `__3` 으로 남는다. 접미사를
            # 떼지 않으면 별개 유닛으로 세어져, 얕게 끝난 초기 램프가 "잘림" 으로
            # 집계되고 잘림 비율이 실제보다 훨씬 높게 나온다.
            rec = dict(unit=run.name.split("__")[0], run=run.name, pr=pr,
                       dataset=DS, hard=g.group(1),
                       th=int(g.group(2)), fmax=float(S.force_N.max()))
            for t in TH:
                F, Dp, censored = absolute_ceiling(S, t, lim)
                rec[f"F@{t}"] = F
                rec[f"censored@{t}"] = censored
                # 잡히지도 잘리지도 않은 세 번째 경우: 응답이 한 번도 문턱을
                # 넘지 않아 기준을 적용할 수 없었다.
                rec[f"unarmed@{t}"] = bool(np.isnan(F) and not censored)
            rows.append(rec)

    D = pd.DataFrame(rows)
    # 9DTact 는 유닛마다 램프가 여러 번이다 — 가장 멀리 간 것 하나만 쓴다
    D = D.sort_values("fmax").groupby(["pr", "unit"], as_index=False).last()

    print(f"  {len(D)} 유닛\n")
    for t in TH:
        c, cen = f"F@{t}", f"censored@{t}"
        print(f"  === 기준 {t} lvl/N ===")
        for pr in D.pr.unique():
            g = D[D.pr == pr]
            got, cut = g[c].notna().sum(), int(g[cen].sum())
            un = int(g[f"unarmed@{t}"].sum())
            med = g[c].median()
            line = (f"    {pr:<14} n={len(g):<3} 잡힘 {got:<3} 잘림 {cut:<3}"
                    + (f"미도달 {un:<3}" if un else " " * 7))
            line += (f" 중앙 {med:6.2f} N" if got else f" {'중앙 —':>13}")
            if cut:
                line += f"   (잘린 것은 >{g.loc[g[cen], 'fmax'].min():.1f} N 하한)"
            print(line)
        print()

    out = ROOT / "data" / "analysis" / "absolute_ceiling.csv"
    out.parent.mkdir(exist_ok=True)
    D.to_csv(out, index=False)
    print(f"  -> {out}")

    # 순위가 기준값에 따라 흔들리나.
    #
    # 잘린 유닛을 빼고 중앙값을 내면 그 중앙값은 **편향된다** — 잘린 쪽이 체계적으로
    # 천장이 높은 유닛이기 때문이다. 잘림이 많은 기준에서는 원리끼리 중앙값을
    # 비교하는 것 자체가 성립하지 않으므로, 순위 안정성은 잘림이 적은 기준에서만
    # 따진다. CENSOR_MAX 를 넘는 원리가 있는 기준은 비교에서 제외한다.
    CENSOR_MAX = 0.10
    print("\n  원리별 중앙값의 순위가 기준값에 따라 바뀌는가:")
    order_seen, usable = set(), []
    for t in TH:
        g = D.groupby("pr")[f"F@{t}"].median().dropna()
        cen = D.groupby("pr")[f"censored@{t}"].mean()
        heavy = [f"{k} {cen[k]:.0%}" for k in g.index if cen[k] > CENSOR_MAX]
        if len(g) < 2:
            print(f"    {t:>4} lvl/N: 비교 가능한 원리가 {len(g)} 개 — 판정 불가")
            continue
        order = tuple(g.sort_values(ascending=False).index)
        line = f"    {t:>4} lvl/N: " + " > ".join(f"{k}({g[k]:.2f})" for k in order)
        if heavy:
            print(line + f"   << 잘림 과다({', '.join(heavy)}) — 비교 제외")
            continue
        print(line)
        order_seen.add(order); usable.append(t)
    print()
    if not usable:
        print("  잘림이 충분히 적은 기준이 하나도 없다 — 중앙값 비교가 성립하지 않는다.")
    elif len(usable) == 1:
        print(f"  잘림이 충분히 적은 기준이 {usable[0]} lvl/N 하나뿐이다 — 기준값에 따라")
        print("  순위가 바뀌는지는 **시험하지 못했다.** 그 하나의 기준이 낸 순위는")
        print("  " + " > ".join(order_seen.pop()) + " 이고, 중앙값 차이가 유의한지도")
        print("  아직 검정하지 않았다(복제 쌍 차이가 중앙 21 % 다).")
    elif len(order_seen) == 1:
        print(f"  잘림이 적은 기준 {usable} 에서 순위가 모두 같다 —")
        print("  기준값 선택이 결론을 만들지 않는다. 다만 중앙값 차이가 유의한지는")
        print("  별도 검정이 필요하다(복제 쌍 차이가 중앙 21 % 다).")
    else:
        print(f"  !! 잘림이 적은 기준 {usable} 안에서도 순위가 바뀐다 —")
        print("  이 자료로는 원리를 가를 수 없다.")


if __name__ == "__main__":
    main()
