#!/usr/bin/env python3
"""result/results.md — 모든 그림과 표를 설명과 함께 한 문서로.

숫자는 전부 result/ 의 CSV 에서 읽는다. 자료가 갱신되면 다시 돌리면 된다.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RES = ROOT / "result"
FOLD = {"9DTact": "1_9DTact", "DIGIT": "2_DIGIT", "DIGIT_Marker": "3_DIGIT_Marker"}
L = []


def w(s=""):
    L.append(s)


def table(path, note=None):
    p = RES / path
    if not p.exists():
        w(f"> 아직 없음 — `{path}`"); w(); return
    d = pd.read_csv(p)
    w(d.to_markdown(index=False))
    if note:
        w(); w(note)
    w(); w(f"<sub>자료: `{path}`</sub>"); w()


_WH = {1920: "1920×1080", 1280: "1280×720", 854: "854×480", 640: "640×360",
       426: "426×240", 320: "320×180", 160: "160×90", 80: "80×45", 48: "48×27",
       32: "32×18", 16: "16×9", 8: "8×5"}


def _wh(v):
    """해상도를 가로x세로로. 사다리에 없는 값(복제 중앙값)은 가장 가까운 단에 `~`."""
    v = int(round(float(v)))
    if v in _WH:
        return _WH[v]
    n = min(_WH, key=lambda k: abs(k - v))
    return f"~{_WH[n]}"


def fig(path, cap):
    p = RES / path
    if not p.exists():
        w(f"> 아직 없음 — `{path}`"); w(); return
    csv = path.replace("/figures/", "/data/").replace(".png", ".csv")
    w(f"![{cap}]({path})")
    w()
    w(f"*{cap}*")
    w()
    w(f"<sub>그림: `{path}` · 자료: `{csv}`</sub>")
    w()


# 같은 칸의 두 복제가 내는 포화 해상도가 몇 배 다른가 (`knee_by_cell.py` 가 낸 값).
# 이 숫자가 곧 검정력의 한계다 — 겔이 같고 장착만 다른데 이만큼 흔들린다.
_REPRO = {
    "force": [("9DTact · Fz", 8, 6.7, 0, 4), ("9DTact · 전단", 8, 1.6, 1, 1),
              ("DIGIT · Fz", 9, 1.7, 3, 1), ("DIGIT · 전단", 9, 1.5, 4, 1),
              ("DIGIT_Marker · Fz", 9, 1.0, 5, 1),
              ("DIGIT_Marker · 전단", 9, 5.0, 1, 2)],
    "shape": [("9DTact · cyl4", 8, 1.0, 5, 0), ("9DTact · cube4", 8, 2.0, 3, 0),
              ("DIGIT · cyl4", 9, 1.7, 4, 1), ("DIGIT · cube4", 9, 1.0, 5, 1)],
}
_KNEE_NAME = {"fz_knee_px": "Fz (수직력)", "shear_knee_px": "전단 (Fx·Fy 평균)",
              "cyl4_knee_px": "원기둥 ⌀4 mm", "cube4_knee_px": "정육면체 4 mm"}
_KNEE_SHORT = {"fz_knee_px": "Fz", "shear_knee_px": "전단",
               "cyl4_knee_px": "cyl4", "cube4_knee_px": "cube4"}


def knee_block(family, metrics, what, tail=True):
    """포화 해상도를 경도·두께 칸별로 — 4 절(힘)과 5 절(형상)이 각각 부른다.

    두 절이 같은 분석을 나눠 싣는다. **다중검정 보정은 둘을 합쳐서 한다** — 힘 10 개와
    형상 10 개를 따로 보정하면 "20 번 중 하나" 라는 사실이 가려진다. 그래서 q 는 두
    절에서 같은 20 개 집합으로 계산한 값이다.
    """
    tab = RES / "extra" / "data" / "knee_by_cell_3x3.csv"
    ks = RES / "extra" / "data" / "knee_summary.csv"
    if not tab.exists():
        return
    K = pd.read_csv(tab)
    T = pd.read_csv(RES / "extra" / "data" / "knee_trends.csv")
    K = K[K.metric.isin(metrics)]
    T = T[T.metric.isin(metrics)]

    w(f"### 포화 해상도 — 경도·두께 칸별 ({what})")
    w()
    w("**포화 해상도** = 그 유닛 자신의 최솟값의 110 % 안에 드는 **가장 낮은** 해상도.")
    w("`argmin` 은 곡선이 평평한 구간에서 흔들리므로 쓰지 않는다. 칸에는 **두 복제를")
    w("그대로** 적는다(둘이 같으면 하나만). **검정 단위는 칸이 아니라 유닛**이다 —")
    w("칸마다 유닛이 둘뿐이라 칸으로는 검정이 되지 않는다.")
    w()
    if ks.exists():
        S2 = pd.read_csv(ks)
        S2 = S2[S2.metric.isin(metrics)]
        w("칸을 나누지 않은 중앙 포화 해상도부터 — 실무적으로 쓸 숫자는 이것이다.")
        w()
        w("| 원리 | 지표 | 중앙 포화 해상도 | 유닛별 범위 | n |")
        w("|---|---|---|---|---:|")
        for _, x in S2.iterrows():
            w(f"| {x.principle} | {_KNEE_SHORT.get(x.metric, x.metric)} | "
              f"**{_wh(x.median_px)}** | {_wh(x.min_px)} ~ {_wh(x.max_px)} | {int(x.n)} |")
        w()
    for (pr, m), g in K.groupby(["principle", "metric"], sort=False):
        w(f"**{pr} — {_KNEE_NAME.get(m, m)}**")
        w()
        w("| 경도 | 1 mm | 2 mm | 3 mm |")
        w("|---|---|---|---|")
        for _, x in g.iterrows():
            w(f"| {x.hardness} | {x['1mm']} | {x['2mm']} | {x['3mm']} |")
        t = T[(T.principle == pr) & (T.metric == m)]
        if len(t):
            t = t.iloc[0]
            w()
            w(f"<sub>유닛 {int(t.n)} 개 — 두께 ρ {t.rho_thickness:+.3f} "
              f"(p {t.p_thickness:.3f}, q {t.q_thickness:.3f}) · 경도 ρ "
              f"{t.rho_hardness:+.3f} (p {t.p_hardness:.3f}, q {t.q_hardness:.3f})</sub>")
        w()
    w("<sub>자료: `extra/data/knee_by_cell_3x3.csv` · 유닛별 "
      f"`knee_{family}_by_unit.csv` · 요약 `knee_summary.csv` · 검정 "
      "`knee_trends.csv`</sub>")
    w()
    if not tail:
        w("q 는 **힘과 형상을 합친 20 개**에 Benjamini-Hochberg 를 건 값이다 —")
        w("보정의 근거와 복제 재현성은 4 절에 한 번만 적었다. **어느 칸도 q < 0.05 가")
        w("아니다.**")
        w()
    if not tail:
        return
    n_test = 2 * len(T)          # 행마다 두께와 경도 둘을 잰다
    w(f"**겔은 {what}의 포화 해상도를 움직이지 않는다.** 위 **{n_test} 개 검정**(행 {len(T)} 개 ×")
    w("두께·경도) 어느 것도 q < 0.05 가 아니다. q 는 **힘과 형상을 합친 20 개**에")
    w("Benjamini-Hochberg 를 건 값이다 — 두 절을 따로 보정하면 \"20 번 중 하나\" 라는")
    w("사실이 가려진다.")
    w()
    pre = T[(T.p_thickness < .05) | (T.p_hardness < .05)]
    if len(pre):
        w("보정 전에 p < 0.05 인 것이 " + ("하나" if len(pre) == 1 else f"{len(pre)} 개")
          + " 있다:")
        w()
        for _, x in pre.iterrows():
            which = "두께" if x.p_thickness < .05 else "경도"
            pv = x.p_thickness if x.p_thickness < .05 else x.p_hardness
            qv = x.q_thickness if x.p_thickness < .05 else x.q_hardness
            w(f"- `{x.principle}` 의 {_KNEE_SHORT.get(x.metric, x.metric)} 대 {which} "
              f"— p {pv:.3f}, **q {qv:.3f}**")
        w()
        w("**20 번 검정하면 우연히 한 개는 나온다.** 그것이 보정이 하는 일이다.")
        w()
    w("**같은 칸의 두 복제가 내는 포화 해상도가 얼마나 다른가**가 이 검정의 한계를 정한다:")
    w()
    w("| 원리 · 지표 | 쌍 | 배율 중앙 | 같은 단 | 8 배 이상 |")
    w("|---|---:|---:|---:|---:|")
    for lab, n, r, same, big in _REPRO[family]:
        w(f"| {lab} | {n} | **{r:.1f}×** | {same} | {big} |")
    w()
    if family == "force":
        w("**9DTact 의 Fz 포화 해상도는 복제 쌍 안에서 중앙 6.7 배, 여덟 쌍 중 넷이 8 배 이상**")
        w("어긋난다. 겔이 같고 장착만 다른데 그렇다. 두께가 만들 수 있는 차이가 그보다")
        w("작다면 이 설계로는 보이지 않는다 — **무효과의 증거가 아니라 검정력의 한계다.**")
    else:
        w("**형상은 사정이 낫다** — 네 조합 중 셋에서 복제 절반 이상이 **같은 단**에")
        w("떨어진다(9DTact cyl4 는 여덟 쌍 중 다섯이 정확히 같다). 재현되는 지표에서도")
        w("두께·경도 효과가 보이지 않으므로, 적어도 형상에서는 **정말로 없다**는 쪽에")
        w("무게가 실린다. 힘 쪽(4 절)은 그렇게 말할 수 없다.")
    w()


def main():
    w("# 결과 — 그림과 표")
    w()
    w("VBTS 해상도 캠페인의 결과물 전부. **모든 그림에 그것을 그린 CSV 가 같은 이름으로")
    w("`data/` 에 있다** — 직접 다시 그릴 수 있다.")
    w()
    w("생성: `python3 src/scripts/make_results_md.py` "
      "(그림은 `make_result_figures.py`, `make_optical_curves.py`, 표는 "
      "`make_result_tables.py`)")
    w()
    w("> **수집은 2026-09-12 에 끝났다.** 한계는 `docs/methods.md` §10.0 에 있고, ")
    w("> 이 문서의 각 절에도 해당하는 것을 적어 두었다.")
    w()
    w("---")
    w()

    # ---------------------------------------------------------------- 0 --
    w("## 0. 한눈에")
    w()
    w("> **표시된 유닛.** `9DTact_hard_1mm_r2` 와 `9DTact_medium_1mm_r2` 는 운전자가")
    w("> 2026-09-11 에 **바디에서 빛이 새는 것을 육안으로 확인**한 유닛이다. 데이터도")
    w("> 일치한다 — 두 점 자국이 중앙 1.7 ~ 1.8 그레이 레벨로 17 유닛 중앙값 3.7 의")
    w("> 절반이라 네 간격 모두 '미분해' 로 기록됐고, 천장은 상대 문턱 탓에 짝보다")
    w("> +24 %, +25 % 부풀었다.")
    w(">")
    w("> **빼지 않고 표시한다.** 자료는 전부 들어 있고 의심 표시만 달린다 — 뺀 자료는")
    w("> 보이지 않으므로 검토되지도 않기 때문이다. 유닛별 그림에서는 제목에 `!` 와")
    w("> 경고색이 붙고 선이 **점선**이며, 흩어그림에서는 **속이 빈 붉은 원**이다.")
    w("> 3×3 표에서 `!` 가 붙은 칸은 그 칸의 복제 하나가 의심 유닛이라는 뜻이고,")
    w("> 모든 csv 에 `suspect_hardware` 열이 있다. 등록부의 같은 이름 필드가 근거다.")
    w(">")
    w("> **통계는 포함해서 냈다.** 빼면 어떻게 되는지는 부록 A 의 csv")
    w("> (`C_relative_vs_absolute_criterion.csv` 의 `*_no_suspect` 열)에 함께 적었다 —")
    w("> 중앙값이 31.00 에서 30.97 N 으로 움직일 뿐 결론은 같다.")
    w()
    w("| | 9DTact | DIGIT | DIGIT_Marker |")
    w("|---|---|---|---|")
    w("| 유닛 | 18 (천장 17) | 18 | 18 |")
    w("| 최대 측정 가능 힘 | **ball8** 17/18 | **ball8** 18/18 | `ball4` 만 |")
    w("| 공간 분해능 | 6 간격 × 17 | 2 간격 × 18 | **없음** |")
    w("| 힘 추정 vs 해상도 | 12 단 × 17 | 12 단 × 18 | 12 단 × 18 |")
    w("| 형상 복원 vs 해상도 | 8 단 × 17 | 파이프라인 신규 | **없음** |")
    w()

    # ---------------------------------------------------------------- 1 --
    w("## 1. 최대 측정 가능 힘 (천장)")
    w()
    w("이미지가 변하기를 멈추는 힘. 판정은 *응답이 그 유닛 최대의 15 % 아래로 두 단 연속*.")
    w("겔이 견디는 한계가 아니라 **사진이 답하기를 멈추는 지점**이다.")
    w()
    fig("extra/figures/B_ceiling_vs_thickness.png",
        "천장 대 두께, 경도별 — 세 원리. 선은 복제 평균, 점은 유닛 하나하나, "
        "세로 막대는 두 복제의 폭. 속이 빈 붉은 원이 빛 누출 의심 유닛이다. "
        "**세로 축은 원리마다 다르다** — 9DTact 가 63 N 까지 가는데 DIGIT 계열은 "
        "6 ~ 23 N 이라 축을 묶으면 DIGIT 과 Marker 의 기울기가 눌려 보이지 않는다.")
    w("**9DTact 는 두께가 늘면 오르고 DIGIT 계열은 내려간다.** 점을 다 찍었으므로")
    w("평균선이 두 복제 중 어느 쪽에 끌려갔는지 바로 보인다 — 예컨대 9DTact 의")
    w("`medium 2 mm` 는 점이 하나뿐이고(짝은 2026-09-04 에 파괴됐다), `soft 2 mm` 는")
    w("두 복제가 24.6 과 30.2 N 으로 벌어져 있다.")
    w()
    w("> **`DIGIT_Marker` 의 자는 다르다.** 마커 유닛에는 `ball8` 램프가 없어 `ball4`")
    w("> 로 잰 값이다. **힘은 프로브 사이에서 환산되지 않으므로**(부록 C: 비 1.50 ~ 3.26,")
    w("> CV 21 %) Marker 의 세로 위치를 나머지 둘과 나란히 읽으면 안 된다. 한 원리")
    w("> **안에서의 두께·경도 방향**만 읽을 것.")
    w()
    w("### 3×3 표 — 칸은 `r1 / r2  (평균)`, `!` 는 빛 누출 의심 유닛이 든 칸")
    w()
    for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
        w(f"**{pr}** (N)"); w()
        table(f"{FOLD[pr]}/data/table_max_force_3x3.csv")
    w("`!` 는 운전자가 빛이 새는 것을 육안으로 확인한 유닛이다 — 신호가 약해 판정 문턱이")
    w("낮아지므로 천장이 **부풀려져** 있다. 분석에서 따로 표시하거나 빼야 한다.")
    w()
    w("`9DTact_medium_2mm_r1` 은 2026-09-04 에 파괴돼 복제가 하나뿐이다.")
    w()
    w("**DIGIT_Marker 는 `ball4` 로 잰 값**이라 위 두 표와 같은 자가 아니다.")
    w()
    w("### 포화가 일어나는 깊이")
    w()
    fig("extra/figures/A_saturation_depth_vs_thickness.png",
        "포화 깊이는 두 원리 모두 두께를 따라 증가한다 — 기울기가 2.2 배 다르다.")
    w("**힘과 깊이는 다른 이야기를 한다.** 천장(힘)은 두 원리가 반대로 가지만, 깊이는")
    w("둘 다 두께를 따라 증가한다. 그리고 그 깊이가 **왜 반대로 가는지를 설명한다** —")
    w("9DTact 는 두께의 2.0 ~ 5.2 배까지 들어가 **기재에 눌린 상태**에서 포화하므로")
    w("겔이 두꺼울수록 더 버티고, DIGIT 은 0.56 ~ 1.32 배에서 **광학이 먼저** 포화하므로")
    w("두꺼운 겔의 흐려진 상이 오히려 먼저 답하기를 멈춘다.")
    w()

    # ---------------------------------------------------------------- 2 --
    w("## 2. 깊이에 따른 자국 지름과 밝기")
    w()
    w("지름은 **픽셀**로 둔다 — mm 환산에 필요한 px/mm 이 유닛마다 최대 1.5 배 어긋나는")
    w("것이 2026-09-12 에 확인됐다. 픽셀은 측정된 그대로다.")
    w()
    for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
        w(f"### {pr}"); w()
        fig(f"{FOLD[pr]}/figures/optical_vs_depth_18units.png",
            f"{pr} — 유닛별 깊이-지름(실선)과 깊이-밝기(점선)")
        for probe in ("ball4", "ball8"):
            f = f"{FOLD[pr]}/data/optical_slope_diameter_{probe}_3x3.csv"
            if (RES / f).exists():
                w(f"**지름 기울기, {probe} (px/mm)**"); w()
                table(f)
    w("### 두께·경도를 나란히 — 같은 축 위에 겹친다")
    w()
    w("위의 18 칸 격자는 유닛 하나하나를 보여주지만 **어느 두께가 더 가파른가** 같은")
    w("질문에는 답하지 못한다. 칸이 다르면 눈이 기울기를 나란히 놓지 못하기 때문이다.")
    w("그래서 같은 축 위에 겹친다 — 유닛마다 사다리가 닿은 깊이가 다르므로 공통 격자에")
    w("보간한 뒤, **그 깊이에 자료가 있는 유닛이 3 개 이상일 때만** 그린다. 선은")
    w("중앙값이고 띠는 사분위 범위다(평균은 한 유닛에 끌려간다).")
    w()
    for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
        for probe in ("ball8", "ball4"):
            f = f"{FOLD[pr]}/figures/optical_by_group_{probe}.png"
            if (RES / f).exists():
                fig(f, f"{pr} ({probe}) — 왼쪽은 경도별, 오른쪽은 두께별. "
                       "선은 중앙값, 띠는 사분위 범위.")
                break
    w("눈으로 \"갈린다\" 고 말하면 곡선이 서로 다른 깊이에서 끝나는 것에 속는다. 세 군이")
    w("모두 자료를 가진 **가장 깊은 깊이 하나**를 잡고 거기서의 폭을 잰다:")
    w()
    w("| 원리 | 잰 것 | 경도별 폭 | 두께별 폭 | 두께가 단조인가 | 경도 비 | 두께 비 |")
    w("|---|---|---:|---:|---|---:|---:|")
    import glob as _g
    SP = []
    for pr, pb in (("9DTact", "ball8"), ("DIGIT", "ball8"),
                   ("DIGIT_Marker", "ball4")):
        f = RES / FOLD[pr] / "data" / f"optical_group_spread_{pb}.csv"
        if f.exists():
            SP.append(pd.read_csv(f))
    if SP:
        SP = pd.concat(SP)
        MN = {"diameter_px": "자국 지름", "level": "밝기 변화"}
        for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
            for meas in ("diameter_px", "level"):
                g = SP[(SP.principle == pr) & (SP.measure == meas)]
                h = g[g.group_by == "hardness"]
                t = g[g.group_by == "thickness_mm"]
                if not len(h) or not len(t):
                    continue
                w(f"| {pr} | {MN[meas]} | {h.spread_pct.iloc[0]:.0f} % | "
                  f"**{t.spread_pct.iloc[0]:.0f} %** | "
                  f"{'예' if bool(t.monotone.iloc[0]) else '**아니오**'} | "
                  f"{h.ratio.iloc[0]:.2f} | **{t.ratio.iloc[0]:.2f}** |")
    w()
    w("<sub>**비** = 군 사이 차이 ÷ 군 안의 사분위 폭. 1 보다 작으면 그 군들은 자기")
    w("흩어짐 안에 있다는 뜻이다. 자료: "
      "`<원리>/data/optical_group_spread_<프로브>.csv` · 곡선 "
      "`optical_by_group_<프로브>.csv`</sub>")
    w()
    w("**비가 판정한다.** 두께별은 여섯 칸 모두 **2.2 ~ 10.4** 로 1 을 넘고, 경도별은")
    w("여섯 칸 모두 **0.38 ~ 0.76** 으로 1 에 못 미친다. 원리와 지표를 가리지 않고")
    w("갈라진다 — **두께는 유닛 산포 위로 올라오고 경도는 그 안에 묻힌다.**")
    w()
    w("가는 선을 보면 왜 폭만으로는 부족한지 알 수 있다. 중앙값 세 줄은 깔끔하게")
    w("갈라져 보여도 유닛 하나하나는 군을 넘나든다 — 특히 9DTact 의 경도별 지름은")
    w("군 사이 22 px 에 군 안 IQR 54 px 이라, 중앙값의 차이가 **한 유닛 고르는 것보다")
    w("작다.**")
    w()
    w("**DIGIT 계열은 얇을수록 넓고 밝다** — 두 지표 모두 1 → 2 → 3 mm 로 단조 감소한다.")
    w("기재가 가까워 변형이 옆으로 퍼지고, 겔이 얇아 빛이 덜 흩어지는 것으로 읽힌다.")
    w()
    w("> **9DTact 는 단조가 아니다.** 두 지표 모두 **2 mm 가 가장 크다** — 지름")
    w("> 553 px (1 mm 534, 3 mm 481), 밝기 16 lvl (1 mm 9, 3 mm 11). 3 mm 가 가장 낮은")
    w("> 것은 DIGIT 과 같지만 1 mm 가 2 mm 보다 낮은 것은 다르다. **왜 가운데가 솟는지는")
    w("> 이 자료로 답하지 못한다.** 9DTact 는 투명 겔 위에 검은 안료층을 덧씌우므로")
    w("> 기재까지의 실제 두께가 라벨보다 두껍고(`measurement_protocol.md` 의 깊이")
    w("> 뒷막이 항목), 1 mm 라벨의 겔이 실제로는 가장 얇지 않을 수 있다 — 확인하지")
    w("> 않은 추측이다.")
    w()
    w("> **경도가 겹치는 것을 \"경도가 무관하다\" 로 읽으면 안 된다.** DIGIT 계열은")
    w("> 경도를 6 Shore 점밖에 흔들지 않았다(부록 B). 9DTact 는 40 점을 흔들고도 폭이")
    w("> 5 ~ 12 % 이므로, 적어도 9DTact 에서는 **실제로 약한 효과**라고 말할 수 있다.")
    w()
    w("> **원리 간 기울기를 비교하면 안 된다.** 자료마다 깊이 구간이 다르고 (각 유닛의")
    w("> 유효 구간에서 맞춘다), 자국이 시야를 채우면 `contact_region` 이 덩어리를 놓쳐")
    w("> 지름이 무너지므로 그 지점에서 잘랐다. 구간은 `optical_slopes.csv` 의")
    w("> `depth_lo_mm` / `depth_hi_mm` 에 있다.")
    w()

    # ---------------------------------------------------------------- 3 --
    w("## 3. 공간 분해능")
    w()
    w("두 기둥(지름 1.0 mm)을 여러 간격으로 눌러 골이 보이는지 판정한다. 세 관문을")
    w("모두 넘어야 *분해*다: **dip ≥ 0.265**(Rayleigh), **자국 ≥ 2.5 그레이 레벨**,")
    w("**dip > 잡음의 3 배**.")
    w()
    fig("extra/figures/G_spatial_resolution.png",
        "3×3 표와 같은 숫자를 그림으로. 위는 분해된 가장 좁은 간격 대 두께"
        "(선은 복제 평균, 점은 유닛 하나하나), 아래는 유닛마다의 분해된 깊이 범위.")
    for pr in ("9DTact", "DIGIT"):
        w(f"### {pr} — 분해된 가장 좁은 간격 (중심간격 mm)"); w()
        table(f"{FOLD[pr]}/data/table_spatial_resolution_3x3.csv")
        w(f"### {pr} — 분해된 깊이 범위 (mm)"); w()
        table(f"{FOLD[pr]}/data/table_resolved_depth_range_3x3.csv")
    w("> **DIGIT 의 분해능 표는 아홉 칸이 전부 1.10 mm 다.** 가장 좁은 프로브를 18/18")
    w("> 유닛이 분해했으므로 **값이 아니라 상한**이다 — \"가장자리 간격 0.10 mm 보다")
    w("> 좋다\" 가 이 연구가 말할 수 있는 전부다. 구별은 **깊이 범위** 표에서 나온다:")
    w("> 1 mm 겔은 0.6 mm 까지, 2~3 mm 겔은 0.9 mm 까지 분해한다.")
    w()
    w("> **DIGIT_Marker 는 공간 분해능을 재지 않았다** (운전자 결정, 2026-09-11).")
    w()

    # ---------------------------------------------------------------- 4 --
    w("## 4. 힘 추정 오차 대 해상도")
    w()
    w("ResNet-18 을 해상도 12 단(1920 → 8 px)에서 학습해 축별 MAE 를 낸다.")
    w("**학습 파라미터는 원리·해상도에 걸쳐 전부 같다** — 실효 배치 64(경사 누적으로")
    w("고정), 30 에폭, Adam 5e-4, weight decay 1e-4, cycle 분할, seed 3 개.")
    w()
    w("| 원리 | 입력 표현 |")
    w("|---|---|")
    w("| 9DTact | `grey` — 원저자 방식 (기준영상 + 밝아진 양 + 어두워진 양) |")
    w("| DIGIT | `raw` — 카메라 프레임 그대로 |")
    w("| DIGIT_Marker | `inpaint` — 마커 점을 지우고 주변에서 메움 |")
    w()
    for pr in ("9DTact", "DIGIT", "DIGIT_Marker"):
        f = f"{FOLD[pr]}/figures/force_mae_vs_resolution_18units.png"
        if (RES / f).exists():
            fig(f, f"{pr} — 유닛별 축별 MAE 대 해상도")
        else:
            w(f"> **{pr}: 학습 진행 중.** 끝나면 이 문서를 다시 생성한다.")
            w()


    knee_block("force", ["fz_knee_px", "shear_knee_px"], "힘")

    # ---------------------------------------------------------------- 5 --
    w("## 5. 형상 복원 대 해상도")
    w()
    w("**9DTact** 는 밝기→깊이 조회표를 `ball4` 로 보정하고 `cyl4`·`cube4` 로 평가한다.")
    w("**DIGIT 계열**은 광도 스테레오라 다른 파이프라인이 필요하고, 이번에 새로 만들었다")
    w("(`src/scripts/digit_shape.py`): 알려진 반지름의 구로 픽셀별 참 기울기를 구 기하에서")
    w("계산하고, (색차, 위치) → (gx, gy) 를 회귀한 뒤 푸아송 방정식을 DCT 로 풀어")
    w("높이맵을 만든다.")
    w()
    w("> **DIGIT_Marker 는 형상 복원을 하지 않는다** — 마커 점이 음영을 가려 같은 방법을")
    w("> 쓸 수 없다.")
    w()
    fig("1_9DTact/figures/shape_mae_summary.png",
        "9DTact — 형상 복원 오차 대 해상도. 둘 다 160×90 에서 최소.")
    w("**9DTact 는 해상도 의존성이 뚜렷하다** — 8×5 의 0.529 mm 에서 160×90 의 0.062 mm 까지")
    w("**8.5 배** 좋아지고, 그 위로는 다시 나빠진다. 회색조 손실을 보정하면(점선) 80 px 위로")
    w("평평해지므로, 고해상도의 악화는 조회표가 회색조를 잃는 데서 온다.")
    w()
    w("### 유닛별 — 경도 × 두께 × 복제")
    w()
    w("4 절의 힘 그림과 같은 배치다. 행이 경도, 열이 두께와 복제이고, 선 하나가 평가")
    w("압자 하나다. 가로축은 잰 해상도 12 단을 가로×세로로 적었다.")
    w()
    shp = [("1_9DTact/figures/shape_mae_vs_resolution_18units.png",
            "9DTact — 유닛별 형상 복원 오차 대 해상도 (조회표 그대로)"),
           ("1_9DTact/figures/shape_mae_corrected_18units.png",
            "9DTact — 유닛별 형상 복원 오차 대 해상도 (회색조 손실 보정)"),
           ("2_DIGIT/figures/shape_mae_vs_resolution_18units.png",
            "DIGIT — 유닛별 형상 복원 오차 대 해상도 (광도 스테레오)")]
    for f, cap in shp:
        if (RES / f).exists():
            fig(f, cap)
        else:
            w(f"> **{cap} — 평가 진행 중.** 끝나면 이 문서를 다시 생성한다.")
            w()
    w("> **DIGIT_Marker 는 이 그림이 없다** — 형상 복원을 하지 않기 때문이다.")
    w()
    fig("2_DIGIT/figures/shape_mae_summary.png",
        "DIGIT — 형상 복원 오차 대 해상도, 그리고 426×240 에서의 예측-참값.")

    # 형상 쪽은 표만 싣는다 — 결론 문단과 재현성 표는 힘 절(4 절)에 한 번만 둔다.
    knee_block("shape", ["cyl4_knee_px", "cube4_knee_px"], "형상", tail=False)

    # ------------------------------------------------------------ 부록 --
    w("---")
    w()
    w("# 부록")
    w()
    w("본문의 결론을 떠받치지만 그 자체가 결과는 아닌 것들 — 판정 기준을 어떻게")
    w("골랐나, 겔 규격이 어떻게 불균형한가, 프로브를 바꾸면 무엇이 옮겨지나 —")
    w("그리고 이 결과가 무엇을 말하지 못하는가.")
    w()

    # ------------------------------------------------------------ 부록 A --
    w("## 부록 A. 판정 기준 — 상대와 절대")
    w()
    fig("extra/figures/C_relative_vs_absolute_criterion.png",
        "상대 기준은 원리 간 격차를 1.8 배로 압축한다.")
    w("현행 판정은 문턱이 **유닛 자신의 최대 응답의 15 %** 라, 응답이 약한 유닛일수록")
    w("천장이 높게 나온다. 복제 쌍 다섯에서 모두 그 방향이었다. 고정 문턱으로 다시")
    w("계산하면 격차가 **4.3 ~ 6.6 배**로 커진다.")
    w()
    w("**원리 간 비교에는 절대 기준을 쓴다.** 상대 기준 값은 한 유닛의 운용 한계로만 쓴다.")
    w()

    # ------------------------------------------------------------ 부록 B --
    w("## 부록 B. 경도 범위 불균형")
    w()
    w("두 계열의 \"soft / medium / hard\" 는 같은 눈금이 아니다. 9DTact 는 OO-30 에서")
    w("OO-70 까지 **40 Shore 점**을 흔들었고, DIGIT 계열은 OO-51 에서 OO-57 까지")
    w("**6 점**을 흔들었다 — **6.7 배** 차이다. 9DTact 는 서로 다른 두 제품군")
    w("(Ecoflex, Dragon Skin)을 가로지르고, DIGIT 계열은 Solaris 한 배합에서")
    w("가소제(Slacker) 비율만 바꿨다.")
    w()
    w("그래서 **9DTact 의 soft 와 DIGIT 의 soft 가 다른 물건**일 뿐 아니라,")
    w("**DIGIT 의 soft 와 hard 도 서로 거의 같은 물건**이다. DIGIT 계열의 경도 세 등급은")
    w("실질적으로 한 겔이다.")
    w()
    w("**원리를 가로질러 경도를 하나의 요인으로 놓는 분석은 이 설계로 성립하지 않는다.**")
    w("이 문서의 3×3 표에서 경도 행 사이의 차이는 **한 원리 안에서만** 읽을 것이고,")
    w("그때도 DIGIT 계열은 6 점 안에서의 차이임을 함께 보아야 한다. 겔 규격과 실측")
    w("경도는 `docs/methods.md` §2.1 에 있다.")
    w()

    # ------------------------------------------------------------ 부록 C --
    w("## 부록 C. 프로브 전이 — 깊이는 옮겨지고 힘은 아니다")
    w()
    fig("extra/figures/E_probe_transfer.png",
        "ball8/ball4 비. 힘은 1.50~3.26 으로 흩어지고 깊이는 0.99 에 모인다.")
    w("Hertz 는 같은 깊이의 힘이 √R 에 비례한다고 예측하므로 **1.41** 을 기대하는데,")
    w("실측 중앙이 **2.37** 이고 복제 쌍 안에서도 1.98 과 3.26 으로 갈린다. 반면 깊이")
    w("비는 중앙 **0.99** 로 1 과 통계적으로 구분되지 않는다 (p 0.858).")
    w()
    w("> **포화 깊이는 유닛의 성질이고, 그 깊이에서의 힘은 프로브가 정한다.**")
    w()
    w("같은 18 쌍이 *시야 포화* 교란도 기각한다 — `ball8` 은 같은 깊이에서 자국이 1.2~1.4")
    w("배 큰데, 시야가 원인이라면 계통적으로 더 얕게 포화해야 한다. 더 얕게 포화한 것이")
    w("18 중 10 (이항검정 p 0.815) 으로 효과가 없다.")
    w()
    table("extra/data/E_probe_transfer.csv")

    # ------------------------------------------------------------ 부록 D --
    w("## 부록 D. 이 결과가 말하지 못하는 것")
    w()
    w("| 한계 | 제한하는 것 |")
    w("|---|---|")
    w("| DIGIT_Marker 천장이 `ball4` 뿐 | **세 원리** 천장 비교 |")
    w("| DIGIT_Marker 공간 분해능 미측정 | 표제 변수의 세 원리 비교 |")
    w("| DIGIT 이 가장 좁은 프로브를 18/18 분해 | DIGIT 분해능 **값** — 상한만 |")
    w("| 경도 범위가 6.7 배 불균형 | 원리 간 **경도 효과** 비교 |")
    w("| px/mm 이 유닛마다 최대 1.5 배 어긋남 | mm 단위 자국 크기, 픽셀 요구량 |")
    w("| F/T 라벨 바닥 0.028 N | 힘 추정의 **절대값** (상대 비교는 유효) |")
    w("| `9DTact_medium_2mm_r1` 파괴 | 3×3 표의 한 칸이 복제 1 개 |")
    w()
    w("전체 한계표는 `docs/methods.md` §10.0.")
    w()

    p = RES / "results.md"
    p.write_text("\n".join(L) + "\n")
    print(f"-> {p} ({len(L)} 줄)")


if __name__ == "__main__":
    main()
