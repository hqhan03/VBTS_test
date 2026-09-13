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
import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
_REG = yaml.safe_load((ROOT / "src" / "config" / "sensor_registry.yaml").read_text())

MARK = "!"           # 그림 제목에 붙이는 표시. NanumGothic 에 없는 글리프는 두부로 나온다
# **표시는 색이 아니라 형태로 한다.** 붉은색을 쓰다가 범주 팔레트의 주황(#D55E00)과
# 헷갈렸다(2026-09-13). 먹색은 어느 범주 색과도 겹치지 않으므로 "또 하나의 군" 으로
# 읽히지 않고 주석으로 읽힌다. 점은 자기 군의 색을 그대로 채우고 테두리만 먹색이다.
INK = "#1a1a1a"
LABEL = "빛 누출 의심"


def suspect(pr=None):
    """의심 유닛. `pr` 을 주면 그 원리의 **짧은 이름**(`hard_1mm_r2`)으로 돌려준다.

    단일 센서 모드에서는 의심 유닛이 이미 빠져 있으므로 **남아 있는 것만** 돌려준다 —
    그러지 않으면 3x3 표에 `!` 가 붙어 "이 칸에 의심 유닛이 있다" 고 거짓말한다.
    """
    out = _suspect_raw(pr)
    if pr is None:
        return out
    return (out & chosen(pr)) if SINGLE else out


def _suspect_raw(pr=None):
    """거르지 않은 원본 집합. `chosen()` 이 이것을 써야 재귀가 생기지 않는다 —
    `suspect()` 는 단일 모드에서 `chosen()` 을 부르기 때문이다."""
    ids = [s["id"] for s in _REG["sensors"] if s.get("suspect_hardware")]
    if pr is None:
        return set(ids)
    return {i[len(pr) + 1:] for i in ids if i.startswith(pr + "_")}


# 옛 이름. 뺄 때 쓰던 것이라 뜻이 달라졌으니 새 코드는 suspect() 를 쓸 것.
excluded = suspect


def is_suspect(pr, unit):
    """짧은 이름과 긴 이름을 모두 받는다. **원본 집합**을 본다 — 단일 모드에서도
    "이 유닛이 빛 누출인가" 의 답은 바뀌지 않는다(표시 여부만 바뀐다)."""
    u = str(unit)
    return u in _suspect_raw(pr) or u in _suspect_raw()


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
    return keep(d, pr, col)


def style(pr, unit, base="-o"):
    """유닛별 그림의 선 모양. 의심 유닛은 점선으로 그린다."""
    return ("--o", 1.1) if is_suspect(pr, unit) else (base, 1.4)


def title(pr, unit):
    """유닛별 그림의 제목과 색."""
    if is_suspect(pr, unit):
        return f"{MARK} {unit}  ({LABEL})", INK
    return unit, "black"


# ------------------------------------------------------- 단일 센서 모드 --
# 환경변수 `VBTS_SINGLE=1` 이면 **셀마다 복제 하나만** 남긴다. 그림·표·csv 가
# `result/single/` 로 나가고 `results_single_sensor.md` 가 그것을 읽는다.
SINGLE = bool(os.environ.get("VBTS_SINGLE"))


def _damaged(pr, unit):
    """자료가 없는 유닛. `9DTact_medium_2mm_r1` 은 2026-09-04 에 파괴돼 수집 자체가
    없다 — 등록부의 `status: damaged` 가 그것이고, 남길 후보가 될 수 없다."""
    for s in _REG["sensors"]:
        if s["id"] == f"{pr}_{unit}":
            return s.get("status") == "damaged"
    return False


def _rank(pr, unit):
    """작을수록 먼저 버린다. `replicate_audit.md` 의 우선순위를 그대로 옮긴 것."""
    if _damaged(pr, unit):
        return -1                     # 0. 자료 없음 — 후보가 아니다
    if is_suspect(pr, unit):
        return 0                      # 1. 확정 불량(빛 누출)
    if unit in _EVIDENCE.get(pr, ()):
        return 1                      # 2. 독립 증거(자료량 부족)가 있는 의심 유닛
    return 2                          # 3. 나머지


# **독립 증거가 있는 의심 유닛** — `twin_audit.py` 의 `suspect_units.csv` 에서
# "서로 다른 종류 두 개 이상" 으로 걸린 것들. 여기 적어 두는 이유는 그 판정이
# 감사 실행마다 조금씩 흔들려도 **단일 센서판의 구성이 흔들리면 안 되기** 때문이다.
# 바뀌면 이 목록과 replicate_audit.md 를 함께 고칠 것.
_EVIDENCE = {
    "DIGIT": {"medium_3mm_r2", "soft_1mm_r1", "medium_2mm_r2"},
    "DIGIT_Marker": {"medium_1mm_r2"},
}


def chosen(pr):
    """그 원리에서 **남길** 유닛의 짧은 이름 집합.

    셀(경도 x 두께)마다 하나다. 규칙은 순서대로:

    1. 한쪽이 **확정 불량**(빛 누출)이면 다른 쪽을 남긴다.
    2. 한쪽에 **독립 증거**(자료량 부족)가 있으면 다른 쪽을 남긴다.
    3. 복제가 하나뿐이면(파괴) 그것을 남긴다.
    4. 그 밖에는 **`r1` 을 남긴다.**

    **4 번이 투표가 아닌 이유.** `replicate_audit.md` §4.1 이 정답 있는 두 셀로
    투표를 시험했더니 하나는 맞고 하나는 **거꾸로** 짚었다 — 가법 기댓값이 틀린
    칸(경도 x 두께 상호작용)에서 "추세에서 먼 쪽" 이 뒤집히기 때문이다. 게다가
    추세에 가까운 쪽을 남기는 선택은 **효과 크기를 부풀린다.** `r1` 은 임의이지만
    **추세에 대해 편향이 없다.** 임의가 편향보다 낫다.
    """
    units = [s["id"][len(pr) + 1:] for s in _REG["sensors"]
             if s.get("principle") == pr]
    out = set()
    for h in ("soft", "medium", "hard"):
        for t in (1, 2, 3):
            cell = sorted(u for u in units if u.startswith(f"{h}_{t}mm_r"))
            if not cell:
                continue
            best = max(cell, key=lambda u: (_rank(pr, u), -int(u[-1])))
            out.add(best)
    return out


def keep(d, pr, col="sensor"):
    """단일 센서 모드일 때만 걸러낸다. 아니면 그대로 돌려준다."""
    if not SINGLE or col not in d:
        return d
    ch = chosen(pr)
    full = {f"{pr}_{u}" for u in ch}
    return d[d[col].isin(ch | full)].copy()
