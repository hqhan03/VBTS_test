#!/usr/bin/env python3
"""0.4 mm 보다 깊은 단에서도 두 점을 분해할 수 있는가 — 방법과 역치의 민감도.

`spatial_resolution.md` §4.4 의 사실: 279 단 중 분해로 인정된 49 단이 **전부
0.1 · 0.2 · 0.3 mm** 에 있고 0.4 mm 이상은 하나도 없다. 자국은 계속 진해지는데
(2.99 → 26.3 그레이 레벨) 골이 사라진다 — 두 자국이 서로 합쳐지기 때문이다.

운전자의 물음: **분석을 바꾸면 깊은 단에서도 분해가 나오는가.** 그래서 같은
프레임에 네 가지 판정을 나란히 적용한다. 앞의 셋은 역치를 건드리지 않고 **무엇을
재는가**를 바꾸고, 넷째는 역치만 바꾼다.

  raw        지금 쓰는 것. 골 = 1 − 최저 / 약한 봉우리, Rayleigh 0.265
  detrend    합쳐진 덩어리의 완만한 외곽(σ = 간격) 을 빼고 남은 구조에서 같은 골
  curv       골이 아니라 **곡률**. 중앙에서 2 차 도함수가 양(국소 최소)이고 그
             크기가 자기 잡음의 3 배를 넘으면 "갈라지기 시작했다" 로 본다.
             Rayleigh 보다 약한 기준이며, Sparrow 한계에 해당한다
  twofit     한 봉우리 모형과 두 봉우리 모형을 맞춰 BIC 를 비교한다. 눈에 보이는
             골이 없어도 두 성분이 하나보다 자료를 잘 설명하면 분해로 본다

**이 스크립트는 무엇이 참인지 정하지 않는다.** 네 판정이 각각 몇 단을 분해로
바꾸는지 세고, 그 대가로 0.1 ~ 0.3 mm 에서 무엇이 달라지는지 함께 보고한다.
기준을 느슨하게 하면 깊은 단이 분해되는 것은 당연하므로, **얕은 단에서 이미
분해된 것을 유지하면서** 깊은 단을 얻는 방법만 의미가 있다.

    python3 src/scripts/resolution_sensitivity.py
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "scripts"))
import analyse_resolution as A  # noqa: E402

DS = ROOT / "data" / "20260911_VBTSresolution_dataset" / "9DTact" / "20260911_passA_pair010"
SEP_MM = A.ELEMENT_MM + 0.10          # pair010: 기둥 지름 1.0 + 간격 0.10


def profile_of(run, row, ref, J):
    img = cv2.cvtColor(cv2.imread(str(run / "shape_pair010" / row.file)),
                       cv2.COLOR_BGR2GRAY)
    raw = np.clip(ref.astype(np.int32) - img.astype(np.int32), 0, 255).astype(np.uint8)
    c = A.blob_centre(raw)
    if c is None:
        return None
    dw, ppm = A.isotropic(raw.astype(np.float32), J, c)
    got = A.axis_and_profile(dw, ppm)
    if got is None:
        return None
    x, prof, _ = got
    g = np.isfinite(prof)
    return x[g], prof[g]


def smooth(y, n):
    k = np.ones(max(int(n), 1)) / max(int(n), 1)
    return np.convolve(y, k, mode="same")


def judge_raw(x, p):
    f, peak, sd, _, _ = A.dip_fraction(x, p, SEP_MM)
    return dict(dip=f, peak=peak, sd=sd,
                ok=bool(np.isfinite(f) and peak >= A.MIN_PEAK
                        and f >= A.RAYLEIGH and np.isfinite(sd)
                        and f > A.NOISE_K * sd))


def judge_detrend(x, p):
    """합쳐진 외곽을 빼고 남은 구조에서 같은 판정."""
    step = np.median(np.diff(x)) if len(x) > 1 else 1.0
    env = smooth(p, SEP_MM / max(step, 1e-9))
    r = p - env
    r = r - r.min() + 1e-6
    return judge_raw(x, r)


def judge_curv(x, p):
    """중앙의 곡률 — Rayleigh 보다 약한 Sparrow 류 기준."""
    step = float(np.median(np.diff(x))) if len(x) > 1 else 1.0
    y = smooth(p, max(3, int(0.10 / max(step, 1e-9))))
    d2 = np.gradient(np.gradient(y, step), step)
    mid = np.abs(x) <= 0.10
    out = np.abs(x) > SEP_MM
    if not mid.any() or out.sum() < 10:
        return dict(curv=np.nan, ok=False)
    c = float(d2[mid].mean())
    noise = float(np.std(d2[out]))
    pk = A.dip_fraction(x, p, SEP_MM)[1]
    return dict(curv=c, curv_noise=noise,
                ok=bool(c > 0 and noise > 0 and c > A.NOISE_K * noise
                        and pk >= A.MIN_PEAK))


def gauss(x, a, c, s):
    return a * np.exp(-0.5 * ((x - c) / s) ** 2)


def judge_twofit(x, p):
    """한 성분 대 두 성분, BIC 비교. 중심은 알려진 ±sep/2 에 고정."""
    from scipy.optimize import least_squares
    h = SEP_MM / 2.0
    m = np.abs(x) <= 1.8 * SEP_MM
    xx, yy = x[m], p[m]
    if len(xx) < 20 or not np.isfinite(yy).all():
        return dict(dbic=np.nan, ok=False)
    a0 = float(yy.max())

    def r1(q):  return gauss(xx, q[0], 0.0, abs(q[1]) + 1e-6) + q[2] - yy
    def r2(q):  return (gauss(xx, q[0], -h, abs(q[2]) + 1e-6)
                        + gauss(xx, q[1], +h, abs(q[2]) + 1e-6) + q[3] - yy)
    try:
        f1 = least_squares(r1, [a0, SEP_MM, 0.0])
        f2 = least_squares(r2, [a0, a0, SEP_MM / 3, 0.0])
    except Exception:
        return dict(dbic=np.nan, ok=False)
    n = len(xx)
    bic = lambda res, k: n * np.log(max(np.sum(res ** 2) / n, 1e-12)) + k * np.log(n)
    d = bic(f1.fun, 3) - bic(f2.fun, 4)          # 양수면 두 성분이 낫다
    pk = A.dip_fraction(x, p, SEP_MM)[1]
    return dict(dbic=float(d), ok=bool(d > 10 and pk >= A.MIN_PEAK))


def control_rows():
    """대조군: `cyl4` 는 지름 4 mm 원기둥 하나 — 자국도 하나다.

    같은 판정을 그대로 걸어 "간격 1.10 mm 의 두 점" 을 찾으면 나오는 것은 전부
    거짓 양성이다. 이것 없이는 깊은 단을 분해로 바꾸는 방법이 구조를 찾아낸 것인지
    만들어낸 것인지 구별할 수 없다 — `twofit` 은 여기서 75 % 가 나온다.
    """
    base = ROOT / "data" / "20260911_VBTSresolution_dataset" / "9DTact" / "20260905_passA_cyl4"
    rows = []
    for run in sorted(p for p in base.iterdir() if p.is_dir()):
        lad = run / "shape_cyl4" / "ladder.csv"
        if not lad.exists():
            continue
        st = json.loads((run / "state.json").read_text())
        J = A.jacobian(st, run.name)
        if J is None:
            continue
        ref = cv2.cvtColor(cv2.imread(str(run / "reference.png")), cv2.COLOR_BGR2GRAY)
        for _, r in pd.read_csv(lad).iterrows():
            img = cv2.imread(str(run / "shape_cyl4" / r.file))
            if img is None:
                continue
            g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            raw = np.clip(ref.astype(np.int32) - g.astype(np.int32), 0, 255).astype(np.uint8)
            c = A.blob_centre(raw)
            if c is None:
                continue
            dw, ppm = A.isotropic(raw.astype(np.float32), J, c)
            got = A.axis_and_profile(dw, ppm)
            if got is None:
                continue
            x, pr, _ = got
            m = np.isfinite(pr)
            e = dict(unit=run.name, depth=float(r.target_depth_mm))
            for name, fn in (("raw", judge_raw), ("detrend", judge_detrend),
                             ("curv", judge_curv), ("twofit", judge_twofit)):
                e[name] = bool(fn(x[m], pr[m])["ok"])
            rows.append(e)
    return pd.DataFrame(rows)


def main() -> int:
    rows = []
    for run in sorted(p for p in DS.iterdir() if p.is_dir()):
        lad = run / "shape_pair010" / "ladder.csv"
        if not lad.exists():
            continue
        st = json.loads((run / "state.json").read_text())
        J = A.jacobian(st, run.name)
        if J is None:
            print(f"  {run.name}: 축척 없음"); continue
        ref = cv2.cvtColor(cv2.imread(str(run / "reference.png")), cv2.COLOR_BGR2GRAY)
        for _, r in pd.read_csv(lad).iterrows():
            got = profile_of(run, r, ref, J)
            if got is None:
                continue
            x, p = got
            e = dict(unit=run.name.replace("9DTact_", ""),
                     depth=round(float(r.target_depth_mm), 2))
            for name, fn in (("raw", judge_raw), ("detrend", judge_detrend),
                             ("curv", judge_curv), ("twofit", judge_twofit)):
                out = fn(x, p)
                e[name] = bool(out["ok"])
                for k, v in out.items():
                    if k != "ok":
                        e[f"{name}_{k}"] = v
            rows.append(e)
    D = pd.DataFrame(rows)
    out = ROOT / "data" / "analysis" / "resolution_sensitivity.csv"
    D.to_csv(out, index=False)
    deep = D[D.depth >= 0.4]
    shal = D[D.depth < 0.4]
    print(f"  {len(D)} 단 ({len(shal)} 얕음 <0.4 mm, {len(deep)} 깊음 >=0.4 mm)"
          f"  -> {out}\n")
    print(f"  {'판정':10s} {'얕은 단 분해':>12s} {'깊은 단 분해':>12s}")
    C = control_rows()
    cout = ROOT / "data" / "analysis" / "resolution_sensitivity_control.csv"
    C.to_csv(cout, index=False)
    print(f"  {'판정':10s} {'얕은 단':>10s} {'깊은 단':>10s} {'거짓 양성(대조군)':>18s}")
    for name in ("raw", "detrend", "curv", "twofit"):
        fp = f"{int(C[name].sum())} /{len(C)} ({100*C[name].mean():.0f} %)" if len(C) else "—"
        print(f"  {name:10s} {int(shal[name].sum()):6d} /{len(shal):<3d} "
              f"{int(deep[name].sum()):6d} /{len(deep):<3d} {fp:>18s}")
    print(f"\n  대조군 {len(C)} 단 -> {cout}")
    print("  깊은 단을 분해로 바꾸면서 거짓 양성이 낮은 판정만 의미가 있다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
