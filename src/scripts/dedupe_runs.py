#!/usr/bin/env python3
"""One folder per unit in every dataset.

A unit that had to be re-run exists as <unit>, <unit>__2, ... . This picks the
run the analyses should use, renames it to the bare unit name, and moves the
rest out of the dataset folder so no glob can reach them again:

  repeated_data/<dataset>/   the run is as complete as the winner -- a second
               measurement of
               the same unit, which is the only same-unit repeatability data the
               campaign has. Never delete these.
  _discarded/  aborted: no ladder, no stream, or a step that produced nothing.

Winner: Pass B follows CANONICAL.yaml. Elsewhere it is the most complete run --
has the pass's ladder, then has a trusted scale, then most rungs, then the last
attempt. (Highest-suffix alone is wrong: 9DTact_hard_1mm_r2__3 has a ladder but
no scale.yaml, so derived_variables lost that unit's px_per_mm to it.)
"""
import re, sys, shutil, datetime, json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2] / "data" / "20260911_VBTSresolution_dataset"
DISCARD = Path(__file__).resolve().parents[2] / "data" / "_discarded"
DRY = "--apply" not in sys.argv
TODAY = datetime.date.today().isoformat()


def probe_dirs(run):
    return {p.name: p for p in run.iterdir() if p.is_dir()}


def score(run):
    """(has_ladder, n_rungs, has_scale, n_stream, n_char, suffix) -- bigger is better.

    characterize/steps.csv counts. Without it this scorer called the 15 N
    ceiling ramp on 9DTact_hard_3mm_r1 an aborted run and proposed discarding
    108 steps of measurement (2026-09-11), because a ceiling pass leaves no
    ladder and no stream -- only that file.
    """
    subs = probe_dirs(run)
    lad = n_rung = 0
    for name, p in subs.items():
        f = p / "ladder.csv"
        if name.startswith("shape_") and f.exists():
            n = sum(1 for _ in f.open()) - 1
            if n > lad:
                lad, n_rung = 1, n
    scale = 0
    for name, p in subs.items():
        if name.startswith("scale_") and (p / "scale.yaml").exists():
            scale = 1
    stream = 0
    f = run / "stream" / "frames.csv"
    if f.exists():
        stream = sum(1 for _ in f.open()) - 1
    char = 0
    f = run / "characterize" / "steps.csv"
    if f.exists():
        char = sum(1 for _ in f.open()) - 1
    m = re.search(r"__(\d+)$", run.name)
    return (lad, n_rung, scale, stream, char, int(m.group(1)) if m else 1)


def reason(run, win):
    s, w = score(run), score(win)
    if s[0] == 0 and s[3] == 0 and s[4] == 0:
        return "중단된 런 — 사다리도 스트림도 램프도 없다"
    if s[4] and w[4]:
        # 램프는 길이로 우열을 가리지 않는다. 짧은 쪽은 대개 **일부러 낮은 상한**으로
        # 잰 것이고(9DTact_hard_3mm_r1 의 15 N 과 20 N), "그 상한에서는 포화하지
        # 않았다" 는 것 자체가 결과다. 버리지 말고 반복 측정으로 보낸다.
        return None
    if s[3] and w[3] and s[3] < w[3]:
        return f"스트림이 짧다 ({s[3]} / {w[3]} 프레임)"
    if s[0] and not s[2] and w[2]:
        return "scale 단계가 결과를 남기지 않았다 (scale.yaml 없음)"
    if s[1] < w[1]:
        return f"사다리가 짧다 ({s[1]} / {w[1]} 단)"
    return None          # as complete as the winner -> a repeat, not a reject


plan = []
for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
    for ds in sorted((ROOT / pr).glob("2026*")):
        # `<원리>/repeated_data/<데이터셋>/` 에 있는 `__N` 은 몇 번째 시도였는지다 —
        # 고치면 안 된다. glob 이 2026* 이라 그쪽은 애초에 걸리지 않지만, 이름이 바뀌어도
        # 걸리지 않도록 여기서도 막는다.
        if ds.parent.name == "repeated_data":
            continue
        canon = None
        cy = ds / "CANONICAL.yaml"
        if cy.exists():
            canon = {k: v.get("run") for k, v in
                     (yaml.safe_load(cy.open()) or {})["canonical"].items()}
        groups = {}
        for d in sorted(p for p in ds.iterdir() if p.is_dir()):
            groups.setdefault(re.sub(r"__\d+$", "", d.name), []).append(d)
        for unit, rs in sorted(groups.items()):
            if len(rs) == 1 and rs[0].name == unit:
                continue
            if canon and canon.get(unit):
                win = ds / canon[unit]
            else:
                win = max(rs, key=score)
            for r in rs:
                if r == win:
                    continue
                why = reason(r, win)
                plan.append(dict(pr=pr, ds=ds.name, unit=unit, run=r.name,
                                 kind="discard" if why else "repeat",
                                 why=why or "승자와 같은 정도로 완결된 두 번째 측정",
                                 win=win.name))
            if win.name != unit:
                plan.append(dict(pr=pr, ds=ds.name, unit=unit, run=win.name,
                                 kind="rename", why="", win=unit))

for kind in ("discard", "repeat", "rename"):
    rows = [p for p in plan if p["kind"] == kind]
    print(f"\n######## {kind}: {len(rows)}")
    for p in rows:
        print(f"  {p['pr']}/{p['ds']}/{p['run']:42s} -> {p['win']:34s} {p['why']}")

if DRY:
    print("\n(모의 실행. --apply 로 실제 이동)")
    sys.exit()

# 순서: 패자를 먼저 치우고, 이름은 그 뒤에 바꾼다. 패자가 승자의 목표 이름을
# 차지하고 있을 수 있기 때문이다 -- 이름을 먼저 바꾸게 했더니
# 9DTact_soft_1mm_r1__2 -> 9DTact_soft_1mm_r1 이 "Directory not empty" 로 죽었다
# (2026-09-11). 안내문이 없는 폴더를 가리키던 문제는 순서가 아니라 `win_now` 로
# 푼다: 최종 이름을 미리 계산해 두고 그것을 적는다.
plan.sort(key=lambda x: 1 if x["kind"] == "rename" else 0)
renamed = {(x["pr"], x["ds"], x["run"]): x["win"] for x in plan if x["kind"] == "rename"}
moved = []
for p in plan:
    p["win_now"] = renamed.get((p["pr"], p["ds"], p["win"]), p["win"])
    ds = ROOT / p["pr"] / p["ds"]
    src = ds / p["run"]
    if p["kind"] == "rename":
        dst = ds / p["win"]
        src.rename(dst)
        (dst / "PROVENANCE.yaml").write_text(yaml.safe_dump(
            {"renamed_from": p["run"], "renamed_on": TODAY,
             "why": "재측정으로 폴더가 갈렸다. 이 런이 분석이 쓰는 런이다.",
             "note": "state.json / zero 의 영점 표면은 이 런 자신의 것이다."},
            allow_unicode=True, sort_keys=False))
    else:
        out = (DISCARD / p["pr"] / p["ds"] if p["kind"] == "discard"
               else ROOT / p["pr"] / "repeated_data" / p["ds"])
        out.mkdir(parents=True, exist_ok=True)
        dst = out / p["run"]
        shutil.move(str(src), str(dst))
        (dst / ("WHY_DISCARDED.md" if p["kind"] == "discard" else "WHY_REPEAT.md")
         ).write_text(f"# {p['run']}\n\n{p['why']}\n\n"
                      f"분석이 쓰는 런: `{p['win_now']}` — "
                      f"`{ROOT.name}/{p['pr']}/{p['ds']}` 안에 있다.\n"
                      f"옮긴 날: {TODAY}\n")
    moved.append(p)
print(f"\n{len(moved)} 폴더 처리")
