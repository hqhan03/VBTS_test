#!/usr/bin/env python3
"""
Common data types for the VBTS testing platform.

CONVENTIONS — these mirror the FAIRINO SDK exactly, not a re-interpretation
-------------------------------------------------------------------------
Everything here follows the convention verified against the installed SDK
(fairino-cpp-sdk v2.3.4-robot3.9.4, ``robot_types.h``) and confirmed by real
hardware logs from the FR5 controller:

  * Cartesian position  : millimetres (``DescTran { double x, y, z; /* mm */ }``)
  * Orientation         : fixed-axis RPY (extrinsic XYZ) Euler angles.
                          ``Rpy.rx`` is documented in the SDK header as
                          "Rotation Angle about fixed axis X". This is NOT a
                          rotation vector and NOT a quaternion, and the axes are
                          FIXED (extrinsic), not the moving/intrinsic frame.
  * Orientation unit    : degrees
  * Pose ordering       : [x, y, z, rx, ry, rz] — the order used by the
                          ``DescPose(x,y,z,rx,ry,rz)`` constructor and by the
                          XML-RPC wire format for MoveJ/MoveL.
  * Joint angles        : degrees (``JointPos { double jPos[6]; /* deg */ }``)

Do not add unit conversion helpers here on a guess. If the experiment protocol
later needs metres or radians, convert at the boundary where the need is
actually established, and keep this module in the robot's native units.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

# Number of robot joints. The FR5 is a 6-axis arm; the SDK types are fixed at 6
# (``jPos[6]``), so this is a property of the protocol, not a configurable.
NUM_JOINTS = 6

# The canonical field order. Kept as data so tests can assert against it rather
# than against a hand-written literal in three places.
POSE_ORDER = ("x", "y", "z", "rx", "ry", "rz")
POSE_UNITS = ("mm", "mm", "mm", "deg", "deg", "deg")


def _as_float_sequence(values: Sequence[float], expected_len: int, what: str) -> tuple[float, ...]:
    """Validate and convert a sequence of numbers.

    Rejects strings and bools explicitly. A ``str`` is a ``Sequence`` and would
    otherwise slip through a naive length check; a ``bool`` is an ``int`` and
    would silently become 0.0/1.0.
    """
    if isinstance(values, (str, bytes)):
        raise TypeError(f"{what}: expected a sequence of numbers, got {type(values).__name__}")
    try:
        items = list(values)
    except TypeError as exc:
        raise TypeError(f"{what}: value is not iterable ({type(values).__name__})") from exc

    if len(items) != expected_len:
        raise ValueError(f"{what}: expected {expected_len} values, got {len(items)}")

    out = []
    for i, v in enumerate(items):
        if isinstance(v, bool):
            raise TypeError(f"{what}[{i}]: bool is not a valid coordinate value")
        if not isinstance(v, (int, float)):
            raise TypeError(f"{what}[{i}]: expected a number, got {type(v).__name__}")
        fv = float(v)
        if fv != fv or fv in (float("inf"), float("-inf")):
            raise ValueError(f"{what}[{i}]: value must be finite, got {v!r}")
        out.append(fv)
    return tuple(out)


@dataclass(frozen=True)
class RobotPose:
    """A Cartesian pose in the FAIRINO convention: [x, y, z, rx, ry, rz].

    Units: x/y/z in **mm**, rx/ry/rz in **degrees**.
    Orientation is fixed-axis (extrinsic) RPY — see the module docstring.

    Frozen so a pose handed to a motion call cannot be mutated afterwards by
    the caller; use :meth:`offset` or :meth:`replace` to derive a new pose.
    """

    x: float
    y: float
    z: float
    rx: float
    ry: float
    rz: float

    def __post_init__(self) -> None:
        # Validate through the same path as from_sequence so direct construction
        # and sequence construction cannot diverge.
        values = _as_float_sequence(
            [self.x, self.y, self.z, self.rx, self.ry, self.rz], 6, "RobotPose"
        )
        for name, value in zip(POSE_ORDER, values):
            object.__setattr__(self, name, value)

    @classmethod
    def from_sequence(cls, values: Sequence[float]) -> "RobotPose":
        """Build from [x, y, z, rx, ry, rz]."""
        return cls(*_as_float_sequence(values, 6, "RobotPose"))

    def as_tuple(self) -> tuple[float, float, float, float, float, float]:
        """Return [x, y, z, rx, ry, rz] — the FAIRINO wire order."""
        return (self.x, self.y, self.z, self.rx, self.ry, self.rz)

    def as_list(self) -> list[float]:
        return list(self.as_tuple())

    def offset(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0,
               drx: float = 0.0, dry: float = 0.0, drz: float = 0.0) -> "RobotPose":
        """Return a new pose translated/rotated by the given deltas.

        This is a plain component-wise addition in the pose's own reference
        frame. It is correct for translation deltas; for orientation it is only
        valid for small angles about a single axis, because fixed-axis RPY
        angles do not compose by addition in general. Do not use it to build
        large multi-axis rotations.
        """
        return RobotPose(
            self.x + dx, self.y + dy, self.z + dz,
            self.rx + drx, self.ry + dry, self.rz + drz,
        )

    def __str__(self) -> str:
        return (f"[{self.x:.3f}, {self.y:.3f}, {self.z:.3f}, "
                f"{self.rx:.3f}, {self.ry:.3f}, {self.rz:.3f}]")


@dataclass(frozen=True)
class JointState:
    """Six joint angles J1..J6 in **degrees** — FAIRINO ``JointPos.jPos[6]``."""

    positions_deg: tuple[float, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "positions_deg",
            _as_float_sequence(self.positions_deg, NUM_JOINTS, "JointState"),
        )

    @classmethod
    def from_sequence(cls, values: Sequence[float]) -> "JointState":
        return cls(_as_float_sequence(values, NUM_JOINTS, "JointState"))

    def as_tuple(self) -> tuple[float, ...]:
        return self.positions_deg

    def as_list(self) -> list[float]:
        return list(self.positions_deg)

    def __str__(self) -> str:
        return "[" + ", ".join(f"{v:.3f}" for v in self.positions_deg) + "]"


@dataclass(frozen=True)
class RobotState:
    """A snapshot of controller state.

    ``simulated`` is the load-bearing field: when True this snapshot came from
    :class:`~vbts_platform.robot_interface.RobotInterface`'s internal dry-run
    model and describes NO physical robot. Never log or store a snapshot
    without carrying this flag along with it.

    Fields sourced from the 20004 real-time stream are None until a frame long
    enough to contain them has actually been observed.
    """

    tcp_pose: RobotPose | None = None
    joints: JointState | None = None

    robot_state: int | None = None      # 1-stop 2-run 3-pause 4-drag
    robot_mode: int | None = None       # per RT stream: 1-manual, 0-auto
    main_code: int | None = None
    sub_code: int | None = None

    # Safety / motion status (RT stream additive block)
    motion_done: int | None = None
    emergency_stop: int | None = None
    collision_state: int | None = None
    safety_stop0: int | None = None
    safety_stop1: int | None = None
    joint_torque: tuple[float, ...] | None = None

    simulated: bool = False

    @property
    def is_safe_to_move(self) -> bool | None:
        """True/False from observed safety flags, or None if not yet observed.

        Deliberately tri-state. A missing reading must not read as "safe", and
        the caller has to decide what to do about None. This is a status
        summary only — it is NOT an automatic safety stop, which is explicitly
        out of scope until a later task defines the force limits.
        """
        flags = (self.emergency_stop, self.collision_state,
                 self.safety_stop0, self.safety_stop1)
        if any(f is None for f in flags):
            return None
        return not any(flags)


@dataclass(frozen=True)
class MotionCommand:
    """A fully-resolved motion request, before it reaches the wire.

    Built and validated by RobotInterface, then either logged (dry run) or
    handed to the parameter builders. Keeping it as a value object means the
    dry-run log and the real RPC path describe the same object, so what you
    read in a dry run is what would have been sent.
    """

    kind: str                       # "MoveJ" | "MoveL"
    target_pose: RobotPose
    target_joints: JointState | None = None
    tool: int = 0
    user: int = 0
    vel: float = 20.0               # % of max, [0..100]
    acc: float = 50.0               # % — SDK header: "not open for now"
    ovl: float = 100.0              # velocity scaling factor, [0..100]
    blend: float = -1.0             # -1.0 = move-to-position (blocking)
    offset_flag: int = 0            # 0 = no offset
    offset_pose: RobotPose = field(
        default_factory=lambda: RobotPose(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    )
    exaxis: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)

    def __post_init__(self) -> None:
        if self.kind not in ("MoveJ", "MoveL"):
            raise ValueError(f"MotionCommand.kind must be 'MoveJ' or 'MoveL', got {self.kind!r}")
        for name in ("vel", "ovl"):
            value = getattr(self, name)
            if not 0.0 <= float(value) <= 100.0:
                raise ValueError(f"MotionCommand.{name} must be in [0, 100], got {value!r}")
        object.__setattr__(
            self, "exaxis", _as_float_sequence(self.exaxis, 4, "MotionCommand.exaxis")
        )

    def describe(self) -> str:
        """Human-readable multi-line form, used for the dry-run log."""
        lines = [
            f"target       = {self.target_pose}",
            f"unit         = [mm, mm, mm, deg, deg, deg]",
        ]
        if self.target_joints is not None:
            lines.append(f"joints (deg) = {self.target_joints}")
        lines += [
            f"velocity     = {self.vel} %",
            f"acceleration = {self.acc} %",
            f"ovl          = {self.ovl} %",
            f"blend        = {self.blend}"
            + ("  (-1.0 = blocking, move to position)" if self.blend == -1.0 else ""),
            f"tool         = {self.tool}",
            f"user         = {self.user}",
        ]
        return "\n".join(lines)
