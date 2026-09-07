# 사용하지 않는 런

`data/<principle>/<dataset>/<sensor>` 에서 옮겨온 런들. **지운 것이 아니라 옮긴 것**이고,
원래 경로는 이 폴더 아래 그대로 재현되어 있다.

## 왜 여기 있나

한 (패스, 센서) 조합에는 논문에 쓸 런이 하나만 남는다. 나머지가 여기 온다:

* **중복·미완** — 시작만 하고 끝나지 않은 시도. state.json 에 zero/shape/scale/stream 이 없다.
* **`__badzero`, `__noisyzero`, `__settle015`, `__read06`, `__overpressed`** — 프로토콜을
  바꿔가며 다시 잰 것들. 옆에 정상 런이 있다.
* **`__WRONG_SENSOR`, `__UNVERIFIED`** — 장착된 센서가 이름과 달랐거나 확인되지 않은 런.
* **`__2`, `__3`** 등 — 같은 조합의 이전 시도. 남긴 것은 항상 가장 최근의 정상 런이다.

## 남길 런을 고른 규칙

`scripts/analyse_resolution.py` 가 쓰는 규칙과 **글자 그대로 같다**: 격리 표식이 붙지 않고,
접미사를 뗀 이름이 센서 id 와 같으며, 실제 데이터가 있는 폴더 중 **가장 최근 것**.
119개 조합을 대조해 불일치 0건임을 확인한 뒤 옮겼으므로,
`data/9DTact/resolution_measurements.csv` 의 210행은 그대로 재현된다.

## 깊이에 대한 주의

경로가 `data/_discarded/<principle>/<dataset>/<run>/` 로 한 단계 깊다. 이건 의도적이다.
분석 코드가 런을 찾을 때 쓰는 glob 은 `data/*/*/state.json` 과 `data/*/*/*/state.json`
두 가지뿐이라, 한 단계 더 깊은 이 폴더는 어디에도 걸리지 않는다.
얕게 옮기면 폐기한 런이 다시 스캔에 들어온다.
