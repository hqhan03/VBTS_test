"""Keep a continuously-acquiring F/T task drained, and remember what it saw.

`FTInterface` opens a hardware-timed continuous task at 2 kHz. The DAQ fills
its buffer whether or not anyone reads, and the driver aborts the task with
-200279 once it overruns. Any loop that holds the task open while doing
something slow between reads -- rendering a camera frame, waiting for a
blocking MoveL -- will hit that.

Reading flat out on a separate thread keeps the buffer empty. Consumers take
the most recent completed read instead of asking the DAQ for one, which is also
what they actually want: the force *now*, not a queued backlog.

The reads are short (20 ms) and every one is kept with its wall-clock time, so
a camera frame taken at time t can be labelled with the force integrated over
the same interval the sensor was integrating light: `window(t - exposure, t)`.
Reading one long average per frame instead would put the force reading AFTER
the frame it labels, by up to the averaging time, which at 15 fps is longer
than the frame itself.
"""

from __future__ import annotations

import threading
import time
from collections import deque

import numpy as np


class ForceReader:
    def __init__(self, ft, tare: np.ndarray | None = None,
                 duration_s: float = 0.1, chunk_s: float = 0.02,
                 history_s: float = 3600.0):
        self.ft = ft
        self.tare = None if tare is None else np.asarray(tare, dtype=float)
        # `duration_s` is what one `read()` averages over: the same 0.1 s the
        # single-shot reads used, so the seek loops see the same 0.02 N scatter
        # they were tuned against.
        self.duration_s = duration_s
        self.chunk_s = chunk_s
        self.chunk_n = max(1, int(round(chunk_s * ft.sample_rate_hz)))
        self.per_read = max(1, int(round(duration_s / chunk_s)))
        self._hist: deque = deque(maxlen=int(history_s / chunk_s))
        self._count = 0
        self._error: str | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> "ForceReader":
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                w, block = self.ft.read_wrench(samples=self.chunk_n, tared=False)
            except Exception as exc:
                with self._lock:
                    self._error = str(exc).splitlines()[0]
                return
            # Hardware-timed: the chunk ENDS at the host time the read returned.
            # Its midpoint is the honest single timestamp for its mean.
            t_end = block.t_wall
            t_mid = t_end - 0.5 * self.chunk_n / self.ft.sample_rate_hz
            m = np.asarray(w, dtype=float).mean(axis=1)
            with self._lock:
                if self.tare is not None:
                    m = m - self.tare
                self._hist.append((t_mid, m))
                self._count += 1

    # -- the API the seek loops use ----------------------------------------

    def _mean_last(self, n: int) -> np.ndarray:
        items = list(self._hist)[-n:]
        if not items:
            return np.zeros(6)
        return np.mean([w for _, w in items], axis=0)

    def read(self) -> tuple[np.ndarray, str | None]:
        """Mean of the last `duration_s` of data, and any acquisition error."""
        with self._lock:
            return self._mean_last(self.per_read), self._error

    def read_fresh(self, timeout_s: float = 5.0) -> tuple[np.ndarray, str | None]:
        """A reading made entirely of data acquired after this call.

        After a move completes, the buffered chunks still describe the robot
        mid-travel. Waiting for `per_read` new chunks guarantees the average
        covers only what happened after the move did.
        """
        with self._lock:
            start = self._count
            err = self._error
        if err:
            return self.read()
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            with self._lock:
                if self._error:
                    return self._mean_last(self.per_read), self._error
                if self._count >= start + self.per_read:
                    return self._mean_last(self.per_read), None
            time.sleep(0.005)
        return self.read()

    # -- the API the frame labeller uses ------------------------------------

    def window(self, t0: float, t1: float) -> tuple[np.ndarray, int]:
        """Mean wrench over chunks whose midpoints fall in [t0, t1].

        Returns (wrench, n_chunks). With no chunk inside the window -- a window
        shorter than a chunk, or one that fell between two -- the nearest chunk
        is used and n is 0, so the caller can see the label was interpolated
        rather than integrated.
        """
        with self._lock:
            items = list(self._hist)
        if not items:
            return np.zeros(6), 0
        inside = [w for t, w in items if t0 <= t <= t1]
        if inside:
            return np.mean(inside, axis=0), len(inside)
        tm = 0.5 * (t0 + t1)
        t, w = min(items, key=lambda tw: abs(tw[0] - tm))
        return w, 0

    def history(self) -> tuple[np.ndarray, np.ndarray]:
        """Every chunk so far: (times, wrenches) with wrenches shaped (n, 6)."""
        with self._lock:
            items = list(self._hist)
        if not items:
            return np.zeros(0), np.zeros((0, 6))
        return (np.array([t for t, _ in items]),
                np.array([w for _, w in items]))

    def set_tare(self, tare: np.ndarray) -> None:
        with self._lock:
            self.tare = np.asarray(tare, dtype=float)

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=2.0)
