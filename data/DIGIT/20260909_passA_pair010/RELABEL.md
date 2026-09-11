# 라벨 교정 — 2026-09-10

이 pass 는 입력된 이름에서 soft 와 hard 가 바뀐 채로 수집됐다. 운영자가 알렸고
`scripts/identify_gel_colour.py` 의 무부하 색비율 판정이 확인했다(라벨까지의 거리가
판정된 겔의 4–36 배; medium 여섯 런은 모두 옳다). `campaign_protocol.md` §4.11.

폴더 이름은 **실제 겔**로 고쳤고, 각 `meta.yaml` 의 `sensor_id_as_typed` 에 입력값이 남아 있다.

| 입력된 이름 | 실제 겔 (현재 폴더 이름) |
|---|---|
| DIGIT_hard_1mm_r1 | DIGIT_soft_1mm_r1 |
| DIGIT_hard_1mm_r2 | DIGIT_soft_1mm_r2 |
| DIGIT_hard_2mm_r1 | DIGIT_soft_2mm_r1 |
| DIGIT_hard_2mm_r2 | DIGIT_soft_2mm_r2 |
| DIGIT_hard_3mm_r1 | DIGIT_soft_3mm_r1 |
| DIGIT_soft_1mm_r1 | DIGIT_hard_1mm_r1 |
| DIGIT_soft_2mm_r1 | DIGIT_hard_2mm_r1 |
| DIGIT_soft_3mm_r1 | DIGIT_hard_3mm_r1 |

## 3 mm r2 충돌 — 해결됨 (2026-09-10)

처음에는 두 런이 같은 이름을 요구해 손대지 않고 두었다. 운영자가 hard_3mm_r2 를 다시 장착해 한 번 더
측정하자 답이 나왔다: **새 런의 색이 "soft_3mm_r2" 로 입력된 런과 0.0005 로 사실상 동일**하고, "hard_3mm_r2"
로 입력된 런과는 0.0189 로 멀다. 즉 그 pass 는 **예외 없이** 전부 뒤바뀌어 있었고, 운영자가 "확실하다" 고
한 런도 실제로는 hard_3mm_r2 였다.

| 입력된 이름 | 실제 겔 | 현재 폴더 |
|---|---|---|
| DIGIT_hard_3mm_r2 | soft_3mm_r2 | `DIGIT_soft_3mm_r2` |
| DIGIT_soft_3mm_r2 | hard_3mm_r2 | `DIGIT_hard_3mm_r2` |
| (재장착, 입력도 hard_3mm_r2) | hard_3mm_r2 | `DIGIT_hard_3mm_r2` |

hard_3mm_r2 는 이렇게 **같은 프로브로 두 번** 측정됐다 — 재장착·재영점이 만드는 측정 산포를
재는 데 쓸 수 있다. **그렇게 했다** (2026-09-11): 재장착 런을 분석이 쓰는 `DIGIT_hard_3mm_r2` 로
두고, 먼저 잰 런은 `../20260909_passA_pair010_repeats/DIGIT_hard_3mm_r2` 로 옮겼다.
`scripts/repeat_spread.py` 가 둘을 겹쳐 읽는다 — 공통 깊이에서 힘의 cv 0.097, sd 0.041 N 이고,
같은 데이터셋 18 유닛 사이의 cv 0.507 이므로 유닛 차이가 재장착 산포의 5.2 배다.

세 런 모두 라이브러리의 3 mm r2 항목과는 확신 있게 맞지 않는다(최적 medium_3mm_r2, 여유 1.3 배). 같은 겔의
두 런이 0.0005 로 일치하므로 방법의 정밀도 문제는 아니고, **Pass B 쪽 3 mm r2 라벨이 의심된다.**
