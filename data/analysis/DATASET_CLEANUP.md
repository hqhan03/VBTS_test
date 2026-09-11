# 데이터셋 정리 — 유닛당 폴더 하나 (2026-09-11)

> **세 원리 폴더는 `data/20260911_VBTSresolution_dataset/` 안에 있다** (운전자 지정,
> 2026-09-11). 재고는 그 폴더의 `DATA_INVENTORY.md`, 만드는 것은
> `scripts/dataset_audit.py` 다. 같은 날 `data/` 최상위도 다섯 항목으로 줄였다 —
> 어디에 무엇이 있는지는 `data/README.md`.

재측정한 유닛은 디스크에 `<유닛>`, `<유닛>__2`, … 로 남는다. 폴더 이름은 분석이 어떤 런을
읽을지 정하는 값이므로, 같은 유닛이 여러 폴더로 갈려 있으면 스크립트마다 다른 런을 집는다.
실제로 그런 일이 있었다(아래 "정리가 고친 것"). 그래서 데이터셋마다 **유닛당 폴더 하나**로
줄였다.

## 어느 런을 남겼나

| 대상 | 규칙 |
|---|---|
| Pass B (`*_passB_ball8`) | 그 폴더의 `CANONICAL.yaml` 이 정한 런 (`scripts/write_canonical.py`: 1000 프레임을 채운 것 중 마지막) |
| 그 외 (ball4 / cyl4 / cube4 / pair\*) | **가장 완결된 런** — 그 pass 의 사다리가 있는가 → 축척이 남았는가(`scale.yaml`) → 단이 많은가 → 마지막 시도인가, 순서로 |

"가장 높은 접미사" 만으로 고르면 틀린다. `9DTact_hard_1mm_r2__3` 은 사다리는 있지만
`scale_ball4` 가 아무것도 남기지 않은 런이고, `scripts/derived_variables.py` 의
`passa_run()` 이 접미사만 보고 그것을 집어 **이 유닛의 `px_per_mm` 를 잃고 있었다.**

## 남기지 않은 런은 어디로 갔나

| 어디로 | 무엇 | 수 |
|---|---|---|
| `_discarded/<원리>/<데이터셋>/` | 중단된 런 — 사다리도 스트림도 없거나, 한 단계가 결과를 남기지 않았거나, 스트림이 짧다. 각 폴더에 `WHY_DISCARDED.md` | 54 |
| `<원리>/repeated_data/<데이터셋>/` | **승자와 같은 정도로 완결된 두 번째 측정.** 버리지 말 것 — 같은 유닛을 다시 잰 데이터는 이것뿐이다. 각 폴더에 `WHY_REPEAT.md`, 원리마다 `repeated_data/README.md` | 18 |

이름을 고친 30 폴더에는 `PROVENANCE.yaml` 을 두어 원래 이름과 왜 갈렸는지를 적었다.

## 정리가 고친 것

1. **`data/analysis/pair_resolution.csv` 가 `hard_3mm_r2` 를 두 번 세고 있었다.** `pair_summary.py`
   는 폴더를 전부 훑고 이름에서 `__N` 만 떼므로, 갈린 두 폴더가 같은 유닛의 두 행이 됐다.
   37 행 → 36 행.
2. **`data/analysis/derived_variables.csv` 의 `9DTact_hard_1mm_r2` 에 축척이 없었다.** 위의 이유로
   `px_per_mm` 가 비어 있었다(지금 88.30, `scale_trusted` 참). `hertz_k` 0.955 → 1.331,
   `hertz_n` 1.259 → 2.042 로 함께 고쳐졌다. 그 결과 `correlations.csv` 에서
   `hertz_n → fz_best` 가 ρ +0.350 q 0.032 에서 ρ +0.272 q 0.118 로 **유의하지 않게**
   되었다 — 어느 문서도 이 관계를 주장하지 않았으므로 철회할 것은 없지만, 표를 읽는 사람이
   알아야 한다.
3. **`data/analysis/gel_identity.csv` 가 중단된 런을 한 행으로 세고 있었다**(0 프레임인데
   `reference.png` 이 있었다). 19 행 → 18 행.
4. **등록부의 없는 경로 15 개.** `config/sensor_registry.yaml` 의 `run:` 이 지워지거나
   이름이 바뀐 폴더를 가리키고 있었다. 지금은 살아 있는 폴더를 가리키고 `run_folder_was`
   에 원래 이름이 남는다. 고칠 수 없는 3 개(2026-09-11 이전에 지워진 폴더)는
   `run_missing: true` 로 표시했고, 그중 **파괴 사례**는 남아 있는 증거 경로를
   `run_evidence` 로 적었다.
5. **`analyse_resolution.py` 가 버린 런을 읽을 수 있었다.** 데이터셋을 이름으로 찾을 때
   `data/*/<데이터셋>` 과 `data/*/*/<데이터셋>` 을 보는데, 후자가
   `data/_discarded/<원리>/<데이터셋>` 에도 걸린다. 지금은 `_discarded` 를 뺀다.
6. **같은 유닛 반복 측정 10 유닛 18 런을 찾았다.** 캠페인에 없던 재현성의 바닥이 여기서
   나온다 — `scripts/repeat_spread.py`, `campaign_protocol.md` §4.15.

## 폴더를 옮기면서 바뀐 숫자 하나

`data/analysis/pair_resolution.csv` 의 두 행(`hard_3mm_r1` 의 pair025·pair010)이 달라졌다. 원인은
**빌려 쓰는 축척의 중앙값**이다: 자기 축척이 자기 검사를 통과하지 못한 유닛은
`analyse_resolution.py` 가 "믿을 수 있는 축척 전부의 중앙값" 을 빌려 쓰는데, 그 "전부" 를
`state.json` 글롭으로 모은다. 반복 측정 18 런이 데이터셋 옆(`<데이터셋>_repeats/`)에 있던
동안에는 그 글롭에 걸려서 **열 유닛이 2 ~ 5 번씩 세어졌다**. `repeated_data/` 로 옮기니
걸리지 않는다 — 유닛마다 한 번씩 세는 쪽이 중앙값으로 옳다.

바뀐 것은 36 행 중 2 행이고, 둘 다 그 스크립트가 "mm 축은 잠정, ±15 %" 라고 스스로
표시하는 유닛이다. dip 은 0.106 → 0.097 로 움직였다. 나머지 34 행과 다른 표
(`ceiling_summary`, `cyl4_summary`, `repeat_spread`, `marker_occlusion`)는 **바이트 단위로
동일**하다.

## 정리 뒤 폴더 수

데이터셋마다 유닛당 폴더 하나:

| 원리 | 데이터셋 | 폴더 |
|---|---|---|
| 9DTact | `20260905_passA_ball4` | 17 |
| 9DTact | `20260905_passA_cube4` | 17 |
| 9DTact | `20260905_passA_cyl4` | 17 |
| 9DTact | `20260905_passA_pair025` | 17 |
| 9DTact | `20260905_passA_pair050` | 17 |
| 9DTact | `20260905_passA_pair075` | 17 |
| 9DTact | `20260905_passA_pair100` | 17 |
| 9DTact | `20260907_passB_ball8` | 17 |
| DIGIT | `20260908_passA_ball4` | 18 |
| DIGIT | `20260908_passA_pair100` | 1 |
| DIGIT | `20260908_passB_ball8` | 18 |
| DIGIT | `20260909_passA_pair010` | 18 |
| DIGIT | `20260909_passA_pair025` | 18 |
| DIGIT | `20260910_passA_calibgrid` | 18 |
| DIGIT | `20260910_passA_cube4` | 18 |
| DIGIT | `20260910_passA_cyl4` | 18 |
| DIGIT_Marker | `20260908_passA_ball4` | 18 |
| DIGIT_Marker | `20260908_passB_ball8` | 18 |
| DIGIT_Marker | `20260910_passA_calibgrid` | 18 |
| DIGIT_Marker | `20260910_passA_cube4` | 18 |
| DIGIT_Marker | `20260910_passA_cyl4` | 18 |

9DTact 는 17 유닛(`medium_2mm_r1` 은 파괴됨), DIGIT / DIGIT_Marker 는 18 유닛이다.
`DIGIT/20260908_passA_pair100` 의 1 은 그 pass 에서 한 유닛만 측정했기 때문이다
(`data_wishlist.md` #0).

반복 측정은 원리마다 `repeated_data/<데이터셋>/` 한 곳에 모았다(운전자 지정, 2026-09-11):

| 원리 | 데이터셋 | 유닛 | 반복 런 |
|---|---|---:|---:|
| 9DTact | `20260905_passA_ball4` | 5 | 11 |
| 9DTact | `20260905_passA_pair100` | 2 | 2 |
| DIGIT | `20260909_passA_pair010` | 1 | 1 |
| DIGIT | `20260910_passA_cube4` | 1 | 1 |
| DIGIT_Marker | `20260908_passB_ball8` | 1 | 3 |

폴더 이름에 남은 `__N` 은 그날의 몇 번째 시도였는지이고, 데이터셋 폴더 밖에 있으므로 어떤
glob 도 그것을 유닛으로 집지 않는다. 원리마다 `repeated_data/README.md` 가 읽는 법을 적는다.

## 다시 확인하는 법

```bash
# 데이터셋마다 유닛당 폴더 하나인가
for pr in 9DTact DIGIT DIGIT_Marker; do
  for d in data/$pr/2026*/; do
    n=$(ls -1d "$d"*/ 2>/dev/null | grep -cE "__[0-9]+/$")
    [ "$n" -gt 0 ] && echo "$d: __N 폴더 $n 개"
  done
done
# 천장이 등록부와 맞는가
python3 src/scripts/ceiling_summary.py --check
# 등록부의 run 경로가 다 존재하는가 (run_missing 표시된 것 제외)
```
