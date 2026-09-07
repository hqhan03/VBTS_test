"""Log the robot's TCP pose continuously from the 20004 state stream.

The XML-RPC channel on 20003 is the one the motion commands go down, and a
blocking MoveL holds it for the length of the move. Polling the pose there
would return nothing while the robot is actually moving -- which is exactly
when a frame needs a pose. The binary state stream is independent of that
channel and updates at about 96 Hz here (measured 2026-09-04, 191 distinct
poses in 2 s), and its TCP pose agrees with GetActualTCPPose to 2 um.
"""

from __future__ import annotations

import threading
import time

import numpy as np

from .robot_interface import RobotInterface


def _as_list(p) -> list:
    if hasattr(p, "as_list"):
        return [float(v) for v in p.as_list()]
    try:
        return [float(v) for v in p]
    except TypeError:
        return [float(getattr(p, k)) for k in ("x", "y", "z", "rx", "ry", "rz")]


class PoseLogger:
    def __init__(self, ip: str, rate_hz: float = 50.0):
        self.ip = ip
        self.period = 1.0 / rate_hz
        self._t: list[float] = []
        self._p: list[list] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._error: str | None = None
        self._r: RobotInterface | None = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "PoseLogger":
        self._r = RobotInterface(ip=self.ip, dry_run=False, allow_real_motion=False)
        self._r.connect(read_only=True)
        time.sleep(1.0)
        self._thread.start()
        return self

    def _run(self) -> None:
        last = None
        while not self._stop.is_set():
            try:
                p = _as_list(self._r.get_tcp_pose())
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self._error = str(exc).splitlines()[0]
                time.sleep(self.period)
                continue
            t = time.time()
            # The stream repeats a pose until the next packet; storing only
            # changes keeps the log honest about when the pose was actually known.
            if p != last:
                with self._lock:
                    self._t.append(t)
                    self._p.append(p)
                last = p
            time.sleep(self.period)

    def at(self, t: float) -> tuple[list, float]:
        """Pose at time t, and the gap to the nearest logged pose.

        Position is interpolated linearly between neighbours; orientation is
        taken from the nearer neighbour, which avoids inventing an angle across
        the +-180 wrap. The robot moves under a millimetre per step here, so the
        interpolation error is microns.
        """
        with self._lock:
            T = np.array(self._t)
            P = np.array(self._p)
        if T.size == 0:
            return [float("nan")] * 6, float("inf")
        i = int(np.searchsorted(T, t))
        if i == 0:
            return P[0].tolist(), float(abs(T[0] - t))
        if i >= T.size:
            return P[-1].tolist(), float(abs(t - T[-1]))
        t0, t1 = T[i - 1], T[i]
        w = 0.0 if t1 == t0 else float((t - t0) / (t1 - t0))
        pos = (1 - w) * P[i - 1][:3] + w * P[i][:3]
        rot = P[i][3:] if w >= 0.5 else P[i - 1][3:]
        gap = float(min(abs(t - t0), abs(t1 - t)))
        return [*pos.tolist(), *rot.tolist()], gap

    def history(self) -> tuple[np.ndarray, np.ndarray]:
        with self._lock:
            return np.array(self._t), np.array(self._p)

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
        if self._r is not None:
            try:
                self._r.disconnect()
            except Exception:  # noqa: BLE001
                pass
