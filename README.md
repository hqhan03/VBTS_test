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

## 캠페인의 현재 (2026-09-13, 수집 종료)

53 유닛 전부에 힘 추정 쓸기가 있고, DIGIT 계열 36 유닛 전부에 광도 보정 격자가 있으며,
모든 데이터셋이 유닛당 정확히 한 폴더를 갖는다(`data/analysis/DATASET_CLEANUP.md` —
분리돼 있던 폴더가 한 유닛의 축척을 잃게 하고 다른 하나를 두 번 세게 하고 있었다).

표제 질문 — **오차가 포화하는 해상도가 겔에 따라 다른가** — 의 답은 **아니다**다.
√2 사다리에서 두 DIGIT 계열 모두 무릎이 두께에 대해 평평하고(p 0.85, p 0.66), 2 배
사다리에서 나왔던 유일한 유의 결과는 무릎 추정이 불안정해서 생긴 허상이었다
(`docs/cross_principle.md` §3.10). 방향 자체는 학습 없이 재는 두 측정에서 살아남지만,
학습된 무릎으로는 보이지 않는다.

### 그 뒤에 바뀐 것 — 옛 절을 읽기 전에 알아 둘 것

| 바뀐 것 | 어디에 |
|---|---|
| **천장을 두 원리에서 한 프로브(`ball8`)로 다시 쟀다.** `ball4` 로 선언한 9DTact 천장 다섯 개를 철회했다 — 다섯 다 공의 지름보다 깊어서 접촉이 구가 아니라 **자루**였다 | `docs/force_ceiling.md` §6.3(철회), §6.8(35 유닛 비교: 31.00 대 17.33 N, 1.8 배) |
| **DIGIT 겔의 경도를 실측했다**: OO-51 / 54 / 57 대 9DTact 의 OO-30 / 50 / 70. 두 계열이 흔든 폭이 6 점과 40 점으로 **6.7 배** 다르므로 **경도 축으로는 두 원리를 비교할 수 없다**. 거기 기대고 있던 결론을 철회했다 | `docs/methods.md` §2.1, `docs/force_ceiling.md` §6.8 결론 3 |
| **세 원리를 1920×1080 부터 8×5 까지, 학습 파라미터를 전부 같게 고정한 채 다시 학습했다.** 하나로 합친 노름 대신 축별 Fx/Fy/Fz MAE 를 낸다 | `docs/force_estimation.md` §2.6, `result/results.md` §8 |
| **사전등록한 H9 이 맞았다** — 마커는 전단의 해상도 의존성을 **뒤집는다**. 1920×1080 이 80×45 보다 나은 유닛이 9DTact 2/15, DIGIT 1/18 인데 Marker 는 **15/18**(p 0.002)이다. 다만 기전은 H9 이 상정한 것이 아닐 것이다 | `docs/cross_principle.md` §3.5a, `docs/force_estimation.md` §2.6 |
| **DIGIT 형상의 "평평한 곡선" 을 철회했다.** 기준영상 결함이었다 — `reference.png` 가 이후 프레임보다 8~14 % 밝다. 고치니 MAE < 0.1 mm 인 유닛이 6/18 에서 **15/18** 로, 해상도 의존성이 평평에서 **3.9 배**로 바뀌었다. 남은 한계는 정확도가 아니라 **깊이의 절대 배율** | `docs/shape_reconstruction.md` §5, `docs/methods.md` §10.0 |
| **빛 새는 두 유닛을 제외했다** (`9DTact_hard_1mm_r2`, `9DTact_medium_1mm_r2`). 등록부의 `suspect_hardware` 가 근거이고, `result/` 의 모든 그림·표·csv 에서 빠진다 | `docs/replicate_audit.md`, `docs/force_ceiling.md` §6.5c |

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

## 두 가지 규칙

**`data/` 는 저장소에 없다 — 그러나 `result/` 는 있다.** 측정도, 아래 절들이 인용하는
결과표(`data/analysis/*.csv`)도, 그 안의 문서도 전부 측정 기계에만 있다. 여기 적힌 모든
숫자는 그 표에서 읽어 넣은 것이고, 각각을 다시 만드는 스크립트를 옆에 적어 두었다.
논문에 넣을 그림과 표는 **`../result/`** 에 **그것을 그린 csv 와 함께** 복사해 두어
어디서나 열린다.

**기계가 읽는 진실은 여기가 아니라 `config/` 에 있다.** `sensor_registry.yaml`(센서별
한계, 겔 모델, 수집 정책), `probes.yaml`(압자 기하, TCP, 접촉 법칙), `ft_config.yaml`
(배선, 고장, 보정), `camera_config.yaml` 이 코드가 읽는 것이다. **문서의 숫자가 설정과
다르면 문서가 낡은 것이고, 설정이 이긴다.**

---

## 물릴 네 가지

**1. `python3` 말고 `/usr/bin/python3` 을 쓸 것.** PATH 의 `python3` 은 Anaconda 이고
`nidaqmx` 가 없다. `run_one_sensor.py` 가 시작할 때 검사해서 **로봇이 움직이기 전에**
거부한다.

**2. `Dev1/ai5` 와 `Dev1/ai6` 은 고장이다. 절대 게이지를 배정하지 말 것.**
`ai5` 는 단선이고, `ai6` 은 바로 앞 채널의 2.1 % 를 끌어온다. SG5 가 `ai7` 에 있는 것이
그 때문이다. 두 고장 다 `ft_config.yaml` 의 `known_hardware_faults` 에 있고, 둘 중
하나라도 채널 목록에 돌아오면 단위 테스트가 실패한다. **초기의 "유령 횡력" 결과는 전부
여기서 나왔다.**

**3. 로봇은 사고로 움직일 수 없고, 그것은 의도된 것이다.** 통과하려고 관문을 "고치지"
말 것.

**4. `SetToolCoord` 는 저장만 하는 호출이 아니다.** FAIRINO 문서가 "set **and load**"
라고 적어 두었다 — 쓰는 레지스터를 활성화한다. 활성화 없이 저장하려면 `SetToolList` 를
쓸 것. **tool 0 은 절대 덮어쓰지 말 것**, tool 1 은 이미 적용된 TCP 를 담고 있으니
운전자에게 묻지 않고 바꾸지 말 것.

---

## 무엇이 로봇을 멈춰 세우나

이 저장소에는 서로 다른 안전 이야기가 둘 있고, 옛 문서들은 첫째만 설명했다.

**옛 `RobotInterface` 관문.** 기본이 `dry_run=True`(소켓을 열지 않는다),
`allow_real_motion=False`(`dry_run` 만 끄면 예외가 난다), 그리고 실제 RPC 전달은
아예 배선되지 않았다. **캠페인의 어느 것도 이 클래스를 지나가지 않는다.** 가지 않은
길이니 건드리지 말 것.

**캠페인이 실제로 쓰는 길**은 `move_probe.py` 와 `run_indentation.py` 이고, 그 관문은:

| 관문 | 하는 일 |
|---|---|
| `--confirm MOVE` / `--confirm RUN` | 명령줄에 그 토큰이 글자 그대로 없으면 어떤 스크립트도 동작을 명령하지 않는다 |
| 읽기 전용 대리자 | 진단은 `Get*` 만 통과시키는 허용 목록을 쓴다. `SetToolCoord`, `MoveL`, `RobotEnable` 따위는 선에 닿기 전에 `PermissionError` 를 낸다 |
| 네트워크 사전 점검 | 로봇을 건드리는 모든 스크립트가 경로를 먼저 보고, 192.168.58.2 로 갈 트래픽이 기본 경로로 나가면 거부한다 |
| `ready_to_move()` | 컨트롤러가 수동 모드이면 거부한다 — 손으로 조그하면 항상 거기에 남는다 |
| 관절 변화 상한 | 계획된 동작의 최대 관절 변화가 상한을 넘으면 재구성으로 보고 보내지 않는다. 잘못된 IK 분기를 잡는 것이 이것인데, 이 팔에서는 관절 하나가 200° 넘게 돈다 |
| 기울기 / 반경 관문 | 압자가 겔 법선에서 몇 도 이상 벗어나거나 센서 축에서 벗어나면 런을 멈춘다 |
| 모든 출구에서 park | 실패한 런도, 예외도, Ctrl-C 도 프로세스가 끝나기 전에 압자를 들어 올린다 |

`apply_tcp_to_tool_register.py` 만 일부러 읽기 전용 대리자 밖에 있다. 쓰기가 일어날 수
있는 유일한 곳이고, `SetToolCoord` 또는 `SetToolList` 만 보낼 수 있다. **tool 0 은 절대
덮어쓰지 말 것.** tool 1 은 적용된 TCP 를 담고 있으니 운전자에게 묻지 않고 바꾸지 말 것.

---

## 센서 하나 돌리기

```bash
# Pass B (힘 추정), 센서 하나, 처음부터 끝까지 — 약 15 분
src/scripts/pass_b_sensor.sh 9DTact_soft_1mm_r1

# Pass A (형상 + 분해능), 센서 하나에 압자 하나
src/scripts/pass_a_sensor.sh 9DTact_soft_1mm_r1 pair050

# 읽기 전용: 팔이 어디 있나, 움직일 준비가 됐나
/usr/bin/python3 src/scripts/move_probe.py --status

# 런이 어떤 상태로 끝났든 겔에서 들어 올리기
/usr/bin/python3 src/scripts/run_one_sensor.py --sensor <id> --from park --to park --confirm RUN
```

두 pass 스크립트는 **모든 출구에서** 압자를 겔 위 **78 mm** 에 둔다 — 실패도 Ctrl-C 도
마찬가지다. 그렇게 끝나지 않은 런이 있다면 무언가 잘못된 것이니, 아무것도 건드리기 전에
`--status` 로 확인할 것.

## 분석

```bash
# 한 pass, 한 센서의 공간 분해능
/usr/bin/python3 src/scripts/analyse_resolution.py 20260905_passA_pair050 9DTact_hard_3mm_r2

# 형상 복원, 전 유닛 (data/20260911_VBTSresolution_dataset/9DTact/shape_reconstruction*.csv 를 쓴다)
/usr/bin/python3 src/scripts/analyse_shape.py

# 한 유닛의 겔 법선 보정 (동작을 명령하지 않는다)
/usr/bin/python3 src/scripts/gel_normal.py --sensor 9DTact_hard_3mm_r1

# 쌍둥이 불일치·경향성 이상치·자료량 부족
python3 src/scripts/twin_audit.py

# 논문용 그림과 표를 result/ 로 — 각각 그것을 그린 csv 와 함께
python3 src/scripts/make_result_tables.py      # 3x3 표, 칸은 "r1 / r2  (평균)"
python3 src/scripts/make_result_figures.py     # 원리를 가로지르는 그림 A~F
python3 src/scripts/make_force_mae_figures.py  # 축별 MAE 대 해상도
python3 src/scripts/make_shape_figures.py      # 형상 정확도 대 해상도
python3 src/scripts/make_optical_curves.py     # 깊이에 따른 자국 지름과 밝기
python3 src/scripts/make_results_md.py         # 위의 결과로 result/results.md 를 쓴다
```

**그림마다 같은 숫자의 csv 를 옆에 남긴다.** 분석을 다시 돌리지 않고도 그림을 다시
그릴 수 있다.

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
