#!/usr/bin/env python3
"""What tool orientation is perpendicular to a sensor's gel, and by how much?

The approach direction has always been the NOMINAL sensor normal, column 2 of
sensor_to_base_transform. Measured 2026-09-06 over 17 units and 51 plane fits,
the gel sits +2.19 +- 0.65 deg away from it in sensor y (every unit positive)
and -0.09 +- 0.50 deg in x, i.e. indistinguishable from zero in x. A one-sided
error that survives re-seating every sensor is not seventeen tilted gels; it is
the transform's normal being wrong in y.

This prints the correction. It commands NO motion.
"""
import argparse, json, glob, sys
from pathlib import Path
import numpy as np, yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src")); sys.path.insert(0, str(ROOT / "scripts"))
import run_indentation as R
chk, cal = R.chk, R.cal


def plane_of(sensor):
    """Mean measured slope of that unit's gel, over every pass that fitted one."""
    sx, sy, n = [], [], 0
    for p in glob.glob(str(ROOT / "data" / "**" / "20260905_passA_*" / "*" / "state.json"),
                       recursive=True):
        name = Path(p).parent.name
        for s in ("__2", "__3", "__badzero", "__settle015", "__failed1", "__failed2"):
            name = name.replace(s, "")
        if name != sensor:
            continue
        for v in (json.loads(Path(p).read_text()).get("scale") or {}).values():
            if isinstance(v, dict) and v.get("plane_slope_y") is not None:
                sx.append(v["plane_slope_x"]); sy.append(v["plane_slope_y"]); n += 1
    if not n:
        return None
    return float(np.mean(sx)), float(np.mean(sy)), n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sensor", required=True)
    ap.add_argument("--ip", default="192.168.58.2")
    a = ap.parse_args()

    run = R.active_run() if hasattr(R, "active_run") else None
    meta = None
    for c in sorted(glob.glob(str(ROOT / "data" / "**" / "20260905_passA_*"
                                  / a.sensor / "meta.yaml"), recursive=True)):
        meta = yaml.safe_load(open(c))
    if meta is None:
        raise SystemExit(f"no meta.yaml for {a.sensor}")
    Rsb = np.array(meta["sensor_to_base_transform"]["rotation_sensor_to_base"], float)
    n_nom = Rsb[:, 2]

    got = plane_of(a.sensor)
    if got is None:
        raise SystemExit(f"no measured plane for {a.sensor}")
    sx, sy, npass = got
    # Gel surface height in sensor coordinates is h = h0 + sx*x + sy*y, so the
    # outward normal is proportional to (-sx, -sy, 1).
    n_gel_s = np.array([-sx, -sy, 1.0]); n_gel_s /= np.linalg.norm(n_gel_s)
    n_gel = Rsb @ n_gel_s

    q = chk.ReadOnlyProxy(a.ip)
    pose = q("GetActualTCPPose", 0)[1:]
    rpy = pose[3:6]
    M = cal.rpy_to_matrix(*rpy)
    z_tool = M[:, 2]
    # The tool z may point either way along the axis; take the sense that faces
    # the gel so the correction is the small one, not 180 deg minus it.
    sgn = 1.0 if float(z_tool @ n_nom) >= 0 else -1.0

    def ang(u, v):
        return float(np.degrees(np.arccos(np.clip(abs(u @ v) /
                     (np.linalg.norm(u) * np.linalg.norm(v)), -1, 1))))

    print(f"  sensor {a.sensor}   plane from {npass} fit(s)")
    print(f"    slope x {sx:+.5f} mm/mm = {np.degrees(np.arctan(sx)):+.2f} deg")
    print(f"    slope y {sy:+.5f} mm/mm = {np.degrees(np.arctan(sy)):+.2f} deg")
    print(f"\n  tool axis vs NOMINAL normal : {ang(z_tool, n_nom):.2f} deg")
    print(f"  tool axis vs GEL normal     : {ang(z_tool, n_gel):.2f} deg   <- what we want at 0")

    v = np.cross(sgn * z_tool, n_gel)
    s = np.linalg.norm(v)
    if s < 1e-9:
        print("\n  already aligned; nothing to do.")
        return 0
    axis = v / s
    deg = float(np.degrees(np.arcsin(np.clip(s, -1, 1))))
    M_new = R.rot_about(axis, deg) @ M
    rpy_new = R.matrix_to_rpy(M_new)
    print(f"\n  rotate {deg:.2f} deg about base axis "
          f"[{axis[0]:+.3f} {axis[1]:+.3f} {axis[2]:+.3f}]")
    print(f"    rpy now  [{rpy[0]:9.3f} {rpy[1]:9.3f} {rpy[2]:9.3f}]")
    print(f"    rpy new  [{rpy_new[0]:9.3f} {rpy_new[1]:9.3f} {rpy_new[2]:9.3f}]")
    print(f"    change   [{rpy_new[0]-rpy[0]:+9.3f} {rpy_new[1]-rpy[1]:+9.3f} "
          f"{rpy_new[2]-rpy[2]:+9.3f}]")
    chk_tool = R.rot_about(axis, deg) @ M
    print(f"\n  check: new tool axis vs gel normal "
          f"{ang(chk_tool[:, 2], n_gel):.3f} deg")
    print(f"  check: new tool axis vs nominal normal "
          f"{ang(chk_tool[:, 2], n_nom):.3f} deg  (should be about "
          f"{ang(n_gel, n_nom):.2f})")
    print("\n  NO MOTION COMMANDED.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
