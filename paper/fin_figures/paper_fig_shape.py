#!/usr/bin/env python3
"""논문 그림 — 형상 복원: 깊이와 가로 크기. (V.B)

**요구 밀도를 정하는 것은 겔이 아니라 과업이다.** 한 센서 위의 두 프로브가
10 % 평탄 밀도에서 **38 배** 갈린다 — 광도 계열 원기둥 R ≈ 2.2 대 정육면체
R ≈ 83 px/mm². 겔 설계(두께·경도)로는 그 근처의 차이도 검출되지 않았다.
이 그림이 이 논문에서 가장 센 양성 증거다.

**정육면체를 빼지 않는다.** 초안의 "형상은 2.9 ~ 6.3 px/mm² 에서 plateau" 는
광도 정육면체를 뺀 값이고, 과업 간 차이를 열일곱 배 줄여 전달한다. 넷을 다
실어야 "과업이 정한다" 가 그림으로 읽힌다.

아랫줄이 따로 있어야 하는 이유
    깊이가 평탄해지는 것과 **가로 크기가 맞는 것은 다른 일이다.** 깊이 오차가
    평탄한 구간에서도 정육면체의 지름은 내내 크게 읽힌다(반깊이 윤곽이 실제
    모서리 바깥에 선다). 저밀도에서 그 값이 작아지는 것은 **블러가 윤곽을 안으로
    당긴 것**이지 측정이 좋아진 것이 아니다 — 두 오차가 상쇄되는 것뿐이다.

가장 낮은 단은 **실패이지 측정이 아니다**
    9DTact 의 8 px 단은 아홉 시편 중 **셋만** 값을 냈다(`shape_vs_resolution.csv`
    의 `cyl4_raw_mae` 가 여섯에서 NaN — 행은 있고 값이 없다). 그 셋의 중앙값을
    곡선으로 이으면 **16 px 보다 낮게** 찍혀 "8 px 에서 더 정확하다" 로 읽힌다 —
    살아남은 시편만 남은 것인데. 그래서 **아홉 전부가 값을 낸 단에만** 선과 띠를
    그리고, 그러지 못한 단은 축 위에 `×` 로만 찍는다. 곡선이 그냥 끊긴 것으로
    보이지 않게 하려는 표시다.

    걸리는 단: 9DTact 깊이 8 px (3/9) · 9DTact 지름 8 px (3/9) 와 16 px (8/9,
    원기둥) · DIGIT 지름 8 px (7/9, 원기둥).

세로 축 — 윗줄은 나누고 아랫줄은 묶는다
    **윗줄(깊이 오차)은 원리끼리 견줄 수 없다.** 두 파이프라인이 서로 다른 깊이
    구간을 평가한다(광도 0.010 ~ 0.578 mm, 깊이 참조형 중앙 최심 0.761 mm) —
    같은 축에 놓으면 없는 비교가 생긴다. 그래서 칸마다 따로 잡았다.
    **아랫줄(지름 오차)은 묶는다.** 둘 다 같은 ⌀4 mm 프로브를 재는 것이므로
    0 선이 양쪽에서 같은 뜻이고, 그래서 비교가 성립한다.

색과 선 모양
    색이 프로브(원기둥 파랑 · 정육면체 빨강), **선 모양도 프로브**다(실선 ·
    파선). 겹친 것은 낭비가 아니다 — `CLAUDE.md` 가 적어 둔 대로 흑백 인쇄에서
    두 선이 구분되지 않는 문제를 선 모양이 푼다. 원리는 색이 아니라 **열**이
    가른다.

삼각형 — 10 % 평탄점
    유닛마다 구한 뒤 중앙값(n = 9), `knee_shape_by_unit.csv` 가 정본이다.
    9DTact 의 둘(5.53 · 4.91)이 거의 겹치므로 정육면체를 한 단 아래에 찍었다 —
    **두 프로브가 같은 밀도를 요구한다는 것 자체가 광도 계열과의 대비**다.

무엇을 못 그렸나
    계획서 F6 의 네 패널 중 둘이 이 기계에서 안 된다.
    **(a) 높이맵 세 장**(320 · 80 · 16 px)은 원영상이 필요하다 — 실험 기계.
    **(d) 전처리 스케일 비교**(픽셀 고정 커널 대 배율 커널)는 자료가 아예 없다.
    `shape_reconstruction.md` §6.5a 의 표는 **17 유닛(54 유닛 집합)의 중앙값**이라
    `CLAUDE.md` §1 에 걸린다 — 논문 그림에 그대로 옮기면 안 된다. 그리려면 옛
    커널 팔을 **선택된 아홉 시편으로 다시 돌려야** 한다. 저장소의 csv 는 이미
    고친 판이다(48 px 0.072 · 80 px 0.062 로 §6.5a 의 "새" 행과 맞는다).

칸마다 정해진 센서 하나 (`CLAUDE.md` §1) — 원리당 아홉 시편.

캡션이 져야 할 것
    1. 행이 잰 것(위 깊이 오차 · 아래 지름 오차), 열이 원리.
    2. 선은 아홉 시편의 중앙값, 띠는 사분위 범위. 칸마다 시편 하나이므로
       띠는 **시편 간 산포**이지 측정 불확도가 아니다.
    3. **윗줄의 세로 축이 칸마다 다르고 원리끼리 견주면 안 된다.**
    4. 아랫줄의 0 선은 참 지름 4 mm. **부호를 접지 않았다** — 크게 읽는 것과
       작게 읽는 것은 다른 고장이다.
    5. 아랫줄에서 **띠가 축 위로 잘린 곳이 있다** (광도 계열의 가장 낮은 두 단).
       잘린 것이지 없는 것이 아니다 — 저밀도에서 반깊이 윤곽이 화면을 채워
       시편 간 산포가 커진다.
    6. 삼각형 = 10 % 평탄 밀도의 유닛별 값의 중앙값(n = 9).
    7. **`×` 는 아홉 시편이 다 값을 내지 못한 단**이다. 선은 아홉 전부가 값을 낸
       단에만 그렸다 — 몇만 살아남은 단의 중앙값은 군의 중앙값이 아니다.

자료
    `result/single/{1_9DTact,2_DIGIT}/data/shape_mae_vs_resolution_9units.csv`
    · `..._size_err_vs_resolution_9units.csv`
    · 삼각형은 `result/single/extra/data/knee_shape_by_unit.csv`
"""
import numpy as np
import pandas as pd

import paper_style as PS
from paper_style import BLUE, RED, DISPLAY

PS.use_paper_style()
import matplotlib.pyplot as plt           # noqa: E402
import matplotlib.ticker as mticker       # noqa: E402

FOLD = {"9DTact": "1_9DTact", "DIGIT": "2_DIGIT"}
PRINCIPLES = ("9DTact", "DIGIT")
# (프로브, 색, 선 모양, 범례 이름, 평탄점 열)
PROBES = [("cyl4", BLUE, "-", "cylinder ⌀4", "cyl4_knee_R"),
          ("cube4", RED, "--", "cube 4 mm", "cube4_knee_R")]
ROWS = [("shape_mae_vs_resolution", "depth MAE [mm]", True),
        ("shape_size_err_vs_resolution", "diameter error [mm]", False)]

XT = [0.1, 1, 10, 100, 1000, 10000]
XTL = ["0.1", "1", "10", r"$10^2$", r"$10^3$", r"$10^4$"]


def load(pr, stem):
    """유닛 × 단. csv 에 폭이 없으므로 **전해상도(1920 px)를 기준으로** 되찾는다.

    밀도는 폭의 제곱에 비례한다. 유닛 안의 순위로 붙이면 단이 열둘이 아닌 유닛
    (9DTact cyl4 에 열한 단짜리가 있다)에서 어긋나므로 그렇게 하지 않는다.
    """
    f = PS.ROOT / f"result/single/{FOLD[pr]}/data/{stem}_9units.csv"
    d = pd.read_csv(f)
    assert d.sensor.nunique() == 9, f"{pr}/{stem}: 시편이 아홉이 아니다"
    assert not d.suspect_hardware.any(), f"{pr}/{stem}: 의심 유닛이 있다"
    out = []
    for _, g in d.groupby(["sensor", "probe"]):
        g = g.sort_values("density_px_per_mm2").copy()
        g["width_px"] = (1920 * np.sqrt(g.density_px_per_mm2
                                        / g.density_px_per_mm2.max())).round().astype(int)
        out.append(g)
    d = pd.concat(out)
    d["principle"], d["measure"] = pr, stem
    return d


def main():
    data = {(pr, stem): load(pr, stem)
            for pr in PRINCIPLES for stem, _y, _t in ROWS}
    knee = pd.read_csv(PS.ROOT / "result/single/extra/data/knee_shape_by_unit.csv")

    tags = iter("abcd")
    fig, axes = plt.subplots(len(ROWS), len(PRINCIPLES),
                             figsize=(PS.FULL_W_NARROW, 4.35), sharex=True)

    for row, (stem, ylab, with_knee) in enumerate(ROWS):
        for col, pr in enumerate(PRINCIPLES):
            ax = axes[row, col]
            d = data[(pr, stem)]
            if not with_knee:
                # 참 지름 4 mm. 부호를 접지 않으므로 0 선이 있어야 읽힌다.
                ax.axhline(0, c=PS.MUTED, lw=0.6, zorder=1)

            for k, (probe, c, ls, lab, kcol) in enumerate(PROBES):
                g = d[d.probe == probe]
                n = g.groupby("width_px").sensor.nunique()
                q = g.groupby("width_px").mae_mm.quantile([.25, .5, .75]).unstack()
                xs = g.groupby("width_px").density_px_per_mm2.median()
                # **아홉 전부가 값을 낸 단에만** 선과 띠를 그린다. 몇만 살아남은
                # 단의 중앙값은 군의 중앙값이 아니라 생존자의 중앙값이다.
                ok = n[n == 9].index
                ax.fill_between(xs[ok], q.loc[ok, .25], q.loc[ok, .75],
                                color=c, alpha=0.14, lw=0, zorder=2)
                ax.plot(xs[ok], q.loc[ok, .5], ls, c=c, lw=1.8, label=lab,
                        zorder=3)
                # 그러지 못한 단 — 곡선이 그냥 끊긴 것으로 보이지 않게
                for w in n[n < 9].index:
                    # 두 프로브가 같은 단에서 함께 실패하면 표식이 겹친다 —
                    # 삼각형과 같은 규칙으로 정육면체를 한 단 아래에 찍는다
                    ax.plot([xs[w]], [-0.055 * k], marker="x", ms=4.5, mew=1.4,
                            c=c, clip_on=False,
                            transform=ax.get_xaxis_transform(), zorder=5)

                if with_knee:
                    kn = knee[knee.principle == pr][kcol].median()
                    # 9DTact 의 두 값이 거의 겹친다 — 정육면체를 한 단 아래로
                    ax.plot([kn], [-0.055 * k], marker="^", ms=5.0, c=c,
                            clip_on=False,
                            transform=ax.get_xaxis_transform(), zorder=6)

            ax.set_xscale("log")
            ax.set_xticks(XT)
            ax.set_xticklabels(XTL)
            ax.xaxis.set_minor_locator(mticker.NullLocator())
            ax.yaxis.set_major_locator(mticker.MaxNLocator(4))
            ax.set_title(f"({next(tags)}) {DISPLAY[pr]}" if row == 0
                         else f"({next(tags)})", loc="left")
            if col == 0:
                ax.set_ylabel(ylab)
            if row == len(ROWS) - 1:
                ax.set_xlabel("pixel density $R$ [px/mm$^2$]")
            PS.style(ax)

    # **아랫줄만 축을 묶는다** — 같은 ⌀4 mm 프로브를 재므로 0 선이 같은 뜻이다.
    # 윗줄은 두 파이프라인이 다른 깊이 구간을 평가하므로 묶지 않는다.
    lo = min(a.get_ylim()[0] for a in axes[1])
    hi = max(a.get_ylim()[1] for a in axes[1])
    for a in axes[1]:
        a.set_ylim(lo, hi)
    axes[1, 1].set_yticklabels([])
    for a in axes[0]:
        a.set_ylim(0, a.get_ylim()[1])
    axes[0, 0].legend(loc="upper center", frameon=False, handlelength=1.9,
                      handletextpad=0.5, labelspacing=0.20, borderpad=0.1,
                      fontsize=9.0)

    fig.tight_layout(w_pad=0.8, h_pad=0.9)
    out = pd.concat(data.values())[
        ["principle", "measure", "sensor", "probe", "width_px",
         "density_px_per_mm2", "mae_mm"]]
    PS.save(fig, out, "fig_shape")

    # 그림이 말하는 것을 숫자로 — 과업이 요구 밀도를 얼마나 가르나
    rows = []
    for pr in PRINCIPLES:
        k = knee[knee.principle == pr]
        for probe, _c, _ls, _lab, kcol in PROBES:
            rows.append(dict(principle=pr, probe=probe,
                             knee_R_median=k[kcol].median(),
                             knee_R_min=k[kcol].min(), knee_R_max=k[kcol].max()))
    S = pd.DataFrame(rows)
    print("\n  아홉이 다 값을 내지 못한 단 (선을 긋지 않고 × 로만 찍은 곳)")
    for (pr, stem), d in data.items():
        for probe, *_ in PROBES:
            n = d[d.probe == probe].groupby("width_px").sensor.nunique()
            bad = n[n < 9]
            for w, cnt in bad.items():
                print(f"    {pr:<7}{stem.split('_')[1]:<5}{probe:<6}"
                      f"{w:>5} px — {cnt}/9")
    print("\n  10 % 평탄 밀도 (유닛별 중앙값, n = 9)")
    for _, r in S.iterrows():
        print(f"    {r.principle:<7}{r.probe:<6} R = {r.knee_R_median:7.2f} px/mm²"
              f"   유닛별 {r.knee_R_min:.2f} ~ {r.knee_R_max:.1f}")
    print(f"\n  과업 간 최대 배수 {S.knee_R_median.max() / S.knee_R_median.min():.0f} 배 "
          f"— 광도 정육면체 {S.knee_R_median.max():.1f} 대 광도 원기둥 "
          f"{S.knee_R_median.min():.2f}")
    print("  한 센서 안에서만 봐도 광도 계열은 "
          f"{S[S.principle == 'DIGIT'].knee_R_median.max() / S[S.principle == 'DIGIT'].knee_R_median.min():.0f} 배, "
          "깊이 참조형은 "
          f"{S[S.principle == '9DTact'].knee_R_median.max() / S[S.principle == '9DTact'].knee_R_median.min():.2f} 배")
    S.to_csv(PS.FIGS / "fig_shape_stats.csv", index=False)
    print(f"  -> paper/fin_figures/fig_shape_stats.csv  ({len(S)} 행)")


if __name__ == "__main__":
    main()
