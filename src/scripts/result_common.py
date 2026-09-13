#!/usr/bin/env python3
"""`result/` 를 만드는 스크립트들이 함께 쓰는 것 — 의심 유닛의 **표기**.

**어떤 유닛인가.** 운전자가 2026-09-11 에 두 유닛의 바디에서 **빛이 새는 것을 육안으로
확인**했다(`9DTact_hard_1mm_r2`, `9DTact_medium_1mm_r2`). 데이터도 일치한다: 두 점 자국의
깊이가 중앙 1.7 ~ 1.8 그레이 레벨로 17 유닛 중앙값 3.7 의 절반이라 네 간격 모두 '미분해'
로 기록됐고(`docs/spatial_resolution.md` §4.6), 천장은 자기 피크의 15 % 라는 상대 문턱
때문에 짝보다 +24 %, +25 % 부풀었다(`docs/force_ceiling.md` §6.5c).

**빼지 않고 표기한다(2026-09-13).** 한때 `result/` 에서 통째로 뺐다. 지금은 **자료는
그대로 두고 의심 표시만 단다** — 읽는 사람이 그 유닛이 있었다는 것과 그것이 무엇이었는지
둘 다 볼 수 있어야 하고, 뺀 자료는 보이지 않으므로 검토되지도 않기 때문이다.

- csv: `suspect_hardware` 열이 붙는다
- 유닛별 그림: 제목에 `💡` 와 경고색, 선은 점선
- 3×3 표: 칸에 `!` 가 붙는다 (그 칸의 복제 하나가 의심 유닛이라는 뜻)
- 통계: 포함해서 내되, 뺐을 때의 값을 함께 적는다

**어디가 진실인가.** 등록부의 `suspect_hardware: true` 다. 여기에 이름을 적어 두지 않는
이유는 그것이 두 벌의 진실을 만들기 때문이다.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
_REG = yaml.safe_load((ROOT / "src" / "config" / "sensor_registry.yaml").read_text())

MARK = "!"           # 그림 제목에 붙이는 표시. NanumGothic 에 없는 글리프는 두부로 나온다
LABEL = "빛 누출 의심"


def suspect(pr=None):
    """의심 유닛. `pr` 을 주면 그 원리의 **짧은 이름**(`hard_1mm_r2`)으로 돌려준다."""
    ids = [s["id"] for s in _REG["sensors"] if s.get("suspect_hardware")]
    if pr is None:
        return set(ids)
    return {i[len(pr) + 1:] for i in ids if i.startswith(pr + "_")}


# 옛 이름. 뺄 때 쓰던 것이라 뜻이 달라졌으니 새 코드는 suspect() 를 쓸 것.
excluded = suspect


def is_suspect(pr, unit):
    """짧은 이름과 긴 이름을 모두 받는다."""
    u = str(unit)
    return u in suspect(pr) or u in suspect()


def reason(pr, unit):
    """왜 의심스러운지 — 그림에 적는다. 아니면 None."""
    for s in _REG["sensors"]:
        if s["id"] in (unit, f"{pr}_{unit}") and s.get("suspect_hardware"):
            return s.get("suspect_note", LABEL).split(".")[0]
    return None


def mark(d, pr, col="sensor"):
    """데이터프레임에 `suspect_hardware` 열을 붙인다. 행은 하나도 버리지 않는다."""
    if col not in d:
        return d
    d = d.copy()
    d["suspect_hardware"] = d[col].map(lambda u: is_suspect(pr, u))
    return d


def style(pr, unit, base="-o"):
    """유닛별 그림의 선 모양. 의심 유닛은 점선으로 그린다."""
    return ("--o", 1.1) if is_suspect(pr, unit) else (base, 1.4)


def title(pr, unit):
    """유닛별 그림의 제목과 색."""
    if is_suspect(pr, unit):
        return f"{MARK} {unit}  ({LABEL})", "#c2553a"
    return unit, "black"
