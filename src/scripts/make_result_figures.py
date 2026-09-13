#!/usr/bin/env python3
"""result/ 의 그림과 표 — 그림마다 그것을 그린 CSV 를 짝으로 남긴다.

운전자가 직접 다시 그릴 수 있어야 하므로, 어떤 그림도 CSV 없이 저장하지 않는다.
숫자는 전부 등록부와 steps.csv 에서 나오고 로봇은 쓰지 않는다.
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import result_common as RC
import yaml

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "result"
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
REG = yaml.safe_load(open(ROOT / "src" / "config" / "sensor_registry.yaml"))

# 원리별 색. 같은 원리는 어느 그림에서나 같은 색을 쓴다.
C = {"9DTact": "#1f6f8b", "DIGIT": "#c2553a", "DIGIT_Marker": "#6a8e3b"}
# 경도는 밝기로. 순서가 있는 변수이므로 한 색의 농담이 맞다.
CH = {"soft": "#9ec5d8", "medium": "#4a8fa8", "hard": "#134b5f"}
TAG = {"9DTact": "20260911_passC_ceiling_ball8",
       "DIGIT": "20260912_passC_ceiling_ball8"}


def style(ax):
    ax.spines[["top", "right"]].set_visible(False)
    ax.grid(alpha=.25, lw=.6)
    ax.set_axisbelow(True)


def save(fig, df, stem, folder="extra"):
    d = RES / folder
    (d / "figures").mkdir(parents=True, exist_ok=True)
    (d / "data").mkdir(parents=True, exist_ok=True)
    fig.savefig(d / "figures" / f"{stem}.png", dpi=200, bbox_inches="tight")
    plt.close(fig)
    df.to_csv(d / "data" / f"{stem}.csv", index=False)
    print(f"  -> {folder}/figures/{stem}.png  +  {folder}/data/{stem}.csv  ({len(df)} 행)")


def ceilings():
    """잰 천장. 9DTact·DIGIT 은 `ball8`, DIGIT_Marker 는 `ball4` 다.

    **프로브가 다르므로 Marker 의 값을 나머지 둘과 나란히 읽으면 안 된다**
    (`force_ceiling.md` §6.7: 힘은 프로브 사이에서 환산되지 않는다 — 비 1.50~3.26,
    CV 21 %). 그래도 싣는 것은 **두께·경도에 대한 방향**은 한 원리 안에서 읽히기
    때문이다. 열 `probe` 에 어느 자로 쟀는지 적어 둔다.
    """
    rows = []
    for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
        tag = TAG.get(pr)
        for s in REG["sensors"]:
            if s.get("principle") != pr:
                continue
            ir = s.get("image_response") or {}
            run = s.get("run") or ""
            if not ir.get("reached"):
                continue
            if tag:
                if tag not in run:
                    continue
                probe = "ball8"
            else:                       # Marker 는 ball8 램프가 없다
                if "calibgrid" not in run:
                    continue
                probe = "ball4"
            rows.append(dict(principle=pr, probe=probe,
                             unit=s["id"].replace(pr + "_", ""),
                             hardness=s["hardness"], thickness_mm=s["thickness_mm"],
                             ceiling_N=ir["max_measurable_force_N"],
                             depth_mm=ir["max_measurable_depth_mm"],
                             peak_lvl_per_N=ir["peak_slope_levels_per_N"],
                             suspect_hardware=bool(s.get("suspect_hardware"))))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------- A --
def fig_A(D):
    """포화 깊이 대 두께. 두 원리가 반대로 가는 것이 이 캠페인의 주 결과다."""
    fig, ax = plt.subplots(figsize=(5.2, 3.8))
    out = []
    for pr, g in D.groupby("principle"):
        j = (np.random.default_rng(0).random(len(g)) - .5) * .12
        ok = ~g.suspect_hardware.values
        ax.scatter(g.thickness_mm.values[ok] + j[ok], g.depth_mm.values[ok],
                   s=34, c=C[pr], alpha=.75, edgecolor="white", lw=.6,
                   label=pr, zorder=3)
        if (~ok).any():
            ax.scatter(g.thickness_mm.values[~ok] + j[~ok],
                       g.depth_mm.values[~ok], s=52, facecolor="none",
                       edgecolor="#c2553a", lw=1.5, zorder=5)
        m, b = np.polyfit(g.thickness_mm, g.depth_mm, 1)
        xs = np.linspace(.8, 3.2, 20)
        ax.plot(xs, m * xs + b, c=C[pr], lw=1.8, alpha=.9, zorder=2)
        r = np.corrcoef(g.thickness_mm, g.depth_mm)[0, 1] ** 2
        ax.annotate(f"{m:+.2f} mm/mm   R²={r:.2f}", (3.2, m * 3.2 + b),
                    color=C[pr], fontsize=8.5, ha="right",
                    xytext=(0, 11 if pr == "9DTact" else -16),
                    textcoords="offset points",
                    bbox=dict(fc="white", ec="none", alpha=.85, pad=1.4))
        out.append(g.assign(fit_slope=m, fit_intercept=b, fit_r2=r))
    ax.set_xticks([1, 2, 3]); ax.set_xlabel("겔 두께 (mm)")
    ax.set_ylabel("포화 깊이 (mm)")
    ax.set_title("포화가 일어나는 깊이는 두께를 따라간다", fontsize=10.5, loc="left")
    ax.legend(frameon=False, fontsize=8.5); style(ax)
    save(fig, pd.concat(out), "A_saturation_depth_vs_thickness")


# ------------------------------------------------------------------- B --
def fig_B(D):
    """천장 대 두께, 경도별. 선은 복제 평균, 점은 **유닛 하나하나**다.

    평균만 그리면 두 복제가 얼마나 벌어져 있는지 보이지 않는다. 두 점을 다 찍고
    선으로 잇는다. 세로 막대는 두 복제의 폭이다.
    """
    prs = [p for p in ("9DTact", "DIGIT", "DIGIT_Marker") if (D.principle == p).any()]
    # **y 축을 공유하지 않는다.** 9DTact 가 63 N 까지 가는데 DIGIT 계열은 6~23 N 이라,
    # 축을 묶으면 DIGIT 과 Marker 의 기울기가 아래쪽에 눌려 보이지 않는다. 축이 다르다는
    # 것은 제목과 그림 제목에 적고, 어차피 Marker 는 프로브가 달라 세로로 비교하면
    # 안 되는 값이다(force_ceiling.md 6.7).
    fig, axes = plt.subplots(1, len(prs), figsize=(4.4 * len(prs), 3.9),
                             sharey=False, squeeze=False)
    axes = axes[0]
    rng = np.random.default_rng(0)
    for ax, pr in zip(axes, prs):
        g = D[D.principle == pr]
        for h in ("soft", "medium", "hard"):
            gg = g[g.hardness == h]
            if not len(gg):
                continue
            k = gg.groupby("thickness_mm").ceiling_N.agg(["mean", "min", "max"])
            ax.plot(k.index, k["mean"], "-", c=CH[h], label=h, lw=1.8, zorder=3)
            ax.vlines(k.index, k["min"], k["max"], color=CH[h], lw=1.0,
                      alpha=.55, zorder=2)
            # 유닛 하나하나. 겹치지 않게 아주 조금만 흔든다
            j = (rng.random(len(gg)) - .5) * .14
            ok = ~gg.suspect_hardware.values
            ax.scatter(gg.thickness_mm.values[ok] + j[ok],
                       gg.ceiling_N.values[ok], s=26, c=CH[h],
                       edgecolor="white", lw=.6, zorder=4)
            # 의심 유닛은 속을 비우고 테두리만
            if (~ok).any():
                ax.scatter(gg.thickness_mm.values[~ok] + j[~ok],
                           gg.ceiling_N.values[~ok], s=46, facecolor="none",
                           edgecolor="#c2553a", lw=1.5, marker="o", zorder=5)
                for x, y in zip(gg.thickness_mm.values[~ok] + j[~ok],
                                gg.ceiling_N.values[~ok]):
                    ax.annotate(RC.MARK, (x, y), fontsize=7, color="#c2553a",
                                xytext=(5, 4), textcoords="offset points", zorder=6)
        pb = g.probe.iloc[0] if len(g) else "—"
        ax.set_title(f"{pr}   ({pb}, {g.unit.nunique()} 유닛)", fontsize=10,
                     loc="left", color=C[pr])
        ax.set_xticks([1, 2, 3]); ax.set_xlim(.7, 3.3)
        ax.set_xlabel("겔 두께 (mm)"); style(ax)
        # y 라벨을 칸마다 단다 — 축이 따로라는 것을 눈금과 함께 보이게 한다
        ax.set_ylabel("최대 측정 가능 힘 (N)", fontsize=9)
    axes[0].legend(frameon=False, fontsize=8.5, title="경도", title_fontsize=8.5)
    # matplotlib 은 마크다운을 그리지 않는다 — 별표를 쓰면 별표가 그대로 나온다
    fig.suptitle("천장 대 두께 — 선은 복제 평균, 점은 유닛 하나하나.  "
                 f"세로 축은 칸마다 다르다  ({RC.MARK} = {RC.LABEL})",
                 fontsize=10.5, x=.04, ha="left")
    fig.tight_layout(rect=[0, 0, 1, .95])
    save(fig, D[["principle", "probe", "unit", "hardness", "thickness_mm",
                 "ceiling_N", "depth_mm", "suspect_hardware"]],
         "B_ceiling_vs_thickness")


# ------------------------------------------------------------------- D --
def fig_D():
    """경도 범위 불균형 — 철회한 결론 3 의 근거."""
    S = {"9DTact": dict(soft=30, medium=50, hard=70),
         "DIGIT": dict(soft=51, medium=54, hard=57)}
    fig, ax = plt.subplots(figsize=(5.6, 2.6))
    rows = []
    for i, (pr, d) in enumerate(S.items()):
        v = list(d.values())
        ax.plot([min(v), max(v)], [i, i], c=C[pr], lw=6, alpha=.28,
                solid_capstyle="round")
        # DIGIT 은 세 점이 6 Shore 안에 몰려 라벨이 겹친다. 위아래로 어긋내되
        # 순서(soft<medium<hard)는 유지한다 — 몰려 있다는 사실 자체가 이 그림의 요점이다.
        stag = [.34, .19, .34] if max(d.values()) - min(d.values()) < 15 else [.19] * 3
        for (h, x), dy in zip(d.items(), stag):
            ax.plot(x, i, "o", c=CH[h], ms=11, mec="white", mew=1.4, zorder=3)
            ax.annotate(h, (x, i + dy), ha="center", fontsize=7.5, color=CH[h])
            rows.append(dict(principle=pr, hardness=h, shore_OO=x))
        ax.annotate(f"{max(v)-min(v)} 점", (max(v) + 1.5, i), va="center",
                    fontsize=9, color=C[pr], weight="bold")
    ax.set_yticks([0, 1]); ax.set_yticklabels(list(S), fontsize=9.5)
    ax.set_xlabel("Shore OO"); ax.set_xlim(24, 80); ax.set_ylim(-.5, 1.75)
    ax.set_title("경도를 흔든 범위가 6.7 배 다르다 — 원리 간 경도 효과는 비교 불가",
                 fontsize=10, loc="left")
    style(ax); ax.grid(axis="y", alpha=0)
    save(fig, pd.DataFrame(rows), "D_hardness_range_imbalance")


# ------------------------------------------------------------------- C --
def fig_C():
    """상대 기준이 원리 간 격차를 압축한다 — 절대 기준을 써야 하는 이유."""
    # **의심 유닛을 포함한 값이다**(2026-09-13). 빼면 어떻게 되는지를 함께 싣는다 —
    # 어느 쪽을 골라도 결론이 같다는 것이 이 표가 보여야 할 것이기 때문이다.
    rows = [dict(criterion="상대 (자기 피크의 15 %)", ninedtact=31.00, digit=17.33,
                 ratio=1.79, p="4.8e-07", n_9dtact=17,
                 ninedtact_no_suspect=30.97, ratio_no_suspect=1.79,
                 p_no_suspect="1.2e-06", usable=True),
            dict(criterion="절대 1.0 lvl/N", ninedtact=30.42, digit=7.02,
                 ratio=4.33, p="8.8e-07", n_9dtact=16,
                 ninedtact_no_suspect=30.81, ratio_no_suspect=4.39,
                 p_no_suspect="2.3e-06", usable=True),
            dict(criterion="절대 2.0 lvl/N", ninedtact=18.10, digit=2.73,
                 ratio=6.64, p="2.4e-03", n_9dtact=16,
                 ninedtact_no_suspect=18.58, ratio_no_suspect=6.81,
                 p_no_suspect="4.2e-03", usable=True)]
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    y = np.arange(len(df))[::-1]
    ax.barh(y + .18, df.ninedtact, .34, color=C["9DTact"], label="9DTact")
    ax.barh(y - .18, df.digit, .34, color=C["DIGIT"], label="DIGIT")
    for i, r in zip(y, df.itertuples()):
        ax.annotate(f"{r.ratio:.1f}×", (max(r.ninedtact, r.digit) + 1, i),
                    va="center", fontsize=9, weight="bold")
    ax.set_yticks(y); ax.set_yticklabels(df.criterion, fontsize=9)
    ax.set_xlabel("천장 중앙값 (N)")
    ax.set_title("상대 기준은 격차를 1.8 배로 압축한다", fontsize=10.5, loc="left")
    ax.legend(frameon=False, fontsize=8.5); style(ax); ax.grid(axis="y", alpha=0)
    save(fig, df, "C_relative_vs_absolute_criterion")


# ------------------------------------------------------------------- E --
def fig_E():
    """프로브를 바꾸면 힘은 흩어지고 깊이는 옮겨진다."""
    d = pd.read_csv(RES / "extra" / "data" / "E_probe_transfer.csv") \
        if (RES / "extra" / "data" / "E_probe_transfer.csv").exists() else None
    if d is None:
        rows = []
        for s in REG["sensors"]:
            if s.get("principle") != "DIGIT":
                continue
            ir = s.get("image_response") or {}
            if not (ir.get("reached") and "20260912_passC" in (s.get("run") or "")):
                continue
            b4 = None
            for e in list(s.get("history", [])) + [s]:
                if "calibgrid" in (e.get("run") or ""):
                    i4 = e.get("image_response") or {}
                    if i4.get("reached"):
                        b4 = (i4["max_measurable_force_N"], e.get("safe_depth_mm"))
            if not b4:
                continue
            rows.append(dict(unit=s["id"].replace("DIGIT_", ""),
                             hardness=s["hardness"], thickness_mm=s["thickness_mm"],
                             ball4_N=b4[0], ball4_depth_mm=b4[1],
                             ball8_N=ir["max_measurable_force_N"],
                             ball8_depth_mm=ir["max_measurable_depth_mm"]))
        d = pd.DataFrame(rows)
        d["force_ratio"] = d.ball8_N / d.ball4_N
        d["depth_ratio"] = d.ball8_depth_mm / d.ball4_depth_mm
    fig, ax = plt.subplots(figsize=(5.0, 3.4))
    for col, lab, c in (("force_ratio", "힘 비", "#c2553a"),
                        ("depth_ratio", "깊이 비", "#1f6f8b")):
        ax.scatter(d[col], np.full(len(d), 1 if col == "force_ratio" else 0),
                   s=46, c=c, alpha=.7, edgecolor="white", lw=.7, zorder=3)
        m = d[col].median()
        ax.plot([m, m], [(1 if col == "force_ratio" else 0) - .26,
                         (1 if col == "force_ratio" else 0) + .26],
                c=c, lw=2.4, zorder=4)
        ax.annotate(f"중앙 {m:.2f}", (m, (1 if col == "force_ratio" else 0) + .34),
                    ha="center", fontsize=9, color=c, weight="bold")
    ax.axvline(1.0, color="#888", ls=":", lw=1.2, zorder=1)
    ax.axvline(1.414, color="#888", ls="--", lw=1.0, zorder=1)
    ax.annotate("Hertz 예측 √R=1.41", (1.414, -.45), fontsize=7.5,
                color="#666", ha="center")
    ax.set_yticks([0, 1]); ax.set_yticklabels(["깊이 비", "힘 비"], fontsize=9.5)
    ax.set_xlabel("ball8 / ball4"); ax.set_ylim(-.6, 1.6)
    ax.set_title("포화 깊이는 프로브에 무관하고, 그 깊이의 힘은 아니다",
                 fontsize=10, loc="left")
    style(ax); ax.grid(axis="y", alpha=0)
    save(fig, d, "E_probe_transfer")


# ------------------------------------------------------------------- F --
def fig_F():
    """자국 대비 — 9DTact 의 '분해 실패' 상당수는 대비 부족이다."""
    import glob
    rows = []
    for f in glob.glob(str(DS / "9DTact" / "20260911_passA_pair150" / "*" /
                           "shape_pair150" / "ladder.csv")):
        u = Path(f).parent.parent.name.replace("9DTact_", "").split("__")[0]
        L = pd.read_csv(f)
        col = "mean_abs_diff_in_region" if "mean_abs_diff_in_region" in L else None
        if col is None:
            continue
        rows.append(dict(unit=u, peak_lvl=float(L[col].max()),
                         median_lvl=float(L[col].median()),
                         suspect_hardware=RC.is_suspect("9DTact", u)))
    if not rows:
        print("  F: pair150 사다리 없음 — 건너뜀")
        return
    d = pd.DataFrame(rows).sort_values("peak_lvl")
    fig, ax = plt.subplots(figsize=(6.0, 4.0))
    c = ["#c2553a" if v < 2.5 else "#1f6f8b" for v in d.peak_lvl]
    ax.barh(range(len(d)), d.peak_lvl, color=c, height=.7)
    ax.axvline(2.5, color="#444", ls="--", lw=1.3)
    ax.annotate("판정 바닥 2.5 레벨", (2.6, len(d) - 1.4), fontsize=8, color="#444")
    ax.set_yticks(range(len(d)))
    ax.set_yticklabels([f"{RC.MARK} {u}" if sp else u
                        for u, sp in zip(d.unit, d.suspect_hardware)], fontsize=7.5)
    for t, sp in zip(ax.get_yticklabels(), d.suspect_hardware):
        if sp:
            t.set_color("#c2553a")
    ax.set_xlabel("자국 최대 대비 (그레이 레벨)")
    ax.set_title("분해 실패의 상당수는 골이 아니라 대비의 문제다",
                 fontsize=10.5, loc="left")
    style(ax); ax.grid(axis="y", alpha=0)
    save(fig, d, "F_imprint_contrast")


def main():
    plt.rcParams["font.family"] = ["NanumGothic", "DejaVu Sans"]
    # NanumGothic 에 유니코드 마이너스(U+2212) 글리프가 없어 축 라벨이
    # "6 x 10<깨짐>2" 로 나온다. ASCII 하이픈을 쓰게 한다.
    plt.rcParams["axes.unicode_minus"] = False
    # 로그 축 라벨은 mathtext 로 그려지고 그것도 NanumGothic 을 따라가
    # "10<깨짐>1" 이 된다. mathtext 에는 완전한 폰트를 따로 준다.
    plt.rcParams["mathtext.fontset"] = "dejavusans"
    D = ceilings()
    D.to_csv(RES / "extra" / "data" / "ceilings_ball8.csv", index=False)
    fig_A(D); fig_B(D); fig_C(); fig_D(); fig_E(); fig_F()


if __name__ == "__main__":
    main()
