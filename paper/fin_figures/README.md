# paper/fin_figures — 논문에 들어가는 그림과 그것을 그린 코드

**그림 · 코드 · csv 가 한 폴더에 있다.** 이 폴더만 통째로 건네면 누구든 다시 그린다.

```
cd paper/fin_figures
python3 paper_fig_ceiling.py
```

필요한 것: `matplotlib` · `pandas` · `numpy` · `scipy`.
자료는 `result/single/` 의 csv 에서 읽는다 — `data/` 가 없는 기계에서도 돌아간다.

| 파일 | 무엇 |
|---|---|
| `paper_style.py` | 판형 · 색 · 저장. **모든 그림이 이것을 import 한다** |
| `paper_fig_ceiling.py` | 영상 응답 포화 힘 대 두께 (IV.C) |

색은 `src/scripts/palette.py` 하나에서 나온다 — `result/` 의 그림과 같은 색을 써야
하므로 여기에 값을 베껴 두지 않는다.

## 그림마다 나오는 것

`paper_style.save()` 가 셋을 함께 낸다. **csv 없이 그림을 저장하지 않는다.**

| 확장자 | 무엇 |
|---|---|
| `.pdf` | 본문에 넣는 것. 벡터, 글꼴 Type 42 |
| `.png` | 문서·메신저 미리보기용 |
| `.csv` | 그 그림을 그린 자료 그대로 — 직접 다시 그릴 수 있게 |

검정을 낸 그림은 `<이름>_stats.csv` 를 따로 낸다.

## 규칙

`CLAUDE.md` 가 정본이고, 여기서는 그중 그림에 걸리는 것만 다시 적는다.

- **칸마다 정해진 센서 하나만 쓴다** — 원리당 9, 합 27 (`result/single/`).
  고르지 않은 복제를 산포 목적으로도 겹쳐 찍지 않는다.
- IEEE 두 단 판형 — 한 단 3.50 in · 두 단 7.16 in. 다른 폭을 쓰지 않는다.
- 색만으로 군을 가르지 않는다. 경도마다 표식 모양(`o` / `s` / `^`)을 함께 건다.
- 무엇을 싣고 무엇을 빼는가는 `../figure_plan.md` 가 정한다.

`../figures/` 는 그 전에 만든 `fig1` ~ `fig4b` 가 있는 곳이다. **섞지 않는다** —
matplotlib 으로 옮길 때마다 하나씩 이리로 넘어온다.
