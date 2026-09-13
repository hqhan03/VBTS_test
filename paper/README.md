# paper/ — ICRA 2027 원고

| 파일 | 무엇 |
|---|---|
| `paper_draft.txt` | **정본.** 영문 본문. 논문에 실제로 들어가는 것. |
| `paper_draft_ko.txt` | 작업용 한국어 대역본. 문단 태그로 영문판과 1:1 대응. |
| `template/ieeeconf_letter.doc` | IEEE 학회 Word 템플릿 (원본 파일명 `cssA4.doc`). |

## 규칙

- **영문판이 정본이다.** 영문 문단을 고치면 한국어판의 같은 태그도 함께 고친다.
- 문단은 `[ABS]`, `[I-1]`, `[II-T1]`, `[III-B5]` 처럼 태그로 식별한다. 두 파일의
  같은 태그는 같은 내용을 담는다. 태그를 지우거나 번호를 다시 매기지 않는다 —
  대역이 끊긴다.
- 아직 숫자가 없는 자리는 `[X]`, `[Y]`, `[CONFIRM: ...]` 로 비워 두고, 파일 끝
  `OPEN QUESTIONS / TO RESOLVE` 에 왜 비었는지 적는다. **숫자가 존재하기 전에
  방향을 단정하지 않는다.**
- 본문에 쓰는 모든 수치의 근거는 `docs/` 와 `result/` 에 있다.
  요약은 `docs/RESULTS_SUMMARY.md`, 그림·표는 `result/results.md`.

## 템플릿 주의

파일명은 `cssA4` 지만 내용은 **US-letter 판**(`ieeeconf_letter.dot`)이고, 본문에
"A4 에는 쓰지 말라" 고 적혀 있다. ICRA 2027 CFP 가 요구하는 판형을 확인하고
필요하면 A4 템플릿을 따로 받는다.
