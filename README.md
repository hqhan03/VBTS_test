# VBTS 해상도 캠페인

**시각 기반 촉각 센서(VBTS)의 힘·형상 추정이 겔에 따라 어떻게 달라지는가.**
FAIRINO FR5 로봇 팔과 ATI Mini45 6축 F/T 셀로, 세 가지 촉각 센서 원리를 같은 겔 세트에
올려 같은 프로토콜로 측정했다.

| | |
|---|---|
| 원리 | **9DTact** · **DIGIT** · **DIGIT_Marker** (마커가 찍힌 DIGIT 겔) |
| 겔 | 경도 3 × 두께 3 (1 / 2 / 3 mm) × 반복 2 = 원리당 **18 유닛** |
| 경도 | 9DTact **OO-30 / 50 / 70** · DIGIT 계열 **OO-51 / 54 / 57** — 같은 눈금이 아니다 |
| 프로브 | 구 ⌀4·⌀8 mm, 정육면체 4 mm, 원기둥 ⌀4 mm, 두 기둥(간격 0.10 ~ 1.00 mm), 격자 |
| 규모 | 겔 유닛 54 개, 최종 데이터셋의 런 **461 개 (166 GB)** |

> **수집은 2026-09-12 에 끝났다.** 더 이상 측정하지 않는다. 논문을 쓸 때 필요한 세 가지:
> **`docs/methods.md`** 가 Method 전체이고 그 **§10.0 에 영구 한계표**가 있다 —
> 무엇을 답하지 못했고 그것이 어느 주장을 제한하는지가 한 표에 있다.
> **`result/results.md`** 에 논문에 넣을 그림과 표가 설명과 함께 모여 있고,
> 그림마다 **같은 자료의 csv 가 옆에 있다**(직접 다시 그릴 수 있게).

## 저장소 구조

```
.
├── src/                코드 전부 (src/README.md)
│   ├── vbts_platform/  로봇 · F/T · 카메라를 다루는 라이브러리
│   ├── scripts/        실험을 돌리는 것과 분석하는 것
│   ├── config/         장비 설정, 프로브 치수, 센서 등록부, ATI 보정 파일
│   └── tests/          127 개 — 대부분 로봇이 움직이지 않는지를 검사한다
├── docs/               방법과 결과 (docs/README.md 가 색인)
├── result/             **논문용 그림·표·csv** (result/results.md 가 전부 설명한다)
│   ├── 1_9DTact/  2_DIGIT/  3_DIGIT_Marker/    원리별 figures/ 와 data/
│   └── extra/          원리를 가로지르는 그림 A ~ F
└── data/               측정 — **깃헙에 없다.** 이 기계에만 있다 (data/README.md)
    ├── 20260911_VBTSresolution_dataset/   최종 데이터셋
    ├── analysis/       분석이 낸 표
    ├── earlier_datasets/  프로토콜 확정 전의 측정
    ├── rig/            장비 쪽 기록
    └── _discarded/     버린 런 (이유와 함께)
```

**`data/` 는 깃헙에 올리지 않는다.** 측정도, 분석이 낸 표도, 그 안의 문서도 전부
이 기계(와 그 백업)에만 있다 — 97,849 개 파일, 203 GB. 저장소에 올라가는 것은
`src/` · `docs/` · `result/` 뿐이다. 규칙은 `.gitignore` 맨 아래.

그래서 아래 표에서 `data/` 로 시작하는 항목과 문서가 인용하는 표
(`data/analysis/*.csv`)는 **이 기계에서만** 열린다. 문서의 숫자는 그 표에서 읽어
넣은 것이고, 다시 만드는 명령은 아래 "돌리는 법" 에 있다. **`result/` 는 예외다** —
그림과 그 그림을 만든 csv 가 저장소 안에 함께 들어 있어 어디서나 열린다.

## 어디부터 읽나

| 알고 싶은 것 | |
|---|---|
| **논문에 넣을 그림과 표 전부, 설명과 함께** | **`result/results.md`** |
| 세 원리가 어떻게 다른가, 그리고 **이 캠페인이 무엇을 틀렸는가** | `docs/cross_principle.md` (§5 가 자기비판) |
| **논문 Method 에 들어갈 측정 방법 전부** | **`docs/methods.md`** |
| 그 방법이 어떻게 그렇게 됐나 — 날짜순 기록, 사고와 수정 | `docs/campaign_protocol.md` · `docs/measurement_protocol.md` |
| **힘 추정 — 세 원리 전부, 해상도별 축별 MAE** | **`docs/force_estimation.md`** |
| 센서가 **어느 힘까지 읽을 수 있나** (이미지 포화) | `docs/force_ceiling.md` (§6.8 이 표제 비교) |
| **형상 복원** — 9DTact 의 밝기→깊이, DIGIT 의 광도 스테레오 | `docs/shape_reconstruction.md` |
| 어떤 데이터가 있고 **무엇이 없나** | `data/20260911_VBTSresolution_dataset/DATA_INVENTORY.md` (이 기계) — 만드는 것은 `src/scripts/dataset_audit.py` |
| 무엇을 더 모아야 하나 | `docs/data_wishlist.md` |
| 문서 전체 색인 | `docs/README.md` |

## 캠페인의 표제 질문과 답

**"힘 추정 오차가 포화하는 카메라 해상도가 겔에 따라 다른가?"** → **아니다.**
√2 간격 사다리에서 두 DIGIT 계열 모두 무릎이 두께에 대해 평평하다
(DIGIT ρ −0.047 p 0.854, Marker ρ −0.113 p 0.656).
2 배 사다리에서 나왔던 유일한 유의 결과는 무릎 추정이 불안정해서 생긴 허상이었다
(`docs/cross_principle.md` §3.10). 방향 자체는 학습 없이 재는 두 측정에서 살아남지만,
학습된 무릎으로는 보이지 않는다.

세 원리 전부를 1920×1080 부터 8×5 까지 12 단에서, **학습 파라미터를 원리·해상도에
걸쳐 똑같이 고정한 채** 다시 학습해 Fx·Fy·Fz 를 따로 냈다 (`docs/force_estimation.md`
§2.6, `result/results.md` §8).

**측정된 것 중 확실한 것: 최대 측정 가능 힘은 겔의 이미지 응답이 정한다.**
같은 프로브(`ball8`)로 35 유닛을 실측하면 9DTact 중앙 **31.00 N**, DIGIT 중앙
**17.33 N** 으로 **1.8 배**이고 범위는 겹친다 (24.6 ~ 63.2 N 대 11.1 ~ 23.4 N).
두께가 두 원리에서 **반대로** 작용한다 — 9DTact 는 두꺼울수록 오르고(hard 에서
30.8 → 61.7 N), DIGIT 은 내려간다(18.2 → 12.8 N). 기전은 포화가 일어나는 깊이다:
9DTact 는 두께의 2.0 ~ 5.2 배까지 들어가 **기재에 눌린 상태**에서 포화하고, DIGIT 은
0.56 ~ 1.32 배에서 **광학이 먼저** 포화한다 (`docs/force_ceiling.md` §6.8).

> **경도 축은 두 원리를 비교할 수 없다.** 9DTact 는 Shore **40 점**, DIGIT 계열은
> **6 점**을 흔들었다 — 6.7 배 차이다. "경도가 DIGIT 의 천장을 가르지 못한다" 는
> 관찰은 그래서 철회했다(`docs/methods.md` §2.1). 원리를 가로질러 경도를 하나의
> 요인으로 놓는 분석은 전부 이 불균형을 함께 보고해야 한다.

## 돌리는 법

```bash
# 테스트 (이 기계의 ROS conftest 를 피해야 한다)
python3 -m pytest src/tests/ -q --rootdir=. -p no:cacheprovider

# 분석 표 다시 만들기 — 어느 스크립트가 어느 표를 쓰는지는 docs/README.md
python3 src/scripts/dataset_audit.py        # 재고
python3 src/scripts/ceiling_summary.py --check   # 천장이 등록부와 맞는지

# result/ 다시 만들기 — 그림과 그 옆의 csv 를 함께 쓴다
python3 src/scripts/make_result_tables.py    # 3x3 표 (칸은 r1 / r2 (평균))
python3 src/scripts/make_result_figures.py   # 원리를 가로지르는 그림 A ~ F
python3 src/scripts/make_force_mae_figures.py  # 축별 MAE 대 해상도
python3 src/scripts/make_shape_figures.py    # 형상 정확도 대 해상도
python3 src/scripts/make_optical_curves.py   # 깊이에 따른 자국 지름과 밝기
python3 src/scripts/make_results_md.py       # 위의 결과로 result/results.md 를 쓴다

# 로봇 — 한 유닛 전체
python3 src/scripts/run_one_sensor.py --sensor <유닛> --dataset <데이터셋> --probe ball4
```

**로봇은 사람이 겔을 갈아 끼운 뒤에만 돈다.** 측정이 끝나면 프로브를 올린다.
안전 장치는 `src/vbts_platform/robot_interface.py` 와 그것을 검사하는
`src/tests/test_robot_interface.py` 에 있다.
