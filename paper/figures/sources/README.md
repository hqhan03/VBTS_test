# Figure 1 의 원본 촬영본

`data/` 는 깃헙에 올리지 않으므로(표준), **그림을 다시 그리는 데 꼭 필요한
다섯 장만** 여기 둔다. 전부 1920×1080 원본이고 손대지 않았다.

| 파일 | 원래 자리 | 무엇 |
|---|---|---|
| `fig1b_hard_1mm_r1_pair100_d0.30.png` | `9DTact/20260905_passA_pair100/9DTact_hard_1mm_r1/shape_pair100/` | (b) 왼쪽 — 1 mm 겔, 접촉 |
| `fig1b_hard_1mm_r1_reference.png` | 같은 런의 `reference.png` | (b) 왼쪽 — 그 런의 무접촉 기준 |
| `fig1b_hard_3mm_r1_pair100_d0.30.png` | `.../9DTact_hard_3mm_r1/shape_pair100/` | (b) 오른쪽 — 3 mm 겔, 접촉 |
| `fig1b_hard_3mm_r1_reference.png` | 같은 런의 `reference.png` | (b) 오른쪽 — 그 런의 기준 |
| `fig1c_hard_2mm_r1_ball8_000501.png` | `9DTact/20260907_passB_ball8/9DTact_hard_2mm_r1/stream/` | (c) 축소 시연에 쓰는 접촉 프레임 |

## 읽는 법

**(b) 에 그려지는 것은 원본이 아니라 `|접촉 − 기준|`** 이다(σ = 3 가우시안
평활 뒤, 두 장이 **같은 표시 범위**). 그래서 기준영상이 짝으로 필요하다.
두 유닛은 같은 경도(hard), 같은 프로브(`pair100`, 기둥 ⌀1.0 mm 둘, 중심 간격
2.00 mm), 같은 압입(0.30 mm)이고 **두께만** 1 mm 와 3 mm 로 다르다.

**(c) 는 원본 한 장을 면적 평균으로 줄여** 320 · 80 · 16 px 폭을 만든다.
`stream/` 1000 장 가운데 중간 프레임(`000501.png`)이고, `paper_fig1.py` 가
`len(cand)//2` 로 고르던 바로 그 장이다.

## 다시 그리기

`paper_fig1.py` 는 이 폴더를 **먼저** 보고, 없으면 `data/` 로 물러난다. 그러니
이 저장소만 있으면 그림이 그대로 다시 나온다.

```bash
python3 src/scripts/paper_fig1.py
```
