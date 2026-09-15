# 원고 점검 — 그림·표 배치와 캡션 다시 쓰기          rev. 2026-09-15

대상: `ICRA2027_Hyeokgyu_Han.docx` (그림 10 · 표 5), 기준: IEEE 회의 템플릿
(`ieeeconf_letter.dot`) · `CLAUDE.md` · `paper/figure_plan.md` · `paper/fin_figures/`.

템플릿이 배치에 거는 것은 넷이다 — **그림·표는 단의 위나 아래에 두고 가운데를
피한다 · 큰 것은 두 단을 가로지른다 · 캡션은 그림 아래·표 머리는 표 위 ·
본문이 인용한 다음에 넣는다.** 아래는 그 넷과 자료 일치를 함께 본 것이다.

---

## 0. 한눈에

| | 상태 |
|---|---|
| 캡션이 표·그림 위/아래로 제자리에 있나 | **통과** — 표 머리 다섯 다 위, 그림 캡션 열 다 아래 |
| 본문이 그림을 제대로 부르나 | **열 장 중 아홉이 인용 없음**, 남은 인용은 번호가 틀렸다 |
| 표 번호가 맞나 | **본문이 부르는 표 둘이 문서에 없다**, 나머지는 두 칸 밀렸다 |
| 두 단 그림이 두 단을 쓰나 | **열 장 전부 한 단(3.43 in)** — 글자가 4.5 ~ 5.3 pt 로 눌린다 |
| 캡션이 그림과 맞나 | **여섯이 자리표시자거나 옛 판 설명** (3 · 4 · 5 · 6 · 9 · 10) |
| 표 제목이 표와 맞나 | **III · IV 가 없는 열을 약속한다** |

고치는 차례: **C(판형) → A·B(번호) → E(캡션) → F(자료 오류)**. C 를 먼저
하는 것은 단을 가로지르게 바꾸면 그림이 통째로 다른 자리에 떨어져 A 를 두 번
하게 되기 때문이다.

---

## A. 본문이 그림을 부르지 않는다 — 부르는 것도 번호가 틀렸다

템플릿: *"Insert figures and tables after they are cited in the text."*

| 본문 자리 | 지금 적힌 것 | 실제로 가리키는 그림 |
|---|---|---|
| `[III-A1]` | `Fig. 1a` | 두 바디를 함께 말하는 문장이므로 **`Fig. 1`** (패널 지정 불필요) |
| `[V-A4]` (두 번) | `Fig. 2` | **힘 오차 그림** (지금 Fig. 7) |
| `[V-B2]` | `Fig. 3b` | **해당 패널이 문서에 없다** — 광도 계열의 예측·참 깊이 기울기(0.16 ~ 0.92) 그림. 넣든지 인용을 빼든지 정해야 한다 |
| `[V-B3]` | `Fig. 3c`, `Fig. 3e` | **`Fig. 8a`**, 그리고 겔로 나눈 곡선은 **`Fig. 9`** |
| `[V-B5]` | `Fig. 3d` | **`Fig. 8c` · `Fig. 8d`** |

**인용이 아예 없는 그림: 2 · 4 · 5 · 6 · 7 · 8 · 9 · 10.** 여덟 장이 본문과
끈이 없다. Fig. 5(포화 천장)는 `[IV-C2]` 가, Fig. 4(두 접촉)는 `[IV-B2]` 가,
Fig. 9(평탄 밀도)는 `[V-A4]`·`[V-B3]` 가 자연스러운 자리다.

## B. 표 번호가 두 칸 밀렸다 — 본문이 부르는 표 둘이 없다

| 본문 자리 | 지금 적힌 것 | 문제 |
|---|---|---|
| `[III-B4]` | `Table II` (구성별 측정 항목) | **그 표가 없다.** `figure_plan` §5 의 "시편·평가 항목 커버리지" 표다 |
| `[III-C2]` | `Table II` (프로브 넷) | 같은 표를 가리킨다 |
| `[IV-A1]` | `Table III` (군 중앙값 배수) | **그 표가 없다.** 그 내용은 지금 Fig. 3 이 그림으로 진다 |
| `[IV-C3]` | `Table V` (포화 깊이) | 실제로는 천장 표 = 지금 `Table III`. 게다가 그 표에 깊이 열이 없다(§D) |
| `[V-A3]` `[V-A4]`(3회) `[VI-A1]`, Fig. 7 캡션 | `Table VI` | **없는 번호.** 힘 표 = 지금 `Table IV` |
| — | — | `Table V`(형상)는 본문 인용이 하나도 없다 |

### 권하는 정리 — 표 하나를 더하고 하나를 버린다

커버리지 표는 본문이 두 번 부르므로 **넣는 것**이 맞고(`figure_plan` §5 도
남길 표로 지정), 자국 배수 표는 Fig. 3 과 겹치므로 **버리고** `[IV-A1]` 이
Fig. 3 을 가리키게 한다.

| 새 번호 | 내용 | 지금 |
|---|---|---|
| I | 조성과 실측 쇼어 | I |
| **II** | **구성 × 프로브 × 측정 항목 커버리지** | **없음, 새로 만든다** |
| III | 분해된 가장 좁은 중심 간격 | II |
| IV | 영상 응답 천장 (+ 포화 깊이 열) | III |
| V | 힘 추정 | IV |
| VI | 형상 복원 | V |

이렇게 하면 `[III-B4]`·`[III-C2]` 의 `Table II` 와 `[V-*]`·`[VI-A1]` 의
`Table VI` 가 **고치지 않아도 맞는다.** 고칠 것은 `[IV-A1]`(표 → Fig. 3),
`[IV-C3]`(`Table V` → `Table IV`), 그리고 `[V-B1]` 에 `Table VI` 인용 한 줄뿐이다.

## C. 두 단 그림이 한 단에 들어가 있다 — 이것이 가장 큰 배치 문제

문서에 `sectPr` 가 하나뿐이고 `w:cols num="2"` 이다. **두 단을 가로지르는
그림이 하나도 없다** — 열 장 전부 247 pt(3.43 in) 한 단 폭이다.

`fin_figures` 가 그린 원본 판형과 대면:

| 그림 | 원본 폭 | 문서 폭 | 배율 | 9 pt 글자가 |
|---|---:|---:|---:|---:|
| Fig. 3 자국 성장 | 6.86 in | 3.43 | 0.50× | **4.5 pt** |
| Fig. 4 두 접촉 | 6.10 | 3.42 | 0.56× | **5.0 pt** |
| Fig. 5 포화 천장 | 5.80 | 3.42 | 0.59× | **5.3 pt** |
| Fig. 6 요구 해상도 | 6.27 | 3.42 | 0.55× | **4.9 pt** |
| Fig. 9 평탄 밀도 | 6.33 | 3.42 | 0.54× | **4.9 pt** |

템플릿은 **그림 라벨 8 pt** 를 요구한다. 지금은 그 절반을 조금 넘는다.
`CLAUDE.md` §2 의 "글자 크기는 인쇄에서 읽히는 것이 기준" 도 여기서 깨진다 —
좁게 그리고 크게 앉히기로 한 판형인데 **더 좁게 앉혔다.**

**고치는 법.** 그림 자리마다 **연속 구역 나누기**(Layout → Breaks →
Continuous)를 앞뒤로 넣고 그 구역만 1 단으로 돌린 뒤, 그림을 폭 7.16 in 으로
앉힌다. Fig. 7(여섯 칸)·Fig. 8·Fig. 3·Fig. 4·Fig. 9 는 두 단이 아니면 못 읽는다.
Fig. 1(폭발도)·Fig. 2(리그 사진)만 한 단으로 둘 수 있다.

덧붙는 것 둘:

- 그림이 전부 본문 흐름 속 **인라인**이라 단 가운데에 떨어진다. 템플릿은 단의
  위·아래를 요구한다. 구역을 나누면 자연히 해결된다.
- 그림을 전부 **PNG** 로 넣었다. `fin_figures` 는 Type 42 를 심은 `.pdf` 를 함께
  내므로(`CLAUDE.md` §2) 그쪽을 넣는 편이 낫다. 해상도는 대개 330 ~ 800 dpi 로
  넉넉하지만 **Fig. 2 리그 사진만 255 dpi** 로 템플릿 권고 300 dpi 아래다.

## D. 표 제목이 표 내용과 다르다

- **Table III** — 제목이 "천장(N) **과 포화 깊이(mm)**" 인데 표에 힘 한 열뿐이다.
  `[IV-C2]` 의 핵심 주장("포화 깊이가 두께를 따른다, ρ = +0.95")을 받칠 숫자가
  문서에 없다. 깊이를 괄호로 같은 칸에 넣거나 열을 더할 것. 마커 구성이 빠진
  것도 제목이 말해야 한다(프로브가 ⌀4 mm 라 같은 자로 잰 것이 아니다).
- **Table IV** — 제목이 "for three tolerances" 인데 열은 τ = 10 % 와 20 % **둘**
  뿐이다(τ = 5 % 없음). "마지막 열은 τ = 10 % 에서 중앙값 곡선의 평탄점" 이라는데
  마지막 열은 `Per-unit range` 다. 그리고 **어느 채널인지 적혀 있지 않다** —
  값(0.057 / 0.073 / 0.094 N)은 `[V-A5]` 의 **합력**이고 Fig. 7 은 **Fz** 다(§F2).
- **Table V** — "brackets give the median rung width and the per-unit range" 인데
  괄호는 단 폭만이고 per-unit range 는 따로 열이다.
- Table I · II 는 제목과 내용이 맞는다.

## E. 캡션이 그림과 맞지 않는다 — 여섯

| 그림 | 지금 캡션 | 실제 그림 |
|---|---|---|
| Fig. 3 | `ee` | 자국 성장 여덟 칸 (2 × 4) |
| Fig. 4 | **두 칸짜리 옛 판** 설명 — (a) 를 "최소 간격 대 두께", (b) 를 화소 스윕이라 적는다 | **다섯 칸**: (a)(b) 자국 두 장, (c) 단면, (d) 최소 간격, (e) 화소 스윕 |
| Fig. 5 | `bb` | 포화 천장 두 칸 |
| Fig. 6 | Fig. 4 캡션의 잘린 복사본 | **요구 입력 해상도** (줄인 프레임 셋 + 힘 MAE) |
| Fig. 9 | Fig. 7 캡션의 잘린 조각 | 평탄 밀도 대 겔, 네 칸 |
| Fig. 10 | Fig. 7 캡션의 잘린 조각 | 설계 흐름도 |

Fig. 1 · 2 · 7 · 8 의 캡션은 그림과 맞는다(§2 에서 다듬기만 한다).

## F. 자료가 어긋나는 곳 둘 — 캡션만 고쳐서는 안 된다

1. **"아홉 광도 시편 모두 1.10 mm 를 분해했다" 는 여덟이다.** 광도 `hard_2mm`
   유닛에는 두 기둥 램프가 없다(`paper_fig_separation.py` 의 주석). 네 군데를
   함께 고칠 것 — Table II 제목 · Fig. 4 캡션 · `[IV-B2]` · `[VI-A3]`.
2. **Fig. 7 의 삼각형과 Table IV 가 다른 값이다.** 17.3 / 13.3 / 23.0 (그림) 대
   13.6 / 6.7 / 23.0 (표). 전자는 **Fz**, 후자는 **합력**이라 서로 다른 양이고,
   여기에 `figure_plan` §4-8 의 **학습 판 A·B** 문제가 겹친다. 둘 중 어느 판인지
   한 줄로 밝히고 그림·표·본문이 끝까지 같은 것을 쓸 것.

## G. 잔 문제

- **V 장 제목 오타** — `Estimation Performance Versus Pixelk Density`.
- 장 제목 대소문자가 섞였다 — `INTRODUCTION` · `METHODS` 대 `Related work` ·
  `Contact Response`. V 장 제목만 왼쪽 정렬이다.
- **초고 표지가 남아 있다** — `[III-A1]` 류 절 태그 전부, `[AUTHOR CHECK: …]` 셋.
- 그림 문단 스타일이 제각각이다 — Fig. 1·3·4·5 는 `ab`(본문), Fig. 6 이후는
  `Text`. 가운데 정렬은 Fig. 2 하나뿐. 캡션도 Fig. 3 것만 `ab` 이고 나머지는
  `figurecaption` 이다. 하나로 맞출 것.
- **Fig. 2 사진과 캡션이 어긋나 보인다.** 캡션은 "probe is carried by the FR5
  flange **through** the ATI Mini45" 라는데 사진의 `(e)` 화살표는 흰 마운트
  **아래** 금속 원통을 가리킨다. `figure_plan` F2 도 "F/T 셀이 흰 마운트에 가려
  보이지 않는다" 고 적어 두었다. **어느 쪽이 맞는지 확인하고 사진이나 문장 중
  하나를 고칠 것** — 힘을 어디서 재는지가 이 논문 신뢰도의 절반이다.
- **Fig. 9 의 범례가 `soft / medium / hard`** 다. 다른 그림은 실측 쇼어를 적는다.
  `CLAUDE.md` §4("흔든 폭을 함께 적는다")에 맞추려면 눈금을 적거나 캡션이 진다.
- **Fig. 5 에 마커 칸이 없다.** `figure_plan` F0 은 1 × 3 을 요구했다(원리마다
  부호가 다른 것이 이 절의 결과다). 칸을 더하든지, 캡션이 왜 없는지 말할 것.
- **흑백 인쇄** — `CLAUDE.md` §2 의 경고 그대로다. 선 모양도 선 끝 라벨도 없어
  Fig. 3 · 5 · 7 의 세 계열이 흑백에서 구분되지 않는다.

---

## 1. 그림 번호 — 권하는 차례

`figure_plan` §1 은 요구 입력 해상도 그림(F1)을 **I 장**에 두기로 되어 있는데
지금은 V 장 머리에 인용 없이 놓여 있다. 그것만 앞으로 보내면 **7 ~ 10 은 그대로**
있고 1 ~ 6 이 한 칸씩 돈다.

| 새 | 내용 | 절 | 지금 |
|---:|---|---|---:|
| 1 | 요구 입력 해상도 | I | 6 |
| 2 | 두 바디 폭발도 | III-A | 1 |
| 3 | 압입 리그 | III-C | 2 |
| 4 | 자국 성장 | IV-A | 3 |
| 5 | 두 접촉 분리 | IV-B | 4 |
| 6 | 영상 응답 천장 | IV-C | 5 |
| 7 | 힘 추정 오차 대 밀도 | V-A | 7 |
| 8 | 형상 복원 대 밀도 | V-B | 8 |
| 9 | 평탄 밀도와 겔 | V-B 끝 | 9 |
| 10 | 설계 흐름 | VII | 10 |

아래 캡션은 **이 번호**로 적었다. 차례를 그대로 두기로 하면 1 ~ 6 의 번호만
지금 것으로 되돌리면 되고 본문은 그대로다.

---

## 2. 캡션 — 다시 적은 것 (그대로 붙여 쓸 수 있다)

원칙 셋: **패널이 무엇인지 캡션이 진다**(그림 안의 글자를 걷어냈으므로),
**선·띠·표식이 무엇인지 적는다**, **`CLAUDE.md` §4 의 상한을 넘지 않는다**
— "무관하다" 가 아니라 "이 설계로는 검출되지 않았다".

### Fig. 1 — 요구 입력 해상도 (I 장, 두 단)

> **Fig. 1.** How much image a force estimate needs, depth-referenced
> configuration. (a)–(c) One contact frame (specimen hard, 2 mm, ⌀8 mm sphere)
> area-averaged to pixel densities R = 220, 13.8, and 0.55 px/mm², in greyscale
> on a common display range. (d) Median normal-force MAE of the nine
> depth-referenced specimens against R, each specimen evaluated at its own
> density. The error is flat from the full frame down to roughly ten pixels per
> square millimetre and rises only below that. R is the number of pixels divided
> by the gel area the camera sees (Section V), which is the quantity that can be
> compared across units and configurations; the three frames are one specimen,
> the curve is the nine. This figure and Fig. 5 ask different questions and are
> not to be read as one result.

### Fig. 2 — 두 바디 폭발도 (III-A, 한 단 가능)

> **Fig. 2.** Exploded views of the two sensor bodies. (a) Depth-referenced body
> (9DTact-type): A1 black skin (0.5 mm), A2 translucent sensing layer (1, 2, or
> 3 mm — the varied layer), A3 transparent silicone base (4.5 mm), A4 acrylic
> window (2 mm), A5 gel frame, A6 camera module, A7 illumination board, A8
> housing. (b) Photometric body (DIGIT-type): B1 white reflective skin, B2
> transparent gel (1, 2, or 3 mm — the varied layer), B3 acrylic window (3 mm)
> and frame, B4 camera module, B5 illumination board, B6 housing. The marker
> variant uses body (b) unchanged and differs only in the gel, which carries a
> printed dot grid 0.5 mm below the reflective layer. Within a family every unit
> is the same body with only the gel module exchanged, so a within-family
> comparison is a gel comparison. "Thickness" throughout this paper means the
> varied layer alone (A2, B2); the depth-referenced stack carries a further
> 4.5 mm compliant layer (A3) beneath it that the photometric stack does not,
> which Section IV-C takes up.

### Fig. 3 — 압입 리그 (III-C, 한 단)

> **Fig. 3.** Indentation rig: (a) FAIRINO FR5 flange, (b) probe, (c) gel module
> under test, (d) fixture, (e) ATI Mini45 six-axis force/torque sensor. The gel
> module is clamped to the optical table and the probe is driven along each
> unit's own fitted gel normal (Section III-C); every force reported in this
> paper is read at (e).

*(§G 의 하중 경로 확인이 끝나면 마지막 문장에 "in the load path between the
flange and the probe" 또는 "between the fixture and the table" 중 맞는 쪽을
넣을 것. 지금은 어느 쪽도 주장하지 않게 적었다.)*

### Fig. 4 — 자국 성장 (IV-A, 두 단)

> **Fig. 4.** Imprint growth under the ⌀8 mm sphere, depth-referenced
> configuration, nine specimens in groups of three. Top row, imprint diameter;
> bottom row, mean intensity change over the central half of the frame.
> Columns: (a, e) against indentation depth, grouped by measured Shore OO
> hardness; (b, f) against depth, grouped by gel thickness; (c, g) against normal
> force, grouped by hardness; (d, h) against force, grouped by thickness. The
> same colour therefore means hardness in (a, c, e, g) and thickness in
> (b, d, f, h), and each panel carries its own legend. Line, group median; band,
> interquartile range of the three specimens of that group. The left half and the
> right half are the same imprints on the same ramps and differ only in the
> abscissa: at equal depth the curves separate by thickness and overlap by
> hardness, and at equal force they do the reverse, with the separation carried
> by intensity rather than by diameter. Diameter is left in pixels because a
> unit's pixels-per-millimetre varies with gel thickness by up to 1.5×
> (Section III-A), so converting to millimetres would fold magnification into the
> measurement. Cite only the panels whose groups are ordered; several are not.
> One specimen per cell, so the bands are between-specimen scatter and not a
> measurement uncertainty, and slopes are not to be compared with the photometric
> family, which was ramped over a different depth range.

### Fig. 5 — 두 접촉 분리 (IV-B, 두 단)

> **Fig. 5.** Two-contact separation, depth-referenced configuration. (a, b)
> Difference images |contact − reference| for two specimens that differ only in
> gel thickness (hard, 1 mm and 3 mm), the same two-post probe (two ⌀1.0 mm posts
> at 2.00 mm centre spacing) and the same 0.30 mm indentation, in greyscale on a
> common display range so that the two are read against the same scale. (c)
> Intensity profile across the two posts for the same two imprints; the dashed
> line is the 2.5 grey-level signal gate of Section IV-B. (d) Finest centre
> spacing resolved at full resolution against gel thickness, nine specimens, one
> per cell, coloured by measured Shore OO. A specimen counts as resolving a
> spacing if any rung of its depth ladder passes the signal, noise, and Rayleigh
> gates of Section IV-B. The finest spacing follows thickness (Spearman
> ρ = +0.75, p = 0.021, n = 9) and not hardness (|ρ| ≤ 0.32, p ≥ 0.41). (e) The
> same decision applied to area-averaged frames, for the 2.00 mm pair at 0.30 mm
> indentation on specimen soft, 2 mm — the only one of the nine that resolved this
> pair at every depth rung at full resolution, so that what the gel cannot do is
> not mixed into what the pixels cannot do. The dashed line is the Rayleigh
> threshold, Dip = 0.265, and the decision is read above or below it; the pair
> separates from R ≈ 4.9 px/mm² upward. The × at the left marks a rung where the
> contact was not detected at all, which is a different failure from a trough too
> shallow to pass. The narrowest probe we could make has a centre spacing of
> 1.10 mm and all eight photometric specimens ramped with it resolved it, so for
> that family the measurement is an upper bound and no floor was reached; the
> photometric family is therefore not plotted in (d), which carries no line
> marking that bound. One specimen per cell, no error bars; between-build scatter
> is quoted in Section VI-A.

### Fig. 6 — 영상 응답 천장 (IV-C, 두 단)

> **Fig. 6.** Image-response ceiling against gel thickness, ⌀8 mm sphere: (a)
> depth-referenced, (b) photometric. Nine specimens per panel, one per cell; the
> series is the measured Shore OO hardness, and the two families do not share a
> hardness scale — 40 Shore OO points in (a) against 6 points in (b). The ceiling
> is the force at which the image stops changing (Section IV-C), declared
> relative to each unit's own maximum response, so the values may be compared
> within a panel but not across panels; the vertical scales also differ. The
> thickness trend reverses between the two designs: the ceiling rises with
> thickness in (a) (ρ = +0.63, p = 0.068) and falls in (b) (ρ = −0.90, p = 0.001).
> Hardness is not associated with the ceiling in either (ρ = +0.37 and +0.05,
> p ≥ 0.33), but in (a) the hard-to-soft ratio grows with thickness (0.99, 1.43,
> and 2.04 at 1, 2, and 3 mm). The marker configuration was ramped with a
> different probe and is not shown. One specimen per cell, so there are no error
> bars; between-build scatter is quoted in Section VI-A.

### Fig. 7 — 힘 추정 오차 대 화소 밀도 (V-A, 두 단)

> **Fig. 7.** Force-estimation error against pixel density R. Rows:
> depth-referenced (a, b), photometric (c, d), photometric with markers (e, f).
> The left column splits the nine specimens of each configuration by gel
> thickness and the right column splits the same nine by measured Shore OO
> hardness, so the thin lines are identical between the two columns and only the
> group medians change. Thin line, one specimen (median over training seeds)
> plotted at that specimen's own pixel density; thick line, median of the three
> specimens of a group, pooled by ladder rung. In neither split do the three
> group medians leave the spread of the individual specimens — the between-group
> spread is 0.29 to 0.67 times the between-specimen spread at the same rung. The
> triangle under each axis is the normal-force plateau density at τ = 10 %, taken
> as the median of the nine per-unit values (17.3, 13.3, and 23.0 px/mm²); it is
> the same in both columns because the two columns divide the same nine
> specimens. These are per-axis Fz values, whereas Table V reports the resultant,
> which is a different quantity; shear is given in Section V-A. The vertical scale
> differs between rows and values must not be compared across them — the three
> configurations were trained on different input representations (three-channel,
> raw colour, inpainted). Hardness spans 40 Shore OO points in (b) against 6
> points in (d) and (f). One specimen per cell, no error bars; the null result is
> a limit of detection with nine specimens per configuration, not a demonstration
> of independence (Section VI-A).

### Fig. 8 — 형상 복원 대 화소 밀도 (V-B, 두 단)

> **Fig. 8.** Shape reconstruction against pixel density R. Top row, depth error;
> bottom row, error of the recovered lateral size; (a, c) depth-referenced,
> (b, d) photometric. Solid blue, ⌀4 mm cylinder; dashed red, 4 mm cube. The line
> is the median of the nine specimens and the band their interquartile range,
> which is between-specimen scatter and not a measurement uncertainty. Triangles
> mark the τ = 10 % plateau density (median of the per-unit values): 5.5 and
> 4.9 px/mm² in (a), 2.2 and 83.2 px/mm² in (b) — a factor of 38 between two
> probes on one sensor against 1.13 between the same two probes on the other. The
> vertical scales of (a) and (b) differ and must not be compared, because the two
> pipelines are scored over different depth ranges. (c) and (d) share a scale:
> both measure the same ⌀4 mm probe and zero is the true 4 mm in each. The sign
> is not folded — reading large and reading small are different failures. The ×
> marks a rung at which not all nine specimens returned a reconstruction; the line
> and band are drawn only where all nine did, because at the lowest rung six of
> the nine depth-referenced specimens returned no value and a median there would
> be a median of survivors. Bands that reach the top of (d) are clipped, not
> absent.

### Fig. 9 — 평탄 밀도와 겔 설계 (V-B 끝, 두 단)

> **Fig. 9.** Plateau density against gel design, τ = 10 %. Rows: force (a, b)
> and depth of the ⌀4 mm cylinder (c, d); columns: the same data split by gel
> thickness (a, c) and by hardness grade (b, d). Within each configuration's row
> the grey bar spans the minimum to maximum per-unit plateau density, the grey
> dots are its individual specimens, and the three coloured dots are the group
> medians, offset vertically in a fixed order (1, 2, 3 mm; soft, medium, hard) so
> that the groups are told apart by position as well as by colour. Read one thing
> from it: whether the three coloured dots spread along the grey bar. They do not
> — in none of the six rows was the plateau density associated with thickness or
> hardness (|ρ| ≤ 0.58, q ≥ 0.51 after Benjamini–Hochberg correction), while the
> per-unit spread within one configuration covers two to three orders of
> magnitude. With nine specimens per configuration a gel effect smaller than that
> spread could not have been detected; this is a limit of detection, not a
> demonstration of independence. The hardness grades are Shore OO-30/50/70 in the
> depth-referenced configuration and OO-51/54/57 in the photometric ones, so (b)
> and (d) do not shake the same variable by the same amount. Force is the
> resultant, per unit, as in Table V. The 4 mm cube is not drawn; its values are
> in Table VI.

### Fig. 10 — 설계 흐름 (VII, 두 단)

> **Fig. 10.** Where the measurements of this paper enter a sensor design. The
> task and the imaging principle fix two specifications: the contact response the
> sensor must cover (force range, two-contact separation) and the feature to be
> estimated with the error one is prepared to accept. Gel thickness and hardness
> act on the first (Section IV); pixel density acts on the second (Section V). In
> this campaign the two branches did not meet — no effect of thickness or
> hardness on the plateau density survived correction, and the plateau density
> followed the task and the tolerance instead — so the two were chosen on
> separate evidence here. That is a statement about what this design could
> resolve, not a claim that the two are independent, and the numbers on any
> particular path are to be measured on the designer's own sensor and pipeline.

---

## 3. 표 머리 — 다시 적은 것

### TABLE I

> **TABLE I.** Sensing-layer formulation and measured Shore OO hardness of each
> gel grade. The two families do not share a hardness scale: the depth-referenced
> gels span 40 Shore OO points across two product lines, the photometric gels 6
> points within one formulation, so every hardness result is read within a family.

### TABLE II — **새로 만들 것** (본문이 두 번 부른다)

> **TABLE II.** Coverage of the campaign: which probe was run on which
> configuration, and which measurement each supports. Two-contact separation was
> not run on the marker configuration, imprint growth and image saturation are
> reported for the two configurations ramped with the ⌀8 mm sphere, and shape
> reconstruction was not attempted on the marker configuration because the dots
> occlude the shading the photometric method depends on.

행은 구성 셋, 열은 프로브 넷(⌀8 mm 구 · ⌀4 mm 원기둥 · 4 mm 정육면체 · 두 기둥
여섯) 과 측정 항목 넷(자국 성장 · 두 접촉 분리 · 포화 · 힘/형상 추정)이다.
`[III-B4]` 와 `[III-C2]` 의 문장이 그대로 표가 된다.

### TABLE III (지금 II)

> **TABLE III.** Finest resolved centre spacing (mm) and, in brackets, the
> indentation depth range over which it held (mm), at full resolution,
> depth-referenced configuration, one specimen per cell. All eight photometric
> specimens ramped with the two-post probes resolved the narrowest spacing tested
> (1.10 mm centre spacing), so for that family the entry would be an upper bound
> rather than a value and the family is not tabulated; 1 mm photometric gels
> resolved that pair to 0.6 mm indentation and 2–3 mm gels to 0.9 mm.

### TABLE IV (지금 III) — **깊이 열을 더하든지 제목에서 뺄 것**

> **TABLE IV.** Image-response ceiling, the force (N) at which the image stops
> changing, with the indentation depth at that point (mm) in brackets, ⌀8 mm
> sphere, one specimen per cell. The criterion is relative to each unit's own
> maximum response (Section IV-C), so values are compared within a configuration
> and not between them. The marker configuration was ramped with the ⌀4 mm sphere
> and is not included.

### TABLE V (지금 IV) — **채널과 허용치를 제목이 밝힐 것**

> **TABLE V.** Force estimation, resultant force, n = 9 specimens per
> configuration: the minimum MAE (median over units of each unit's best rung) and
> the pixel density R at which the error enters the τ = 10 % and τ = 20 %
> plateaus, with the pixel width of the median rung in brackets. The last column
> is the range of the nine per-unit plateau densities. Per-axis Fz values, which
> are what Fig. 7 plots, are a different quantity; τ = 5 % is reported in the text
> only, because it did not reproduce between two training runs of the same
> specimens (Section V-A).

*(τ = 5 % 열을 실을 것인지는 `figure_plan` §F5 의 미결이다. 싣는다면 제목의
마지막 문장을 "the τ = 5 % column is reported for completeness and did not
reproduce between two training runs" 로 바꾼다.)*

### TABLE VI (지금 V)

> **TABLE VI.** Shape reconstruction: the depth MAE on the plateau (median over
> the nine units, given as the range of the three thickness-group medians) and the
> pixel density at which the error enters the τ = 10 % plateau (median of the
> per-unit values, with the pixel width of the median rung in brackets). The last
> column is the range of the nine per-unit plateau densities. The two pipelines
> are scored over different depth ranges, so MAE is compared within a
> configuration and not between them.

---

## 4. 고칠 것 차례 — 본문 쪽

1. **`Fig. 2` → `Fig. 7`** (`[V-A4]`, 두 군데), **`Fig. 3c/3e` → `Fig. 8a` ·
   `Fig. 9`**, **`Fig. 3d` → `Fig. 8c` · `Fig. 8d`** (`[V-B3]` · `[V-B5]`).
   `[V-B2]` 의 **`Fig. 3b` 는 가리킬 그림이 없다** — 패널을 만들든지 인용을 뺀다.
2. 인용이 없는 그림 여덟에 인용을 붙인다 (§A 끝의 자리 제안).
3. 표를 §B 의 여섯으로 다시 매기고, `[IV-A1]` 을 Fig. 4 로, `[IV-C3]` 의
   `Table V` 를 `Table IV` 로 고치고, `[V-B1]` 에 `Table VI` 인용을 넣는다.
4. §F1 의 "nine photometric specimens" 를 네 군데에서 **eight** 로 고친다.
5. §F2 의 학습 판을 하나로 정하고 그림·표·본문·초록을 맞춘다.
6. `Pixelk` 오타, 장 제목 대소문자, 절 태그와 `[AUTHOR CHECK]` 제거.
