# 데이터 재고 — 원리 × 프로브 × 겔 유닛

`scripts/dataset_audit.py` 가 디스크만 보고 만든다. 기준은 설계값 **경도 3 × 두께 3 ×
반복 2 = 유닛 18 개**이고, 9DTact 는 `medium_2mm_r1` 이 파괴돼 **17 개**다
(`docs/force_ceiling.md` §7). 칸의 숫자는 **그 pass 가 남겨야 하는 파일까지 갖춘 유닛 수**
/ 기대값이다 — 폴더만 있고 사다리가 비었으면 세지 않는다.

## 폴더 구조

```
data/20260911_VBTSresolution_dataset/
├── <원리>/                        9DTact | DIGIT | DIGIT_Marker
│   ├── <YYYYMMDD>_<pass>/         프로브 하나 = pass 하나, 유닛당 폴더 하나
│   │   └── <원리>_<경도>_<두께>mm_r<반복>/
│   │       ├── state.json meta.yaml summary.yaml   그 런이 무엇을 했나
│   │       ├── zero/                              영점 표면 찾기
│   │       ├── shape_<프로브>/ladder.csv           깊이 사다리 (Pass A)
│   │       ├── scale_<프로브>/scale.yaml           mm -> px 축척
│   │       ├── stream/frames.csv                  프레임당 힘·자세 (Pass B)
│   │       ├── calibgrid_ball4/grid.csv           광도 보정 격자
│   │       └── characterize/steps.csv             최대 측정 가능 힘 램프
│   ├── repeated_data/<pass>/<런>/  같은 유닛 두 번째·세 번째 측정
│   └── *.csv                       그 원리의 스윕 결과
└── DATA_INVENTORY.md               이 문서
```

버린 런은 여기 없다 — `data/_discarded/<원리>/<pass>/` 에 이유와 함께 있다.
유닛당 폴더를 하나로 줄인 기록은 `data/DATASET_CLEANUP.md` 다.

## 프로브 격자

| pass | 프로브 | 9DTact | DIGIT | DIGIT_Marker |
|---|---|---|---|---|
| `passA_ball4` | 구 ⌀4 mm | **17 / 17** | **18 / 18** | **18 / 18** |
| `passA_cube4` | 정육면체 4 mm | **17 / 17** | **18 / 18** | **18 / 18** |
| `passA_cyl4` | 원기둥 ⌀4 mm | **17 / 17** | **18 / 18** | **18 / 18** |
| `passA_pair010` | 두 기둥, 간격 0.10 mm | — | **18 / 18** | — |
| `passA_pair025` | 두 기둥, 간격 0.25 mm | **17 / 17** | **18 / 18** | — |
| `passA_pair050` | 두 기둥, 간격 0.50 mm | **17 / 17** | — | — |
| `passA_pair075` | 두 기둥, 간격 0.75 mm | **17 / 17** | — | — |
| `passA_pair100` | 두 기둥, 간격 1.00 mm | **17 / 17** | ⚠ 1 / 18 | — |
| `passA_calibgrid` | 구 ⌀4 mm 격자 + 램프 | — | **18 / 18** | **18 / 18** |
| `passB_ball8` | 구 ⌀8 mm | **17 / 17** | **18 / 18** | **18 / 18** |

`—` 는 그 원리에 그 pass 가 **없다**는 뜻이다. 빈 칸이 이 표의 요점이다.

## 시작만 한 pass

유닛 하나둘만 재고 멈춘 pass 다. 아래 "비어 있는 유닛" 표에서는 빼고 센다 —
거기 넣으면 재지 않은 유닛 열여섯 줄이 결함처럼 보인다. 이것은 결함이 아니라
**수집이 안 된 것**이고, 없는 pass 와 같은 성격이다.

| pass | 원리 | 채운 유닛 | 기대 |
|---|---|---:|---:|
| `passA_pair100` | DIGIT | 1 | 18 |

## 없는 pass — 설계에는 있고 디스크에는 없는 것

| pass | 프로브 | 없는 원리 |
|---|---|---|
| `passA_pair010` | 두 기둥, 간격 0.10 mm | 9DTact, DIGIT_Marker |
| `passA_pair025` | 두 기둥, 간격 0.25 mm | DIGIT_Marker |
| `passA_pair050` | 두 기둥, 간격 0.50 mm | DIGIT, DIGIT_Marker |
| `passA_pair075` | 두 기둥, 간격 0.75 mm | DIGIT, DIGIT_Marker |
| `passA_pair100` | 두 기둥, 간격 1.00 mm | DIGIT_Marker |
| `passA_calibgrid` | 구 ⌀4 mm 격자 + 램프 | 9DTact |

## 있는 pass 안에서 비어 있는 유닛

**없다 — 끝까지 돌린 pass 는 모두 기대한 유닛을 다 채웠다.**

## 원리별 합계

| 원리 | pass | 기대 유닛 | 채운 유닛 | 프로브 종류 |
|---|---:|---:|---:|---:|
| 9DTact | 8 | 136 | 136 | 8 |
| DIGIT | 8 | 144 | 127 | 8 |
| DIGIT_Marker | 5 | 90 | 90 | 5 |

## 겔 규격이 세 원리에 고르게 있나

한 규격이 어느 원리에서 빠지면 그 규격은 원리 비교에 못 쓴다.

| 겔 | 9DTact | DIGIT | DIGIT_Marker |
|---|---:|---:|---:|
| `soft_1mm_r1` | 8 / 8 | 7 / 8 | 5 / 5 |
| `soft_1mm_r2` | 8 / 8 | 7 / 8 | 5 / 5 |
| `soft_2mm_r1` | 8 / 8 | 7 / 8 | 5 / 5 |
| `soft_2mm_r2` | 8 / 8 | 7 / 8 | 5 / 5 |
| `soft_3mm_r1` | 8 / 8 | 7 / 8 | 5 / 5 |
| `soft_3mm_r2` | 8 / 8 | 7 / 8 | 5 / 5 |
| `medium_1mm_r1` | 8 / 8 | 7 / 8 | 5 / 5 |
| `medium_1mm_r2` | 8 / 8 | 7 / 8 | 5 / 5 |
| `medium_2mm_r1` | 파괴 | 7 / 8 | 5 / 5 |
| `medium_2mm_r2` | 8 / 8 | 7 / 8 | 5 / 5 |
| `medium_3mm_r1` | 8 / 8 | 7 / 8 | 5 / 5 |
| `medium_3mm_r2` | 8 / 8 | 7 / 8 | 5 / 5 |
| `hard_1mm_r1` | 8 / 8 | 7 / 8 | 5 / 5 |
| `hard_1mm_r2` | 8 / 8 | 7 / 8 | 5 / 5 |
| `hard_2mm_r1` | 8 / 8 | 7 / 8 | 5 / 5 |
| `hard_2mm_r2` | 8 / 8 | 7 / 8 | 5 / 5 |
| `hard_3mm_r1` | 8 / 8 | 8 / 8 | 5 / 5 |
| `hard_3mm_r2` | 8 / 8 | 7 / 8 | 5 / 5 |

숫자는 **그 유닛이 채운 pass 수 / 그 원리가 가진 pass 수**다. 분모가 원리마다 다른 것이
위 첫 표의 빈 칸이고, 분자가 분모보다 작은 것이 두 번째 표다.

## `characterize` (최대 측정 가능 힘) 는 원리마다 다른 pass 에 있다

| 원리 | 어느 데이터셋 안에 | 램프가 있는 유닛 |
|---|---|---:|
| 9DTact | `20260907_passB_ball8` | 17 / 17 |
| DIGIT | `20260910_passA_calibgrid` | 18 / 18 |
| DIGIT_Marker | `20260910_passA_calibgrid` | 18 / 18 |

9DTact 는 Pass B 안에서 돌렸고 **이미지 포화에 닿지 못해 천장이 하한으로만 남았다**;
DIGIT 계열은 격자 pass 뒤에 따로 돌려 36 / 36 실측했다 (`docs/force_ceiling.md` §6).

## 같은 유닛을 두 번 이상 잰 것

분석이 쓰는 런은 데이터셋 안에 하나뿐이고, 두 번째·세 번째 측정은
`<원리>/repeated_data/<데이터셋>/` 에 있다. 재현성의 바닥은 여기서만 나온다
(`docs/campaign_protocol.md` §4.15).

| 원리 | 데이터셋 | 유닛 | 반복 런 |
|---|---|---:|---:|
| 9DTact | `20260905_passA_ball4` | 5 | 11 |
| 9DTact | `20260905_passA_pair100` | 2 | 2 |
| DIGIT | `20260909_passA_pair010` | 1 | 1 |
| DIGIT | `20260910_passA_cube4` | 1 | 1 |
| DIGIT_Marker | `20260908_passB_ball8` | 1 | 3 |

---

유닛-pass 칸 370 개 중 353 개가 채워져 있다 (95.4 %). 표 데이터는 `data/dataset_audit.csv`.