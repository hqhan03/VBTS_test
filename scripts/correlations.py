#!/usr/bin/env python3
"""What predicts a unit's force-estimation performance, and its resolution need?

Joins data/derived_variables.csv (one row per unit, every measurable property)
with the performance each unit reached:

  9DTact        Fz / shear best, knee, resolution loss from the 3-seed shear-knee
                sweep (shear_knee_none.csv, block metrics); shape reconstruction
                and spatial-resolution metrics from contact_radius.csv
  DIGIT_Marker, DIGIT   the same force metrics from force_vs_resolution_grey.csv
                (1 seed until the 3-seed pass lands; knee provisional)

Spearman rank correlations, per principle (n = 17-18) and pooled with the
principle noted, Benjamini-Hochberg across the table. Prints the associations
that survive and the ones that do not, and draws a heatmap plus scatter panels
for the strongest. A correlation here is a hypothesis to check against the
physics, not a result -- n is small and everything co-varies with gel spec.
"""
import sys, os, numpy as np, pandas as pd
from scipy.stats import spearmanr
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyse_saturation import load as load_sweep, per_unit

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda *p: os.path.join(ROOT, "data", *p)

DERIVED = ["hertz_k", "hertz_n", "hertz_a_ball8", "d_2N_mm", "a_2N_mm", "mu", "creep_mm_per_cycle",
           "px_per_mm", "tilt_deg", "pedestal_ratio", "img_slope_lvl_per_N", "img_slope_lvl_per_mm",
           "imprint_area_slope_pct_per_N", "img_resp_at_2N", "bw_normal_f90", "bw_shear_f90", "shear_snr",
           "fz_noise_mae", "lat_noise_mae", "fz_rate_per_frame", "lat_rate_per_frame", "fz_sd_0N", "lat_sd_0N",
           "thickness_mm", "hard"]
PERF = ["fz_best", "fz_knee", "fz_res_loss", "sh_best", "sh_knee", "sh_res_loss"]


def perf_from_sweep(path, principle):
    d = load_sweep(path); out = None
    for chan, col in (("fz", "fz"), ("sh", "sh")):
        pu = per_unit(d, col).rename(columns={"best": f"{chan}_best", "knee": f"{chan}_knee", "res_loss": f"{chan}_res_loss",
                                               "n_seeds": f"{chan}_seeds"})[["unit", f"{chan}_best", f"{chan}_knee", f"{chan}_res_loss", f"{chan}_seeds"]]
        out = pu if out is None else out.merge(pu, on="unit", how="outer")
    out["principle"] = principle
    return out


def bh(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p); r = np.empty(n); r[o] = np.arange(1, n + 1)
    q = p * n / r; q_sorted = np.minimum.accumulate(q[o][::-1])[::-1]; out = np.empty(n); out[o] = q_sorted
    return np.minimum(out, 1.0)


def _resid_ranks(s, col, group):
    """Ranks of `col` with the per-group mean rank removed -- a rank-partial
    correlation that controls for principle. Pooling principles otherwise turns
    every DIGIT-vs-9DTact difference (worse floor, brighter pedestal, stiffer
    gels, other bandwidth) into a spurious 'correlation'."""
    r = s[col].rank()
    return r - r.groupby(s[group]).transform("mean")


def table(df, label, min_n=8, partial=None):
    rows = []
    for x in DERIVED:
        for y in PERF:
            cols = [x, y] + ([partial] if partial else [])
            s = df[cols].dropna()
            if len(s) < min_n or s[x].nunique() < 3 or s[y].nunique() < 3: continue
            if partial:
                if s[partial].nunique() < 2: continue
                rx, ry = _resid_ranks(s, x, partial), _resid_ranks(s, y, partial)
                r = spearmanr(rx, ry)
            else:
                r = spearmanr(s[x], s[y])
            rows.append(dict(scope=label, x=x, y=y, n=len(s), rho=r.statistic, p=r.pvalue))
    t = pd.DataFrame(rows)
    if len(t): t["q"] = bh(t.p.values)
    return t


if __name__ == "__main__":
    dv = pd.read_csv(D("derived_variables.csv"))
    perf = []
    if os.path.exists(D("9DTact", "shear_knee_none.csv")): perf.append(perf_from_sweep(D("9DTact", "shear_knee_none.csv"), "9DTact"))
    for pr in ("DIGIT_Marker", "DIGIT"):
        f = D(pr, "force_vs_resolution_grey.csv")
        if os.path.exists(f):
            try: perf.append(perf_from_sweep(f, pr))
            except Exception as e: print(f"  {pr} sweep not usable yet: {e}")
    perf = pd.concat(perf, ignore_index=True) if perf else pd.DataFrame(columns=["unit", "principle"])
    df = dv.merge(perf, on=["unit", "principle"], how="left")
    # 9DTact-only shape / spatial-resolution metrics
    cr = D("9DTact", "contact_radius.csv")
    if os.path.exists(cr):
        c = pd.read_csv(cr); c["unit"] = c.sensor.str.replace("9DTact_", "", regex=False); c["principle"] = "9DTact"
        df = df.merge(c[["unit", "principle", "n_resolved", "dip_175_max", "um_per_level", "cyl4_corrected_rms_after_linear"]], on=["unit", "principle"], how="left")
    df.to_csv(D("derived_with_performance.csv"), index=False)
    print(f"  joined: {len(df)} units; performance available for {df.fz_best.notna().sum()}")
    tabs = ([table(df[df.principle == pr], pr) for pr in df.principle.unique()]
            + [table(df, "pooled"), table(df, "pooled|principle", partial="principle")])
    T = pd.concat([t for t in tabs if len(t)], ignore_index=True)
    T.to_csv(D("correlations.csv"), index=False)
    for scope in T.scope.unique():
        s = T[T.scope == scope].sort_values("p")
        print(f"\n=== {scope}: {len(s)} tests, {int((s.q < 0.10).sum())} with q < 0.10 ===")
        print(s.head(14).to_string(index=False, float_format=lambda v: f"{v:+.3f}" if abs(v) < 10 else f"{v:.0f}"))
    # shape / resolution vs derived, 9DTact only
    n9 = df[df.principle == "9DTact"]
    if "n_resolved" in n9 and n9.n_resolved.notna().sum() > 8:
        print("\n=== 9DTact: shape / spatial-resolution metrics vs derived ===")
        for y in ("n_resolved", "dip_175_max", "um_per_level", "cyl4_corrected_rms_after_linear"):
            best = []
            for x in DERIVED:
                s = n9[[x, y]].dropna()
                if len(s) >= 8 and s[x].nunique() > 2: r = spearmanr(s[x], s[y]); best.append((r.pvalue, x, r.statistic, len(s)))
            best.sort(); print(f"  {y:32s} " + "  ".join(f"{x} rho {rho:+.2f} p {p:.3f}" for p, x, rho, n in best[:3]))
    # figure: heatmap of pooled rho, masked where q >= 0.1
    P = T[T.scope == "pooled|principle"]
    if len(P):
        M = P.pivot(index="x", columns="y", values="rho").reindex(index=DERIVED, columns=PERF)
        Q = P.pivot(index="x", columns="y", values="q").reindex(index=DERIVED, columns=PERF)
        fig, ax = plt.subplots(figsize=(7.5, 9))
        im = ax.imshow(M.values.astype(float), cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
        for i in range(M.shape[0]):
            for j in range(M.shape[1]):
                v = M.values[i, j]; q = Q.values[i, j]
                if np.isfinite(v): ax.text(j, i, f"{v:+.2f}" + ("*" if q < 0.10 else ""), ha="center", va="center", fontsize=8, color="k")
        ax.set_xticks(range(len(PERF))); ax.set_xticklabels(PERF, rotation=45, ha="right"); ax.set_yticks(range(len(DERIVED))); ax.set_yticklabels(DERIVED)
        ax.set_title("Spearman rho, derived unit property x force-estimation performance\n(all principles, rank-partial controlling for principle; * = BH q < 0.10)", fontsize=10)
        fig.colorbar(im, ax=ax, shrink=0.6); fig.tight_layout(); fig.savefig(os.path.join(ROOT, "docs", "figures", "correlations_pooled.png"), dpi=140); plt.close(fig)
        print("  -> docs/figures/correlations_pooled.png")
