#!/usr/bin/env python3
"""ball4 와 ball8 이 같은 겔에서 같은 표면 높이를 보는가.

`probes.yaml` 은 ball8 의 팁 끝점이 ball4 와 같은 플랜지 거리에 있다는 것을 **설계상
주장**으로만 적어 두고, 같은 센서에서 ball4 가 기록한 표면과 0.1 mm 안에서 일치하는지
확인하도록 요구한다. 이 스크립트가 그 확인을 모든 유닛에 대해 수행한다.

`zero` 단계는 표면을 두 가지로 낸다:

  surface_mm              힘-깊이 Hertz 적합의 d0 — **모델에 의존한다**
  image_onset_surface_mm  이미지가 처음 변한 깊이 — **모델에 의존하지 않는다**

두 프로브가 팁 끝점을 공유하지 않는다면 두 추정치가 **함께** 어긋나야 한다.
적합만 어긋나고 이미지 개시가 일치한다면, 차이는 프로브 기하가 아니라 **반지름에 따라
달라지는 적합 편향**이다 — Hertz 는 반무한 탄성체를 가정하고, 반지름이 큰 쪽이 같은
힘에서 더 얕게 들어가므로 겔이 모델을 벗어날 때 d0 가 더 크게 밀린다.
"""
import sys, glob, yaml, statistics as st
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "data"

def collect(principle=None):
    rows = defaultdict(dict)          # unit -> probe -> {fit, onset, run}
    for f in glob.glob(str(ROOT / "**" / "zero" / "zero.yaml"), recursive=True):
        p = Path(f)
        unit = p.parent.parent.name
        if principle and not unit.startswith(principle):
            continue
        z = yaml.safe_load(open(f))
        probe = z.get("probe")
        if probe not in ("ball4", "ball8"):
            continue
        fit, onset = z.get("surface_mm"), z.get("image_onset_surface_mm")
        if fit is None:
            continue
        prev = rows[unit].get(probe)
        # 유닛·프로브당 가장 최근 것 하나만 — 같은 프로브를 여러 번 쟀으면 마지막
        if prev is None or z.get("at", "") > prev["at"]:
            rows[unit][probe] = {"fit": fit, "onset": onset,
                                 "at": z.get("at", ""), "run": str(p.parent.parent)}
    return rows

def main():
    principle = sys.argv[1] if len(sys.argv) > 1 else None
    rows = collect(principle)
    both = {u: v for u, v in rows.items() if "ball4" in v and "ball8" in v}
    if not both:
        print("ball4 와 ball8 을 모두 잰 유닛이 없다"); return

    print(f"{'유닛':<26}{'ball4 적합':>10}{'ball8 적합':>11}{'차':>8}"
          f"{'ball4 개시':>11}{'ball8 개시':>11}{'차':>8}")
    d_fit, d_onset, gap4, gap8 = [], [], [], []
    for u in sorted(both):
        a, b = both[u]["ball4"], both[u]["ball8"]
        df = b["fit"] - a["fit"]; d_fit.append(df)
        line = f"{u:<26}{a['fit']:>10.3f}{b['fit']:>11.3f}{df:>+8.3f}"
        if a["onset"] is not None and b["onset"] is not None:
            do = b["onset"] - a["onset"]; d_onset.append(do)
            gap4.append(a["fit"] - a["onset"]); gap8.append(b["fit"] - b["onset"])
            line += f"{a['onset']:>11.3f}{b['onset']:>11.3f}{do:>+8.3f}"
        else:
            line += f"{'—':>11}{'—':>11}{'—':>8}"
        print(line)

    def stat(name, v, n_req=2):
        if len(v) < n_req: print(f"  {name}: n={len(v)} — 판정 불가"); return None
        m = st.median(v)
        print(f"  {name:<34} 중앙 {m:+.3f} mm   평균 {st.mean(v):+.3f} "
              f"± {st.stdev(v):.3f}   범위 {min(v):+.3f} ~ {max(v):+.3f}   n={len(v)}")
        return m

    print(f"\n  프로브 {len(both)} 쌍" + (f" ({principle})" if principle else ""))
    mf = stat("ball8 − ball4, 힘 적합", d_fit)
    mo = stat("ball8 − ball4, 이미지 개시", d_onset)
    print()
    stat("적합 − 개시, ball4", gap4)
    stat("적합 − 개시, ball8", gap8)

    print()
    if mf is None: return
    if abs(mf) <= 0.1:
        print("  판정: 힘 적합이 0.1 mm 안에서 일치한다 — 공통 끝점 확인.")
    elif mo is not None and abs(mo) <= 0.1:
        print(f"  판정: 힘 적합은 {mf:+.3f} mm 어긋나지만 **이미지 개시는 {mo:+.3f} mm 로 일치한다**.")
        print("        팁 끝점은 공유되고, 어긋난 것은 Hertz 적합의 d0 다 — 반지름에 따라")
        print("        커지는 모델 편향이다. 프로브 간 깊이를 비교할 때는 이미지 개시를 쓴다.")
    else:
        print(f"  판정: 두 추정치가 함께 어긋난다 (적합 {mf:+.3f}, 개시 "
              f"{mo if mo is None else f'{mo:+.3f}'} mm) — 팁 끝점이 공유되지 않는다.")
        print("        ball8 로 잰 모든 깊이가 그만큼 편향되어 있다.")

if __name__ == "__main__":
    main()
