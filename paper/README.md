# paper/ — ICRA 2027 원고

| 파일 | 무엇 |
|---|---|
| `paper_draft.md` | **정본.** 영문 본문(2026-09-14 재작성). 논문에 실제로 들어가는 것. |
| `paper_draft_kr.md` | 첨삭용 한국어 대역본. 문단 태그로 영문판과 1:1 대응. |
| `paper_draft.txt`, `paper_draft_ko.txt` | 비어 있는 이전 파일. `.md` 두 파일이 대체한다. |
| `template/ieeeconf_letter.doc` | IEEE 학회 Word 템플릿 (원본 파일명 `cssA4.doc`). |

## 규칙

- **영문판이 정본이다.** 영문 문단을 고치면 한국어판의 같은 태그도 함께 고친다.
- 문단은 `[ABS]`, `[I-1]`, `[II-T1]`, `[III-B5]` 처럼 태그로 식별한다. 두 파일의
  같은 태그는 같은 내용을 담는다. 태그를 지우거나 번호를 다시 매기지 않는다 —
  대역이 끊긴다.
- 아직 확인되지 않은 자리는 `[AUTHOR CHECK: ...]` 로 표시하고, 파일 끝
  `OPEN QUESTIONS / TO RESOLVE` (한국어판 `미해결 항목`) 에 왜 열려 있는지 적는다.
  **숫자가 존재하기 전에 방향을 단정하지 않는다.**
- 본문은 2026-09-14 에 업로드된 `paper_outline.txt` 와 `outline.txt`(2 판), `docs/`,
  `result/` 를 읽고 처음부터 다시 썼다. 표의 수치는 `result/single/` 과
  `paper/figures/` 의 CSV 에서 재계산해 넣었고, 구성안과 어긋난 자리는 본문 끝
  `OPEN ITEMS` 에 적었다.
- 본문에 쓰는 모든 수치의 근거는 `docs/` 와 `result/` 에 있다.
  요약은 `docs/RESULTS_SUMMARY.md`, 그림·표는 `result/results.md`.

## 템플릿 주의

파일명은 `cssA4` 지만 내용은 **US-letter 판**(`ieeeconf_letter.dot`)이고, 본문에
"A4 에는 쓰지 말라" 고 적혀 있다. ICRA 2027 CFP 가 요구하는 판형을 확인하고
필요하면 A4 템플릿을 따로 받는다.
