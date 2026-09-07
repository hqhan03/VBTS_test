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
# The sizes people use, then halving in exact 16:9 (integer sides at 48x27,
# 32x18, 16x9), ending at 8x5 -- the width-8 size closest to 16:9. 480p and
# 240p are their conventional 854x480 and 426x240 (16:9 to 0.1 %).
SIZES = ((1920, 1080), (1280, 720), (854, 480), (640, 360), (426, 240),
         (320, 180), (160, 90), (80, 45), (48, 27), (32, 18), (16, 9), (8, 5))
reg = yaml.safe_load(open(ROOT / "config" / "sensor_registry.yaml"))
units = sys.argv[1:] or [e["id"] for e in reg["sensors"] if e["id"].startswith("9DTact")
                          and e.get("gel_model") and e["id"] != "9DTact_medium_2mm_r1"]
rows = []
for s in sorted(units):
    for (wpx, hpx) in SIZES:
        shape.set_downscale(wpx, hpx, W0, H0)
        f = shape.DOWNSCALE
        try:
            o, _ = shape.analyse(s)
        except Exception as exc:  # noqa: BLE001
            o = {"sensor": s.replace("9DTact_", ""), "downscale": f, "error": f"{type(exc).__name__}: {exc}"}
        o["downscale"] = f
        o["width_px"], o["height_px"] = wpx, hpx
        rows.append(o)
        print(f"  {o['sensor']:16s} x{f:<6.2f} {o['width_px']:4d}x{o['height_px']:<4d} {o.get('px_per_mm', float('nan')):6.2f} px/mm  "
              f"rms {o.get('cyl4_corrected_rms_after_linear', float('nan')):.4f}  "
              f"size {o.get('cyl4_corrected_size_err', float('nan')):+.2f}  "
              f"sq {o.get('cube4_corrected_squareness', float('nan')):.2f}  {o.get('error','')}", flush=True)
D = pd.DataFrame(rows)
D.to_csv(ROOT / "data" / "9DTact" / "shape_vs_resolution.csv", index=False)
print(f"-> {ROOT/'data'/'9DTact'/'shape_vs_resolution.csv'} ({len(D)} rows)")
