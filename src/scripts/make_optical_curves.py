#!/usr/bin/env python3
"""깊이에 따른 자국 지름과 밝기 — 유닛별 그래프 + 기울기 3x3 표.

지름은 **픽셀**로 둔다. mm 로 바꾸려면 px/mm 이 필요한데 그 값이 유닛마다
최대 1.5 배 어긋나는 것이 2026-09-12 에 확인됐다(digit_shape.py 의 fit_scale).
픽셀은 측정된 그대로다.

자료는 두 종류에서 온다. 둘 다 깊이·자국·밝기를 한 행에 담는다:
  characterize/steps.csv     램프. 깊이 범위가 넓다 (선호)
  shape_<probe>/ladder.csv   형상 사다리. 얕지만 유닛이 다 있다 (대체)
"""
import glob
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import result_common as RC

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
RES = ROOT / "result"
FOLD = {"9DTact": "1_9DTact", "DIGIT": "2_DIGIT", "DIGIT_Marker": "3_DIGIT_Marker"}
HARD = ["soft", "medium", "hard"]
PC = {"ball4": "#c2553a", "ball8": "#1f6f8b"}

# (원리, 프로브) -> 후보 경로. 앞에서부터 있는 것을 쓴다.
SRC = {
    ("9DTact", "ball4"): ["20260911_passC_ceiling/*/characterize/steps.csv",
                          "20260905_passA_ball4/*/shape_ball4/ladder.csv"],
    ("9DTact", "ball8"): ["20260911_passC_ceiling_ball8/*/characterize/steps.csv",
                          "20260907_passB_ball8/*/characterize/steps.csv"],
    ("DIGIT", "ball4"): ["20260910_passA_calibgrid/*/characterize/steps.csv"],
    ("DIGIT", "ball8"): ["20260912_passC_ceiling_ball8/*/characterize/steps.csv"],
    ("DIGIT_Marker", "ball4"): ["20260910_passA_calibgrid/*/characterize/steps.csv"],
    ("DIGIT_Marker", "ball8"): [],          # 램프가 없다 — passB 는 광학 열이 없다
}


import matplotlib.ticker as mticker
SIZES_WH = [(1920, 1080), (1280, 720), (854, 480), (640, 360), (426, 240),
            (320, 180), (160, 90), (80, 45), (48, 27), (32, 18), (16, 9), (8, 5)]
XT = [w for w, _ in SIZES_WH]
XTL = [f"{w}\u00d7{h}" for w, h in SIZES_WH]


def res_axis(ax, yt=None, fs=7):
    """해상도 축을 가로x세로로 적고 보조선을 켠다."""
    ax.set_xticks(XT); ax.set_xticklabels(XTL, fontsize=fs, rotation=90)
    ax.xaxis.set_minor_locator(mticker.NullLocator())
    if yt is not None:
        ax.set_yticks(yt)
        ax.set_yticklabels([f"{v:g}" for v in yt], fontsize=fs + 1)
    ax.yaxis.set_minor_formatter(mticker.NullFormatter())
    ax.grid(True, which="major", axis="both", alpha=.35, lw=.55, color="#b0b0b0")
    ax.set_axisbelow(True)

def plain_log(ax, which="y"):
    """로그 축 눈금을 평범한 숫자로. mathtext 를 쓰지 않게 해 마이너스 깨짐을 없앤다.

    NanumGothic 에 U+2212 글리프가 없어 로그 포매터의 $10^{-1}$ 이 "10<깨짐>1" 로
    나온다. axes.unicode_minus 도 mathtext.fontset 도 이 경로에는 듣지 않았다.
    """
    from matplotlib.ticker import FuncFormatter, NullFormatter
    f = FuncFormatter(lambda v, _: f"{v:g}")
    for a in ([ax.yaxis] if which == "y" else
              [ax.xaxis] if which == "x" else [ax.xaxis, ax.yaxis]):
        a.set_major_formatter(f)
        a.set_minor_formatter(NullFormatter())

def load(pr, probe):
    """(유닛, 깊이, 지름 px, 밝기) 표. 여러 런이 있으면 가장 긴 것."""
    rows = []
    for pat in SRC[(pr, probe)]:
        for f in glob.glob(str(DS / pr / pat)):
            u = Path(f).parents[1].name.replace(pr + "_", "").split("__")[0]
            d = pd.read_csv(f)
            dia = "radius_px"
            lvl = ("img_mean_abs_diff" if "img_mean_abs_diff" in d
                   else "mean_abs_diff_in_region")
            if dia not in d or lvl not in d:
                continue
            rows.append(pd.DataFrame(dict(
                unit=u, probe=probe, source=Path(f).parents[2].name,
                depth_mm=d.depth_mm,
                # 힘은 같은 행에 이미 있다 — 깊이 대신 x 로 쓰면 힘 곡선이 된다
                force_N=d.force_N if "force_N" in d else np.nan,
                diameter_px=2 * d[dia], level=d[lvl])))
    if not rows:
        return pd.DataFrame()
    D = pd.concat(rows)
    # **소스를 하나로 통일한다.** 유닛마다 다른 pass 를 쓰면 깊이 구간이 달라져
    # 기울기가 비교 불가가 된다 — 9DTact ball4 에서 복제 쌍이 119 대 317 로
    # 벌어진 것이 그 때문이었다(8 유닛은 깊은 램프, 9 유닛은 얕은 사다리).
    best = D.groupby("source").unit.nunique().idxmax()
    return RC.mark(D[D.source == best], pr, "unit")


CLIFF = 0.70          # 누적 최대 대비 — 이 밑으로 처음 떨어지는 곳에서 자른다


def valid_span(g):
    """검출이 살아 있는 구간만. 자국이 시야를 채우면 `contact_region` 이 덩어리를
    놓쳐 지름이 0 으로 무너지고, 그 뒤 0 과 수백 사이를 오간다(면적 감시를 떼어낸
    것과 같은 원인, docs/force_ceiling.md 6.5b). 그 구간을 넣고 직선을 맞추면
    복제 쌍 안에서 119 대 317, 심지어 음수 기울기가 나온다.

    **문턱은 재서 골랐다(2026-09-13).** 자국 지름은 깊이에 대해 단조 증가하므로
    누적 최대보다 크게 내려가는 것은 물리가 아니라 검출 실패다. 문턱을 0.30 에서
    0.90 까지 쓸어 보면 **0.60 ~ 0.85 구간에서 잘리는 계열 수가 전혀 변하지
    않는다**(DIGIT 11 계열 66 점, Marker 5 계열 44 점, 9DTact 0). 0.90 에서
    14 계열 118 점으로 급증하는데, 거기서부터는 정당한 자료를 먹는다. 평탄 구간
    가운데인 0.70 을 쓴다.

    처음에 쓴 0.30 은 너무 느슨했다 — 1 mm 유닛 네 개의 낙폭이 누적 최대의
    39 ~ 47 % 여서 통과했고, 그림에 수직 절벽으로 남았다."""
    g = g.sort_values("depth_mm").reset_index(drop=True)
    run = g.diameter_px.cummax()
    bad = (g.diameter_px < CLIFF * run) & (run > 0)
    if bad.any():
        g = g.iloc[:int(bad.idxmax())]
    return g


# 기울기를 맞추는 **공통 깊이 창**. 자료마다 깊이 범위가 다르다 — ball4 사다리는
# 0.07~0.57 mm, 램프는 5 mm 까지 간다. 창을 맞추지 않으면 유닛마다 다른 구간의
# 기울기를 비교하게 되고, 9DTact ball4 의 복제 쌍이 119 대 317 로 벌어진다.
WINDOW = (0.10, 0.50)


def slopes(D, window=WINDOW):
    """유닛·프로브별 기울기 — 지름 px/mm 와 밝기 lvl/mm. 공통 창 안에서만."""
    out = []
    for (u, p), g in D.groupby(["unit", "probe"]):
        g = valid_span(g[g.depth_mm > 0])
        # 창은 각 유닛 자신의 유효 구간이다. 자료마다 깊이 범위가 달라 고정 창을
        # 쓰면 두꺼운 겔이 통째로 빠진다(얕은 깊이에선 자국이 아직 검출되지 않는다).
        # 그래서 구간을 표에 함께 적고, **원리 간 기울기 비교는 하지 않는다.**
        g = g[g.diameter_px > 0]
        if len(g) < 4:
            continue
        sd = np.polyfit(g.depth_mm, g.diameter_px, 1)[0]
        sl = np.polyfit(g.depth_mm, g.level, 1)[0]
        out.append(dict(unit=u, probe=p, hardness=u.split("_")[0],
                        thickness_mm=int(u.split("_")[1][0]), rep=int(u[-1]),
                        n=len(g), depth_lo_mm=g.depth_mm.min(),
                        depth_hi_mm=g.depth_mm.max(),
                        r2=float(np.corrcoef(g.depth_mm, g.diameter_px)[0, 1] ** 2),
                        dia_slope_px_per_mm=sd, level_slope_per_mm=sl))
    return pd.DataFrame(out)


def grid3x3(S, col, fmt="{:.0f}", suspect=None):
    """3x3. 칸 = 'r1 / r2  (평균)'. 의심 유닛이 든 칸에는 `!` 를 붙인다."""
    suspect = suspect or set()
    rows = []
    for h in HARD:
        r = {"hardness": h}
        for t in (1, 2, 3):
            v = S[(S.hardness == h) & (S.thickness_mm == t)].sort_values("rep")[col].dropna()
            if not len(v):
                r[f"{t}mm"] = "—"
            else:
                e = " / ".join(fmt.format(x) for x in v)
                r[f"{t}mm"] = f"{e}  ({fmt.format(v.mean())})" if len(v) > 1 else e
            if any(u.startswith(f"{h}_{t}mm_") for u in suspect):
                r[f"{t}mm"] += " !"
        rows.append(r)
    return pd.DataFrame(rows)


def panel(pr, D):
    """유닛 18 개 격자. 프로브당 선 하나, 지름과 밝기를 두 축에."""
    units = [f"{h}_{t}mm_r{r}" for h in HARD for t in (1, 2, 3) for r in (1, 2)]
    drawn = []          # 그린 숫자를 그대로 csv 로 남긴다
    fig, axes = plt.subplots(3, 6, figsize=(19, 9), sharex=True)
    for ax, u in zip(axes.ravel(), units):
        g = D[D.unit == u]
        if not len(g):
            ax.text(.5, .5, "자료 없음", ha="center", va="center", fontsize=8,
                    color="#999", transform=ax.transAxes)
            ax.text(.5, .38, RC.reason(pr, u) or "", ha="center", va="center",
                    fontsize=7.5, color="#c07a50", transform=ax.transAxes)
            ax.set_title(u, fontsize=8, color="#999"); ax.set_xticks([]); ax.set_yticks([])
            continue
        a2 = ax.twinx()
        for p, gg in g.groupby("probe"):
            # 기울기와 같은 자를 쓴다. valid_span 이 slopes() 에만 걸려 있어
            # 표는 잘라 쓰고 그림은 검출이 무너진 뒤의 절벽까지 그리고 있었다.
            gg = valid_span(gg[gg.depth_mm > 0])
            gg = gg[gg.diameter_px > 0].sort_values("depth_mm")
            if len(gg) < 2:
                continue
            ls, lw = RC.style(pr, u, "-o")
            ax.plot(gg.depth_mm, gg.diameter_px, ls, c=PC[p], lw=lw, ms=3.6,
                    mec="white", mew=.6, label=p, zorder=3)
            a2.plot(gg.depth_mm, gg.level, "--s", c=PC[p], lw=1.1, ms=2.8,
                    alpha=.65, mec="white", mew=.4)
            drawn.append(gg[["unit", "probe", "depth_mm", "diameter_px",
                             "level"]].assign(
                                 suspect_hardware=RC.is_suspect(pr, u)))
        tt, tc = RC.title(pr, u)
        ax.set_title(tt, fontsize=8.5 if tc == "black" else 7.2, color=tc)
        ax.tick_params(labelsize=7); a2.tick_params(labelsize=6, colors="#777")
        ax.spines[["top"]].set_visible(False); a2.spines[["top"]].set_visible(False)
        # 보조선: 눈금마다 가로·세로 모두
        ax.grid(True, which="major", axis="both", alpha=.35, lw=.5,
                color="#b0b0b0")
        ax.set_axisbelow(True)
    for ax in axes[-1]:
        ax.set_xlabel("깊이 (mm)", fontsize=8)
    for ax in axes[:, 0]:
        ax.set_ylabel("자국 지름 (px)", fontsize=8)
    h, l = axes[0, 0].get_legend_handles_labels()
    fig.legend(h, l, loc="upper right", frameon=False, fontsize=9, ncol=2)
    fig.suptitle(f"{pr} — 깊이에 따른 자국 지름(실선, 왼쪽 축)과 밝기 변화"
                 f"(점선, 오른쪽 축)", fontsize=12, x=.09, ha="left")
    fig.tight_layout(rect=[0, 0, 1, .96])
    d = RES / FOLD[pr]
    (d / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(d / "figures" / "optical_vs_depth_18units.png", dpi=150,
                bbox_inches="tight")
    plt.close(fig)
    (d / "data").mkdir(parents=True, exist_ok=True)
    (pd.concat(drawn) if drawn else pd.DataFrame()).to_csv(
        d / "data" / "optical_vs_depth_18units.csv", index=False)


# **순서가 있는 변수지만 한 색의 농담을 쓰지 않는다.** 유닛별 곡선을 흐리게 깔면
# 같은 계통의 세 농담이 서로 묻혀 어느 군인지 못 가린다. 뚜렷이 갈리는 세 색을 쓰고,
# 순서는 범례의 차례가 진다. Okabe-Ito 계열이라 색각 이상에서도 갈린다 — 인접 쌍
# 최악 ΔE 11.0 (deutan), 보통 시야 25.8, 바탕 대비 전부 3:1 이상.
from palette import HARD3 as CH_G, THICK3 as CT_G


def group_curves(pr, D, probe, xcol="depth_mm", xlab="깊이 (mm)",
                 stem="optical_by_group"):
    """두께·경도별로 곡선을 겹쳐 본다 — 유닛 18 칸으로는 비교가 안 되기 때문이다.

    18 유닛 격자는 유닛 하나하나를 보여주지만, **어느 두께가 더 가파른가** 같은
    질문에는 답하지 못한다. 칸이 달라 눈이 기울기를 나란히 놓지 못한다. 그래서
    같은 축 위에 겹친다.

    **깊이 격자를 맞춘다.** 유닛마다 사다리가 닿은 깊이가 다르므로(얇은 겔은 얕게
    끝난다) 공통 격자에 보간한 뒤 **그 깊이에 자료가 있는 유닛이 3 개 이상일 때만**
    그린다. 띠는 사분위 범위이고, 선은 중앙값이다 — 평균은 한 유닛에 끌려간다.
    """
    G = D[D.probe == probe].copy()
    if not len(G):
        return None
    # `load()` 는 유닛 이름만 싣는다 — 여기서 경도와 두께를 풀어 쓴다
    G["hardness"] = G.unit.str.split("_").str[0]
    G["thickness_mm"] = G.unit.str.extract(r"_(\d)mm_")[0].astype(int)
    G = G[G[xcol].notna()]
    if not len(G):
        return None
    lo = float(G[xcol][G[xcol] > 0].min())
    hi = float(G.groupby("unit")[xcol].max().quantile(.8))
    if not np.isfinite(hi) or hi <= lo:
        return None
    grid = np.linspace(lo, hi, 40)

    def curves(key, col):
        out = {}
        for k, g in G.groupby(key):
            ys = []
            for _, gg in g.groupby("unit"):
                gg = valid_span(gg[gg.depth_mm > 0])
                gg = gg[(gg.diameter_px > 0) & gg[xcol].notna()].sort_values(xcol)
                if len(gg) < 4:
                    continue
                y = np.interp(grid, gg[xcol], gg[col],
                              left=np.nan, right=np.nan)
                y[(grid < gg[xcol].min()) | (grid > gg[xcol].max())] = np.nan
                ys.append(y)
            if len(ys) < 2:
                continue
            A = np.vstack(ys)
            n = np.sum(~np.isnan(A), axis=0)
            with np.errstate(all="ignore"):
                med = np.nanmedian(A, axis=0)
                q1 = np.nanpercentile(A, 25, axis=0)
                q3 = np.nanpercentile(A, 75, axis=0)
            m = n >= 3
            # 유닛별 곡선도 함께 돌려준다 — 중앙값과 띠만 보면 **그 띠를 몇 개가**
            # **만들었는지**, 한 유닛이 튀어서 생긴 폭인지가 보이지 않는다.
            out[k] = (grid[m], med[m], q1[m], q3[m], int(A.shape[0]), A)
        return out

    fig, axes = plt.subplots(2, 2, figsize=(10.4, 7.4), sharex=True)
    rows = [("diameter_px", "자국 지름 (px)"), ("level", "밝기 변화 (lvl)")]
    cols = [("hardness", "경도별", CH_G, ["soft", "medium", "hard"]),
            ("thickness_mm", "두께별", CT_G, [1, 2, 3])]
    tidy = []
    for i, (col, ylab) in enumerate(rows):
        for j, (key, title, cmap, order) in enumerate(cols):
            ax = axes[i, j]
            cv = curves(key, col)
            for k in order:
                if k not in cv:
                    continue
                x, med, q1, q3, n, A = cv[k]
                lab = f"{k} mm" if key == "thickness_mm" else str(k)
                # 유닛 하나하나를 흐리게 뒤에 깐다
                for row in A:
                    ax.plot(grid, row, "-", c=cmap[k], lw=.7, alpha=.22,
                            zorder=1)
                ax.fill_between(x, q1, q3, color=cmap[k], alpha=.12, lw=0,
                                zorder=2)
                # 중앙값 선에 흰 테두리를 둘러 세 색이 겹쳐도 서로 끊겨 보이게 한다
                ax.plot(x, med, "-", c="white", lw=4.0, alpha=.85, zorder=3)
                ax.plot(x, med, "-", c=cmap[k], lw=2.4, label=f"{lab}  (n={n})",
                        zorder=4)
                tidy.append(pd.DataFrame(dict(
                    principle=pr, probe=probe, measure=col, group_by=key,
                    group=str(k), n_units=n, x_name=xcol, x=x,
                    median=med, q1=q1, q3=q3)))
            ax.set_ylabel(ylab, fontsize=9)
            ax.set_title(title, fontsize=10, loc="left")
            ax.legend(frameon=False, fontsize=8.5)
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(True, which="major", alpha=.3, lw=.5, color="#b0b0b0")
            ax.set_axisbelow(True)
            if i == 1:
                ax.set_xlabel(xlab)
    fig.suptitle(f"{pr} — 같은 축 위에 겹친 곡선, x = {xlab} ({probe}). "
                 f"굵은 선은 중앙값, "
                 "띠는 사분위 범위, 가는 선은 유닛 하나하나",
                 fontsize=11.5, x=.04, ha="left")
    fig.tight_layout(rect=[0, 0, 1, .955])
    d = RES / FOLD[pr]
    (d / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(d / "figures" / f"{stem}_{probe}.png", dpi=180,
                bbox_inches="tight")
    plt.close(fig)
    if tidy:
        T = pd.concat(tidy)
        T.to_csv(d / "data" / f"{stem}_{probe}.csv", index=False)
        # **어느 쪽이 더 크게 가르나.** 눈으로 "갈린다" 고 말하면 곡선이 서로 다른
        # 깊이에서 끝나는 것에 속는다. 세 군이 모두 자료를 가진 가장 깊은 깊이
        # 하나를 잡고 거기서의 폭을 잰다 — 그래야 같은 조건에서 견준다.
        rows = []
        for (meas, key), g in T.groupby(["measure", "group_by"]):
            piv = g.pivot_table(index="x", columns="group",
                                values="median").dropna()
            if not len(piv):
                continue
            at = piv.index[-1]; v = piv.loc[at]
            gg = g[g.x == at]
            between = float(v.max() - v.min())
            within = float((gg.q3 - gg.q1).median())
            rows.append(dict(principle=pr, probe=probe, measure=meas,
                             group_by=key, x=xcol, at_x=at,
                             between=between, within_iqr=within,
                             # **이것이 판정이다.** 군 사이 차이가 군 안의 산포보다
                             # 큰가. 1 보다 작으면 그 군들은 자기 흩어짐 안에 있다.
                             ratio=between / within if within else float("nan"),
                             **{f"g_{k}": float(v[k]) for k in v.index},
                             spread_pct=float((v.max() - v.min())
                                              / v.median() * 100),
                             monotone=bool(
                                 list(v[sorted(v.index)]) ==
                                 sorted(v[sorted(v.index)], reverse=True)
                                 or list(v[sorted(v.index)]) ==
                                 sorted(v[sorted(v.index)]))))
        if rows:
            pd.DataFrame(rows).to_csv(
                d / "data" / f"{stem.replace('by_group', 'group_spread')}"
                f"_{probe}.csv", index=False)
    print(f"    -> {FOLD[pr]}/figures/{stem}_{probe}.png")
    return True


def reversal(pr, D, probe):
    """x 축을 깊이에서 힘으로 바꾸면 **어느 변수가 갈리는지가 바뀐다** — 한 장에.

    행은 잰 것(지름·밝기), 열은 (x 축) x (나눈 변수) 넷이다. 왼쪽 두 열이 깊이,
    오른쪽 두 열이 힘이고, 각 쌍의 앞이 경도별 뒤가 두께별이다. 같은 자국, 같은
    램프, 바뀐 것은 x 축뿐이므로 **열을 가로질러 읽으면 뒤집힘이 보인다.**
    """
    G = D[D.probe == probe].copy()
    if not len(G) or "force_N" not in G:
        return None
    G["hardness"] = G.unit.str.split("_").str[0]
    G["thickness_mm"] = G.unit.str.extract(r"_(\d)mm_")[0].astype(int)

    tidy = []

    def band(xcol, key, col, order, cmap, ax):
        g = G[G[xcol].notna()]
        lo = float(g[xcol][g[xcol] > 0].min())
        hi = float(g.groupby("unit")[xcol].max().quantile(.8))
        if not np.isfinite(hi) or hi <= lo:
            return
        grid = np.linspace(lo, hi, 40)
        for k in order:
            gg0 = g[g[key] == k]
            ys = []
            for _, u in gg0.groupby("unit"):
                u = valid_span(u[u.depth_mm > 0])
                u = u[(u.diameter_px > 0) & u[xcol].notna()].sort_values(xcol)
                if len(u) < 4:
                    continue
                y = np.interp(grid, u[xcol], u[col], left=np.nan, right=np.nan)
                y[(grid < u[xcol].min()) | (grid > u[xcol].max())] = np.nan
                ys.append(y)
            if len(ys) < 2:
                continue
            A = np.vstack(ys)
            n = np.sum(~np.isnan(A), axis=0)
            with np.errstate(all="ignore"):
                med, q1, q3 = (np.nanmedian(A, 0), np.nanpercentile(A, 25, 0),
                               np.nanpercentile(A, 75, 0))
            m = n >= 3
            for row in A:
                ax.plot(grid, row, "-", c=cmap[k], lw=.6, alpha=.18, zorder=1)
            ax.fill_between(grid[m], q1[m], q3[m], color=cmap[k], alpha=.13,
                            lw=0, zorder=2)
            lab = f"{k} mm" if key == "thickness_mm" else str(k)
            ax.plot(grid[m], med[m], "-", c="white", lw=3.6, alpha=.85, zorder=3)
            ax.plot(grid[m], med[m], "-", c=cmap[k], lw=2.2, label=lab, zorder=4)
            tidy.append(pd.DataFrame(dict(
                principle=pr, probe=probe, measure=col, x_name=xcol,
                group_by=key, group=str(k), n_units=int(A.shape[0]),
                x=grid[m], median=med[m], q1=q1[m], q3=q3[m])))

    COLS = [("depth_mm", "hardness", "깊이 × 경도", ["soft", "medium", "hard"], CH_G),
            ("depth_mm", "thickness_mm", "깊이 × 두께", [1, 2, 3], CT_G),
            ("force_N", "hardness", "힘 × 경도", ["soft", "medium", "hard"], CH_G),
            ("force_N", "thickness_mm", "힘 × 두께", [1, 2, 3], CT_G)]
    ROWS = [("diameter_px", "자국 지름 (px)"), ("level", "밝기 변화 (lvl)")]
    fig, axes = plt.subplots(2, 4, figsize=(16.4, 7.2))
    for i, (col, ylab) in enumerate(ROWS):
        for j, (xcol, key, title, order, cmap) in enumerate(COLS):
            ax = axes[i, j]
            band(xcol, key, col, order, cmap, ax)
            ax.set_title(title, fontsize=10.5, loc="left")
            ax.set_xlabel("깊이 (mm)" if xcol == "depth_mm" else "힘 (N)",
                          fontsize=9)
            if j == 0:
                ax.set_ylabel(ylab, fontsize=9.5)
            ax.legend(frameon=False, fontsize=8)
            ax.spines[["top", "right"]].set_visible(False)
            ax.grid(True, which="major", alpha=.28, lw=.5, color="#b0b0b0")
            ax.set_axisbelow(True)
        # 행 안에서 y 축을 맞춘다 — 열을 가로질러 읽어야 하기 때문이다
        lo = min(a.get_ylim()[0] for a in axes[i])
        hi = max(a.get_ylim()[1] for a in axes[i])
        for a in axes[i]:
            a.set_ylim(lo, hi)
    fig.suptitle(f"{pr} ({probe}) — x 축을 바꾸면 갈리는 변수가 바뀐다. "
                 "왼쪽 두 열은 깊이, 오른쪽 두 열은 힘",
                 fontsize=12, x=.03, ha="left")
    fig.tight_layout(rect=[0, 0, 1, .955])
    d = RES / "extra"
    (d / "figures").mkdir(parents=True, exist_ok=True)
    fig.savefig(d / "figures" / f"H_reversal_{pr}_{probe}.png", dpi=170,
                bbox_inches="tight")
    plt.close(fig)
    (d / "data").mkdir(parents=True, exist_ok=True)
    if tidy:
        pd.concat(tidy).to_csv(
            d / "data" / f"H_reversal_{pr}_{probe}.csv", index=False)
    print(f"    -> extra/figures/H_reversal_{pr}_{probe}.png")
    return True


def main():
    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    # NanumGothic 에 유니코드 마이너스(U+2212) 글리프가 없어 축 라벨이
    # "6 x 10<깨짐>2" 로 나온다. ASCII 하이픈을 쓰게 한다.
    plt.rcParams["axes.unicode_minus"] = False
    # 로그 축 라벨은 mathtext 로 그려지고 그것도 NanumGothic 을 따라가
    # "10<깨짐>1" 이 된다. mathtext 에는 완전한 폰트를 따로 준다.
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
        D = pd.concat([load(pr, p) for p in ("ball4", "ball8")], ignore_index=True)
        d = RES / FOLD[pr] / "data"
        d.mkdir(parents=True, exist_ok=True)
        if not len(D):
            print(f"  {pr}: 광학 자료 없음"); continue
        D.to_csv(d / "optical_vs_depth.csv", index=False)
        S = slopes(D)
        S.to_csv(d / "optical_slopes.csv", index=False)
        for p in S.probe.unique():
            g = S[S.probe == p]
            grid3x3(g, "dia_slope_px_per_mm", suspect=RC.suspect(pr)).to_csv(
                d / f"optical_slope_diameter_{p}_3x3.csv", index=False)
            grid3x3(g, "level_slope_per_mm", "{:.1f}",
                    suspect=RC.suspect(pr)).to_csv(
                d / f"optical_slope_level_{p}_3x3.csv", index=False)
        panel(pr, D)
        for probe in sorted(D.probe.unique()):
            group_curves(pr, D, probe)
            group_curves(pr, D, probe, xcol="force_N", xlab="힘 (N)",
                         stem="force_by_group")
        if pr == "9DTact" and "ball8" in set(D.probe):
            reversal(pr, D, "ball8")
        got = ", ".join(f"{p} {S[S.probe==p].unit.nunique()}유닛"
                        for p in sorted(S.probe.unique()))
        print(f"  {pr:<13} {len(D):>6} 행  ({got})")
        for p in sorted(S.probe.unique()):
            print(f"     지름 기울기 {p} (px/mm):")
            print(grid3x3(S[S.probe == p], "dia_slope_px_per_mm",
                          suspect=RC.suspect(pr)).to_string(index=False))


if __name__ == "__main__":
    main()
