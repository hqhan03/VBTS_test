# paper/fin_figures — 논문에 들어가는 그림과 그것을 그린 코드

**그림 · 코드 · csv 가 한 폴더에 있다.** 이 폴더만 통째로 건네면 누구든 다시 그린다.

```
cd paper/fin_figures
python3 paper_fig_ceiling.py          # 한 장씩
for f in paper_fig_*.py; do python3 "$f"; done   # 전부
```

필요한 것: `matplotlib` · `pandas` · `numpy` · `scipy`, 그리고 자국 그림에는 `opencv-python`.
자료는 `result/single/` 의 csv 와 `paper/figures/sources/` 의 원본 넉 장에서 읽는다 —
**`data/` 가 없는 기계에서도 전부 돌아간다.**

| 파일 | 무엇 | 자리 |
|---|---|---|
| `paper_style.py` | 판형 · 색 · 저장. **모든 그림이 이것을 import 한다** | — |
| `paper_fig_input_resolution.py` | **Figure 1** — 줄인 영상 셋 (a)(b)(c), 힘 (d), 형상 (e) | F1, I 장 |
| `paper_fig_growth.py` | 자국 성장 — 깊이 기준 대 힘 기준 | F3, IV.A |
| `paper_fig_separation.py` | 두 접촉 분리 — 자국 (a)(b), 단면 (c), 겔 (d), 화소 (e) | F4, IV.B |
| `paper_fig_ceiling.py` | 영상 응답 포화 힘 대 두께 | F0, IV.C |
| `paper_fig_ceiling_schematic.py` | 시편 판 — 두께 1·2·3 mm 와 경도 OO-30/50/70, 같은 힘 (흰 바탕) | F0s, III |
| `paper_fig_plateau_gel.py` | 평탄 밀도와 겔 — 표 V 를 받친다 | F7, V.A · V.B |

## 그림마다 나오는 것

`paper_style.save()` 가 셋을 함께 낸다. **csv 없이 그림을 저장하지 않는다.**

| 확장자 | 무엇 |
|---|---|
| `.pdf` | 본문에 넣는 것. 벡터, 글꼴 Type 42 (Type 3 은 PDF eXpress 가 되돌려 보낸다) |
| `.png` | 문서·메신저 미리보기용 |
| `.csv` | 그 그림을 그린 자료 그대로 — 직접 다시 그릴 수 있게 |

한 판에 자료가 둘 이상 들어가면 나머지는 `<이름>_<무엇>.csv` 로 따로 낸다
(`fig_separation_sweep.csv`, `fig_separation_profile.csv`). 검정을 낸 그림은
`<이름>_stats.csv` 를 낸다.

## 규칙

`../../CLAUDE.md` 가 정본이고, 여기서는 그중 그림에 걸리는 것만 다시 적는다.

- **칸마다 정해진 센서 하나만 쓴다** — 원리당 9, 합 27 (`result/single/`).
  고르지 않은 복제를 산포 목적으로도 겹쳐 찍지 않는다.
- **색은 `paper_style.py` 가 정한다** — 파랑 `#0047B3` · 초록 `#007A29` ·
  빨강 `#D40000` · 검정뿐이고, 순서가 있는 변수는 무를수록 파랑 · 단단할수록 빨강.
  `result/` 의 그림이 쓰는 `src/scripts/palette.py` 와 **갈린다** — 값을 옮겨
  적지 말고 각자의 파일에서 가져올 것.
- 판형은 한 단 `COL_W` 3.50 in · 두 단 `FULL_W` 7.16 in. **두 단 그림은 7.16
  보다 좁게 그려도 된다** — `\textwidth` 로 앉히면 그만큼 확대돼 글자가 커진다.
  두 패널짜리 기본값이 `FULL_W_NARROW` 6.10 in 이다.
- 글자 크기 · rcParams 를 그림 쪽에서 다시 쓰지 않는다. `paper_style` 한 곳에서 건다.
- 그림 안에는 설명 글자를 넣지 않는다. 제목은 `(a)` ~ `(e)` 뿐이고 **나머지는
  캡션이 진다** — 무엇을 캡션이 져야 하는지는 각 스크립트의 docstring 에 적혀 있다.
- 무엇을 싣고 무엇을 빼는가는 `../figure_plan.md` 가 정한다.

`../figures/` 는 그 전에 만든 `fig1` ~ `fig4b` 가 있는 곳이다. **섞지 않는다** —
matplotlib 으로 옮길 때마다 하나씩 이리로 넘어온다. 다만 `../figures/sources/`
의 원본 다섯 장은 계속 쓴다(자국 두 쌍, 축소 시연 한 장).
