#!/usr/bin/env python3
"""
ATI calibration file parsing and raw-voltage -> wrench conversion.

    FT29831.cal  ->  ATICalibration  ->  W = M_user . (v - v0)

THE ONLY CALIBRATION SOURCE IS THE FILE.
No generic Mini45 matrix, no coefficient from a datasheet, no invented scale
factor appears anywhere in this module. Every number used at runtime is read
out of the .cal file that shipped with this specific transducer.

WHICH MATRIX
------------
ATI writes the calibration twice in the file:

  <Axis>      ATI-internal, scaled by a per-axis `scale` attribute.
  <UserAxis>  the user-facing matrix, with <BasicTransform> already folded in.

The file's own header comment says to use <UserAxis>, and that is what
`to_wrench()` uses. <Axis> and its scales are parsed only so the module can
prove it understood the file: `verify_internal_consistency()` reconstructs
<UserAxis> from <Axis>/scale plus <BasicTransform> and checks they agree. On
FT29831.cal they agree to better than 1e-5.

Because <UserAxis> already contains <BasicTransform> (Dz = 6.858 mm on this
sensor), the transform must NOT be applied again to measurements; doing so
would double-count the origin shift and corrupt Tx and Ty.

FRAME
-----
Every wrench produced here is in the ATI sensor frame. Not the holder frame,
not the robot base frame. No frame transformation happens in this module.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import numpy as np

NUM_GAUGES = 6
WRENCH_AXES = ("Fx", "Fy", "Fz", "Tx", "Ty", "Tz")
GAUGE_NAMES = tuple(f"SG{i}" for i in range(NUM_GAUGES))

# The frame every wrench in this codebase is expressed in, until a later task
# defines the holder and robot transforms.
SENSOR_FRAME = "ATI_sensor_frame"


class CalibrationError(RuntimeError):
    """The calibration file is missing, malformed, or for the wrong sensor."""


# --------------------------------------------------------------------------
# Units. Every factor is exact by definition and carries its source.
# --------------------------------------------------------------------------
# 1 lbf = 4.4482216152605 N exactly (NIST SP 811; from the defined pound mass
#         0.45359237 kg and standard gravity 9.80665 m/s^2).
# 1 in  = 0.0254 m exactly (1959 international yard and pound agreement).
_LBF_TO_N = 4.4482216152605
_IN_TO_M = 0.0254

_FORCE_TO_N = {
    "N": 1.0, "KN": 1000.0,
    "LB": _LBF_TO_N, "LBF": _LBF_TO_N, "KLB": _LBF_TO_N * 1000.0,
}
_TORQUE_TO_NM = {
    "N-M": 1.0, "NM": 1.0, "N-MM": 1e-3, "N-CM": 1e-2, "KN-M": 1000.0,
    "LB-IN": _LBF_TO_N * _IN_TO_M, "LBF-IN": _LBF_TO_N * _IN_TO_M,
    "LB-FT": _LBF_TO_N * _IN_TO_M * 12.0, "LBF-FT": _LBF_TO_N * _IN_TO_M * 12.0,
    "KLB-IN": _LBF_TO_N * _IN_TO_M * 1000.0,
}


def _norm_unit(raw: str) -> str:
    return str(raw).strip().upper().replace("_", "-").replace(" ", "")


def force_factor_to_newton(unit: str) -> float:
    key = _norm_unit(unit)
    if key not in _FORCE_TO_N:
        raise CalibrationError(f"unsupported force unit {unit!r}; known: {sorted(_FORCE_TO_N)}")
    return _FORCE_TO_N[key]


def torque_factor_to_newton_metre(unit: str) -> float:
    key = _norm_unit(unit)
    if key not in _TORQUE_TO_NM:
        raise CalibrationError(f"unsupported torque unit {unit!r}; known: {sorted(_TORQUE_TO_NM)}")
    return _TORQUE_TO_NM[key]


@dataclass(frozen=True)
class ATICalibration:
    """A parsed ATI calibration file.

    `user_matrix` is the 6x6 conversion actually used at runtime:
    rows are (Fx, Fy, Fz, Tx, Ty, Tz), columns are gauges SG0..SG5 in the order
    the file lists them.
    """

    source_path: Path
    serial: str
    body_style: str
    family: str
    num_gauges: int
    part_number: str
    cal_date: str
    force_units: str
    torque_units: str
    dist_units: str
    output_mode: str
    output_range: str
    hw_temp_comp: str
    gain_multiplier: str
    output_bipolar: str
    user_matrix: np.ndarray
    max_loads: dict[str, float]
    basic_transform: dict[str, float]
    _axis_matrix: np.ndarray | None = field(repr=False, default=None)
    _axis_scales: np.ndarray | None = field(repr=False, default=None)

    # -- parsing -----------------------------------------------------------

    @classmethod
    def from_file(cls, path: str | Path, expected_serial: str | None = None) -> "ATICalibration":
        path = Path(path)
        if not path.is_file():
            raise CalibrationError(f"calibration file not found: {path}")
        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as exc:
            raise CalibrationError(f"{path}: not valid XML ({exc})") from exc

        if root.tag != "FTSensor":
            raise CalibrationError(f"{path}: root is <{root.tag}>, expected <FTSensor>")
        cal = root.find("Calibration")
        if cal is None:
            raise CalibrationError(f"{path}: no <Calibration> element")

        serial = (root.get("Serial") or "").strip()
        if not serial:
            raise CalibrationError(f"{path}: <FTSensor> has no Serial attribute")
        if expected_serial and serial.upper() != str(expected_serial).strip().upper():
            raise CalibrationError(
                f"{path}: calibration is for sensor {serial!r} but {expected_serial!r} was "
                "expected. Refusing to use a calibration from a different transducer."
            )

        try:
            num_gauges = int(root.get("NumGages", NUM_GAUGES))
        except ValueError as exc:
            raise CalibrationError(f"{path}: NumGages is not an integer") from exc
        if num_gauges != NUM_GAUGES:
            raise CalibrationError(
                f"{path}: NumGages={num_gauges}; this module handles {NUM_GAUGES}-gauge sensors"
            )

        force_units = (cal.get("ForceUnits") or "").strip()
        torque_units = (cal.get("TorqueUnits") or "").strip()
        if not force_units or not torque_units:
            raise CalibrationError(
                f"{path}: ForceUnits/TorqueUnits missing; refusing to guess the native units"
            )
        force_factor_to_newton(force_units)          # fail now, not mid-experiment
        torque_factor_to_newton_metre(torque_units)

        bt_el = cal.find("BasicTransform")
        basic_transform = (
            {k: float(bt_el.get(k, 0.0)) for k in ("Dx", "Dy", "Dz", "Rx", "Ry", "Rz")}
            if bt_el is not None else {}
        )

        return cls(
            source_path=path.resolve(),
            serial=serial,
            body_style=(root.get("BodyStyle") or "").strip(),
            family=(root.get("Family") or "").strip(),
            num_gauges=num_gauges,
            part_number=(cal.get("PartNumber") or "").strip(),
            cal_date=(cal.get("CalDate") or "").strip(),
            force_units=force_units,
            torque_units=torque_units,
            dist_units=(cal.get("DistUnits") or "").strip(),
            output_mode=(cal.get("OutputMode") or "").strip(),
            output_range=(cal.get("OutputRange") or "").strip(),
            hw_temp_comp=(cal.get("HWTempComp") or "").strip(),
            gain_multiplier=(cal.get("GainMultiplier") or "").strip(),
            output_bipolar=(cal.get("OutputBipolar") or "").strip(),
            user_matrix=cls._read_axis_block(cal, "UserAxis", path, num_gauges),
            max_loads=cls._read_max_loads(cal),
            basic_transform=basic_transform,
            _axis_matrix=cls._read_axis_block(cal, "Axis", path, num_gauges, required=False),
            _axis_scales=cls._read_axis_scales(cal),
        )

    @staticmethod
    def _read_axis_block(cal, tag: str, path: Path, num_gauges: int,
                         required: bool = True) -> np.ndarray | None:
        found = {el.get("Name"): el for el in cal.findall(tag)}
        missing = [a for a in WRENCH_AXES if a not in found]
        if missing:
            if not required:
                return None
            raise CalibrationError(f"{path}: <{tag}> missing axes {missing}")
        rows = []
        for axis in WRENCH_AXES:
            raw = found[axis].get("values")
            if raw is None:
                raise CalibrationError(f"{path}: <{tag} Name='{axis}'> has no values attribute")
            try:
                vals = [float(v) for v in raw.split()]
            except ValueError as exc:
                raise CalibrationError(
                    f"{path}: <{tag} Name='{axis}'> has non-numeric values") from exc
            if len(vals) != num_gauges:
                raise CalibrationError(
                    f"{path}: <{tag} Name='{axis}'> has {len(vals)} values, expected {num_gauges}")
            rows.append(vals)
        matrix = np.array(rows, dtype=float)
        if not np.all(np.isfinite(matrix)):
            raise CalibrationError(f"{path}: <{tag}> contains NaN or infinity")
        return matrix

    @staticmethod
    def _read_axis_scales(cal) -> np.ndarray | None:
        scales = []
        for axis in WRENCH_AXES:
            el = next((e for e in cal.findall("Axis") if e.get("Name") == axis), None)
            if el is None or el.get("scale") is None:
                return None
            try:
                scales.append(float(el.get("scale")))
            except ValueError:
                return None
        return np.array(scales, dtype=float)

    @staticmethod
    def _read_max_loads(cal) -> dict[str, float]:
        out = {}
        for el in cal.findall("UserAxis"):
            name, raw = el.get("Name"), el.get("max")
            if name in WRENCH_AXES and raw is not None:
                try:
                    out[name] = float(raw)
                except ValueError:
                    pass
        return out

    # -- integrity ---------------------------------------------------------

    def verify_internal_consistency(self, tol: float = 1e-4) -> bool:
        """Reconstruct <UserAxis> from <Axis>/scale + <BasicTransform>.

        Agreement proves the parser read the scales, the axis ordering and the
        origin shift correctly. Returns False if the file lacks <Axis> data to
        check against — unverifiable, not wrong.
        """
        if self._axis_matrix is None or self._axis_scales is None or not self.basic_transform:
            return False
        u = self._axis_matrix / self._axis_scales[:, None]
        fx, fy, fz = u[0], u[1], u[2]
        dx = self.basic_transform.get("Dx", 0.0)
        dy = self.basic_transform.get("Dy", 0.0)
        dz = self.basic_transform.get("Dz", 0.0)
        recon = np.vstack([
            fx, fy, fz,
            u[3] + fy * dz - fz * dy,      # Tx
            u[4] + fz * dx - fx * dz,      # Ty
            u[5] + fx * dy - fy * dx,      # Tz
        ])
        return bool(np.max(np.abs(recon - self.user_matrix)) < tol)

    # -- conversion --------------------------------------------------------

    @property
    def force_to_newton(self) -> float:
        return force_factor_to_newton(self.force_units)

    @property
    def torque_to_newton_metre(self) -> float:
        return torque_factor_to_newton_metre(self.torque_units)

    @property
    def si_matrix(self) -> np.ndarray:
        """`user_matrix` rescaled to output N and N*m whatever the file's native
        units are. For FT29831.cal both factors are 1.0, so it is unchanged."""
        s = np.array([self.force_to_newton] * 3 + [self.torque_to_newton_metre] * 3)
        return self.user_matrix * s[:, None]

    def to_wrench(self, gauge_volts: Sequence[float] | np.ndarray,
                  bias: Sequence[float] | np.ndarray | None = None) -> np.ndarray:
        """W = M_si . (v - v0). Returns N and N*m in the ATI sensor frame.

        Accepts one sample of shape (6,) or a block of shape (6, n) with gauges
        on the first axis, matching the DAQ read layout, and returns the same
        shape.

        `gauge_volts` MUST already be in SG0..SG5 order. This method cannot
        detect a wrong ordering — that is what the explicit `channels` list in
        ft_config.yaml, and the 1 kg validation, are for.
        """
        v = np.asarray(gauge_volts, dtype=float)
        if v.shape[0] != NUM_GAUGES:
            raise ValueError(
                f"expected {NUM_GAUGES} gauge values on the first axis, got shape {v.shape}")
        if not np.all(np.isfinite(v)):
            raise ValueError("gauge voltages contain NaN or infinity")
        if bias is not None:
            b = np.asarray(bias, dtype=float)
            if b.shape != (NUM_GAUGES,):
                raise ValueError(f"bias must have {NUM_GAUGES} elements, got {b.shape}")
            if not np.all(np.isfinite(b)):
                raise ValueError("bias contains NaN or infinity")
            v = v - (b[:, None] if v.ndim == 2 else b)
        return self.si_matrix @ v

    def exceeds_max_load(self, wrench: Sequence[float]) -> dict[str, float]:
        """Axes whose magnitude is beyond the calibrated range, with the value.

        Reporting only. Nothing here stops an acquisition; the calibration is
        simply not valid outside these bounds.
        """
        w = np.asarray(wrench, dtype=float)
        out = {}
        for i, axis in enumerate(WRENCH_AXES):
            limit = self.max_loads.get(axis)
            if limit is not None and abs(w[i]) > limit:
                out[axis] = float(w[i])
        return out

    def metadata(self) -> dict:
        """Everything a data file needs to stay interpretable later."""
        return {
            "calibration_file": str(self.source_path),
            "serial": self.serial,
            "body_style": self.body_style,
            "family": self.family,
            "part_number": self.part_number,
            "cal_date": self.cal_date,
            "num_gauges": self.num_gauges,
            "gauge_order": list(GAUGE_NAMES),
            "native_force_unit": self.force_units,
            "native_torque_unit": self.torque_units,
            "dist_units": self.dist_units,
            "output_mode": self.output_mode,
            "output_range": self.output_range,
            "hw_temp_comp": self.hw_temp_comp,
            "gain_multiplier": self.gain_multiplier,
            "output_bipolar": self.output_bipolar,
            "basic_transform": dict(self.basic_transform),
            "basic_transform_already_in_user_matrix": True,
            "max_loads_native": dict(self.max_loads),
            "force_to_N": self.force_to_newton,
            "torque_to_Nm": self.torque_to_newton_metre,
            "matrix_source": "UserAxis",
            "user_matrix": self.user_matrix.tolist(),
            "internally_consistent": self.verify_internal_consistency(),
            "frame": SENSOR_FRAME,
        }

    def summary(self) -> str:
        return (f"ATI {self.body_style} s/n {self.serial} ({self.part_number}), "
                f"cal {self.cal_date}, units {self.force_units}/{self.torque_units}")
