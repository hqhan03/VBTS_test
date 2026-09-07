#!/usr/bin/env python3
"""
RobotInterface — the single entry point every experiment protocol uses.

Protocol code must never call `fr5_io` (or raw XML-RPC) directly. Everything
goes through this class, so that the dry-run gate and the motion guards cannot
be bypassed by accident.

SAFETY MODEL
------------
Three independent gates stand between calling ``move_linear()`` and the robot
actually moving. All three must be opened deliberately:

  1. ``dry_run=False``        — default is True. While True, no socket is ever
                                opened and no RPC is ever issued.
  2. ``allow_real_motion=True`` — default is False. Flipping only gate 1 raises
                                RuntimeError, so a stray ``dry_run=False`` cannot
                                move the arm.
  3. Real RPC dispatch is NOT WIRED UP in this module yet, and deliberately so.
                                Two protocol facts are still unverified against
                                hardware (see MODE_TODO and IK_TODO below), and
                                guessing either could produce unintended motion.
                                The real path raises NotImplementedError until
                                those are confirmed on a powered-on robot.

Gate 3 disappears in a later task, after the hardware bring-up described in
`connect(read_only=True)`. Gates 1 and 2 are permanent.

WHAT IS SIMULATED
-----------------
In dry-run mode this class keeps an internal pose/joint model so a protocol can
be stepped through end to end without hardware. That model is a bookkeeping
convenience, not a physics simulation: it assumes every commanded motion
succeeds exactly and instantly. It knows nothing about reachability, joint
limits, singularities, or collisions. Every value it returns is tagged
``simulated=True`` — never record such a value as a measurement.
"""

from __future__ import annotations

import logging
from typing import Sequence

from . import fr5_io
from .types import (
    NUM_JOINTS,
    JointState,
    MotionCommand,
    RobotPose,
    RobotState,
)

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Unresolved protocol facts — do not guess these, verify them on hardware.
# --------------------------------------------------------------------------

MODE_TODO = """\
UNVERIFIED: which Mode() the FR5 requires for protocol MoveL/MoveJ.

Evidence gathered so far disagrees on intent, not on the constant:
  * fr5_tcp_jog_gui.py calls Mode(1) and labels it "manual" (jogging).
  * tesollo_manus_teleop/.../fairino_lowlevel_controller_node.cpp calls Mode(0)
    and labels it "automatic mode" before ServoJ/ServoCart/MoveJ. That node has
    521 successful run logs against this robot, so Mode(0) is known to work for
    MoveJ specifically.
  * The SDK header robot.h documents `Mode(int mode)` WITHOUT stating what 0 and
    1 mean. The meaning appears only in the RT-stream struct comment
    (robot_types.h: "robot_mode: 1-Manual mode; 0-Auto mode").

So Mode(0)=auto is very likely correct for our MoveL protocol, but it is
inferred from a neighbouring struct comment plus one node's usage, not from the
API contract. `operation_mode` is therefore left null in robot_config.yaml.
Resolve by reading `robot_mode` off the RT stream during a read-only connect.
"""

IK_TODO = """\
UNVERIFIED: the Cartesian-only MoveL path.

The XML-RPC "MoveL" method requires BOTH a joint target and a Cartesian target
in the same parameter array (indices 0-5 and 6-11). The SDK's convenience
overload MoveL(DescPose*, ...) does not send a different message: it calls
GetInverseKin(0, desc_pos, config, &jPos) first (robot.cpp:951) and then
delegates to the full form. A Cartesian move is therefore TWO round trips.

So `_build_move_l_params` needs joints the caller has not got yet. Task 3 must
add a `get_inverse_kin()` call and confirm its `config` argument semantics
(-1 = "solve from current joint position") against hardware before this is safe.
"""


class RobotInterfaceError(RuntimeError):
    """Base error. Subclasses RuntimeError so the required guard type holds."""


class MotionNotAllowedError(RobotInterfaceError):
    """Raised when a motion is requested without the explicit opt-in."""


class NotConnectedError(RobotInterfaceError):
    """Raised when an operation needs a connection that was never opened."""


class RobotInterface:
    """High-level robot control with a dry-run mode that touches no hardware.

    Args:
        ip: Controller address. Only used when ``dry_run=False``.
        dry_run: When True (the default) no socket is opened and no RPC is sent.
        allow_real_motion: Second gate. Must ALSO be True for motion.
        tool: Tool coordinate frame id. SDK English header documents [0..14].
        user: Workpiece (user) coordinate frame id, [0..14].
        operation_mode: Value to pass to ``Mode()``. ``None`` means "unverified,
            do not send" — see :data:`MODE_TODO`.
        initial_pose / initial_joints: Seed state for the dry-run model.
    """

    def __init__(
        self,
        ip: str = fr5_io.DEFAULT_ROBOT_IP,
        *,
        dry_run: bool = True,
        allow_real_motion: bool = False,
        tool: int = 0,
        user: int = 0,
        operation_mode: int | None = None,
        initial_pose: RobotPose | Sequence[float] | None = None,
        initial_joints: JointState | Sequence[float] | None = None,
    ) -> None:
        self.ip = ip
        self.dry_run = bool(dry_run)
        self.allow_real_motion = bool(allow_real_motion)
        self.tool = int(tool)
        self.user = int(user)
        self.operation_mode = operation_mode

        self._connected = False
        self._read_only = True
        self._cmds: fr5_io.FR5Commands | None = None
        self._rt: fr5_io.RealtimeState | None = None

        # --- dry-run model. Meaningless unless self.dry_run is True. --------
        if initial_pose is None:
            initial_pose = RobotPose(0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        elif not isinstance(initial_pose, RobotPose):
            initial_pose = RobotPose.from_sequence(initial_pose)
        if initial_joints is None:
            initial_joints = JointState.from_sequence([0.0] * NUM_JOINTS)
        elif not isinstance(initial_joints, JointState):
            initial_joints = JointState.from_sequence(initial_joints)

        self._sim_pose: RobotPose = initial_pose
        self._sim_joints: JointState = initial_joints
        self._sim_command_log: list[MotionCommand] = []

        if self.dry_run and self.allow_real_motion:
            # Not an error, but it reads like a mistake, so say so out loud.
            logger.warning(
                "allow_real_motion=True has no effect while dry_run=True; "
                "no hardware will be touched."
            )

    # ---------------------------------------------------------------- state

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def read_only(self) -> bool:
        return self._read_only

    @property
    def simulated(self) -> bool:
        """True when every reading from this instance is from the dry-run model."""
        return self.dry_run

    @property
    def command_log(self) -> list[MotionCommand]:
        """Motion commands issued in dry-run mode, oldest first."""
        return list(self._sim_command_log)

    # ----------------------------------------------------------- connection

    def connect(self, read_only: bool = True) -> None:
        """Open a connection.

        ``read_only=True`` (the default) opens ONLY the observation paths: the
        20004 real-time state stream and the 20003 command channel used purely
        for status reads. It deliberately does NOT call RobotEnable, Mode, or
        SetSpeed.

        That is a behavioural difference from fr5_tcp_jog_gui.py, which runs
        ``RobotEnable(1) -> Mode(1) -> SetSpeed(n)`` on connect. Implicit
        enabling is exactly what must not happen here: a protocol run should be
        able to observe the robot without ever energising it, which is also how
        `Mode` and the F/T presence get verified before anything moves.

        ``read_only=False`` is the motion-enabled connection. It requires
        ``allow_real_motion=True`` and is not implemented yet (gate 3).
        """
        if self._connected:
            raise RobotInterfaceError("already connected; call disconnect() first")

        if self.dry_run:
            self._connected = True
            self._read_only = bool(read_only)
            logger.info(
                "[DRY RUN] connect(read_only=%s) — no socket opened, ip=%s",
                read_only, self.ip,
            )
            return

        if not read_only:
            self._require_real_motion("connect(read_only=False)")
            raise NotImplementedError(
                "Motion-enabled connect is not wired up yet.\n\n" + MODE_TODO
            )

        # Real read-only connection. Reachable only with an explicit
        # dry_run=False, and it cannot move the robot: nothing below enables
        # the servos or sets a mode.
        cmds = fr5_io.FR5Commands(self.ip)
        cmds.get_sdk_version()          # proves the RPC server answered
        rt = fr5_io.RealtimeState(self.ip)
        rt.start()
        self._cmds = cmds
        self._rt = rt
        self._connected = True
        self._read_only = True
        logger.info("Connected read-only to %s (no enable, no mode change)", self.ip)

    def disconnect(self) -> None:
        """Close everything. Safe to call when not connected."""
        if self.dry_run:
            if self._connected:
                logger.info("[DRY RUN] disconnect()")
            self._connected = False
            return

        if self._rt is not None:
            self._rt.stop()
            self._rt = None
        if self._cmds is not None:
            self._cmds.close()
            self._cmds = None
        self._connected = False
        logger.info("Disconnected from %s", self.ip)

    def __enter__(self) -> "RobotInterface":
        self.connect(read_only=True)
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.disconnect()

    # --------------------------------------------------------------- guards

    def _require_real_motion(self, what: str) -> None:
        """Gate 2. Raises unless real motion has been explicitly opted into."""
        if not self.allow_real_motion:
            raise MotionNotAllowedError(
                f"{what} refused: allow_real_motion is False.\n"
                "Real robot motion needs BOTH gates open:\n"
                "    RobotInterface(dry_run=False, allow_real_motion=True)\n"
                "Setting dry_run=False alone is deliberately not enough."
            )

    def _require_connected(self, what: str) -> None:
        if not self._connected:
            raise NotConnectedError(f"{what} requires a connection; call connect() first")

    # ----------------------------------------------------------- state read

    def get_tcp_pose(self) -> RobotPose:
        """Current TCP pose, [x, y, z, rx, ry, rz] in mm/deg.

        In dry-run mode this returns the SIMULATED pose, not a measurement.
        """
        self._require_connected("get_tcp_pose()")
        if self.dry_run:
            return self._sim_pose
        rt = self._rt
        if rt is None or rt.tcp_pose is None:
            raise NotConnectedError("no real-time frame received yet")
        return RobotPose.from_sequence(rt.tcp_pose)

    def get_joint_positions(self) -> JointState:
        """Current joint angles in degrees.

        In dry-run mode this returns the SIMULATED joints, not a measurement.
        """
        self._require_connected("get_joint_positions()")
        if self.dry_run:
            return self._sim_joints
        rt = self._rt
        if rt is None or rt.joints is None:
            raise NotConnectedError("no real-time frame received yet")
        return JointState.from_sequence(rt.joints)

    def get_robot_state(self) -> RobotState:
        """Full status snapshot, including the safety block when available."""
        self._require_connected("get_robot_state()")
        if self.dry_run:
            return RobotState(
                tcp_pose=self._sim_pose,
                joints=self._sim_joints,
                simulated=True,
            )
        rt = self._rt
        if rt is None:
            raise NotConnectedError("real-time stream not running")
        return RobotState(
            tcp_pose=RobotPose.from_sequence(rt.tcp_pose) if rt.tcp_pose else None,
            joints=JointState.from_sequence(rt.joints) if rt.joints else None,
            robot_state=rt.robot_state,
            robot_mode=rt.robot_mode,
            main_code=rt.main_code,
            sub_code=rt.sub_code,
            motion_done=rt.motion_done,
            emergency_stop=rt.emergency_stop,
            collision_state=rt.collision_state,
            safety_stop0=rt.safety_stop0,
            safety_stop1=rt.safety_stop1,
            joint_torque=rt.joint_torque,
            simulated=False,
        )

    # --------------------------------------------------------------- motion

    def move_linear(
        self,
        target: RobotPose | Sequence[float],
        *,
        vel: float = 20.0,
        acc: float = 50.0,
        ovl: float = 100.0,
        blend: float = -1.0,
        joints: JointState | Sequence[float] | None = None,
    ) -> MotionCommand:
        """Straight-line Cartesian move to ``target`` (mm/deg).

        ``joints`` is the joint-space solution for ``target``. The FR5 wire
        protocol requires it alongside the pose (see :data:`IK_TODO`); it is
        optional here only so a dry run can be stepped through before the IK
        call exists.

        Returns the resolved MotionCommand — in dry-run mode that is the whole
        result, and it is what would have been sent.
        """
        # Gate 2 first, before argument resolution can raise anything else.
        # "You are not allowed to move" outranks "your argument was malformed".
        if not self.dry_run:
            self._require_real_motion("MoveL")

        pose = target if isinstance(target, RobotPose) else RobotPose.from_sequence(target)
        joint_state = self._coerce_joints(joints)

        command = MotionCommand(
            kind="MoveL", target_pose=pose, target_joints=joint_state,
            tool=self.tool, user=self.user,
            vel=vel, acc=acc, ovl=ovl, blend=blend,
        )
        return self._dispatch(command)

    def move_joint(
        self,
        target_joints: JointState | Sequence[float],
        *,
        pose: RobotPose | Sequence[float] | None = None,
        vel: float = 20.0,
        acc: float = 50.0,
        ovl: float = 100.0,
        blend: float = -1.0,
    ) -> MotionCommand:
        """Joint-space move to ``target_joints`` (degrees).

        ``pose`` is the forward-kinematics pose of those joints. As with
        MoveL, the wire protocol carries both; the SDK's joint-only overload
        just calls GetForwardKin first (robot.cpp:772).
        """
        # Gate 2 first — see the matching comment in move_linear().
        if not self.dry_run:
            self._require_real_motion("MoveJ")

        joint_state = (
            target_joints if isinstance(target_joints, JointState)
            else JointState.from_sequence(target_joints)
        )
        if pose is None:
            # Unknown without forward kinematics. In dry run we carry the last
            # simulated pose so the record is complete; it is NOT the true FK.
            resolved_pose = self._sim_pose if self.dry_run else None
            if resolved_pose is None:
                raise ValueError(
                    "move_joint() needs `pose` (the forward-kinematics result) "
                    "outside dry-run mode; the MoveJ wire format carries both."
                )
        else:
            resolved_pose = pose if isinstance(pose, RobotPose) else RobotPose.from_sequence(pose)

        command = MotionCommand(
            kind="MoveJ", target_pose=resolved_pose, target_joints=joint_state,
            tool=self.tool, user=self.user,
            vel=vel, acc=acc, ovl=ovl, blend=blend,
        )
        return self._dispatch(command)

    def stop(self) -> None:
        """Halt motion (``StopMotion``).

        Note the deliberate asymmetry: stop() does NOT require
        ``allow_real_motion``. That gate exists to stop unintended motion from
        STARTING; a command that can only halt the arm should never be harder
        to issue than the command that started it.
        """
        if self.dry_run:
            logger.info("[DRY RUN] StopMotion")
            return
        self._require_connected("stop()")
        raise NotImplementedError(
            "StopMotion dispatch is not wired up yet (gate 3).\n"
            "Until then, the jog GUI's STOP button remains the manual fallback."
        )

    def _coerce_joints(
        self, joints: JointState | Sequence[float] | None
    ) -> JointState | None:
        if joints is None:
            return None
        return joints if isinstance(joints, JointState) else JointState.from_sequence(joints)

    def _dispatch(self, command: MotionCommand) -> MotionCommand:
        """Route a validated command to the dry-run log or the real wire."""
        if self.dry_run:
            self._log_dry_run(command)
            self._apply_to_simulation(command)
            self._sim_command_log.append(command)
            return command

        # Gate 2, checked before anything touches the network.
        self._require_real_motion(command.kind)
        self._require_connected(command.kind)
        if self._read_only:
            raise MotionNotAllowedError(
                f"{command.kind} refused: this is a read-only connection. "
                "Reconnect with connect(read_only=False)."
            )

        # Gate 3.
        raise NotImplementedError(
            f"{command.kind} RPC dispatch is not wired up yet.\n\n"
            f"{MODE_TODO}\n{IK_TODO}"
        )

    def _log_dry_run(self, command: MotionCommand) -> None:
        logger.info("[DRY RUN] %s\n%s", command.kind, command.describe())

    def _apply_to_simulation(self, command: MotionCommand) -> None:
        """Advance the dry-run model. Assumes perfect, instant success."""
        self._sim_pose = command.target_pose
        if command.target_joints is not None:
            self._sim_joints = command.target_joints

    # ---------------------------------------------- wire parameter builders

    def _build_move_l_params(self, command: MotionCommand) -> list[list[float]]:
        """Build the XML-RPC parameter array for "MoveL".

        Layout transcribed from the installed SDK, robot.cpp:842-877
        (``FRRobot::MoveL(JointPos*, DescPose*, ...)``). MoveL packs everything
        into ONE flat 33-element array at ``param[0]`` — note this differs from
        MoveJ, which uses 11 nested top-level parameters. That asymmetry is in
        the SDK, not a mistake here.

            [0..5]   joint target j1..j6           (deg)
            [6..11]  Cartesian target x,y,z,rx,ry,rz (mm, deg)
            [12]     tool
            [13]     user
            [14]     vel        (%)
            [15]     acc        (%)   SDK: "not open for now"
            [16]     ovl        (%)
            [17]     blendR     (-1.0 = blocking)
            [18]     blendMode  (0 = inner-cut transition)
            [19..22] exaxis e0..e3   (mm)
            [23]     search     (0 = no wire-seek; welding feature)
            [24]     offset_flag (0 = no offset)
            [25..30] offset pose x,y,z,rx,ry,rz
            [31]     oacc
            [32]     velAccParamMode (0 = percentage)

        Not part of this array: ``overSpeedStrategy`` and ``speedPercent`` from
        the C++ signature. When overSpeedStrategy > 1 the SDK wraps the MoveL in
        separate ``JointOverSpeedProtectStart`` / ``JointOverSpeedProtectEnd``
        calls (robot.cpp:820-838, 890-902) rather than sending them inline.
        """
        if command.kind != "MoveL":
            raise ValueError(f"_build_move_l_params called with kind={command.kind!r}")
        if command.target_joints is None:
            raise ValueError(
                "MoveL requires a joint-space target alongside the pose.\n\n" + IK_TODO
            )

        # TODO(hardware): `oacc`. The SDK header defaults it to 100.0, but the
        # Cartesian-only overload passes `ovl` into this slot instead
        # (robot.cpp:957) — the two disagree. Using the header default, which is
        # the documented contract. Confirm before relying on acceleration
        # scaling for a force-controlled approach.
        oacc = 100.0
        # velAccParamMode 0 = percentage (the units every other field uses).
        vel_acc_param_mode = 0
        blend_mode = 0      # 0 = inner-cut transition
        search = 0          # 0 = no wire-seek

        params: list[float] = []
        params += list(command.target_joints.as_tuple())      # 0..5
        params += list(command.target_pose.as_tuple())        # 6..11
        params += [float(command.tool), float(command.user)]  # 12,13
        params += [float(command.vel), float(command.acc), float(command.ovl)]  # 14..16
        params += [float(command.blend), float(blend_mode)]   # 17,18
        params += [float(v) for v in command.exaxis]          # 19..22
        params += [float(search), float(command.offset_flag)] # 23,24
        params += list(command.offset_pose.as_tuple())        # 25..30
        params += [float(oacc), float(vel_acc_param_mode)]    # 31,32

        assert len(params) == 33, f"MoveL expects 33 params, built {len(params)}"
        return [params]

    def _build_move_j_params(self, command: MotionCommand) -> list:
        """Build the XML-RPC parameter array for "MoveJ".

        Layout transcribed from the installed SDK, robot.cpp:693-720
        (``FRRobot::MoveJ(JointPos*, DescPose*, ...)``). Unlike MoveL, MoveJ
        uses 11 top-level parameters with nested arrays:

            [0]  [j1..j6]                 (deg)
            [1]  [x, y, z, rx, ry, rz]    (mm, deg)
            [2]  tool
            [3]  user
            [4]  vel       (%)
            [5]  acc       (%)   SDK: "not open for now"
            [6]  ovl       (%)
            [7]  [e0, e1, e2, e3]         (mm)
            [8]  blendT    (-1.0 = blocking; else 0..500 ms)
            [9]  offset_flag
            [10] [ox, oy, oz, orx, ory, orz]

        Note MoveJ's blend argument is a TIME in ms, whereas MoveL's blendR is a
        RADIUS in mm. Both use -1.0 for "move to position (blocking)", which is
        what MotionCommand.blend defaults to.
        """
        if command.kind != "MoveJ":
            raise ValueError(f"_build_move_j_params called with kind={command.kind!r}")
        if command.target_joints is None:
            raise ValueError("MoveJ requires a joint-space target")

        return [
            list(command.target_joints.as_tuple()),   # 0
            list(command.target_pose.as_tuple()),     # 1
            int(command.tool),                        # 2
            int(command.user),                        # 3
            float(command.vel),                       # 4
            float(command.acc),                       # 5
            float(command.ovl),                       # 6
            [float(v) for v in command.exaxis],       # 7
            float(command.blend),                     # 8
            int(command.offset_flag),                 # 9
            list(command.offset_pose.as_tuple()),     # 10
        ]
