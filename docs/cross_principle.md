# 원리·젤·해상도 — 파생 변수, 가설, 검증

2026-09-09 밤. 운용자 지시: 학습을 돌리는 동안 지금까지 모은 데이터에서 구할 수 있는 모든
양을 정리하고, 그것들이 힘 추정·형상 복원 성능과 해상도에 어떻게 연결되는지 **가설을 세우고
직접 검증**하라. 이 문서는 그 기록이다. 가설은 결과를 보기 **전에** 적었다(§2). 결과가
가설을 기각하면 그대로 남긴다.

스크립트: `derived_variables.py` → `data/derived_variables.csv`; `correlations.py` →
`data/correlations.csv`, `figures/correlations_pooled.png`; `cross_principle.py` →
`figures/cross_principle_fz.png`; `analyse_saturation.py` → 원리별 `figures/saturation_*.png`.

## 0. 비교의 규칙

**두께나 경도가 하나라도 다르면 다른 센서다.** 원리 간 비교는 같은 (경도, 두께) 칸 안에서만
한다 — 9DTact soft 1 mm 두 유닛 대 DIGIT soft 1 mm 두 유닛. "DIGIT 전체 평균 대 9DTact
전체 평균"은 젤 분포가 같아도 젤 자체가 다른 물건이므로(마커 젤은 Hertz k 가 1.64 배) 쓰지
않는다. 학습 조건은 모든 해상도·모든 원리에서 같다: ResNet-18, 배치 64(경사 누적), 30 epoch,
검증 집합으로 epoch 선택, 사이클 분할(경계 공동 선택, 테스트 ≥ 8 %), Fz ≤ 2 N 필터, 전단
오차는 전단 블록 프레임에서만.

## 1. 유닛마다 구할 수 있는 양 (`derived_variables.csv`)

| 군 | 변수 | 어디서 | 뜻 |
|---|---|---|---|
| 젤 | `hertz_k`, `hertz_n` | Pass A ball4 사다리, F = k·dⁿ | 강성, 기재 개입(n > 1.5) |
| | `hertz_a_ball8`, `d_2N_mm`, `a_2N_mm` | Pass B zero 적합; 2 N 에서의 깊이; a = √(2Rd − d²), R = 4 | ball8 강성, 접촉 반경 |
| | `mu` | 전단 최대 / 그때의 Fz | 마찰 계수 (0.41–0.69) |
| | `creep_mm_per_cycle` | 전단 사이클 시작 깊이의 기울기 | 홀드 중 크리프 |
| 광학 | `px_per_mm`, `tilt_deg` | Pass A scale.yaml | 축척, 젤 기울기 |
| | `pedestal_ratio` | reference.png / 올바른 기준 | 프로브 그림자(DIGIT 1.09–1.15, 9DTact 1.00) |
| | `img_slope_lvl_per_N`, `img_slope_lvl_per_mm` | 정규 블록 0.2–2 N, 전체 프레임 \|diff\| 평균의 기울기 | **이미지 응답률** — 뉴턴당·mm 당 그림이 얼마나 변하나 |
| | `imprint_area_slope_pct_per_N`, `img_resp_at_2N` | 같은 구간 | 자국이 얼마나 넓어지나, 2 N 에서의 응답 |
| | `bw_normal_f90`, `bw_shear_f90`, `shear_snr` | 잡음 차감 스펙트럼, 0–3 c/mm | 자국·전단 신호의 공간 대역폭, 전단 S/N |
| 라벨 | `fz_noise_mae`, `lat_noise_mae` | 세그먼트 안 2 차 차분 | F/T 라벨 자신의 잡음 바닥 |
| 성능 | `fz_best/knee/res_loss`, `sh_best/knee/res_loss` | 해상도 스윕 (`analyse_saturation`) | 최소 오차, 무릎, 해상도 손실 |
| | `n_resolved`, `dip_175_max`, `um_per_level`, `cyl4_corrected_rms` | 9DTact 만, Pass A | 공간 분해능·형상 복원 |

## 2. 가설 (결과 전에 적음)

- **H1 응답률 → 힘 바닥.** `img_slope_lvl_per_N` 이 클수록(뉴턴당 그림이 많이 변할수록) `fz_best` 가 낮다. 근거: 망은 결국 밝기 변화를 읽는다(§force_estimation 3.2, 스칼라 두 개로 R² 0.94).
- **H2 라벨 잡음 → 힘 바닥.** `fz_noise_mae` 가 `fz_best` 의 하한을 정한다(9DTact 에서 ρ +0.55 였다). 원리를 합쳐도 성립해야 한다.
- **H3 대역폭 → 무릎.** `bw_normal_f90` 이 `fz_knee` 를, `bw_shear_f90` 이 `sh_knee` 를 정한다(Nyquist). 예상: 상관은 있으되 범위가 1.5–1.7 배라 한 칸 안.
- **H4 접촉 반경 → 무릎: 없음.** `a_2N_mm` 은 `fz_knee` 와 무관해야 한다 — 볼이 자국 모양을 정한다는 §2.3b 의 논리.
- **H5 강성 → 전단 해상도 손실.** `hertz_k` 가 클수록 `sh_res_loss` 가 크다(9DTact ρ +0.49). DIGIT 에서도 같은 방향이면 원리 무관한 젤의 성질.
- **H6 프로브 그림자 → DIGIT 의 힘 바닥.** `pedestal_ratio` 가 큰 유닛이 `fz_best` 가 나쁘다 — 그림자가 "darker" 채널의 동적 범위를 잡아먹는다면. 대안: 올바른 기준을 쓰면 무관해야 한다(우리는 올바른 기준으로 학습한다 → **무관이 예측**).
- **H7 원리 간, 같은 젤 칸에서.** DIGIT_Marker 의 Fz 바닥이 9DTact 보다 높다(첫 3 유닛 0.09–0.14 대 0.05). 예상 이유: 응답률(H1)이 낮거나 라벨 잡음(H2)이 높다 — 둘 중 어느 쪽인지 파생 변수가 가른다.
- **H8 형상 복원(9DTact) 과 힘 추정은 다른 것을 요구한다.** `um_per_level`(형상의 양자화 한계)은 `fz_best` 와 무관하고, `n_resolved`(공간 분해능)는 `sh_knee` 와 상관한다.

## 3. 결과

(채워지는 중 — `correlations.py` 첫 실행 뒤.)

## 4. 원리 간 비교, 젤 칸별

(채워지는 중 — DIGIT 비마커 스윕 뒤.)

## 5. 자기비판

(채워지는 중.)
