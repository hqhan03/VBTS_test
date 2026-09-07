"""VBTS internal camera.

Standard UVC, opened through OpenCV. The point of this module is that every
control is set explicitly and verified after the fact: a camera that quietly
re-exposes itself turns gel deformation and camera housekeeping into the same
signal, and nothing downstream can separate them again.
"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

import cv2
import numpy as np
import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent.parent / "config" / "camera_config.yaml"

# OpenCV property ids for the controls this camera actually honours.
_PROPS = {
    "auto_exposure": cv2.CAP_PROP_AUTO_EXPOSURE,
    "exposure": cv2.CAP_PROP_EXPOSURE,
    "auto_wb": cv2.CAP_PROP_AUTO_WB,
    "wb_temperature": cv2.CAP_PROP_WB_TEMPERATURE,
    "brightness": cv2.CAP_PROP_BRIGHTNESS,
    "contrast": cv2.CAP_PROP_CONTRAST,
    "gamma": cv2.CAP_PROP_GAMMA,
}

# UVC exposure_absolute is in units of 100 us. 2047 is therefore 204.7 ms, which
# is why the uncompressed 1080p mode tops out at 4.9 fps: the sensor cannot
# start a new frame before it has finished integrating the last.
EXPOSURE_UNIT_S = 1e-4


class CameraError(RuntimeError):
    pass


class Camera:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self._cap: cv2.VideoCapture | None = None
        self.applied: dict = {}

    @classmethod
    def from_config(cls, path: str | Path | None = None) -> "Camera":
        p = Path(path) if path else DEFAULT_CONFIG
        return cls(yaml.safe_load(open(p)))

    @property
    def opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()

    def open(self, settle_s: float = 1.0, discard: int = 10,
             buffersize: int | None = None) -> None:
        """Open the camera. `buffersize` is the driver queue depth.

        ONE buffer is right for single-shot use and wrong for continuous
        capture, and the difference is a factor of two. Measured 2026-09-07,
        1080p YUYV, 204.7 ms exposure (4.89 fps is the sensor's own limit):

            BUFFERSIZE=1   2.48 fps   58 of 59 gaps exactly 2x the frame period
            BUFFERSIZE=4   4.93 fps   every gap 1x

        With one buffer the driver has nowhere to put the next frame while the
        reader holds the only one, so every second frame is lost. With four,
        nothing is lost -- but a reader that pauses comes back to a BACKLOG:
        after a 1.5 s stall the next four frames arrived 0.8 ms apart, and
        their retrieval times were 1502, 1299, 1092 and 889 ms later than
        their capture times. That is why `grab()` and friends keep one buffer
        (they read only now and then, so a queued frame would be stale) and
        why FrameRecorder, which reads flat out, asks for four AND timestamps
        from the driver rather than from the clock.
        """
        if self.opened:
            raise CameraError("already open")
        f = self.cfg["format"]
        cap = cv2.VideoCapture(self.cfg.get("device", 0), cv2.CAP_V4L2)
        if not cap.isOpened():
            raise CameraError(f"cannot open device {self.cfg.get('device', 0)}")
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*f["fourcc"]))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, f["width"])
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, f["height"])
        # One driver buffer, not the default four. A camera read only now and
        # then hands back the OLDEST queued frame: after a single 0.5 mm press
        # the F/T read 0.38 N while the "current" frame still showed an
        # untouched gel, because it had been captured before the move.
        cap.set(cv2.CAP_PROP_BUFFERSIZE,
                buffersize if buffersize is not None
                else int(f.get("buffersize", 1)))
        # Auto modes off BEFORE the manual values, or the driver overwrites them.
        c = self.cfg["controls"]
        for k in ("auto_exposure", "auto_wb"):
            cap.set(_PROPS[k], c[k])
        for k in ("exposure", "wb_temperature", "brightness", "contrast", "gamma"):
            if k in c:
                cap.set(_PROPS[k], c[k])
        # MJPG frames can be kept as the camera's own JPEG bitstream instead of
        # being decoded and re-encoded. Decoding happens on demand.
        self.raw_jpeg = bool(f.get("fourcc") == "MJPG" and f.get("store_raw_jpeg", True))
        if self.raw_jpeg:
            cap.set(cv2.CAP_PROP_CONVERT_RGB, 0)
        self._cap = cap
        time.sleep(settle_s)
        for _ in range(discard):
            cap.read()
        self.applied = self.read_controls()
        self._verify()

    def read_controls(self) -> dict:
        cap = self._require()
        got = {k: cap.get(p) for k, p in _PROPS.items()}
        fcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        got["fourcc"] = "".join(chr((fcc >> 8 * i) & 0xFF) for i in range(4))
        got["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        got["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        return got

    def _verify(self) -> None:
        """Refuse to hand back a camera that did not take the settings.

        Silently running on auto-exposure is the failure this whole module
        exists to prevent, so it is checked rather than assumed.
        """
        a, f, c = self.applied, self.cfg["format"], self.cfg["controls"]
        bad = []
        if a["fourcc"] != f["fourcc"]:
            bad.append(f"format is {a['fourcc']}, asked for {f['fourcc']}")
        if (a["width"], a["height"]) != (f["width"], f["height"]):
            bad.append(f"size is {a['width']}x{a['height']}, "
                       f"asked for {f['width']}x{f['height']}")
        if a["auto_exposure"] != c["auto_exposure"]:
            bad.append(f"auto_exposure is {a['auto_exposure']}, must be "
                       f"{c['auto_exposure']} (manual)")
        if a["auto_wb"] != c["auto_wb"]:
            bad.append(f"auto_wb is {a['auto_wb']}, must be {c['auto_wb']}")
        if bad:
            self.close()
            raise CameraError("camera did not accept its settings: " + "; ".join(bad))

    @property
    def exposure_s(self) -> float:
        """Integration time of one frame, from the exposure the camera reports."""
        e = self.applied.get("exposure") if self.applied else None
        if e is None:
            e = self.cfg["controls"].get("exposure", 0)
        return float(e) * EXPOSURE_UNIT_S

    @property
    def fourcc(self) -> str:
        return (self.applied or {}).get("fourcc") or self.cfg["format"]["fourcc"]

    @staticmethod
    def decode(frame: np.ndarray) -> np.ndarray:
        """BGR image from whatever `grab` returned -- a raw JPEG buffer in MJPG
        mode, already BGR otherwise."""
        if frame.ndim == 3:
            return frame
        img = cv2.imdecode(frame.reshape(-1), cv2.IMREAD_COLOR)
        if img is None:
            raise CameraError("JPEG decode failed")
        return img

    def _require(self) -> cv2.VideoCapture:
        if not self.opened:
            raise CameraError("camera is not open")
        return self._cap  # type: ignore[return-value]

    def capture_time(self, cap=None) -> float:
        """When the frame just read was captured, on the wall clock.

        uvcvideo stamps every buffer from CLOCK_MONOTONIC as the frame arrives,
        and OpenCV hands that back as CAP_PROP_POS_MSEC. Measured 2026-09-07:
        the retrieval time `time.time()` is a stable 207 ms -- one whole frame
        period -- LATER than this even when the reader is keeping up, and up to
        1502 ms later after a stall, while this stamp stays right. Every force
        label the collect phase writes is aligned to it.

        Falls back to the clock if the driver does not supply a stamp; a camera
        that reports 0 here would otherwise put every frame at the epoch.
        """
        cap = cap if cap is not None else self._require()
        try:
            pos = float(cap.get(cv2.CAP_PROP_POS_MSEC))
        except Exception:  # noqa: BLE001
            return time.time()
        if pos <= 0.0:
            return time.time()
        return pos / 1000.0 + (time.time() - time.monotonic())

    def grab(self) -> tuple[np.ndarray, float]:
        """One frame (BGR), with the time the CAMERA captured it.

        The time used to be `time.time()` at retrieval, which is a stable
        207 ms late (one frame period) and, after any pause, later still: a
        `grab()` 1.5 s after the previous one returns in 1 ms with a frame
        that is 1.5 s old. The stamp now says so instead of hiding it.
        """
        cap = self._require()
        ok, frame = cap.read()
        t = self.capture_time(cap)
        if not ok:
            raise CameraError("frame grab failed")
        return (self.decode(frame) if self.raw_jpeg else frame), t

    def grab_raw(self) -> tuple[np.ndarray, float]:
        """One frame exactly as the camera delivered it: a JPEG buffer in MJPG
        mode, BGR pixels otherwise."""
        cap = self._require()
        ok, frame = cap.read()
        t = self.capture_time(cap)
        if not ok:
            raise CameraError("frame grab failed")
        return frame, t

    def grab_settled(self, discard: int = 2, timeout_s: float = 3.0
                     ) -> tuple[np.ndarray, float]:
        """A frame whose whole exposure happened after this call.

        `discard` used to be the mechanism: throw away a fixed number of frames
        and hope the next one is current. That is both slow and unproven -- it
        cost three reads (1.24 s) and nothing checked the result. The driver
        stamps every frame with when it was captured, so freshness is now
        TESTED, which is quicker in the common case and correct in the case
        the fixed count was guessing at. `discard` is kept as a floor for
        callers that pass it, and as the fallback if no stamp is available.
        """
        cap = self._require()
        t_call = time.time()
        t_end = t_call + timeout_s
        seen = 0
        while True:
            ok, frame = cap.read()
            t = self.capture_time(cap)
            if not ok:
                raise CameraError("frame grab failed")
            seen += 1
            # The whole exposure has to fall after the call, so it is the
            # exposure START that must be past it, not the capture stamp.
            fresh = t - self.exposure_s >= t_call
            # `seen` only bounds the loop; it is not what decides freshness.
            if fresh or seen >= discard + 4 or time.time() >= t_end:
                return (self.decode(frame) if self.raw_jpeg else frame), t

    def grab_after(self, t_after: float, timeout_s: float = 3.0) -> tuple[np.ndarray, float]:
        """A frame whose whole exposure began after `t_after`.

        This used to wait for the RETRIEVAL time to pass `t_after` by two
        exposures plus 50 ms -- a margin sized to cover an unknown lag. The lag
        is no longer unknown: the driver's own stamp says when the frame was
        captured, so the test is now the thing it was approximating.
        """
        cap = self._require()
        t_end = time.time() + timeout_s
        while True:
            ok, frame = cap.read()
            t = self.capture_time(cap)
            if not ok:
                raise CameraError("frame grab failed")
            if t - self.exposure_s >= t_after or time.time() >= t_end:
                return (self.decode(frame) if self.raw_jpeg else frame), t

    def stability(self, seconds: float = 5.0) -> dict:
        """Frame-to-frame brightness scatter — the auto-exposure smoke test."""
        means, t0 = [], time.time()
        while time.time() - t0 < seconds:
            try:
                f, _ = self.grab()
            except CameraError:
                continue
            means.append(float(f.mean()))
        m = np.array(means)
        return {"n_frames": len(m), "fps": len(m) / seconds,
                "mean": float(m.mean()) if len(m) else float("nan"),
                "frame_to_frame_std": float(m.std()) if len(m) else float("nan"),
                "drift": float(m[-5:].mean() - m[:5].mean()) if len(m) >= 10 else 0.0}

    @staticmethod
    def quality(frame: np.ndarray) -> dict:
        """Exposure health, judged on the centre — the edges are vignetted and
        are not where the gel signal lives."""
        g = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = g.shape
        c = g[3 * h // 8:5 * h // 8, 3 * w // 8:5 * w // 8]
        return {"full_mean": float(g.mean()),
                "centre_mean": float(c.mean()),
                "centre_min": int(c.min()), "centre_max": int(c.max()),
                "centre_saturated_pct": float(100 * (c >= 254).mean()),
                "centre_black_pct": float(100 * (c <= 1).mean())}

    def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def __enter__(self) -> "Camera":
        self.open()
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class FrameRecorder:
    """Save every frame the camera produces, with its time, up to a budget.

    A grab thread reads the camera flat out and hands each frame to a small pool
    of writer threads. PNG encoding of a 1080p frame takes about 75 ms, so one
    writer keeps up with 5 fps and three are needed for 15; the JPEG path just
    writes the camera's own bitstream and costs nothing. Frames are only SAVED
    while the recorder is armed and the budget is not spent; the camera keeps
    running regardless, so `snapshot()` always has a current frame.

    The budget is the point. Fifty-four sensors are compared on how well a
    force estimator trains on each, and a comparison between a sensor that gave
    69 frames and one that gave 21 measures dataset size, not the sensor. Every
    run saves exactly `budget` frames and the loading cycles repeat until it is
    spent, so a stiff 3 mm gel and a soft 1 mm one end with the same count.
    """

    def __init__(self, cam: Camera, out_dir: Path, budget: int,
                 png_compression: int = 1, writers: int | None = None,
                 gate=None):
        self.cam = cam
        self.out = Path(out_dir)
        self.out.mkdir(parents=True, exist_ok=True)
        self.budget = int(budget)
        self.png_compression = png_compression
        self.records: list[dict] = []
        self.dropped = 0
        self.grabbed = 0
        self._armed = False
        self._cap = self.budget
        # `gate(tag) -> bool` decides whether THIS frame is worth keeping. Time
        # is the wrong sampling variable: at 5 fps the median neighbouring frame
        # differs by 0.012 N, under the F/T's own 0.02 N noise, so most frames
        # are duplicates in label space and the histogram simply follows how
        # long the probe dwelt at each force.
        self._gate = gate
        self._tag: dict = {}
        self._latest: tuple[np.ndarray, float] | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._q: queue.Queue = queue.Queue(maxsize=90)
        n_writers = writers or (1 if cam.raw_jpeg else 3)
        self._writers = [threading.Thread(target=self._write_loop, daemon=True)
                         for _ in range(n_writers)]
        self._grabber = threading.Thread(target=self._grab_loop, daemon=True)
        self._error: str | None = None

    # -- control ----------------------------------------------------------

    def start(self) -> "FrameRecorder":
        for w in self._writers:
            w.start()
        self._grabber.start()
        return self

    def arm(self, **tag) -> None:
        """Start saving frames, stamping each with `tag` (segment, cycle, ...)."""
        with self._lock:
            self._tag = dict(tag)
            self._armed = True

    def retag(self, **tag) -> None:
        with self._lock:
            self._tag.update(tag)

    def disarm(self) -> None:
        with self._lock:
            self._armed = False

    def set_cap(self, n: int) -> None:
        """Save no more than `n` frames in total until the cap is raised.

        The loading blocks each own a share of the budget. Without a cap the
        normal block finished the cycle it was in and ran 65 frames past its
        share on a 150-frame test, and on a 5 N gel one cycle is over 400
        frames -- the shear block would then have been short by that much on
        stiff sensors and not on soft ones, which is the imbalance the budget
        exists to remove. The motion still completes; it is just not saved.
        """
        with self._lock:
            self._cap = min(int(n), self.budget)

    @property
    def capped(self) -> bool:
        with self._lock:
            return len(self.records) >= self._cap

    @property
    def saved(self) -> int:
        with self._lock:
            return len(self.records)

    @property
    def remaining(self) -> int:
        return max(0, self.budget - self.saved)

    @property
    def done(self) -> bool:
        return self.saved >= self.budget

    @property
    def error(self) -> str | None:
        with self._lock:
            return self._error

    def snapshot(self) -> tuple[np.ndarray, float]:
        """The most recent frame, decoded to BGR, and its time."""
        for _ in range(200):
            with self._lock:
                lt = self._latest
            if lt is not None:
                return self.cam.decode(lt[0]), lt[1]
            time.sleep(0.01)
        raise CameraError("no frame arrived")

    def wait_fresh(self, timeout_s: float = 2.0) -> tuple[np.ndarray, float]:
        """A frame CAPTURED after this call -- the settled-scene equivalent of
        `grab_settled` while the camera is owned by the recorder.

        The times compared here are the driver's capture stamps, so this now
        means what it says. Against retrieval times it did not: a frame handed
        back just after the call had finished exposing 207 ms BEFORE it, and
        after a stall up to 1502 ms before it.
        """
        t_call = time.time()
        t_end = t_call + timeout_s
        while time.time() < t_end:
            with self._lock:
                lt = self._latest
            if lt is not None and lt[1] > t_call + 0.5 * self.cam.exposure_s:
                return self.cam.decode(lt[0]), lt[1]
            time.sleep(0.005)
        return self.snapshot()

    def stop(self) -> None:
        self._stop.set()
        self._grabber.join(timeout=3.0)
        for _ in self._writers:
            self._q.put(None)
        for w in self._writers:
            w.join(timeout=30.0)

    # -- threads ----------------------------------------------------------

    def _grab_loop(self) -> None:
        cap = self.cam._require()
        ext = ".jpg" if self.cam.raw_jpeg else ".png"
        while not self._stop.is_set():
            ok, frame = cap.read()
            t = self.cam.capture_time(cap)
            if not ok:
                with self._lock:
                    self._error = "frame grab failed"
                continue
            self.grabbed += 1
            with self._lock:
                self._latest = (frame, t)
                armed = self._armed and len(self.records) < self._cap
                tag = dict(self._tag)
            # The gate runs outside the lock: it inspects force history and must
            # not block the grab loop's next read.
            save = armed and (self._gate is None or self._gate(tag))
            with self._lock:
                if save and len(self.records) >= self._cap:
                    save = False
                if save:
                    idx = len(self.records) + 1
                    name = f"{idx:06d}{ext}"
                    rec = {"index": idx, "file": name, "t_img": t,
                           "t_exposure_start": t - self.cam.exposure_s, **tag}
                    self.records.append(rec)
            if save:
                try:
                    self._q.put((name, frame), timeout=2.0)
                except queue.Full:
                    # The writers are behind. The record stays -- a labelled
                    # frame that is missing on disk is visible; one silently
                    # renumbered is not.
                    self.dropped += 1
                    rec["missing"] = True

    def _write_loop(self) -> None:
        while True:
            item = self._q.get()
            if item is None:
                return
            name, frame = item
            p = self.out / name
            try:
                if self.cam.raw_jpeg:
                    frame.reshape(-1).tofile(str(p))
                else:
                    cv2.imwrite(str(p), frame,
                                [cv2.IMWRITE_PNG_COMPRESSION, self.png_compression])
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self._error = f"write failed: {exc}"
