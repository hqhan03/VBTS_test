#!/usr/bin/env python3
"""합력 오차 — 세 축을 하나로 합친 힘 오차가 해상도에 어떻게 달리는가.

**왜 따로 필요한가** (2026-09-14, 운전자 요청). 지금까지의 그림은 축별 MAE 다.
그런데 센서를 쓰는 쪽이 아는 것은 축이 아니라 **힘 벡터 하나**다 — "이 손가락이
힘을 몇 N 틀리게 읽는가" 는 ‖F_pred − F_true‖ 의 크기다.

**정확한 값은 이 자료로 낼 수 없다.** 그 양은 프레임마다 세 오차를 함께 봐야
나오는데, 스윕은 축별 MAE 만 내보내고 프레임별 예측을 버린다(가중치도 디스크에
없다). 그래서 **엄밀한 상·하한**을 친다. L2 노름은 볼록하므로 옌센 부등식으로

    √(MAEx² + MAEy² + MAEz²)  ≤  E‖ΔF‖  ≤  MAEx + MAEy + MAEz

왼쪽은 세 축 오차가 프레임마다 **함께 커질 때** 같아지고(우리 경우에 가깝다 —
깊이 압입이 세 축을 동시에 흔든다), 오른쪽은 한 축씩 번갈아 틀릴 때만 닿는다.
그러므로 **하한을 인용하고 상한은 띠로만 보인다.** 띠는 불확실성이 아니라
부등식의 폭이다 — 캡션에 그렇게 적는다.

정확한 값을 원하면 `force_vs_resolution.py` 가 이제 내보내는 `res_mae` 열을
쓰면 된다. 단 전 사다리 재학습이 필요하다(약 21 GPU·시간).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

import pixel_density as PD
import result_common as RC
from palette import PRINCIPLE

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
RES = ROOT / "result" / "single" if RC.SINGLE else ROOT / "result"
PRS = [("9DTact", "Depth-referenced (9DTact)"),
       ("DIGIT", "Photometric (DIGIT)"),
       ("DIGIT_Marker", "Photometric + marker")]
AX = ["fx_mae", "fy_mae", "fz_mae"]
XT = [0.1, 1, 10, 100, 1000, 10000]
XTL = ["0.1", "1", "10", "100", "1000", "10⁴"]


def load_exact(pr):
    """재학습이 낸 **실측** 합력 (`res_mae`). 없으면 None.

    2026-09-15 에 선택 27 유닛을 다시 학습해 얻었다. 하한은 그대로 두고 이것을
    덧그린다 — 어느 쪽도 지우지 않는다. **`axes_source` 가 고른 같은 파일**을
    읽으므로 파선(하한)과 실선(실측)이 같은 학습 판이다.
    """
    f = axes_source(pr)
    if not f.exists():
        return None
    d = RC.keep(pd.read_csv(f), pr, "sensor")
    if "res_mae" not in d:
        return None
    return d.groupby(["sensor", "width_px"]).res_mae.median().reset_index()


def axes_source(pr):
    """축별 MAE 를 어느 학습 판에서 읽을지.

    **하한과 실측은 같은 판에서 와야 한다.** 옌센 부등식은 *그 프레임들의* 축별
    오차와 *그 프레임들의* 합력 사이에 성립한다. 2026-09-15 까지 이 그림은
    하한을 판 A(`_axes.csv`)에서, 실측을 판 B(`_res.csv`)에서 읽고 있었다 —
    두 판은 학습 확률성만 다른 별개의 학습이라 파선이 실선의 하한이라는 보장이
    없었다. 판 B 에 fx/fy/fz 가 다 있으므로 그쪽을 먼저 쓴다.
    """
    res = DS / pr / "force_vs_resolution_res.csv"
    if res.exists():
        d = pd.read_csv(res)
        if {"fx_mae", "fy_mae", "fz_mae", "res_mae"} <= set(d.columns):
            return res
    return DS / pr / "force_vs_resolution_axes.csv"


def load(pr):
    f = axes_source(pr)
    if not f.exists():
        return None
    d = RC.keep(pd.read_csv(f), pr, "sensor")
    # seed 중앙값을 먼저, 그다음 유닛을 가로질러 — 5 절과 같은 집계 순서다.
    k = d.groupby(["sensor", "width_px"])[AX].median()
    k["lo"] = np.sqrt((k[AX] ** 2).sum(axis=1))
    k["hi"] = k[AX].sum(axis=1)
    # Fz 가 제곱합에서 차지하는 몫 — 합력이 무엇에 끌려가는지
    k["fz_share"] = k.fz_mae ** 2 / (k[AX] ** 2).sum(axis=1)
    return k.reset_index()


def sat(v, tol=1.10):
    """포화 해상도 — 최솟값의 110 % 안에 드는 가장 낮은 폭."""
    v = v.dropna()
    return int(v.index[v <= v.min() * tol].min()) if len(v) >= 4 else np.nan


def main():
    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    plt.rcParams["axes.unicode_minus"] = False
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    fig, axes = plt.subplots(1, 2, figsize=(9.6, 3.9))
    rows, summ, summ_ex = [], [], {}

    for pr, nice in PRS:
        k = load(pr)
        if k is None or not len(k):
            continue
        units = sorted(k.sensor.unique())
        m = k.groupby("width_px")[["lo", "hi", "fz_share"] + AX].median()
        R = pd.Series({w: np.median([PD.density(pr, u, w) for u in units])
                       for w in m.index})
        c = PRINCIPLE[pr]
        ax = axes[0]
        ax.fill_between(R[m.index], m.lo, m.hi, color=c, alpha=.14, lw=0)
        ax.plot(R[m.index], m.lo, "--", c=c, lw=1.2, alpha=.8)
        ax.plot(R[m.index], m.hi, "-", c=c, lw=.8, alpha=.55)
        ex = load_exact(pr)
        if ex is not None and len(ex):
            em = ex.groupby("width_px").res_mae.median()
            ax.plot(R[em.index], em.values, "-o", c=c, lw=2.2, ms=4.5,
                    mec="white", mew=.6, label=f"{nice} (실측)")
            summ_ex[pr] = em
        else:
            ax.plot(R[m.index], m.lo, "-o", c=c, lw=2.0, ms=4, mec="white",
                    mew=.6, label=f"{nice} (하한)")
        axes[1].plot(R[m.index], m.fz_share * 100, "-o", c=c, lw=1.8, ms=4,
                     mec="white", mew=.6, label=nice)

        s_lo, s_fz = sat(m.lo), sat(m.fz_mae)
        summ.append(dict(principle=pr, n_units=len(units),
                         best_lo_N=round(float(m.lo.min()), 4),
                         best_at_px=int(m.lo.idxmin()),
                         sat_px=s_lo, sat_R=round(float(R[s_lo]), 2),
                         fz_sat_px=s_fz, fz_sat_R=round(float(R[s_fz]), 2),
                         fz_share_median=round(float(m.fz_share.median()), 3),
                         band_ratio=round(float((m.hi / m.lo).median()), 3)))
        m2 = m.copy()
        if pr in summ_ex:
            m2["res_mae_exact"] = summ_ex[pr].reindex(m2.index)
            x = m2.dropna(subset=["res_mae_exact"])
            summ[-1]["exact_best_N"] = round(float(x.res_mae_exact.min()), 4)
            summ[-1]["bound_over_exact"] = round(
                float((x.lo / x.res_mae_exact).median()), 3)
        rows.append(m2.assign(principle=pr,
                              density_px_per_mm2=R[m2.index].values).reset_index())

    for ax, yl, ttl in ((axes[0], "합력 오차 ‖ΔF‖ (N)",
                         "(a) 세 축을 합친 힘 오차 — 굵은 선이 실측, 점선이 하한, 띠가 부등식의 폭"),
                        (axes[1], "Fz 가 차지하는 몫 (%)",
                         "(b) 합력은 무엇에 끌려가나 — 제곱합에서 Fz 의 비중")):
        ax.set_xscale("log")
        ax.set_xticks(XT); ax.set_xticklabels(XTL, fontsize=8)
        ax.xaxis.set_minor_locator(mticker.NullLocator())
        ax.set_xlabel("화소 밀도 R (px/mm²)", fontsize=9)
        ax.set_ylabel(yl, fontsize=9)
        ax.set_title(ttl, fontsize=9.5, loc="left")
        ax.tick_params(labelsize=8)
        ax.grid(alpha=.3, lw=.5, which="major"); ax.set_axisbelow(True)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_yscale("log")
    axes[0].set_yticks([.05, .1, .2, .3])
    axes[0].set_yticklabels(["0.05", "0.1", "0.2", "0.3"], fontsize=8)
    axes[0].yaxis.set_minor_locator(mticker.NullLocator())
    axes[0].legend(frameon=False, fontsize=7.5, loc="upper left")
    axes[1].set_ylim(0, 100)
    axes[1].axhline(100 / 3, c="#1a1a1a", ls=":", lw=1.0)
    axes[1].annotate("세 축이 같을 때 33 %", (.12, 100 / 3), fontsize=7,
                     va="bottom", color="#1a1a1a")

    fig.tight_layout()
    fd = RES / "extra" / "figures"; dd = RES / "extra" / "data"
    fd.mkdir(parents=True, exist_ok=True); dd.mkdir(parents=True, exist_ok=True)
    fig.savefig(fd / "I_resultant_force.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    pd.concat(rows).to_csv(dd / "I_resultant_force.csv", index=False)
    S = pd.DataFrame(summ)
    S.to_csv(dd / "I_resultant_force_summary.csv", index=False)
    print(S.to_string(index=False))
    print(f"\n  -> {fd / 'I_resultant_force.png'}")


if __name__ == "__main__":
    main()
