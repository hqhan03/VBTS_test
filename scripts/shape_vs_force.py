#!/usr/bin/env python3
"""Do shape reconstruction and force estimation saturate at the same resolution? (9DTact, 17 units)

Joins the per-unit shape-vs-resolution summary (fail_at, bias at 48/32 px, grey
levels used at 48/16 px) and the spatial-resolution test (n_resolved,
dip_175_max, um_per_level) with the per-unit force knees / floors from the
3-seed shear-knee sweep. Spearman with BH over the table; writes
data/20260911_VBTSresolution_dataset/9DTact/shape_vs_force.csv and prints what survives.
"""
import sys, os, numpy as np, pandas as pd
from scipy.stats import spearmanr
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyse_saturation import load, per_unit
from correlations import bh
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__))); D = lambda *p: os.path.join(ROOT, "data", "20260911_VBTSresolution_dataset", "9DTact", *p)
d = load(D("shear_knee_none.csv"))
fz = per_unit(d, "fz")[["unit", "best", "knee", "res_loss"]].rename(columns=lambda c: c if c == "unit" else "fz_" + c)
sh = per_unit(d, "sh")[["unit", "best", "knee", "res_loss"]].rename(columns=lambda c: c if c == "unit" else "sh_" + c)
sv = pd.read_csv(D("shape_vs_resolution_summary.csv")); sv["unit"] = sv.sensor.str.replace("9DTact_", "", regex=False)
cr = pd.read_csv(D("contact_radius.csv")); cr["unit"] = cr.sensor.str.replace("9DTact_", "", regex=False)
m = fz.merge(sh, on="unit").merge(sv.drop(columns=["sensor"]), on="unit", how="left").merge(
    cr[["unit", "n_resolved", "dip_175_max", "um_per_level", "img_slope_lvl_per_mm"]], on="unit", how="left")
m.to_csv(D("shape_vs_force.csv"), index=False)
rows = []
for a in ("bias_48", "bias_32", "lev_48", "lev_16", "n_resolved", "dip_175_max", "um_per_level"):
    for b in ("fz_knee", "sh_knee", "fz_best", "sh_best", "fz_res_loss", "sh_res_loss"):
        s = m[[a, b]].dropna()
        if len(s) >= 8 and s[a].nunique() > 2 and s[b].nunique() > 2:
            r = spearmanr(s[a], s[b]); rows.append(dict(shape=a, force=b, n=len(s), rho=r.statistic, p=r.pvalue))
t = pd.DataFrame(rows); t["q"] = bh(t.p.values); t = t.sort_values("p")
print(f"  {len(t)} tests; q < 0.10: {int((t.q < 0.10).sum())}")
print(t.head(12).to_string(index=False, float_format=lambda v: f"{v:+.3f}"))
t.to_csv(D("shape_vs_force_tests.csv"), index=False)
