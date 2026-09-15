# 그림 캡션 — 본문에 붙일 것                                   rev. 2026-09-15b

`Hyeokgyu_Han_shortened.docx` 의 그림 여섯 칸에 맞춘 캡션 초안이다. 영문 본문이므로
캡션도 영문이고, **각 캡션이 왜 그 문장을 져야 하는지**는 해당 `paper_fig_*.py` 의
머리글에 있다. 숫자는 전부 `fin_figures/*.csv` 에서 가져왔다.

> **본문의 그림 번호가 지금 어긋나 있다.** 본문이 부르는 것은 `Fig. 1a` · `Fig. 2`
> (둘) · `Fig. 3b` `3c` `3d` `3e` 뿐인데, 문서에는 그림 칸이 여섯이다. 아래 §7 이
> 무엇을 무엇으로 고쳐야 하는지 적는다.
>
> **2026-09-15b — 그릴 수 있는 것을 다 그렸다.** 경도 눈금(`fig_hardness`) ·
> 광도 기울기(`fig_slope`) · 합력(`fig_resultant`) 셋이 늘었다. 캡션은 §9 에
> 있고, **열한 장이 본문에 다 들어가지는 않는다** — §10 이 지면을 셈한다.

---

## Fig. 1 — 센서 하드웨어 (III.A)  · 폭발도 두 장

**[AUTHOR CHECK] A1 ~ A8 · B1 ~ B6 의 이름이 그림에도 본문에도 없다.** 아래 괄호는
[III-A2] 의 적층 순서로 **추정한 것**이라 저자가 확인해야 한다. 특히 **어느 층이
1 / 2 / 3 mm 로 바뀌는가**는 이 논문의 독립변수이므로 캡션이 반드시 짚어야 한다.

> **Fig. 1.** Exploded views of the two sensor bodies. (a) Depth-referenced body
> (9DTact-type): A1 black skin (0.5 mm), A2 translucent sensing layer (**1, 2, or
> 3 mm — the varied layer**), A3 transparent silicone base (4.5 mm), A4 acrylic
> window (2 mm), A5 gel frame, A6 camera module, A7 illumination board, A8 housing.
> (b) Photometric body (DIGIT-type): B1 white reflective skin, B2 transparent gel
> (**1, 2, or 3 mm — the varied layer**), B3 acrylic window (3 mm) and frame,
> B4 camera module, B5 illumination board, B6 housing. Within a family every unit
> is the same body with only the gel module exchanged, so a within-family
> comparison is a gel comparison. "Thickness" throughout this paper refers to the
> varied layer only; the depth-referenced stack carries a further 4.5 mm compliant
> layer beneath it that the photometric stack does not, which is taken up in
> Section IV-C. The marker variant uses body (b) unchanged and differs only in the
> gel, which carries a printed dot grid 0.5 mm below the reflective layer.

---

## Fig. 2 — 압입 장치 (III.C)  · 리그 사진, 콜아웃 (a) ~ (e)

**[AUTHOR CHECK] (a) ~ (e) 가 무엇인지 사진에도 본문에도 없다.** 아래는 빈칸이다 —
[III-C1] 이 부르는 이름(FR5 flange · ATI Mini45 · probe · gel module · mount)으로
채우되 **사진에서 실제로 보이는 것**과 맞아야 한다.

> **Fig. 2.** Indentation rig. (a) …, (b) …, (c) …, (d) …, (e) …. The probe is
> carried by the FR5 flange through the ATI Mini45 six-axis force/torque sensor;
> the gel module is clamped to the optical table. Scale bar: … mm.

**모자란 것 둘** (`figure_plan.md` §F2 와 같은 지적)
- **스케일 바가 없다.**
- **F/T 셀이 흰 마운트에 가려 보이지 않는다.** 힘을 어디서 재는지가 이 논문 신뢰도의
  절반이므로, 셀이 보이는 각도의 사진이 있으면 그쪽이 낫다.

---

## Fig. 3 — 두 접촉 분리 (IV.B)  · `fig_separation`

> **Fig. 3.** Two-contact separation. (a) Finest centre spacing resolved at full
> resolution against gel thickness, depth-referenced configuration, nine
> specimens, one per cell; colour gives the measured Shore OO hardness. A specimen
> counts as resolving a spacing if any rung of its depth ladder passes the signal,
> noise, and Rayleigh gates of Section IV-B. The finest spacing follows thickness
> (Spearman ρ = +0.75, p = 0.021, n = 9) and not hardness (|ρ| ≤ 0.32, p ≥ 0.41).
> The narrowest probe we could make has a centre spacing of 1.10 mm and all nine
> photometric specimens resolved it, so for that family the measurement is an
> upper bound on the resolvable spacing and no floor was reached; the photometric
> family is therefore not plotted. (b) The same decision applied to down-scaled
> frames, for the 2.00 mm pair at 0.30 mm indentation on one specimen (soft,
> 2 mm) — the only one of the nine that resolved this pair at every depth rung at
> full resolution, so that what the gel cannot do is not mixed into what the pixels
> cannot do. The dashed line is the Rayleigh threshold, Dip = 0.265; the pair
> separates from R ≈ 4.9 px/mm² upward. The × at the left marks a rung where the
> contact was not detected at all, which is a different failure from a trough too
> shallow to pass. One specimen per cell, so there are no error bars; between-build
> scatter is quoted in Section VI-A.

**왜 이 문장들인가** — 그림 안의 글자와 보조선을 걷어냈으므로(운전자 결정,
2026-09-15) 패널 이름 · 1.10 mm 바닥 · 파선의 뜻 · `×` 의 뜻 넷을 캡션이 진다.

---

## Fig. 4 — 영상 응답 포화 (IV.C)  · `fig_ceiling`

> **Fig. 4.** Image-response ceiling against gel thickness, ⌀8 mm sphere.
> (a) Depth-referenced, (b) photometric; colour gives the measured Shore OO
> hardness. Saturation is defined per unit as the force at which the image change
> per newton has fallen to 15 % of that unit's own maximum response, so the
> ordinate rests on a relative criterion and **values must not be compared between
> panels**; the vertical scales differ as well. The ceiling rises with thickness in
> (a) (ρ = +0.63, p = 0.068) and falls in (b) (ρ = −0.90, p = 0.001); hardness is
> not associated in either (ρ = +0.37, p = 0.33; +0.05, p = 0.89), n = 9 per panel.
> The two panels do not test hardness equally — OO-30/50/70 spans 40 points against
> the 6 points of OO-51/54/57. The marker configuration is not shown because it was
> indented with a different probe (Table II). One specimen per cell, no error bars.

**[AUTHOR CHECK] p 를 어느 자로 적을 것인가.** 위는 본문 [IV-C2] 와 같은 점근 p 다.
정확 순열 p 는 **0.089 / 0.004** 로 셋 다 더 크고 `fig_ceiling_stats.csv` 에 함께
있다. n = 9 에 수준이 셋이라 정확 p 가 더 방어되지만, BH 보정이 점근 p 위에서
돌았으므로 **바꾸려면 다른 절의 p 도 함께** 바꿔야 한다.

---

## Fig. 5 — 힘 추정 (V.A)  · `fig_force`

> **Fig. 5.** Force-estimation error against pixel density R. Rows: depth-
> referenced (a, b), photometric (c, d), photometric with markers (e, f). The left
> column splits the nine specimens of each configuration by gel thickness and the
> right column splits **the same nine** by hardness, so the thin lines are identical
> between the two columns and only the group medians change. Thin line: one
> specimen, median over training seeds, plotted at that specimen's own pixel
> density. Thick line: median of the three specimens of a group, pooled by ladder
> rung. In neither split do the three group medians leave the spread of the
> individual specimens — the between-group spread is 0.29 to 0.67 times the
> between-specimen spread at the same rung. The triangle under each axis is the
> plateau density at τ = 10 %, taken as the median of the nine per-unit values
> (17.3, 13.3, 23.0 px/mm²); it is the same in both columns because the two columns
> divide the same nine specimens. Normal force only; shear is in Table VI. **The
> vertical scale differs between rows and values must not be compared across them**
> — the three configurations were trained on different input representations
> (three-channel, raw colour, inpainted). Hardness is labelled by measured Shore
> OO: a 40-point range in (b) against a 6-point range in (d) and (f). One specimen
> per cell, no error bars; the null result is a limit of detection, not a
> demonstration of independence (Section VI-A).

---

## Fig. 6 — 형상 복원 (V.B)  · `fig_shape`

> **Fig. 6.** Shape reconstruction against pixel density R. Top row, depth error;
> bottom row, error of the recovered lateral size; (a, c) depth-referenced,
> (b, d) photometric. Solid blue, ⌀4 mm cylinder; dashed red, 4 mm cube. The line
> is the median of the nine specimens and the band their interquartile range, which
> is between-specimen scatter and not a measurement uncertainty. Triangles mark the
> τ = 10 % plateau density (median of the per-unit values): 5.5 and 4.9 px/mm² in
> (a), 2.2 and 83.2 px/mm² in (b) — a factor of 38 between two probes on one
> sensor, against 1.13 between the same two probes on the other. **The vertical
> scales of (a) and (b) differ and must not be compared**, because the two
> pipelines are scored over different depth ranges. (c) and (d) share a scale:
> both measure the same ⌀4 mm probe and zero is the true 4 mm in each. The sign is
> not folded — reading large and reading small are different failures. The × marks
> a rung at which not all nine specimens returned a reconstruction; the line and
> band are drawn only where all nine did, because at the lowest rung six of the
> nine depth-referenced specimens returned no value and a median there would be a
> median of survivors. Bands that reach the top of (d) are clipped, not absent.

---

## 7. 본문의 그림 번호를 고칠 것

본문이 부르는 번호가 지금 문서의 그림 순서와 어긋난다.

| 본문 | 지금 가리키는 것 | 고칠 것 |
|---|---|---|
| `Fig. 1a` [III-A1] | 폭발도 (a) | 그대로 |
| `Fig. 2` [V-A4] ×2 | 힘 곡선 | **`Fig. 5`** |
| `Fig. 3c` [V-B3] | 깊이 오차 대 R | **`Fig. 6a, 6b`** |
| `Fig. 3d` [V-B5] | 가로 크기 | **`Fig. 6c, 6d`** |
| `Fig. 3b` [V-B2] | 광도 계열의 유닛별 기울기 (0.16 ~ 0.92) | **없는 패널이다** — §8 A 참조 |
| `Fig. 3e` [V-B3] | 겔로 나눈 형상 곡선 | **없는 패널이다** — 형상은 겔로 나누지 않았다. 문장을 표(ρ, q)로 돌리는 것이 맞다 |
| — | 분리(Fig. 3) · 천장(Fig. 4) | **본문이 한 번도 부르지 않는다.** IV-B2 와 IV-C2 에 참조를 넣을 것 |

---

## 8. 더 넣을 수 있는 그림

### A. IV.A 자국 성장 — **이미 그려져 있는데 문서에 칸이 없다** ★ 가장 아깝다

`fig_growth` (`paper_fig_growth.py`) 가 `fin_figures/` 에 있다. 지금 IV.A 는 Table III
하나로 서 있는데, 이 절의 주장은 **같은 자국·같은 램프인데 x 축만 바꾸면 이기는
변수가 바뀐다**는 것이라 그림이 아니면 전달되지 않는다.

**넣기 전에 맞춰야 할 것** — 그림은 기준점을 깊이 1.03 mm · 힘 1.80 N 으로 잡았고
본문 Table III 은 다른 기준점이다. 배수가 어긋난다:

| | 본문 [IV-A2/A3] | `fig_growth` |
|---|---:|---:|
| 지름, 깊이 × 두께 | 1.33 | 1.33 ✓ |
| 지름, 깊이 × 경도 | 1.10 | 1.16 |
| 지름, 힘 × 두께 | 1.01 | 1.04 |
| 밝기, 힘 × 경도 | 1.91 | **2.00** |

**기준점을 하나로 정하고 그림·표·본문이 같은 값을 쓰게 할 것.** 그러지 않으면 같은
양이 두 값으로 나온다.

### B. 광도 계열의 유닛별 기울기 — 본문이 `Fig. 3b` 로 이미 부르고 있다

"slope of predicted against true depth varied from 0.16 to 0.92 between units" 는
지금 가리킬 그림이 없다. **이 기계에서 그릴 수 있다** —
`result/single/2_DIGIT/data/shape_predictions.csv` 에 유닛 × 단별
`depth_true_mm` · `depth_pred_mm` 가 있다(1 044 행). 1 단 그림 한 장이면 된다.

### C. 합력 오차 — V-A5 가 글로만 말한다

`result/single/extra/data/I_resultant_force.csv` 가 저장소에 있어 그릴 수 있다.
옌센 하한이 실측의 **0.86 ~ 0.90 배**였고 **평탄점의 위치는 하한과 실측이 같았다** —
하한이 얼마나 잘 버텼는지가 그 자체로 방법에 대한 결과다. 다만 Fig. 5 와 같은
이야기를 두 번 하므로 **지면이 [대기] 다** (`figure_plan.md` §3.1).

### D. 경도 눈금 불균형 — III.B 로 올릴 것

`result/single/extra/figures/D_hardness_range_imbalance.png` 가 있다(자료도 함께).
"경도 효과가 검출되지 않았다" 는 **40 점 대 6 점**을 먼저 본 독자에게만 정직하게
읽힌다. 지금은 [III-B1] 문장과 Table I 뿐이다. 논문 판으로 다시 그려야 한다 —
`result/` 그림은 Okabe-Ito 라 `paper_style` 로 옮겨야 한다.

### E. 못 그리는 것 (실험 기계 몫)

- **F6 (a) 높이맵** 320 · 80 · 16 px — 원영상 필요.
- **F6 (d) 전처리 스케일** — 옛 커널 팔 자료가 없다. `shape_reconstruction.md`
  §6.5a 표는 17 유닛(54 유닛 집합)이라 `CLAUDE.md` §1 에 걸려 그대로 쓸 수 없다.
- **F3 의 DIGIT 판** — `make_optical_curves.py:501` 을 풀고 재실행.
- **Fig. 5 의 전단 열** — 정본 전단은 seed 단위 `(Fx+Fy)/2` 의 중앙값인데 저장소
  csv 는 축별 중앙값만 담는다.
- **프로브 5 종 접사** — 사진이 없다. IV.B 전체가 두 기둥 압자에 걸려 있는데 지금
  어느 그림에도 그 형상이 없다.

---

## 9. 새로 그린 셋 — 캡션

### `fig_hardness` — 두 계열이 흔든 경도 폭 (III.B)

> **Fig. N.** Measured Shore OO hardness of the three grades in each family. Each
> point is measured on the cured material, not a manufacturer's nominal value; the
> bar spans the range the family covers. The depth-referenced family spans 40
> points (OO-30 to OO-70) and crosses two product lines (Ecoflex to Dragon Skin),
> whereas the photometric family spans 6 points (OO-51 to OO-57) obtained by
> changing only the plasticiser ratio of one formulation — a 6.7-fold difference in
> the range varied. Every hardness result in this paper must therefore be read
> within a family, and for the photometric family within that narrow range. Marker
> gels are cast from the photometric formulations and are not plotted separately,
> though they measured stiffer under a sphere (Section III-B).

이 그림 하나가 V 장의 "경도 효과 미검출" 을 정직하게 만든다. 1 단이고 높이가
1.6 in 이라 **지면당 정직함의 값이 가장 싸다.**

### `fig_slope` — 광도 계열의 복원 깊이 기울기 (V.B)

> **Fig. N.** Reconstructed against commanded indentation depth for the nine
> photometric specimens, full resolution, ⌀4 mm cylinder; the dotted line is 1:1
> and colour gives gel thickness. Within a specimen the reconstruction is linear
> (r = 0.93 to 1.00), but the slope differs between specimens (0.23 to 0.78) and no
> specimen reaches unity: the visible contact cap is shallower than the probe
> travel, by an amount that differs from unit to unit. Absolute photometric depths
> are therefore specific to a unit, and only the shape of the error-versus-density
> curve is compared across units (Fig. N+1). The slope also tracks thickness
> (ρ = +0.69, p = 0.042, n = 9, uncorrected), which this study reports as an
> observation and does not use as a claim.

**[AUTHOR CHECK] 본문의 "0.16 to 0.92" 를 고쳐야 한다.** 분석 집합 아홉 시편의
전해상도 자유적합은 **0.23 ~ 0.78** (원기둥) · 0.17 ~ 0.73 (정육면체)이다. 원점을
지나게 맞추면 0.49 ~ 1.02, 54 유닛 집합이면 0.05 ~ 0.88 — 어느 쪽도 0.16 ~ 0.92 가
아니다. 저장소 밖에서 온 값이므로 그림을 실으려면 문장을 그림의 값으로 바꾼다.

### `fig_resultant` — 합력 오차와 옌센 하한 (V.A)

> **Fig. N.** Resultant force error against pixel density R. (a) Depth-referenced,
> (b) photometric, (c) photometric with markers. The solid line is the measured
> resultant MAE from a retrained run; the dashed line is the Jensen lower bound
> L = (MAE_x² + MAE_y² + MAE_z²)^½ computed from the per-axis errors, and the band
> runs from that bound to the triangle-inequality upper bound, so the true value
> can lie anywhere inside it. The bound ran at 0.86 to 0.90 of the measured value
> and held at 35 of 36 rungs; at the one exception (c, 160 px) the two come from
> different training runs. The triangle is the τ = 10 % plateau **of this pooled
> curve**, which is a different statistic from the per-unit median marked in
> Fig. N(force) and the two must not be mixed. Normal force contributes 51 to 82 %
> of the sum of squares at every density, so the resultant curve inherits the shape
> of the Fz curve. Vertical scales differ between panels and must not be compared.

**[AUTHOR CHECK] 계획서 §3.1 의 "평탄점의 위치는 하한과 실측이 같았다" 는 정정이
필요하다.** 같은 110 % 규칙으로 다시 내면 깊이 참조형만 맞는다 — 실측 13.65 대
하한 13.65 ✓, DIGIT **2.93 대 18.33**, Marker **22.57 대 361.15**. 광도 두 계열
에서는 실측 곡선이 바닥 근처에서 더 평평해 평탄점이 하한보다 **낮은** 밀도에서
잡힌다. 하한은 크기뿐 아니라 요구 밀도도 보수적으로 잡는다.

### `fig_growth` — 기준점을 본문과 맞출 것 (IV.A)

그림은 이미 있다. 넣기 전에 **기준점 하나**를 정해야 한다. 그림은 세 군이 함께
있는 x 의 중앙(깊이 1.03 mm · 힘 1.80 N)을 쓰고 본문 Table III 는 다른 점을 썼다:

| | 본문 | 그림 | 기준점을 옮기면 |
|---|---:|---:|---|
| 지름 · 깊이 × 두께 | 1.33 | 1.33 ✓ | 1.53 → 1.31 |
| 지름 · 깊이 × 경도 | 1.10 | 1.16 | 1.29 → 1.21 |
| 지름 · 힘 × 두께 | 1.01 | 1.04 | 1.60 → 1.03 |
| 밝기 · 힘 × 경도 | 1.91 | 2.00 | 1.78 → 1.98 |

**자료가 다른 것이 아니라 기준점이 다르다** — `paper_fig_growth.py` 의 실행 출력이
민감도를 함께 찍는다. 본문 값은 대체로 더 깊은·더 큰 하중 쪽이지만 저장소 csv 에서
그 점을 정확히 되찾지는 못했다(Table III 는 실험 기계에서 나왔다). **Table III 를
이 csv 에서 다시 내거나, 기준점을 둘 다에 적고 그림 값을 쓰거나** 둘 중 하나.

---

## 10. 지면 — 열한 장이 다 들어가지 않는다

`figure_plan.md` §0.2 의 예산은 그림 여섯에 ≈ 1.8 쪽이었다. 지금 그릴 수 있는 것이
열하나다(흐름도 · 폭발도 · 리그 · 경도 · 자국 성장 · 분리 · 천장 · 힘 · 합력 ·
형상 · 기울기). 어림 3.4 쪽이라 본문·표와 합치면 **8 쪽을 1 쪽 넘게 넘어간다.**

| 그림 | 단 | 어림 | 판단 |
|---|---|---:|---|
| 흐름도 (설계 결정) | 2 | 0.35 | **본문** — 이 논문이 왜 이 세 변수인지를 세운다 |
| 폭발도 | 2 | 0.35 | **본문** — 적층 단면 없이는 IV.C 가 글로만 남는다 |
| `fig_hardness` | 1 | 0.15 | **본문** — 가장 싸고 가장 정직하다 |
| `fig_growth` | 2 | 0.35 | **본문** — IV.A 가 지금 표 하나로 서 있다 |
| `fig_separation` | 2 | 0.30 | **본문** |
| `fig_ceiling` | 2 | 0.30 | **본문** |
| `fig_force` | 2 | 0.50 | **본문** — 중심 음성 결과 |
| `fig_shape` | 2 | 0.45 | **본문** — 중심 양성 결과 |
| 리그 사진 | 1 | 0.20 | **보충** — Table II 와 III.C 본문이 덮는다 |
| `fig_resultant` | 2 | 0.30 | **보충** — Fig. 힘과 같은 이야기를 두 번 한다 |
| `fig_slope` | 1 | 0.25 | **보충** 또는 본문 — V-B2 한 문장을 받친다. 보충으로 내리면 그 문장에서 그림 참조를 빼야 한다 |

여덟을 본문에 두면 ≈ 2.75 쪽이다. 셋을 보충으로 내리는 것이 §0.2 예산에 가장
가깝다. **리그 사진과 합력을 먼저 내리는 것을 권한다** — 전자는 표가 덮고 후자는
중복이다.
