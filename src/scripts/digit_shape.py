#!/usr/bin/env python3
"""DIGIT 계열의 형상 복원 — 색에서 기울기, 기울기에서 높이.

9DTact 는 **밝기 → 깊이** 조회표 하나로 끝난다(`analyse_shape_resolution.py`).
DIGIT 은 LED 세 개가 서로 다른 방향에서 비추므로 한 픽셀의 색이 **그 점의 표면
기울기**를 담는다. GelSight 계열이 쓰는 표준 절차가 그것이고, 이 파일이 그 절차다:

  1. 알려진 반지름의 구를 여러 위치·깊이에 누른다  -> `calibgrid_ball4`
  2. 각 접촉에서 픽셀별 **참 기울기**를 구 기하로 계산한다 (원 검출 불필요 —
     깊이 d 와 반지름 R 을 알면 접촉 반경도 기울기도 해석적으로 나온다)
  3. (dB, dG, dR, 정규화 x, y) -> (gx, gy) 를 회귀로 학습한다. DIGIT 은 곡면에
     불균일 조명이라 반사함수가 해석적으로 안 나오므로 위치를 함께 넣는다.
  4. 시험 영상에서 픽셀별 기울기를 예측하고 **푸아송 방정식**을 이산 코사인
     변환으로 풀어 높이맵을 만든다.

참고: Yuan et al., *GelSight: High-Resolution Robot Tactile Sensors for
Estimating Geometry and Force*, Sensors 17(12):2762, 2017 — 3 절.

    python3 src/scripts/digit_shape.py calib DIGIT          # 유닛별 룩업 학습
    python3 src/scripts/digit_shape.py eval  DIGIT          # cyl4/cube4 평가
"""
import json
import sys
from pathlib import Path

import cv2
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "data" / "20260911_VBTSresolution_dataset"
OUT = ROOT / "data" / "analysis" / "digit_shape"
BALL_R_MM = 2.0                      # calibgrid 는 ball4 로 돈다
MIN_AREA_PX = 5_000                  # 이보다 작으면 접촉이 없었던 칸이다
GRAD_CLIP = 2.0                      # |기울기| 상한. 구 가장자리에서 발산한다


# ------------------------------------------------------------------ 기하 --
def sphere_gradients(shape, cx, cy, depth_mm, px_per_mm, R=BALL_R_MM):
    """접촉 안 픽셀의 참 (gx, gy) 와 그 마스크.

    깊이 d 로 눌린 반지름 R 의 구에서, 축으로부터 거리 r 인 점의 겔 표면은
    h(r) = d - (R - sqrt(R^2 - r^2)) 만큼 내려가 있고 (r <= a),
    접촉 반경은 a = sqrt(2Rd - d^2), 기울기는 dh/dr = -r / sqrt(R^2 - r^2) 다.
    구의 적도에 가까워지면 기울기가 발산하므로 GRAD_CLIP 으로 자른다 —
    그 띠는 어차피 조명이 스치듯 들어와 색이 포화한다.
    """
    H, W = shape
    d = float(depth_mm)
    if d <= 0 or d >= R:
        return None
    a_mm = float(np.sqrt(max(2 * R * d - d * d, 0.0)))
    a_px = a_mm * px_per_mm
    if a_px < 8:
        return None
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    dx_px, dy_px = x - cx, y - cy
    r_px = np.hypot(dx_px, dy_px)
    m = r_px <= a_px
    if m.sum() < 200:
        return None
    r_mm = r_px / px_per_mm
    denom = np.sqrt(np.maximum(R * R - r_mm * r_mm, 1e-6))
    # dh/dx = (dh/dr)(x/r); r -> 0 에서 0/0 이므로 중심은 0 으로 둔다
    # **높이** z 의 기울기를 낸다 (겔 안쪽이 음수). h(r) 은 아래로 양수인 침하량이라
    # 부호를 한 번 뒤집어야 한다 — 안 뒤집으면 복원 결과가 봉우리로 나온다.
    with np.errstate(invalid="ignore", divide="ignore"):
        gx = np.where(r_px > 1e-6, +(dx_px / px_per_mm) / denom, 0.0)
        gy = np.where(r_px > 1e-6, +(dy_px / px_per_mm) / denom, 0.0)
    ok = m & (np.abs(gx) < GRAD_CLIP) & (np.abs(gy) < GRAD_CLIP)
    # 접촉 밖에서는 구 공식이 무의미하다 (r > R 이면 sqrt 가 클램프돼 폭발한다).
    # 0 으로 눌러 두지 않으면 참 기울기를 적분해도 1937 mm 가 나온다(2026-09-12).
    gx = np.where(ok, gx, 0.0)
    gy = np.where(ok, gy, 0.0)
    return gx.astype(np.float32), gy.astype(np.float32), ok


def a_of(depth_mm, px_per_mm, R=BALL_R_MM):
    """접촉 반경(px)."""
    d = float(depth_mm)
    return float(np.sqrt(max(2 * R * d - d * d, 0.0))) * px_per_mm


def r_of(shape, cx, cy):
    """중심에서의 픽셀 거리."""
    y, x = np.mgrid[0:shape[0], 0:shape[1]].astype(np.float32)
    return np.hypot(x - cx, y - cy)


# ------------------------------------------------------------ 푸아송 적분 --
def integrate(gx, gy):
    """기울기장에서 높이맵. 노이만 경계의 푸아송 방정식을 DCT 로 푼다.

    div(g) = laplacian(z) 를 주파수 영역에서 나눈다. 경계에서 법선 미분이 0 인
    해이므로 상수만큼의 자유도가 남고, 아래에서 가장자리 중앙값을 빼서 고정한다.
    """
    from scipy.fft import dctn, idctn
    H, W = gx.shape
    # div(g) 를 후방차분으로. 부호를 뒤집으면 복원된 높이맵이 통째로 뒤집힌다
    # (2026-09-12: 합성 그릇 -1.0 이 +1.0 으로 나와 잡았다).
    fx = np.zeros_like(gx); fy = np.zeros_like(gy)
    fx[:, 1:] = gx[:, 1:] - gx[:, :-1]
    fy[1:, :] = gy[1:, :] - gy[:-1, :]
    f = fx + fy
    dct = dctn(f, norm="ortho")
    xx, yy = np.meshgrid(np.arange(W), np.arange(H))
    denom = (2 * np.cos(np.pi * xx / W) - 2) + (2 * np.cos(np.pi * yy / H) - 2)
    denom[0, 0] = 1.0
    z = idctn(dct / denom, norm="ortho")
    z[0, 0] = 0.0
    return deplane(z)


def deplane(z, frac=0.12):
    """바깥 테두리를 0 평면으로 잡아 기울어짐과 오프셋을 뺀다.

    배경 기울기가 완벽히 0 이 아니면 적분이 넓은 면적에 걸쳐 완만한 기울어짐을
    만들고, 그것이 최솟값을 밀어내 얕은 자국의 깊이를 배로 부풀린다
    (2026-09-12 실측: 참 0.324 mm 가 0.643 mm 로 나왔다). 테두리는 자국이 닿지
    않는 곳이므로 거기서 평면을 적합해 뺀다.
    """
    H, W = z.shape
    by, bx = max(int(H * frac), 1), max(int(W * frac), 1)
    m = np.zeros((H, W), bool)
    m[:by], m[-by:], m[:, :bx], m[:, -bx:] = True, True, True, True
    y, x = np.mgrid[0:H, 0:W].astype(np.float64)
    A = np.column_stack([x[m], y[m], np.ones(m.sum())])
    c, *_ = np.linalg.lstsq(A, z[m].astype(np.float64), rcond=None)
    return (z - (c[0] * x + c[1] * y + c[2])).astype(np.float32)


def depth_of(z, q=0.1):
    """자국 깊이(mm). 최솟값 대신 하위 q 백분위수 — 픽셀 하나에 흔들리지 않는다."""
    return float(-np.percentile(z, q))


# ------------------------------------------------------------------ 보정 --
def unit_scale(unit_short):
    """px/mm. scale_axes.csv 의 ball4 행. (값, 신뢰 여부)"""
    s = pd.read_csv(ROOT / "data" / "analysis" / "scale_axes.csv")
    s = s[(s.unit == unit_short) & (s.probe == "ball4")]
    if not len(s):
        return None, False
    tr = s[s.trusted.astype(str).str.lower().isin(["true", "1"])]
    r = (tr if len(tr) else s).iloc[-1]
    return float((r.px_x + r.px_y) / 2), bool(len(tr))


def _centroid(v):
    return json.loads(v) if isinstance(v, str) else v


def load_ref(run: Path, calib=False):
    """기준영상. calibgrid 전용 기준영상이 없는 유닛이 있어 fallback 을 둔다."""
    for n in (["reference_calibgrid.png", "reference.png"] if calib
              else ["reference.png", "reference_calibgrid.png"]):
        im = cv2.imread(str(run / n))
        if im is not None:
            return im
    return None


def calib_samples(run: Path, px_per_mm: float, per_frame=8000, bg_mult=4, seed=0):
    """(특징, 목표) — 특징은 [dB, dG, dR, nx, ny], 목표는 [gx, gy]."""
    g = run / "calibgrid_ball4"
    grid = pd.read_csv(g / "grid.csv")
    ref = load_ref(run, calib=True)
    if ref is None:
        return None, None, "기준영상 없음"
    reff = ref.astype(np.float32)
    H, W = ref.shape[:2]
    rng = np.random.default_rng(seed)
    X, Y, used = [], [], 0
    for _, r in grid.iterrows():
        if float(r.area_px) < MIN_AREA_PX:
            continue
        img = cv2.imread(str(g / r.file))
        if img is None or img.shape[:2] != (H, W):
            continue
        cx, cy = _centroid(r.centroid_px)
        out = sphere_gradients((H, W), cx, cy, r.depth_mm, px_per_mm)
        if out is None:
            continue
        gx, gy, ok = out
        idx = np.flatnonzero(ok.ravel())
        if len(idx) > per_frame:
            idx = rng.choice(idx, per_frame, replace=False)
        # 접촉 **밖** 픽셀도 같은 수만큼 넣고 기울기 0 을 준다. 이것이 없으면
        # 배경(색차 ~0)에서 모델이 0 이 아닌 기울기를 내고, 1920x1080 을 적분하는
        # 동안 그 오차가 쌓여 깊이가 7 배로 부푼다(2026-09-12 실측: 0.32 -> 2.34 mm).
        far = np.flatnonzero((r_of(gx.shape, cx, cy) > 1.6 * a_of(r.depth_mm, px_per_mm)).ravel())
        # 실제 프레임은 접촉:배경이 1:37 이다. 1:1 로 학습하면 배경에서 평균 0.034 의
        # 기울기가 남고, 202 만 배경 픽셀에 깔려 적분을 +0.31 mm 부풀린다(2026-09-12).
        if len(far) > per_frame * bg_mult:
            far = rng.choice(far, per_frame * bg_mult, replace=False)
        sel = np.concatenate([idx, far])
        tgt = np.concatenate([
            np.column_stack([gx.ravel()[idx], gy.ravel()[idx]]),
            np.zeros((len(far), 2), np.float32)])
        d = (img.astype(np.float32) - reff).reshape(-1, 3)[sel]
        yy, xx = np.divmod(sel, W)
        X.append(np.column_stack([d, xx / W - 0.5, yy / H - 0.5]).astype(np.float32))
        Y.append(tgt.astype(np.float32))
        used += 1
    if used < 5:
        return None, None, f"쓸 수 있는 보정점 {used} 개"
    return np.concatenate(X), np.concatenate(Y), f"{used} 프레임"


def fit_lut(X, Y, seed=0):
    """색+위치 -> 기울기. 작은 MLP 하나. 조회표보다 위치 의존을 잘 담는다."""
    from sklearn.neural_network import MLPRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import make_pipeline
    m = make_pipeline(StandardScaler(),
                      MLPRegressor(hidden_layer_sizes=(64, 64), max_iter=60, random_state=seed,
                                   early_stopping=True, n_iter_no_change=5))
    m.fit(X, Y)
    return m


# ------------------------------------------------- 유닛별 축척 자기보정 --
FIT_SIZE = (426, 240)          # 축척 적합은 이 해상도에서. 답은 해상도에 무관하다


def fit_scale(run: Path, s0: float, mults=(0.8, 1.0, 1.25, 1.5, 1.75, 2.0), n=5):
    """보정 격자에서 px/mm 를 직접 맞춘다. (최적 px/mm, 배율, MAE, 표)

    `scale_axes.csv` 의 값이 유닛마다 최대 1.5 배 틀린다 — 그리고 그것이
    `trusted` 표시로 설명되지 않는다(2026-09-12: 신뢰 표시된 soft_2mm_r2 가
    1.5 배를 필요로 하고 hard_1mm_r1 은 1.0 이 맞다). 보정 격자는 참 깊이를
    알고 있으므로 거기서 맞추는 편이 근거가 분명하다. 평가는 held-out 형상
    (cyl4 / cube4)으로 하므로 순환이 아니다.
    """
    g = run / "calibgrid_ball4"
    grid = pd.read_csv(g / "grid.csv")
    grid = grid[grid.area_px > MIN_AREA_PX]
    if len(grid) < 5:
        return None, None, None, []
    ref = load_ref(run, calib=True)
    idx = np.linspace(0, len(grid) - 1, min(n, len(grid))).astype(int)
    best, table = None, []
    for mult in mults:
        s = s0 * mult
        X, Y, _ = calib_samples(run, s, per_frame=3000)
        if X is None:
            continue
        m = fit_lut(X, Y)
        err = []
        for i in idx:
            r = grid.iloc[i]
            img = cv2.imread(str(g / r.file))
            if img is None:
                continue
            z, _ = predict_depth(m, img, ref, s, size=FIT_SIZE)
            err.append(depth_of(z) - float(r.depth_mm))
        if not err:
            continue
        mae = float(np.abs(err).mean())
        table.append(dict(mult=mult, px_per_mm=s, mae_mm=mae, bias_mm=float(np.mean(err))))
        if best is None or mae < best[2]:
            best = (s, mult, mae, m)
    if best is None:
        return None, None, None, table
    return best[0], best[1], best[2], table


# ------------------------------------------------------------------ 평가 --
SIZES = [(1920, 1080), (1280, 720), (854, 480), (640, 360), (426, 240),
         (320, 180), (160, 90), (80, 45), (48, 27), (32, 18), (16, 9), (8, 5)]


def predict_depth(model, img, ref, px_per_mm, size=None, contact_mask=True):
    """한 프레임 -> 높이맵(mm). size 가 주어지면 그 해상도로 줄여서 푼다."""
    if size is not None:
        img = cv2.resize(img, size, interpolation=cv2.INTER_AREA)
        ref = cv2.resize(ref, size, interpolation=cv2.INTER_AREA)
        px_per_mm = px_per_mm * size[0] / 1920.0
    H, W = img.shape[:2]
    d = (img.astype(np.float32) - ref.astype(np.float32)).reshape(-1, 3)
    yy, xx = np.divmod(np.arange(H * W), W)
    F = np.column_stack([d, xx / W - 0.5, yy / H - 0.5]).astype(np.float32)
    g = model.predict(F)
    gx = np.clip(g[:, 0], -GRAD_CLIP, GRAD_CLIP).reshape(H, W)
    gy = np.clip(g[:, 1], -GRAD_CLIP, GRAD_CLIP).reshape(H, W)
    # 접촉 마스크. 색차가 작은 곳은 자국이 아니므로 기울기를 0 으로 강제한다.
    # GelSight 구현들이 실제로 하는 것이고, 이것이 없으면 배경의 잔여 기울기가
    # 압도적 면적에 깔려 깊이를 부풀린다.
    if contact_mask:
        mag = np.abs(img.astype(np.float32) - ref.astype(np.float32)).sum(2)
        thr = max(float(np.percentile(mag, 99.0)) * 0.25, 6.0)
        m = (mag > thr).astype(np.uint8)
        k = np.ones((3, 3), np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, k)
        m = cv2.dilate(m, k, iterations=2).astype(bool)
        gx = np.where(m, gx, 0.0)
        gy = np.where(m, gy, 0.0)
    # 기울기는 mm/mm 이고 적분은 픽셀 격자 위에서 하므로 픽셀당 mm 를 곱한다
    z = integrate(gx / px_per_mm, gy / px_per_mm)
    return z, px_per_mm


def eval_unit(run: Path, model, px_per_mm, shape="cyl4", sizes=SIZES):
    """자국 깊이를 참값과 비교. 참값은 사다리가 기록한 `depth_mm` 다."""
    lad = run / f"shape_{shape}" / "ladder.csv"
    if not lad.exists():
        return []
    L = pd.read_csv(lad)
    ref = cv2.imread(str(run / "reference.png"))
    if ref is None:
        return []
    rows = []
    for _, r in L.iterrows():
        f = run / f"shape_{shape}" / r.file if not str(r.file).startswith("/") else Path(r.file)
        if not f.exists():
            f = run / f"shape_{shape}" / Path(str(r.file)).name
        img = cv2.imread(str(f))
        if img is None:
            continue
        for size in sizes:
            z, _ = predict_depth(model, img, ref, px_per_mm, size)
            rows.append(dict(shape=shape, width_px=size[0], depth_true_mm=float(r.depth_mm),
                             force_N=float(r.force_N),
                             depth_pred_mm=depth_of(z),
                             depth_pred_min_mm=float(-z.min()),
                             rms_mm=float(np.sqrt((z ** 2).mean()))))
    return rows


def main():
    print(__doc__.split("\n\n")[0])


if __name__ == "__main__":
    main()
