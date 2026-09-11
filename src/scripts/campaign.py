#!/usr/bin/env python3
"""
Track the 54-sensor campaign: what order, what is done, what is left.

    campaign.py --plan            # build and store the running order
    campaign.py --status          # progress, and the next sensor to mount
    campaign.py --next            # just the next id, for scripting

ORDER
-----
Replicates are deliberately separated. Set 1 covers all 27 conditions once, set
2 repeats them later. Running r1 and r2 back to back would make "replicate
variance" mean "the same gel measured twice in ten minutes", which hides exactly
what replicates are for: mounting, temperature and day-to-day drift.

Within a set the order is shuffled, but with a fixed seed so it is reproducible
and so a paused campaign resumes in the same sequence.

Thickness is NOT blocked together even though that would save handling time. If
the thin sensors were all measured on one day and the thick ones on another,
anything that drifted between those days would arrive in the results wearing the
costume of a thickness effect.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
REG = ROOT / "src" / "config" / "sensor_registry.yaml"


def load():
    return yaml.safe_load(open(REG))


def save(reg):
    REG.write_text(yaml.safe_dump(reg, sort_keys=False, allow_unicode=True))


def build_order(reg, seed: int, by_principle: bool, control: str | None,
                every: int) -> list:
    """Running order, with replicates kept apart.

    Grouping by principle is a handling convenience and a statistical cost:
    principle is one of the three factors, so anything that drifts across the
    campaign -- indenter wear, F/T zero, room temperature -- arrives in the
    results looking like a principle effect. The control sensor is what makes
    that recoverable: the same unit remeasured at intervals gives a drift curve
    that can be subtracted, or at least shown to be flat.
    """
    rng = random.Random(seed)
    if by_principle:
        blocks = []
        for pr in reg["design"]["principles"]:
            for rep in (1, 2):
                b = [s["id"] for s in reg["sensors"]
                     if s["principle"] == pr and s["replicate"] == rep]
                rng.shuffle(b)
                blocks.append(b)
        # r1 of every principle first, then r2, so a condition's two replicates
        # are still separated by the whole of its principle block.
        order = []
        for i in (0, 1):
            for k in range(i, len(blocks), 2):
                order += blocks[k]
    else:
        order = []
        for rep in (1, 2):
            b = [s["id"] for s in reg["sensors"] if s["replicate"] == rep]
            rng.shuffle(b)
            order += b
    if control and every > 0:
        out = []
        for i, sid in enumerate(order):
            if i and i % every == 0:
                out.append(f"CONTROL:{control}")
            out.append(sid)
        order = out
    return order


def run_contents(run):
    """What a run actually holds, as opposed to what the registry claims.

    `characterised` only means the gel model was fitted -- that phase writes
    to the registry and stops before any sample is taken. A sensor is not
    collected until its force ladder and all four shear axes are on disk,
    and several of the early runs have one without the other."""
    if not run:
        return 0, 0
    p = ROOT / str(run) / "state.json"
    if not p.is_file():
        return 0, 0
    try:
        sm = json.load(open(p)).get("samples", [])
    except Exception:
        return 0, 0
    return (sum(1 for x in sm if x.get("phase") == "force_series"),
            sum(1 for x in sm if x.get("phase") == "force_shear"))


def stream_frames(run) -> int:
    """Continuously captured frames on disk for a run (0 for ladder-only runs)."""
    if not run:
        return 0
    p = ROOT / str(run) / "state.json"
    if not p.is_file():
        return 0
    try:
        return int((json.load(open(p)).get("stream") or {}).get("saved", 0))
    except Exception:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--seed", type=int, default=20260902)
    ap.add_argument("--by-principle", action="store_true",
                    help="group by sensor principle instead of shuffling across "
                         "all of them; convenient to handle, but confounds "
                         "principle with anything that drifts over the campaign")
    ap.add_argument("--control", default="9DTact_hard_3mm_r1",
                    help="sensor remeasured at intervals to detect that drift")
    ap.add_argument("--control-every", type=int, default=9)
    a = ap.parse_args()
    reg = load()

    if a.plan:
        order = build_order(reg, a.seed, a.by_principle, a.control, a.control_every)
        reg["campaign"] = {
            "created": datetime.now().isoformat(), "seed": a.seed,
            "order": order,
            "policy": ("set 1 is all 27 conditions in shuffled order, set 2 "
                       "repeats them later so replicate variance carries "
                       "remounting and drift rather than ten minutes"),
        }
        save(reg)
        print(f"  order stored: {len(order)} sensors, seed {a.seed}")
        print(f"  set 1: {' '.join(order[:5])} ...")
        print(f"  set 2 begins at position 28: {order[27]}")
        return 0

    camp = reg.get("campaign")
    if not camp:
        print("  no order yet — run --plan")
        return 2
    byid = {s["id"]: s for s in reg["sensors"]}
    real = [i for i in camp["order"] if not i.startswith("CONTROL:")]
    done = [i for i in real if byid[i].get("status") == "characterised"]
    def collected(sid):
        n, sh = run_contents(byid[sid].get("run"))
        return n >= 4 and sh >= 8

    # A characterised-but-uncollected sensor still needs a run, so --next has
    # to look at what is on disk. Going by status alone skipped four sensors
    # whose gel model was fitted and whose ladder was never taken.
    todo = [i for i in camp["order"]
            if i.startswith("CONTROL:") or not collected(i)]

    if a.next:
        print(todo[0] if todo else "")
        return 0

    full = [i for i in real
            if (lambda t: t[0] >= 4 and t[1] >= 8)(run_contents(byid[i].get("run")))]
    print(f"  {len(done)} of {len(real)} characterised, "
          f"{len(full)} of {len(real)} collected\n")
    print("  full = ladder + all four shear axes   part = one of the two")
    print("  N/S = settled anchor samples, F = continuously captured frames\n")
    for i, sid in enumerate(camp["order"], 1):
        if sid.startswith("CONTROL:"):
            print(f"  {i:>3} ----  drift control: {sid.split(':', 1)[1]}")
            continue
        e = byid[sid]
        n, sh = run_contents(e.get("run"))
        mark = ("full" if n >= 4 and sh >= 8 else
                "part" if n or sh else
                "char" if e.get("status") == "characterised" else
                "redo" if e.get("status") == "needs_remeasure" else "    ")
        extra = ""
        if e.get("safe_force_N"):
            extra = (f"  a={e['gel_model']['hertz_a']:.3f}  "
                     f"ceiling {e['safe_force_N']:.2f} N  "
                     f"{e['ladder_rungs_reached']}/50 rungs")
            ir = e.get("image_response") or {}
            if ir.get("reached"):
                extra += f"  img-sat {ir['max_measurable_force_N']:.2f} N"
            cm = e.get("contact_map") or {}
            if cm:
                extra += (f"  r@0.5mm {cm['at_depth']['region']['radius_px']:.0f}px"
                          f" r@0.5N {cm['at_force']['region']['radius_px']:.0f}px")
        got = f"  {n:>2}N {sh:>2}S" if (n or sh) else "        "
        fr = stream_frames(e.get("run"))
        got += f" {fr:>5}F" if fr else "      "
        print(f"  {i:>3} {mark} {got}  {sid:<26}{extra}")

    if todo:
        print(f"\n  next: {todo[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
