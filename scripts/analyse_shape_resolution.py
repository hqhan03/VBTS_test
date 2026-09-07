#!/usr/bin/env python3
"""How much camera resolution does the shape reconstruction actually use?

Runs analyse_shape's pipeline on every unit with the frames shrunk 1x, 2x, 3x,
4x, 6x, 8x, 12x and 16x (area averaging, reference included), so each unit is
seen as if through a camera with that many fewer pixels per millimetre. The
algorithm is not touched. Per unit and per factor the same scores are taken
as at full resolution; the question asked afterwards is the coarsest scale at
which each score is still as good as the full-resolution one.

    analyse_shape_resolution.py            # all units, writes the CSV
"""
import sys, importlib.util
from pathlib import Path
import pandas as pd, yaml
ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("shape", ROOT / "scripts" / "analyse_shape.py")
shape = importlib.util.module_from_spec(spec); sys.modules["shape"] = shape; spec.loader.exec_module(shape)

# Steps named by the sizes people actually use -- 1080p, 720p, 480p, 360p,
# 240p (16:9, so 1920x1080 ... 427x240) -- then halving on down to 8x4, where
# the imprint is a single pixel. The factor is 1080 / target height.
W0, H0 = 1920, 1080
HEIGHTS = (1080, 720, 480, 360, 240, 180, 90, 45, 22, 11, 4)
FACTORS = tuple(H0 / h for h in HEIGHTS)
reg = yaml.safe_load(open(ROOT / "config" / "sensor_registry.yaml"))
units = sys.argv[1:] or [e["id"] for e in reg["sensors"] if e["id"].startswith("9DTact")
                          and e.get("gel_model") and e["id"] != "9DTact_medium_2mm_r1"]
rows = []
for s in sorted(units):
    for f in FACTORS:
        shape.DOWNSCALE = f
        try:
            o, _ = shape.analyse(s)
        except Exception as exc:  # noqa: BLE001
            o = {"sensor": s.replace("9DTact_", ""), "downscale": f, "error": f"{type(exc).__name__}: {exc}"}
        o["downscale"] = f
        o["width_px"], o["height_px"] = int(round(W0 / f)), int(round(H0 / f))
        rows.append(o)
        print(f"  {o['sensor']:16s} x{f:<6.2f} {o['width_px']:4d}x{o['height_px']:<4d} {o.get('px_per_mm', float('nan')):6.2f} px/mm  "
              f"rms {o.get('cyl4_corrected_rms_after_linear', float('nan')):.4f}  "
              f"size {o.get('cyl4_corrected_size_err', float('nan')):+.2f}  "
              f"sq {o.get('cube4_corrected_squareness', float('nan')):.2f}  {o.get('error','')}", flush=True)
D = pd.DataFrame(rows)
D.to_csv(ROOT / "data" / "9DTact" / "shape_vs_resolution.csv", index=False)
print(f"-> {ROOT/'data'/'9DTact'/'shape_vs_resolution.csv'} ({len(D)} rows)")
