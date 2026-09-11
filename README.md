# VBTS 해상도 캠페인

**시각 기반 촉각 센서(VBTS)의 힘·형상 추정이 겔에 따라 어떻게 달라지는가.**
FAIRINO FR5 로봇 팔과 ATI Mini45 6축 F/T 셀로, 세 가지 촉각 센서 원리를 같은 겔 세트에
올려 같은 프로토콜로 측정했다.

| | |
|---|---|
| 원리 | **9DTact** · **DIGIT** · **DIGIT_Marker** (마커가 찍힌 DIGIT 겔) |
| 겔 | 경도 3 (soft / medium / hard) × 두께 3 (1 / 2 / 3 mm) × 반복 2 = 원리당 **18 유닛** |
| 프로브 | 구 ⌀4·⌀8 mm, 정육면체 4 mm, 원기둥 ⌀4 mm, 두 기둥(간격 0.10 ~ 1.00 mm), 격자 |
| 규모 | 겔 유닛 54 개, 최종 데이터셋의 런 353 개 (159 GB) + 반복 측정 18 런 |

## 저장소 구조

```
.
├── src/                코드 전부 (src/README.md)
│   ├── vbts_platform/  로봇 · F/T · 카메라를 다루는 라이브러리
│   ├── scripts/        실험을 돌리는 것과 분석하는 것
│   ├── config/         장비 설정, 프로브 치수, 센서 등록부, ATI 보정 파일
│   └── tests/          127 개 — 대부분 로봇이 움직이지 않는지를 검사한다
├── docs/               방법과 결과 (docs/README.md 가 색인)
└── data/               측정 — **깃헙에 없다.** 이 기계에만 있다 (data/README.md)
    ├── 20260911_VBTSresolution_dataset/   최종 데이터셋
    ├── analysis/       분석이 낸 표
    ├── earlier_datasets/  프로토콜 확정 전의 측정
    ├── rig/            장비 쪽 기록
    └── _discarded/     버린 런 (이유와 함께)
```

**`data/` 는 깃헙에 올리지 않는다.** 측정도, 분석이 낸 표도, 그 안의 문서도 전부
이 기계(와 그 백업)에만 있다 — 93,000 개 파일, 196 GB. 저장소에 올라가는 것은
`src/` 와 `docs/` 뿐이다. 규칙은 `.gitignore` 맨 아래.

그래서 아래 표에서 `data/` 로 시작하는 항목과 문서가 인용하는 표
(`data/analysis/*.csv`)는 **이 기계에서만** 열린다. 문서의 숫자는 그 표에서 읽어
넣은 것이고, 다시 만드는 명령은 아래 "돌리는 법" 에 있다.

## 어디부터 읽나

| 알고 싶은 것 | |
|---|---|
| 세 원리가 어떻게 다른가, 그리고 **이 캠페인이 무엇을 틀렸는가** | `docs/cross_principle.md` (§5 가 자기비판) |
| **논문 Method 에 들어갈 측정 방법 전부** | **`docs/methods.md`** |
| 그 방법이 어떻게 그렇게 됐나 — 날짜순 기록, 사고와 수정 | `docs/campaign_protocol.md` · `docs/measurement_protocol.md` |
| 센서가 **어느 힘까지 읽을 수 있나** (이미지 포화) | `docs/force_ceiling.md` |
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

측정된 것 중 확실한 것: **최대 측정 가능 힘은 원리가 아니라 겔의 이미지 응답이 정한다**
(36 유닛 실측, 중앙 DIGIT 7.35 N /
Marker 9.56 N, 그러나 응답을 통제하면 원리 차이는
사라진다 — `docs/force_ceiling.md` §4.1).

## 돌리는 법

```bash
# 테스트 (이 기계의 ROS conftest 를 피해야 한다)
python3 -m pytest src/tests/ -q --rootdir=. -p no:cacheprovider

# 분석 표 다시 만들기 — 어느 스크립트가 어느 표를 쓰는지는 docs/README.md
python3 src/scripts/dataset_audit.py        # 재고
python3 src/scripts/ceiling_summary.py --check   # 천장이 등록부와 맞는지

# 로봇 — 한 유닛 전체
python3 src/scripts/run_one_sensor.py --sensor <유닛> --dataset <데이터셋> --probe ball4
```

**로봇은 사람이 겔을 갈아 끼운 뒤에만 돈다.** 측정이 끝나면 프로브를 올린다.
안전 장치는 `src/vbts_platform/robot_interface.py` 와 그것을 검사하는
`src/tests/test_robot_interface.py` 에 있다.
