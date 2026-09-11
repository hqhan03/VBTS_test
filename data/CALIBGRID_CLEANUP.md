# 20260910_passA_calibgrid — 폴더 정리 (2026-09-11)

이 캠페인은 코드를 고쳐 가며 돌았기 때문에 한 유닛이 최대 여덟 번까지 다시 측정됐다.
정리 규칙은 **폴더가 아니라 내용** 기준이다 — 36 유닛 중 12 개는 유효한 격자와 유효한
천장이 서로 다른 폴더에 있었으므로, '마지막 폴더만 남기기' 로는 천장 자료를 버리게 된다.

## 규칙

| 내용 | 이름 |
|---|---|
| 분석이 쓰는 격자 (정렬됨, 0.15 N 미만 프레임이 가장 적음) | `<유닛>` |
| 등록부의 천장이 나온 램프 (격자와 다른 폴더일 때만) | `<유닛>__ceiling` |
| 그 외 | `_discarded/<원리>/20260910_passA_calibgrid/` |

## 이름 변경 26 건

| 이전 | 이후 |
|---|---|
| `DIGIT_hard_1mm_r1__3` | `DIGIT_hard_1mm_r1` |
| `DIGIT_hard_1mm_r1__5` | `DIGIT_hard_1mm_r1__ceiling` |
| `DIGIT_hard_1mm_r2__7` | `DIGIT_hard_1mm_r2__ceiling` |
| `DIGIT_hard_1mm_r2__8` | `DIGIT_hard_1mm_r2` |
| `DIGIT_hard_2mm_r1__3` | `DIGIT_hard_2mm_r1__ceiling` |
| `DIGIT_hard_2mm_r1__4` | `DIGIT_hard_2mm_r1` |
| `DIGIT_hard_2mm_r2__2` | `DIGIT_hard_2mm_r2__ceiling` |
| `DIGIT_hard_2mm_r2__3` | `DIGIT_hard_2mm_r2` |
| `DIGIT_hard_3mm_r1__2` | `DIGIT_hard_3mm_r1__ceiling` |
| `DIGIT_hard_3mm_r1__3` | `DIGIT_hard_3mm_r1` |
| `DIGIT_hard_3mm_r2` | `DIGIT_hard_3mm_r2__ceiling` |
| `DIGIT_hard_3mm_r2__2` | `DIGIT_hard_3mm_r2` |
| `DIGIT_medium_2mm_r1__2` | `DIGIT_medium_2mm_r1__ceiling` |
| `DIGIT_medium_2mm_r1__3` | `DIGIT_medium_2mm_r1` |
| `DIGIT_medium_2mm_r2__2` | `DIGIT_medium_2mm_r2__ceiling` |
| `DIGIT_medium_2mm_r2__3` | `DIGIT_medium_2mm_r2` |
| `DIGIT_medium_3mm_r1` | `DIGIT_medium_3mm_r1__ceiling` |
| `DIGIT_medium_3mm_r1__3` | `DIGIT_medium_3mm_r1` |
| `DIGIT_medium_3mm_r2` | `DIGIT_medium_3mm_r2__ceiling` |
| `DIGIT_medium_3mm_r2__2` | `DIGIT_medium_3mm_r2` |
| `DIGIT_soft_3mm_r1__2` | `DIGIT_soft_3mm_r1` |
| `DIGIT_soft_3mm_r2__2` | `DIGIT_soft_3mm_r2` |
| `DIGIT_Marker_hard_3mm_r1__2` | `DIGIT_Marker_hard_3mm_r1` |
| `DIGIT_Marker_medium_3mm_r1__2` | `DIGIT_Marker_medium_3mm_r1` |
| `DIGIT_Marker_soft_1mm_r1__2` | `DIGIT_Marker_soft_1mm_r1__ceiling` |
| `DIGIT_Marker_soft_1mm_r2__2` | `DIGIT_Marker_soft_1mm_r2__ceiling` |

## 폐기 20 건 (1.11 GB)

버린 이유는 대체로 하나다 — 그 격자나 램프가 만들어진 뒤 코드가 고쳐졌다:
격자 원점이 직전 실행에서 상속되던 버그, 로봇 축 격자(이미지 축 정렬 이전),
autoframe 이 `reference.png` 로 차분하던 때, 사다리 올리기 이전의 약한 접촉,
그리고 characterize 가 격자 마지막 모서리에서 램프를 돌던 때.
각 사유는 `docs/photometric_calibration.md` §2 와 `docs/force_ceiling.md` §2 에 있다.


- `20260910_passA_calibgrid`: `DIGIT_Marker_hard_3mm_r1`, `DIGIT_Marker_medium_3mm_r1`, `DIGIT_hard_1mm_r1`, `DIGIT_hard_1mm_r1__2`, `DIGIT_hard_1mm_r1__4`, `DIGIT_hard_1mm_r2`, `DIGIT_hard_1mm_r2__2`, `DIGIT_hard_1mm_r2__3`, `DIGIT_hard_1mm_r2__4`, `DIGIT_hard_1mm_r2__5`, `DIGIT_hard_1mm_r2__6`, `DIGIT_hard_2mm_r1`, `DIGIT_hard_2mm_r1__2`, `DIGIT_hard_2mm_r2`, `DIGIT_hard_3mm_r1`, `DIGIT_medium_2mm_r1`, `DIGIT_medium_2mm_r2`, `DIGIT_medium_3mm_r1__2`, `DIGIT_soft_3mm_r1`, `DIGIT_soft_3mm_r2`

## 확인

정리 뒤 다시 세었다: **36 / 36 유닛의 등록부 천장을 그 램프에서 정확히 되찾을 수 있고**
(오차 0.0000 N), **36 / 36 유닛이 0.15 N 미만 프레임 없는 정렬 격자를 갖는다.**
