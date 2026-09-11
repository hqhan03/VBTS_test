#!/usr/bin/env python3
"""
FTInterface — ATI Mini45 force/torque acquisition over NI-DAQmx.

THIS IS THE EXPERIMENT'S EXTERNAL F/T SENSOR, and the only class experiment
protocols should use to reach it. It is a different device from the
robot-integrated F/T fields in the FAIRINO real-time stream; nothing here reads
the robot and nothing in `fr5_io` may be used as an experiment measurement.

SIGNAL CHAIN
------------
    ATI Mini45 transducer  (s/n FT29831, cal SI-145-5)
      -> ATI 9105-IFPS-1 (FTIFPS1) power supply / interface
      -> 6 strain-gauge voltages SG0..SG5, ground-referenced differential
      -> NI SCB-68A terminal block
      -> NI PCIe-6343 "Dev1", differential AI
      -> this module

TWO LEVELS, KEPT SEPARATE
-------------------------
    read_raw()     Level A: v = [v0..v5] volts, straight off the DAQ.
    read_wrench()  Level B: W = [Fx, Fy, Fz, Tx, Ty, Tz] in N and N*m,
                   via FT29831.cal, in the ATI sensor frame.

Raw is always available. A wrench additionally depends on the SG->ai mapping
being right, which is a property of the wiring, so `channels` is config-driven
and never inferred from device enumeration order.

INPUT ONLY
----------
This module creates analog-INPUT tasks and nothing else. No analog output, no
digital output, no device reset, no NI MAX write.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from .ati_calibration import (
    GAUGE_NAMES,
    NUM_GAUGES,
    SENSOR_FRAME,
    WRENCH_AXES,
    ATICalibration,
    CalibrationError,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "src" / "config" / "ft_config.yaml"


class FTError(RuntimeError):
    """Base error for acquisition."""


class ChannelMappingError(FTError):
    """The gauge-to-channel mapping is unusable."""


class NotConnectedError(FTError):
    """Operation needs a live DAQ task."""


@dataclass
class FTBlock:
    """One hardware-timed block of samples.

    `volts` is (n_channels, n_samples). Timestamps are taken once per block on
    the host; per-sample times are RECONSTRUCTED from the hardware sample clock,
    never from host polling time — the DAQ clock is what actually spaced the
    samples, so per-sample host stamps would invent jitter that is not there.
    """

    volts: np.ndarray
    t_monotonic: float
    t_wall: float
    sample_rate_hz: float
    block_index: int
    first_sample_index: int

    @property
    def n_samples(self) -> int:
        return self.volts.shape[1]

    def sample_times_monotonic(self) -> np.ndarray:
        t0 = self.t_monotonic - self.n_samples / self.sample_rate_hz
        return t0 + np.arange(self.n_samples) / self.sample_rate_hz

    def sample_times_relative(self) -> np.ndarray:
        return np.arange(self.n_samples) / self.sample_rate_hz


@dataclass
class ChannelHealth:
    """Verdict on one AI channel from a short passive observation."""

    channel: str
    gauge: str
    mean_v: float
    std_v: float
    min_v: float
    max_v: float
    verdict: str          # "ok" | "railed" | "noisy" | "at_ground"

    @property
    def ok(self) -> bool:
        return self.verdict == "ok"


class FTInterface:
    """Hardware-timed, buffered analog input from the Mini45.

    Args:
        calibration: parsed FT29831.cal.
        device: NI device name, e.g. "Dev1".
        channels: the six AI channels carrying SG0..SG5, IN THAT ORDER. Order is
            significant and comes from config, never from enumeration.
        terminal_config / voltage_range / sample_rate_hz / samples_per_read /
        buffer_size: DAQ settings, all supplied rather than defaulted into the
            hardware.
        channel_mapping_confirmed: whether the wiring has actually been verified
            (e.g. by the 1 kg test). Recorded in metadata so a data file always
            says whether its forces rest on a confirmed mapping.
    """

    def __init__(
        self,
        calibration: ATICalibration,
        device: str,
        channels: Sequence[str],
        *,
        terminal_config: str = "differential",
        voltage_range: float = 10.0,
        sample_rate_hz: float = 2000.0,
        samples_per_read: int = 200,
        buffer_size: int | None = None,
        channel_mapping_confirmed: bool = False,
        settle_samples: int = 200,
    ) -> None:
        self.calibration = calibration
        self.device = device
        self.channels = list(channels)
        self.terminal_config = terminal_config
        self.voltage_range = float(voltage_range)
        self.sample_rate_hz = float(sample_rate_hz)
        self.samples_per_read = int(samples_per_read)
        self.buffer_size = int(buffer_size) if buffer_size else self.samples_per_read * 10
        self.channel_mapping_confirmed = bool(channel_mapping_confirmed)
        # Samples read and thrown away right after the task starts. The first
        # samples are an input-settling transient, not signal: measured on this
        # rig, ai1 starts near -8.4 V and RC-decays to its steady 1.16 V over
        # ~34 samples. Left in, that transient poisons the tare average, the
        # baseline statistics and the channel-health verdict.
        self.settle_samples = int(settle_samples)

        if len(self.channels) != NUM_GAUGES:
            raise ChannelMappingError(
                f"expected {NUM_GAUGES} channels for {GAUGE_NAMES}, got {len(self.channels)}: "
                f"{self.channels}"
            )
        if len(set(self.channels)) != NUM_GAUGES:
            raise ChannelMappingError(f"duplicate channels in {self.channels}")
        if self.sample_rate_hz <= 0:
            raise FTError(f"sample_rate_hz must be positive, got {self.sample_rate_hz}")
        if self.samples_per_read <= 0:
            raise FTError(f"samples_per_read must be positive, got {self.samples_per_read}")

        self._task = None
        self._connected = False
        self._block_index = 0
        self._sample_cursor = 0
        self._tare_volts: np.ndarray | None = None
        self._tare_wrench: np.ndarray | None = None
        self._baseline: dict | None = None

    # -- state -------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def gauge_map(self) -> dict[str, str]:
        """SG0..SG5 -> AI channel, in calibration-column order."""
        return dict(zip(GAUGE_NAMES, self.channels))

    @property
    def is_tared(self) -> bool:
        return self._tare_wrench is not None

    def _require_connected(self, what: str) -> None:
        if not self._connected:
            raise NotConnectedError(f"{what} requires connect() first")

    # -- lifecycle ---------------------------------------------------------

    def connect(self) -> None:
        """Start a hardware-timed continuous analog-INPUT task."""
        if self._connected:
            raise FTError("already connected; call disconnect() first")

        import nidaqmx
        from nidaqmx.constants import AcquisitionType, TerminalConfiguration

        term_map = {
            "DIFFERENTIAL": TerminalConfiguration.DIFF,
            "DIFF": TerminalConfiguration.DIFF,
            "RSE": TerminalConfiguration.RSE,
            "NRSE": TerminalConfiguration.NRSE,
            "PSEUDO_DIFF": TerminalConfiguration.PSEUDO_DIFF,
        }
        key = str(self.terminal_config).upper()
        if key not in term_map:
            raise FTError(
                f"unknown terminal_configuration {self.terminal_config!r}; "
                f"expected one of {sorted(term_map)}"
            )

        task = nidaqmx.Task()
        try:
            # One channel at a time, in configured order, so the task's channel
            # order is exactly SG0..SG5 and never depends on enumeration.
            for chan in self.channels:
                task.ai_channels.add_ai_voltage_chan(
                    chan,
                    terminal_config=term_map[key],
                    min_val=-self.voltage_range,
                    max_val=+self.voltage_range,
                )
            task.timing.cfg_samp_clk_timing(
                rate=self.sample_rate_hz,
                sample_mode=AcquisitionType.CONTINUOUS,
                samps_per_chan=self.buffer_size,
            )
            task.start()
        except Exception:
            task.close()
            raise

        self._task = task
        self._connected = True
        self._block_index = 0
        self._sample_cursor = 0

        # Discard the start-up settling transient before anything measures.
        if self.settle_samples > 0:
            try:
                task.read(number_of_samples_per_channel=self.settle_samples,
                          timeout=max(10.0, 5.0 * self.settle_samples / self.sample_rate_hz))
            except Exception:
                self.disconnect()
                raise
            self._block_index = 0
            self._sample_cursor = 0

    def disconnect(self) -> None:
        if self._task is not None:
            try:
                self._task.stop()
            finally:
                self._task.close()
            self._task = None
        self._connected = False

    def __enter__(self) -> "FTInterface":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.disconnect()

    # -- Level A: raw ------------------------------------------------------

    def read_raw(self, samples: int | None = None, timeout: float | None = None) -> FTBlock:
        """Read one block of raw gauge voltages."""
        self._require_connected("read_raw()")
        n = int(samples or self.samples_per_read)
        if timeout is None:
            timeout = max(10.0, 5.0 * n / self.sample_rate_hz)

        data = self._task.read(number_of_samples_per_channel=n, timeout=timeout)
        volts = np.atleast_2d(np.asarray(data, dtype=float))
        block = FTBlock(
            volts=volts,
            t_monotonic=time.monotonic(),
            t_wall=time.time(),
            sample_rate_hz=self.sample_rate_hz,
            block_index=self._block_index,
            first_sample_index=self._sample_cursor,
        )
        self._block_index += 1
        self._sample_cursor += volts.shape[1]
        return block

    # -- Level B: wrench ---------------------------------------------------

    def read_wrench(self, samples: int | None = None, tared: bool = True
                    ) -> tuple[np.ndarray, FTBlock]:
        """Read a block and convert to (Fx, Fy, Fz, Tx, Ty, Tz) in N and N*m.

        Returns (wrench, block), wrench shaped (6, n_samples) in the ATI sensor
        frame. The block is returned alongside so the caller always retains the
        raw voltages and timing behind any force number.

        `tared=False` gives the untared (absolute) wrench.
        """
        self._require_connected("read_wrench()")
        block = self.read_raw(samples=samples)
        bias = self._tare_volts if (tared and self._tare_volts is not None) else None
        wrench = self.calibration.to_wrench(block.volts, bias=bias)
        return wrench, block

    def read_wrench_untared(self, samples: int | None = None
                            ) -> tuple[np.ndarray, FTBlock]:
        return self.read_wrench(samples=samples, tared=False)

    def read_wrench_mean(self, duration_s: float = 1.0, tared: bool = True) -> np.ndarray:
        """Time-averaged wrench over `duration_s`. Averaging in the voltage
        domain first is equivalent because the conversion is linear, and it
        keeps the noise reduction explicit."""
        self._require_connected("read_wrench_mean()")
        volts = self._collect_volts(duration_s)
        bias = self._tare_volts if (tared and self._tare_volts is not None) else None
        return self.calibration.to_wrench(volts.mean(axis=1), bias=bias)

    # -- tare --------------------------------------------------------------

    def tare(self, duration_s: float = 2.0) -> np.ndarray:
        """Measure and store the software zero W0, averaged over `duration_s`.

        SOFTWARE SUBTRACTION ONLY. Nothing is written to the ATI calibration and
        nothing to the NI device: no DAQmx offset, no device coefficient, no NI
        MAX change. Afterwards, tared reads return dW(t) = W(t) - W0.

        The bias is stored in the VOLTAGE domain and subtracted before the
        matrix multiply. Since the conversion is linear the two are equivalent,
        but keeping it in volts means `tare_volts` stays directly comparable to
        `read_raw()` output.

        Call with the sensor installed and untouched: the static weight and
        gravitational moment of the holder and VBTS then land in W0 and drop
        out. W0 is only valid for the pose it was captured in, so re-tare after
        any change of payload or orientation.
        """
        self._require_connected("tare()")
        volts = self._collect_volts(duration_s)
        self._tare_volts = volts.mean(axis=1)
        self._tare_wrench = self.calibration.to_wrench(self._tare_volts)
        return self._tare_wrench.copy()

    def clear_tare(self) -> None:
        self._tare_volts = None
        self._tare_wrench = None

    @property
    def tare_wrench(self) -> np.ndarray | None:
        return None if self._tare_wrench is None else self._tare_wrench.copy()

    @property
    def tare_volts(self) -> np.ndarray | None:
        return None if self._tare_volts is None else self._tare_volts.copy()

    def set_tare_from_volts(self, volts: Sequence[float]) -> None:
        """Set W0 directly from gauge voltages, e.g. restoring a stored zero."""
        v = np.asarray(volts, dtype=float)
        if v.shape != (NUM_GAUGES,):
            raise ValueError(f"tare volts must have {NUM_GAUGES} elements, got {v.shape}")
        if not np.all(np.isfinite(v)):
            raise ValueError("tare volts contain NaN or infinity")
        self._tare_volts = v
        self._tare_wrench = self.calibration.to_wrench(v)

    # -- health ------------------------------------------------------------

    def check_channel_health(self, duration_s: float = 0.5) -> list[ChannelHealth]:
        """Classify each configured channel from a short passive observation.

        A floating AI pin on a multiplexed DAQ does not read zero — it drifts,
        picks up mains, and ghosts the previously sampled channel, often
        railing to the range limit. That produces large, entirely plausible
        force numbers, so it has to be caught before any wrench is trusted
        rather than after.
        """
        self._require_connected("check_channel_health()")
        volts = self._collect_volts(duration_s)
        rail = 0.95 * self.voltage_range
        out = []
        for gauge, chan, row in zip(GAUGE_NAMES, self.channels, volts):
            mean, std = float(row.mean()), float(row.std(ddof=1))
            lo, hi = float(row.min()), float(row.max())
            if max(abs(lo), abs(hi)) >= rail:
                verdict = "railed"
            elif std > 0.050:
                verdict = "noisy"
            elif abs(mean) < 0.02 and std < 5e-4:
                verdict = "at_ground"
            else:
                verdict = "ok"
            out.append(ChannelHealth(chan, gauge, mean, std, lo, hi, verdict))
        return out

    # -- baseline ----------------------------------------------------------

    def collect_raw(self, duration_s: float) -> np.ndarray:
        """Gather `duration_s` of raw gauge voltages as a (6, n) array.

        Public because callers legitimately need the voltages behind an
        averaged measurement — the weight validation re-orders them to test
        candidate channel mappings against the same physical measurement.
        """
        return self._collect_volts(duration_s)

    def _collect_volts(self, duration_s: float) -> np.ndarray:
        want = max(1, int(round(duration_s * self.sample_rate_hz)))
        chunks, got = [], 0
        while got < want:
            block = self.read_raw(min(self.samples_per_read, want - got))
            chunks.append(block.volts)
            got += block.volts.shape[1]
        return np.hstack(chunks)

    def acquire_baseline(self, duration_s: float = 10.0) -> dict:
        """Measure offset and noise with the sensor at rest.

        Reports per-gauge raw voltage statistics and per-axis wrench statistics
        (untared, so the absolute offset is visible). Also returns the raw and
        wrench arrays so a caller can persist them.
        """
        self._require_connected("acquire_baseline()")
        t0_mono, t0_wall = time.monotonic(), time.time()
        volts = self._collect_volts(duration_s)
        elapsed = time.monotonic() - t0_mono
        n = volts.shape[1]
        wrench = self.calibration.to_wrench(volts)

        result = {
            "frame": SENSOR_FRAME,
            "requested_duration_s": float(duration_s),
            "actual_duration_s": float(elapsed),
            "n_samples": int(n),
            "nominal_sample_rate_hz": float(self.sample_rate_hz),
            "effective_sample_rate_hz": float(n / elapsed) if elapsed > 0 else None,
            "t_start_monotonic": float(t0_mono),
            "t_start_wall": float(t0_wall),
            "gauge_map": self.gauge_map,
            "terminal_configuration": self.terminal_config,
            "voltage_range_v": self.voltage_range,
            "channel_mapping_confirmed": self.channel_mapping_confirmed,
            "raw_volts": self._stats(volts, GAUGE_NAMES),
            "wrench": self._stats(wrench, WRENCH_AXES),
            "wrench_units": {"force": "N", "torque": "N_m"},
            "tared": False,
        }
        self._baseline = result
        return {**result, "_raw_array": volts, "_wrench_array": wrench}

    def get_baseline(self) -> dict | None:
        """The most recent baseline summary, or None."""
        return self._baseline

    @staticmethod
    def _stats(data: np.ndarray, names: Sequence[str]) -> dict:
        out = {}
        for name, row in zip(names, data):
            out[str(name)] = {
                "mean": float(row.mean()),
                "std": float(row.std(ddof=1)) if row.size > 1 else 0.0,
                "min": float(row.min()),
                "max": float(row.max()),
                "peak_to_peak": float(row.max() - row.min()),
            }
        return out

    # -- construction ------------------------------------------------------

    @classmethod
    def from_config(cls, config_path: str | Path | None = None) -> "FTInterface":
        """Build from src/config/ft_config.yaml. Opens no hardware; call connect()."""
        cfg, cfg_path = load_ft_config(config_path)
        cal = load_calibration(cfg, cfg_path)
        daq = cfg.get("daq") or {}

        channels = daq.get("channels") or []
        if not channels:
            raise ChannelMappingError(
                f"{cfg_path}: daq.channels is empty. List the six AI channels "
                f"carrying {', '.join(GAUGE_NAMES)}, in that order."
            )
        for key in ("device", "sampling_rate_hz", "samples_per_read"):
            if daq.get(key) is None:
                raise FTError(f"{cfg_path}: daq.{key} is null; set it before acquiring")

        return cls(
            calibration=cal,
            device=daq["device"],
            channels=channels,
            terminal_config=daq.get("terminal_configuration", "differential"),
            voltage_range=float(daq.get("voltage_range", 10.0)),
            sample_rate_hz=float(daq["sampling_rate_hz"]),
            samples_per_read=int(daq["samples_per_read"]),
            buffer_size=daq.get("buffer_size"),
            channel_mapping_confirmed=bool(daq.get("channel_mapping_confirmed", False)),
            settle_samples=int(daq.get("settle_samples", 200)),
        )


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def read_raw_channels(
    channels: Sequence[str],
    *,
    duration_s: float = 3.0,
    terminal_config: str = "differential",
    voltage_range: float = 10.0,
    sample_rate_hz: float = 2000.0,
    settle_samples: int = 200,
) -> np.ndarray:
    """Read an arbitrary set of AI channels and return raw volts, shape (n_ch, n).

    A DIAGNOSTIC helper, deliberately outside FTInterface: it takes any channel
    count and returns VOLTS ONLY, never a wrench, so a diagnostic sweep can
    never be mistaken for a calibrated measurement. Used by the weight
    validation to sample every candidate mapping's channels in ONE task, so a
    single weight placement can discriminate between them.

    Analog input only, like everything else here.
    """
    import nidaqmx
    from nidaqmx.constants import AcquisitionType, TerminalConfiguration

    term = {
        "DIFFERENTIAL": TerminalConfiguration.DIFF, "DIFF": TerminalConfiguration.DIFF,
        "RSE": TerminalConfiguration.RSE, "NRSE": TerminalConfiguration.NRSE,
    }[str(terminal_config).upper()]

    n_want = max(1, int(round(duration_s * sample_rate_hz)))
    with nidaqmx.Task() as task:
        for chan in channels:
            task.ai_channels.add_ai_voltage_chan(
                chan, terminal_config=term,
                min_val=-voltage_range, max_val=+voltage_range)
        task.timing.cfg_samp_clk_timing(
            rate=sample_rate_hz, sample_mode=AcquisitionType.CONTINUOUS,
            samps_per_chan=max(2000, n_want))
        task.start()
        if settle_samples > 0:
            task.read(number_of_samples_per_channel=settle_samples, timeout=30.0)
        data = task.read(number_of_samples_per_channel=n_want,
                         timeout=max(10.0, 5.0 * duration_s))
    return np.atleast_2d(np.asarray(data, dtype=float))


def load_ft_config(config_path: str | Path | None = None) -> tuple[dict, Path]:
    """Load ft_config.yaml; returns (config, resolved path)."""
    import yaml

    path = Path(config_path) if config_path else DEFAULT_CONFIG_PATH
    if not path.is_file():
        raise FTError(f"F/T config not found: {path}")
    with open(path) as fh:
        cfg = yaml.safe_load(fh) or {}
    return cfg, path.resolve()


def load_calibration(cfg: dict, config_path: Path) -> ATICalibration:
    """Resolve and parse the calibration named by `cfg`.

    The configured serial is passed as `expected_serial`, so a calibration from
    a different transducer is rejected rather than silently used.
    """
    sensor = cfg.get("ft_sensor") or {}
    name = sensor.get("calibration_file") or sensor.get("calibration_file_name")
    if not name:
        raise CalibrationError(f"{config_path}: ft_sensor.calibration_file is not set")

    candidate = Path(name)
    if not candidate.is_absolute():
        for base in (PROJECT_ROOT / "calibration", PROJECT_ROOT, config_path.parent):
            trial = base / name
            if trial.is_file():
                candidate = trial
                break
    if not candidate.is_file():
        raise CalibrationError(
            f"calibration file {name!r} not found (searched "
            f"{PROJECT_ROOT/'calibration'}, {PROJECT_ROOT}, {config_path.parent})"
        )
    return ATICalibration.from_file(candidate, expected_serial=sensor.get("serial_number"))
