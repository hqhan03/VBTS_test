# src/ — 코드 전부

2026-09-11 에 `scripts/`, `tests/`, `config/` 를 여기로 들였다. 저장소 루트에는 이제
`src/`, `docs/`, `data/` 와 몇 개의 파일만 있다.

| | 파일 | 무엇 |
|---|---:|---|
| `vbts_platform/` | 9 | **장비를 다루는 라이브러리.** 로봇·F/T·카메라. `scripts/` 가 전부 이것을 쓴다 |
| `scripts/` | 66 | 실험을 돌리는 것과 분석하는 것. 하나가 하나의 일을 한다 |
| `config/` | 6 | 로봇·F/T·카메라 설정, 프로브 치수, **센서 등록부**, ATI 보정 파일 |
| `tests/` | 2 | 127 개. 대부분 **로봇이 움직이지 않는지**를 검사한다 |

## `vbts_platform/`

실험 프로토콜(무엇을 누를지)과 장비 제어(어떻게 움직일지)를 가르는 층이다.
`robot_interface.py` 가 모든 프로토콜이 쓰는 단 하나의 입구이고, 그 아래
`fr5_io.py` 가 FR5 의 XML-RPC 명령 채널(20003)과 실시간 상태 스트림(20004)을 다룬다.
`ft_interface.py` 는 ATI Mini45 를 NI-DAQmx 로 읽고, `ati_calibration.py` 가 생전압을
렌치로 바꾼다. `camera_interface.py` 는 센서 내부 카메라다.

## `scripts/`

로봇을 움직이는 것은 `run_indentation.py`(단계별)와 `run_one_sensor.py`(한 유닛 전체)다.
나머지는 분석이고, 어느 스크립트가 어느 표를 만드는지는 `docs/README.md` 에 있다.
`make_*.py` 여섯 개는 논문용 산출물을 `result/` 에 쓴다 — 그림마다 같은 숫자의 csv 를
옆에 함께 남기므로, 분석을 다시 돌리지 않고도 그림을 다시 그릴 수 있다.
경로는 모두 저장소 루트 기준으로 잡는다 — `Path(__file__).resolve().parents[2]`.

## `config/`

`FT29831.cal` 은 ATI 가 이 Mini45 와 함께 준 보정 파일이다 — 생전압을 렌치로 바꾸는
행렬이고 손대지 않는다. `ft_config.yaml` 이 이름으로 가리키며, 찾는 순서는
`src/config/` → `calibration/` → 저장소 루트 → 설정 파일 옆이다. 2026-09-11 전에는
저장소 루트에 있었으므로 그 두 자리를 남겨 두었다.

`fr5_tcp_jog_gui.py` 는 `scripts/` 에 있다 — 라이브러리보다 먼저 쓴 독립 GUI 로,
FR5 의 두 포트(20003 XML-RPC, 20004 상태 스트림)를 처음 확인한 도구다. `fr5_io.py` 가
그 프로토콜 세부를 여기서 그대로 가져왔다. 아무것도 이것을 import 하지 않는다.

`sensor_registry.yaml` 이 가장 중요하다: 유닛 54 개의 겔 규격, 안전 한계, 측정 이력,
그리고 각 측정이 어느 런에서 나왔는지. 런이 끝날 때마다 갱신된다.

## `tests/`

```bash
python3 -m pytest src/tests/ -q --rootdir=. -p no:cacheprovider
```

`--rootdir`/`-p` 는 이 기계의 ROS 환경이 `conftest` 를 가로채기 때문에 필요하다.
검사의 절반은 안전 장치다 — 드라이런에서 소켓 호출이 나가지 않는지, 감시 장치가
연결보다 먼저 터지는지, 문이 둘 다 열려도 안 움직이는지. 나머지는 깨지면 **조용히**
틀린 데이터를 만드는 것들이다: `movel` 의 33 개 파라미터 자리와 순서, 자세 입력 검증.
