#!/usr/bin/env python3
"""자국이 무너지면 characterize 를 끊는다 — 한 단 급락만 본다.

`characterize` 의 멈춤 조건에는 자국 붕괴가 없다. 파괴된 9DTact_medium_2mm_r1 은
한 단에서 면적이 484,808 -> 5,118 px 로 떨어졌고 그 단의 힘은 이미 21.2 N 이었다.

**옛 기준("면적이 최대의 30 % 밑")은 허위 경보를 낸다.** hard_3mm_r1 을 60 N 까지
올렸을 때 마지막 열 단의 면적이 283, 336, 270, 314, 445, 0, 263, 0, 832, 292 로
0 과 수백을 오갔다 — 자국이 시야를 채우면서 `contact_region` 문턱이 덩어리를 못 잡는
현상이고, 겔은 무사했다(램프 전후 표면 +0.008 mm). 그 기준은 포화 직전에 램프를
끊었을 것이다.

**이미지로는 가를 수 없다.** 파괴된 겔도 붕괴 단에서 이미지 변화가 계속 증가한다
(54.33 -> 55.90 -> 57.44). 가르는 것은 붕괴의 **모양**이다:

    파괴:  자기 최대에 있던 면적이 **한 단에** 99 % 무너진다
    허위:  면적이 이미 오래전부터 작고, 작은 값들 사이에서 오르내린다

기준: 힘 10 N 을 넘은 뒤, **직전 단이 최대의 50 % 이상**이었는데 이번 단이 그
직전의 **30 % 밑**으로 떨어지면 SIGINT.
"""
import os, signal, sys, time
from pathlib import Path
import pandas as pd

PREV_MIN_FRAC, DROP_FRAC, MIN_FORCE, MIN_PEAK = 0.50, 0.30, 10.0, 50_000


def collapsed(S):
    """(끊을까, 설명). 램프 표를 통째로 받아 마지막 전이만 본다."""
    if "area_px" not in S or len(S) < 2:
        return False, ""
    peak = int(S.area_px.max())
    if peak < MIN_PEAK:
        return False, ""
    hot = S[S.force_N > MIN_FORCE]
    if len(hot) < 2:
        return False, ""
    prev, last = int(hot.area_px.iloc[-2]), int(hot.area_px.iloc[-1])
    if prev >= PREV_MIN_FRAC * peak and last < DROP_FRAC * prev:
        return True, (f"{prev:,} -> {last:,} px 한 단에 "
                      f"{100 * (1 - last / max(prev, 1)):.0f} % 붕괴 "
                      f"(최대 {peak:,})")
    return False, ""


def main():
    steps, pid = Path(sys.argv[1]), int(sys.argv[2])
    while True:
        if not Path(f"/proc/{pid}").exists():
            print("  감시: 램프 종료"); return
        try:
            S = pd.read_csv(steps)
        except Exception:
            time.sleep(1); continue
        hit, why = collapsed(S)
        if hit:
            print(f"  !! 자국 붕괴: {why} — 램프를 끊는다")
            os.kill(pid, signal.SIGINT)
            return
        time.sleep(1)


if __name__ == "__main__":
    main()
