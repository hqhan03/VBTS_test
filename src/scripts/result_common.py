#!/usr/bin/env python3
"""`result/` 를 만드는 스크립트들이 함께 쓰는 것 — 지금은 유닛 제외 하나다.

**왜 제외하나.** 운전자가 2026-09-11 에 두 유닛의 바디에서 **빛이 새는 것을 육안으로
확인**했다. 데이터도 일치한다: 두 점 자국의 깊이가 중앙 1.7 ~ 1.8 그레이 레벨로 17 유닛
중앙값 3.7 의 절반이라 네 간격 모두 '미분해' 로 기록됐고(`docs/spatial_resolution.md`
§4.6), 천장은 자기 피크의 15 % 라는 상대 문턱 때문에 짝보다 +24 %, +25 % 부풀었다
(`docs/force_ceiling.md` §6.5c). 겔이 아니라 **바디**를 재고 있는 유닛이므로 겔의 성질을
논하는 어떤 그림·표에도 들어가면 안 된다.

**어디가 진실인가.** 등록부의 `suspect_hardware: true` 다. 여기에 이름을 적어 두지
않는 이유는 그것이 두 벌의 진실을 만들기 때문이다 — 등록부를 고치면 이 파일도 따라
고쳐야 하는 상태를 만들지 않는다.
"""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
_REG = yaml.safe_load((ROOT / "src" / "config" / "sensor_registry.yaml").read_text())


def excluded(pr=None):
    """제외 유닛. `pr` 을 주면 그 원리의 **짧은 이름**(`hard_1mm_r2`)으로 돌려준다."""
    ids = [s["id"] for s in _REG["sensors"] if s.get("suspect_hardware")]
    if pr is None:
        return set(ids)
    return {i[len(pr) + 1:] for i in ids if i.startswith(pr + "_")}


def reason(pr, unit):
    """그 유닛이 왜 빠졌는지 — 그림의 빈 칸에 적는다."""
    for s in _REG["sensors"]:
        if s["id"] in (unit, f"{pr}_{unit}") and s.get("suspect_hardware"):
            return "빛 누출 — 제외"
    return None


def drop(d, pr, col="sensor"):
    """데이터프레임에서 제외 유닛을 뺀다. 짧은 이름과 긴 이름을 모두 받는다."""
    ex = excluded(pr)
    if not ex or col not in d:
        return d
    full = {f"{pr}_{u}" for u in ex}
    return d[~d[col].isin(ex | full)].copy()
