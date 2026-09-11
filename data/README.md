# data/ — 무엇이 어디에 있나

2026-09-11 에 다섯 항목으로 줄였다. 그 전에는 최상위에 폴더 24 개와 파일 24 개가 있었다.

| 항목 | 크기 | 무엇 |
|---|---:|---|
| `20260911_VBTSresolution_dataset/` | 159G | **최종 데이터셋.** 세 원리 × 프로브별 pass × 겔 유닛. 재고는 그 안의 `DATA_INVENTORY.md` |
| `analysis/` | 428K | 분석이 낸 표 21 개와 정리 기록 두 편 |
| `earlier_datasets/` | 26G | 프로토콜을 확정하기 전의 측정 6 벌 |
| `rig/` | 131M | 로봇 · F/T · TCP 장비 쪽 기록 16 벌 |
| `_discarded/` | 9.5G | 버린 런. 폴더마다 `WHY_DISCARDED.md` |
| `_active_run.txt` | — | 마지막으로 돌린 런의 경로 (`data/` 기준 상대). `run_indentation.py` 가 읽고 쓴다 |

## `20260911_VBTSresolution_dataset/`

캠페인이 답하려는 질문의 데이터가 여기 있다. 세 원리(9DTact / DIGIT / DIGIT_Marker),
프로브마다 pass 하나, 유닛당 폴더 하나. 같은 유닛을 두 번 이상 잰 런은 원리마다
`repeated_data/` 에 따로 있다 — 재현성의 바닥이 거기서만 나오기 때문이다.
구조와 빠진 데이터는 `20260911_VBTSresolution_dataset/DATA_INVENTORY.md`,
만드는 것은 `scripts/dataset_audit.py`.

## `analysis/`

스크립트가 쓰고 문서가 인용하는 표다. 전부 다시 만들 수 있다 — 어느 스크립트가 어느
표를 쓰는지는 `docs/README.md` 에 있다. 여기 있는 두 md 는 데이터셋을 어떻게 정리했는지의
기록이다: `DATASET_CLEANUP.md`(유닛당 폴더 하나로 줄인 과정과 그것이 고친 결함),
`CALIBGRID_CLEANUP.md`(격자 pass 만의 정리).

## `earlier_datasets/`

지금 프로토콜 이전의 측정이다. **분석이 쓰지 않는다.** 그래도 지우지 않는 이유는
`20260904_probe_tests/9DTact_medium_2mm_r1/characterize_to30N_nosub` 같은 것이 있기
때문이다 — 이 캠페인에서 겔이 영구변형된 **유일한** 기록이고
`docs/force_ceiling.md` §7 이 그것을 인용한다.

- `20260901_protocol_development`
- `20260903_ladder_protocol`
- `20260903_raw_dataset`
- `20260904_4mmBall`
- `20260904_probe_tests`
- `20260905_method_development`

## `rig/`

겔이 아니라 **장비**를 잰 것들. 좌표 변환, F/T 영점과 여기, TCP 보정, SG5 배선,
모션 로그. `frame_transform/` 은 살아 있다 — `run_indentation.py` 가 매 런마다 가장
최근 `transform.yaml` 을 읽는다.

- `daq_mapping`
- `diagnostics`
- `final_ft_validation`
- `frame_analysis`
- `frame_transform`
- `ft_baseline`
- `manual_ft_excitation`
- `manual_ft_excitation_final`
- `motion`
- `motion_enable`
- `robot_readonly_check`
- `sg5_mapping`
- `sg5_relocation`
- `tcp_application`
- `tcp_calibration`
- `weight_validation`
