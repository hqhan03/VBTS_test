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
├── docs/               방법과 결과 (색인은 이 파일의 「어디부터 읽나」)
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

## 어디부터 읽나 — 문서 색인

| 알고 싶은 것 | 읽을 것 |
|---|---|
| **논문에 넣을 그림과 표 전부, 설명과 csv 와 함께** | **`result/results.md`** — 한 장 요약도 이것이다 |
| **논문 Method 전체** — 장비, 시료, 압자, 절차, 정의, 통계 | **`docs/methods.md`** |
| 캠페인이 무엇이고, 네 시험이 무엇이고, 어디까지 왔나 | **`docs/campaign_protocol.md`** ← 여기서 시작 |
| 로봇이 실제로 무엇을 하나 — 동작 하나하나와 그 뒤의 실측값 | **`docs/measurement_protocol.md`** |
| **세 원리가 어떻게 다른가, 그리고 이 캠페인이 무엇을 틀렸나** | **`docs/cross_principle.md`** ← 결과이고, §5 가 자기비판 |
| **시험 1, 힘 추정** — 세 원리 전부, 해상도별 축별 MAE | **`docs/force_estimation.md`** (§7 이 DIGIT 계열의 입력 표현 비교) |
| **시험 2, 형상 복원** — 9DTact 의 밝기→깊이 조회표와 DIGIT 의 광도 스테레오 | **`docs/shape_reconstruction.md`** (§5 가 DIGIT 파이프라인, `src/scripts/digit_shape.py`) |
| **시험 3, 공간 분해능** — 방법과 전 유닛 결과 | **`docs/spatial_resolution.md`** |
| **시험 4, 최대 측정 가능 힘** — 방법, 전 유닛, 그리고 왜 이것으로 센서를 비교할 수 없나 | **`docs/force_ceiling.md`** |
| 형상 복원에 카메라 해상도가 얼마나 필요한가 (축소 쓸기) | `docs/shape_vs_resolution.md` |
| 다른 분석이나 다른 역치로 0.3 mm 보다 깊은 두 점을 분해할 수 있나 | `docs/spatial_resolution_sensitivity.md` |
| **쌍둥이 복제가 얼마나 어긋나고, 어느 쪽을 버릴 것인가** | **`docs/replicate_audit.md`** (`src/scripts/twin_audit.py`) |
| DIGIT 광도 보정 격자가 어떻게 작동하고 유닛 사이에서 전이되나 | `docs/photometric_calibration.md` |
| 이 캠페인의 전처리·학습이 DIGIT/GelSight 문헌과 어디서 갈리나 | `docs/method_vs_literature.md` |
| 경도와 두께를 한 변수(접촉 반지름)로 묶을 수 있나 — 시도 | `docs/contact_variable.md` |
| 구가 표면을 왜 너무 깊게 읽나 | `docs/hertz_zero_bias.md` |
| 두 기둥 압자의 두 기둥이 왜 같은 힘으로 안 눌리나 | `docs/pair_contact_asymmetry.md` |
| **유닛의 숫자 중 얼마가 겔이고 얼마가 장착 방식인가** | `docs/campaign_protocol.md` §4.15 (`src/scripts/repeat_spread.py`) |
| 센서 좌표계·베이스 좌표계·겔이 어떻게 얽히나 | `docs/frames_and_transforms.md` |
| TCP 숫자가 어디서 나왔나 | `docs/tcp_calibration_history.md` |
| 파일이 어디에 쓰이고 그 안에 무엇이 있나 | `docs/data_recording.md` |
| 무엇이 아직 없고 그것을 모으는 데 얼마가 드나 | `docs/data_wishlist.md` |
| 다시 잰 유닛 중 분석이 **어느 런**을 읽나, 그리고 그 분리가 무엇을 가리고 있었나 | `data/analysis/DATASET_CLEANUP.md` |
| **`data/` 아래 무엇이 어디 있나** | `data/README.md` |
| **원리·압자·겔 유닛별로 어떤 자료가 있고 무엇이 없나** | `data/20260911_VBTSresolution_dataset/DATA_INVENTORY.md` (`src/scripts/dataset_audit.py`) |
| 코드가 무엇인가 — 라이브러리, 스크립트, 설정, 테스트 | `src/README.md` |
| 2026-09-05 의 단일 유닛 형상 파일럿 | `docs/archive/shape_reconstruction_pilot.html` |
| 대체된 문서, 출처 보존용 | `docs/archive/` |

---

## 이 프로젝트가 자꾸 다시 배우는 습관

여기서 **추론으로 세운 속도 가설은 전부 틀렸거나 미미했다.** 큰 이득은 부분을 재는
데서 나왔다. 카메라가 일주일 동안 두 프레임에 한 장을 버리고 있었는데(한계 4.89 fps
에서 2.44 fps), USB 대역폭을 아무리 생각해도 찾지 못한 것을 **세 줄짜리 벤치마크가 1 분**
만에 찾았다. 마찬가지로 "접촉이 축에서 벗어났다" 는 메시지가 세 번의 런을 움직이는
무언가를 찾게 만들었는데, 반경은 0.010 mm 로 일정했고 그 오프셋은 그 단계가 시작되기도
전에 물려받은 것이었다.

**믿기 전에 재고, 잰 숫자를 그것이 정당화하는 결정 옆에 적을 것.** 여기 문서들이
괄호 안 숫자로 가득한 이유가 그것이다 — 그것이 나중에 선택을 검토할 수 있게 만든다.
