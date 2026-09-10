#!/usr/bin/env python3
"""Does one unit's photometric calibration apply to another?

DIGIT reads surface slope from colour, so shape reconstruction needs a map
(position, colour) -> slope. That map is measured by pressing a sphere of known
radius over a grid (run_indentation.py --phase calibgrid). The question this
answers is how many units have to be measured: if the map transfers, a few
units cover the campaign; if it does not, every unit needs its own.

For each unit and each grid point it takes the mean per-channel change inside
the imprint, divided by the actual indentation depth -- actual, because the
force gives it and the commanded depth does not (the gel plane is tilted and
the surface settles between runs). That is the response in levels per mm at
that place in the field.

Then it correlates those response maps between units, and separates the pairs
into REPLICATES (same hardness and thickness, so the same gel spec) and
different cells. A calibration that transfers would show high correlation at
least between replicates.

Usage: calibgrid_transfer.py [dataset]   (default 20260910_passA_calibgrid)
"""
import sys, re, itertools
import numpy as np, pandas as pd, cv2, yaml
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CH = ("dB", "dG", "dR")
MATCH_PX = 140.0          # two imprints closer than this are the same place


def gel_model(unit):
    reg = yaml.safe_load(open(ROOT / "config" / "sensor_registry.yaml"))
    for s in reg["sensors"]:
        if s["id"] == unit and s.get("gel_model"):
            g = s["gel_model"]
            return float(g["hertz_a"]), float(g["free_exponent"])
    return None


def response_map(run: Path, unit: str):
    f = run / "calibgrid_ball4" / "grid.csv"
    if not f.exists():
        return None
    g = pd.read_csv(f)
    km = gel_model(unit)
    if km is None:
        return None
    k, n = km
    ref = None
    for nm in ("reference_calibgrid.png", "reference_working.png",
               "reference.png"):
        if (run / nm).exists():
            ref = cv2.imread(str(run / nm)).astype(np.float32); break
    if ref is None:
        return None
    rows = []
    for _, r in g.iterrows():
        p = run / "calibgrid_ball4" / r.file
        if not p.exists():
            continue
        im = cv2.imread(str(p)).astype(np.float32)
        d = im - ref
        a = cv2.GaussianBlur(np.abs(d).max(2), (0, 0), 7)
        m = (a > max(5.0, 0.5 * a.max())).astype(np.uint8)
        nb, lab, st, cen = cv2.connectedComponentsWithStats(m, 8)
        if nb < 2:
            continue
        i = 1 + int(np.argmax(st[1:, 4]))
        m = lab == i                      # the imprint, not the imprint plus noise
        if st[i, 4] < 200:
            continue
        cx, cy = cen[i]
        H, W = a.shape
        x0, y0, w0, h0, _ = st[i]
        clear = min(x0, W - (x0 + w0), y0, H - (y0 + h0))
        depth = (max(r.force_N, 1e-6) / k) ** (1.0 / n) if r.force_N > 0 else np.nan
        if not np.isfinite(depth) or depth < 0.02:
            continue
        rows.append(dict(x=r.x_mm, y=r.y_mm, dep=r.target_depth_mm, depth=depth,
                         cx=float(cx), cy=float(cy), clear=int(clear),
                         area=int(m.sum()),
                         **{c: float(d[:, :, i][m].mean()) / depth
                            for i, c in enumerate(CH)}))
    return pd.DataFrame(rows) if rows else None


if __name__ == "__main__":
    ds = sys.argv[1] if len(sys.argv) > 1 else "20260910_passA_calibgrid"
    maps = {}
    for principle in ("DIGIT", "DIGIT_Marker"):
        base = ROOT / "data" / principle / ds
        if not base.exists():
            continue
        for run in sorted(base.glob(f"{principle}_*")):
            unit = re.sub(r"__\d+$", "", run.name)
            r = response_map(run, unit)
            if r is None or len(r) < 8:
                print(f"  {run.name}: 격자 없음/부족"); continue
            # Several runs of one unit exist -- code was being fixed between
            # them -- and the last one on disk is not the best one. Keep the
            # grid that covers the most of the frame with the most points: a
            # run whose autoframe misfired collapsed its lattice to 24 % of the
            # field, and that grid answers a different question from one that
            # spans it.
            score = len(r) * float(r.cx.std() * r.cy.std())
            if unit in maps and maps[unit][1] >= score:
                print(f"    (keeping the earlier {unit} grid, it covers more)")
                continue
            maps[unit] = (r, score)
            print(f"  {unit:26s} {len(r):3d} 점  dG {r.dG.mean():+7.1f} lvl/mm  "
                  f"dB {r.dB.mean():+7.1f}  dR {r.dR.mean():+6.1f}")
    maps = {u: v[0] for u, v in maps.items()}
    if len(maps) < 2:
        print("\n  비교하려면 유닛이 둘 이상 필요합니다."); sys.exit(0)
    print(f"\n=== 유닛 쌍 비교 ({len(maps)} 유닛) ===")
    # Pair points by where the imprint LANDED IN THE IMAGE, not by the offset
    # the robot was told to make. The map being compared is a function of place
    # in the picture, and the picture is not squarely mounted on the robot: over
    # the first six units the mm -> px fit came out rotated 20.8-32.4 deg, scaled
    # 82-109 px/mm, and centred anywhere over 475 px of the frame. Merging on the
    # commanded (x, y) therefore compared different parts of the field, and the
    # correlation it produced tracked how far apart two units' grid centres were
    # (Spearman -0.75, p 0.001) rather than anything about the gel.
    def match(a, b, tol=MATCH_PX):
        out = []
        for dep, ga in a.groupby("dep"):
            gb = b[b.dep == dep]
            if not len(gb):
                continue
            for _, ra in ga.iterrows():
                d = np.hypot(gb.cx - ra.cx, gb.cy - ra.cy)
                j = d.idxmin()
                if d[j] <= tol:
                    out.append({**{f"{c}_a": ra[c] for c in CH},
                                **{f"{c}_b": gb.loc[j, c] for c in CH},
                                "dist": float(d[j])})
        return pd.DataFrame(out)

    rows = []
    for u, v in itertools.combinations(sorted(maps), 2):
        a, b = maps[u], maps[v]
        a = a[a.clear >= 30]
        b = b[b.clear >= 30]          # a clipped imprint has a biased mean
        m = match(a, b)
        if len(m) < 6:
            print(f"  {u} vs {v}: 화면에서 겹치는 점 {len(m)}개뿐 -- 건너뜀")
            continue
        cu = re.search(r"(soft|medium|hard)_(\d)mm", u)
        cv_ = re.search(r"(soft|medium|hard)_(\d)mm", v)
        same = bool(cu and cv_ and cu.groups() == cv_.groups())
        rows.append(dict(a=u, b=v, n=len(m), replicate=same,
                         dist_px=float(m.dist.mean()),
                         **{c: float(np.corrcoef(m[f"{c}_a"], m[f"{c}_b"])[0, 1])
                            for c in CH}))
    d = pd.DataFrame(rows)
    if not len(d):
        print("  겹치는 격자점이 없습니다."); sys.exit(0)
    for lab, sub in (("복제 쌍 (같은 경도·두께)", d[d.replicate]),
                     ("다른 칸", d[~d.replicate])):
        if not len(sub):
            continue
        print(f"\n  {lab}: {len(sub)} 쌍")
        for c in CH:
            print(f"    {c} 상관 중앙 {sub[c].median():+.3f}  범위 "
                  f"{sub[c].min():+.3f}..{sub[c].max():+.3f}")
    out = ROOT / "data" / "calibgrid_transfer.csv"
    d.to_csv(out, index=False)
    print(f"\n  -> {out}")
