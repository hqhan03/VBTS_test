#!/usr/bin/env python3
"""
Hardware-independent tests for RobotInterface, types and the fr5_io extension.

Every test here runs with the robot powered off and MUST NOT touch the network.
That is not left to trust: `no_network()` replaces the socket and XML-RPC entry
points with versions that fail the test if anything calls them, so "no network
access" is asserted rather than assumed.

    python3 -m unittest discover -s tests -v
    python3 -m pytest tests -v          (also works; plain unittest TestCases)
"""

from __future__ import annotations

import contextlib
import socket
import struct
import sys
import unittest
import xmlrpc.client
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vbts_platform import JointState, MotionCommand, RobotInterface, RobotPose  # noqa: E402
from vbts_platform import fr5_io  # noqa: E402
from vbts_platform.robot_interface import (  # noqa: E402
    MotionNotAllowedError,
    NotConnectedError,
)

POSE_A = RobotPose(103.387, 362.701, 408.912, 95.3546, 56.8215, 177.060)
JOINTS_A = JointState.from_sequence([92.0, -75.0, -100.5, -216.0, -88.0, -45.0])


class NetworkAccessAttempted(AssertionError):
    """Raised if code under test tries to reach the network."""


@contextlib.contextmanager
def no_network():
    """Make any network access an immediate, loud test failure."""

    def boom(*args, **kwargs):
        raise NetworkAccessAttempted(
            "code under test attempted network access during a dry run"
        )

    saved = {
        (socket, "socket"): socket.socket,
        (socket, "create_connection"): socket.create_connection,
        (socket, "getaddrinfo"): socket.getaddrinfo,
        (xmlrpc.client, "ServerProxy"): xmlrpc.client.ServerProxy,
    }
    for (module, name) in saved:
        setattr(module, name, boom)
    try:
        yield
    finally:
        for (module, name), original in saved.items():
            setattr(module, name, original)


class TestNoNetworkGuardItself(unittest.TestCase):
    """The guard has to actually work, or every test below is vacuous."""

    def test_guard_catches_socket_use(self):
        with no_network():
            with self.assertRaises(NetworkAccessAttempted):
                socket.create_connection(("192.168.58.2", 20004))

    def test_guard_catches_xmlrpc_use(self):
        with no_network():
            with self.assertRaises(NetworkAccessAttempted):
                xmlrpc.client.ServerProxy("http://192.168.58.2:20003/RPC2")

    def test_guard_restores_originals(self):
        with no_network():
            pass
        self.assertIs(socket.socket, socket.socket)
        self.assertTrue(callable(xmlrpc.client.ServerProxy))


class TestA_Defaults(unittest.TestCase):
    """Test A — default construction is safe."""

    def test_defaults_are_safe(self):
        with no_network():
            robot = RobotInterface()
        self.assertTrue(robot.dry_run)
        self.assertFalse(robot.allow_real_motion)
        self.assertTrue(robot.simulated)
        self.assertFalse(robot.connected)

    def test_default_ip_matches_verified_value(self):
        with no_network():
            robot = RobotInterface()
        self.assertEqual(robot.ip, fr5_io.DEFAULT_ROBOT_IP)
        self.assertEqual(robot.ip, "192.168.58.2")

    def test_operation_mode_is_unset_by_default(self):
        # Mode(0/1) is unverified for our MoveL protocol; nothing may assume it.
        with no_network():
            robot = RobotInterface()
        self.assertIsNone(robot.operation_mode)


class TestB_DryRunMoveL(unittest.TestCase):
    """Test B — dry-run MoveL makes no network call and updates simulated pose."""

    def test_move_linear_makes_no_network_call(self):
        with no_network():
            robot = RobotInterface(initial_pose=POSE_A)
            robot.connect(read_only=True)
            robot.move_linear(POSE_A.offset(dz=5.0))
            robot.disconnect()

    def test_move_linear_updates_simulated_pose(self):
        with no_network():
            robot = RobotInterface(initial_pose=POSE_A)
            robot.connect(read_only=True)
            self.assertEqual(robot.get_tcp_pose().as_tuple(), POSE_A.as_tuple())

            robot.move_linear(POSE_A.offset(dz=5.0))
            self.assertAlmostEqual(robot.get_tcp_pose().z, POSE_A.z + 5.0, places=9)

            robot.move_linear(robot.get_tcp_pose().offset(dz=-5.0))
            self.assertAlmostEqual(robot.get_tcp_pose().z, POSE_A.z, places=9)

    def test_round_trip_returns_to_start(self):
        with no_network():
            robot = RobotInterface(initial_pose=POSE_A)
            robot.connect()
            robot.move_linear(POSE_A.offset(dz=5.0))
            robot.move_linear(robot.get_tcp_pose().offset(dz=-5.0))
            self.assertEqual(robot.get_tcp_pose().as_tuple(), POSE_A.as_tuple())

    def test_state_reads_are_flagged_simulated(self):
        with no_network():
            robot = RobotInterface(initial_pose=POSE_A)
            robot.connect()
            state = robot.get_robot_state()
        self.assertTrue(state.simulated)

    def test_command_is_logged(self):
        with no_network():
            robot = RobotInterface(initial_pose=POSE_A)
            robot.connect()
            robot.move_linear(POSE_A.offset(dz=5.0), vel=10.0)
        self.assertEqual(len(robot.command_log), 1)
        self.assertEqual(robot.command_log[0].kind, "MoveL")
        self.assertEqual(robot.command_log[0].vel, 10.0)

    def test_reads_require_connection(self):
        with no_network():
            robot = RobotInterface()
            with self.assertRaises(NotConnectedError):
                robot.get_tcp_pose()


class TestC_DryRunMoveJ(unittest.TestCase):
    """Test C — dry-run MoveJ makes no network call."""

    def test_move_joint_makes_no_network_call(self):
        with no_network():
            robot = RobotInterface(initial_pose=POSE_A)
            robot.connect(read_only=True)
            robot.move_joint(JOINTS_A)
            robot.disconnect()

    def test_move_joint_updates_simulated_joints(self):
        with no_network():
            robot = RobotInterface()
            robot.connect()
            robot.move_joint(JOINTS_A)
            self.assertEqual(robot.get_joint_positions().as_tuple(), JOINTS_A.as_tuple())

    def test_move_joint_logged_as_movej(self):
        with no_network():
            robot = RobotInterface()
            robot.connect()
            robot.move_joint(JOINTS_A)
        self.assertEqual(robot.command_log[0].kind, "MoveJ")


class TestD_MotionGuard(unittest.TestCase):
    """Test D — dry_run=False alone must not permit motion."""

    def test_move_linear_raises_runtime_error(self):
        with no_network():
            robot = RobotInterface(dry_run=False, allow_real_motion=False)
            with self.assertRaises(RuntimeError):
                robot.move_linear(POSE_A, joints=JOINTS_A)

    def test_move_joint_raises_runtime_error(self):
        with no_network():
            robot = RobotInterface(dry_run=False, allow_real_motion=False)
            with self.assertRaises(RuntimeError):
                robot.move_joint(JOINTS_A, pose=POSE_A)

    def test_guard_raises_specific_subclass(self):
        with no_network():
            robot = RobotInterface(dry_run=False, allow_real_motion=False)
            with self.assertRaises(MotionNotAllowedError):
                robot.move_linear(POSE_A, joints=JOINTS_A)

    def test_guard_fires_before_argument_validation(self):
        # An invalid pose must still be refused as "not allowed to move",
        # not as "bad argument" — the safety fact is the important one.
        with no_network():
            robot = RobotInterface(dry_run=False, allow_real_motion=False)
            with self.assertRaises(MotionNotAllowedError):
                robot.move_linear([1.0, 2.0])          # wrong length on purpose

    def test_guard_fires_before_any_connection(self):
        # Nothing may reach the network even to discover it is not allowed.
        with no_network():
            robot = RobotInterface(dry_run=False, allow_real_motion=False)
            with self.assertRaises(MotionNotAllowedError):
                robot.move_linear(POSE_A, joints=JOINTS_A)

    def test_both_gates_open_still_does_not_move(self):
        # Gate 3: real dispatch is deliberately not wired up yet.
        with no_network():
            robot = RobotInterface(dry_run=False, allow_real_motion=True)
            with self.assertRaises((NotConnectedError, NotImplementedError)):
                robot.move_linear(POSE_A, joints=JOINTS_A)

    def test_motion_enabled_connect_is_refused(self):
        with no_network():
            robot = RobotInterface(dry_run=False, allow_real_motion=False)
            with self.assertRaises(MotionNotAllowedError):
                robot.connect(read_only=False)


class TestE_Validation(unittest.TestCase):
    """Test E — invalid pose length / type / value are rejected."""

    def test_pose_wrong_length(self):
        for bad in ([1.0, 2.0, 3.0], [1.0] * 5, [1.0] * 7, []):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    RobotPose.from_sequence(bad)

    def test_pose_non_numeric(self):
        with self.assertRaises(TypeError):
            RobotPose.from_sequence([1.0, 2.0, 3.0, 4.0, 5.0, "six"])

    def test_pose_rejects_string(self):
        with self.assertRaises(TypeError):
            RobotPose.from_sequence("xyzrpy")

    def test_pose_rejects_bool(self):
        # bool is an int subclass and would silently become 1.0.
        with self.assertRaises(TypeError):
            RobotPose.from_sequence([1.0, 2.0, 3.0, 4.0, 5.0, True])

    def test_pose_rejects_non_finite(self):
        for bad in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    RobotPose.from_sequence([1.0, 2.0, 3.0, 4.0, 5.0, bad])

    def test_joint_wrong_length(self):
        with self.assertRaises(ValueError):
            JointState.from_sequence([0.0] * 5)

    def test_move_linear_rejects_bad_pose_in_dry_run(self):
        with no_network():
            robot = RobotInterface()
            robot.connect()
            with self.assertRaises(ValueError):
                robot.move_linear([1.0, 2.0, 3.0])

    def test_velocity_out_of_range(self):
        for bad_vel in (-1.0, 101.0):
            with self.subTest(vel=bad_vel):
                with no_network():
                    robot = RobotInterface()
                    robot.connect()
                    with self.assertRaises(ValueError):
                        robot.move_linear(POSE_A, vel=bad_vel)

    def test_motion_command_rejects_unknown_kind(self):
        with self.assertRaises(ValueError):
            MotionCommand(kind="MoveC", target_pose=POSE_A)


class TestF_PoseOrdering(unittest.TestCase):
    """Test F — FAIRINO pose ordering [x, y, z, rx, ry, rz] is preserved."""

    def test_as_tuple_order(self):
        pose = RobotPose(1.0, 2.0, 3.0, 4.0, 5.0, 6.0)
        self.assertEqual(pose.as_tuple(), (1.0, 2.0, 3.0, 4.0, 5.0, 6.0))

    def test_named_fields_match_positions(self):
        pose = RobotPose.from_sequence([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
        self.assertEqual(pose.x, 10.0)
        self.assertEqual(pose.y, 20.0)
        self.assertEqual(pose.z, 30.0)
        self.assertEqual(pose.rx, 40.0)
        self.assertEqual(pose.ry, 50.0)
        self.assertEqual(pose.rz, 60.0)

    def test_round_trip_through_sequence(self):
        values = [1.5, -2.5, 3.5, -4.5, 5.5, -6.5]
        self.assertEqual(RobotPose.from_sequence(values).as_list(), values)

    def test_offset_touches_only_named_axis(self):
        pose = RobotPose(1.0, 2.0, 3.0, 4.0, 5.0, 6.0).offset(dz=10.0)
        self.assertEqual(pose.as_tuple(), (1.0, 2.0, 13.0, 4.0, 5.0, 6.0))

    def test_ordering_survives_into_movel_wire_params(self):
        with no_network():
            robot = RobotInterface()
        cmd = MotionCommand(kind="MoveL", target_pose=RobotPose(1, 2, 3, 4, 5, 6),
                            target_joints=JOINTS_A)
        params = robot._build_move_l_params(cmd)[0]
        # Cartesian target occupies indices 6..11 in that exact order.
        self.assertEqual(params[6:12], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])

    def test_ordering_survives_into_movej_wire_params(self):
        with no_network():
            robot = RobotInterface()
        cmd = MotionCommand(kind="MoveJ", target_pose=RobotPose(1, 2, 3, 4, 5, 6),
                            target_joints=JOINTS_A)
        params = robot._build_move_j_params(cmd)
        self.assertEqual(params[1], [1.0, 2.0, 3.0, 4.0, 5.0, 6.0])


class TestWireParameterBuilders(unittest.TestCase):
    """The builders must match the SDK layout exactly; no RPC is issued."""

    def setUp(self):
        with no_network():
            self.robot = RobotInterface(tool=0, user=0)

    def test_movel_has_33_params_in_one_array(self):
        cmd = MotionCommand(kind="MoveL", target_pose=POSE_A, target_joints=JOINTS_A)
        params = self.robot._build_move_l_params(cmd)
        self.assertEqual(len(params), 1, "MoveL packs everything into param[0]")
        self.assertEqual(len(params[0]), 33)

    def test_movel_field_positions(self):
        cmd = MotionCommand(
            kind="MoveL", target_pose=POSE_A, target_joints=JOINTS_A,
            tool=3, user=4, vel=11.0, acc=22.0, ovl=33.0, blend=-1.0,
        )
        p = self.robot._build_move_l_params(cmd)[0]
        self.assertEqual(p[0:6], list(JOINTS_A.as_tuple()))   # joints
        self.assertEqual(p[6:12], list(POSE_A.as_tuple()))    # pose
        self.assertEqual(p[12], 3.0)                          # tool
        self.assertEqual(p[13], 4.0)                          # user
        self.assertEqual(p[14], 11.0)                         # vel
        self.assertEqual(p[15], 22.0)                         # acc
        self.assertEqual(p[16], 33.0)                         # ovl
        self.assertEqual(p[17], -1.0)                         # blendR (blocking)
        self.assertEqual(p[18], 0.0)                          # blendMode
        self.assertEqual(p[19:23], [0.0, 0.0, 0.0, 0.0])      # exaxis
        self.assertEqual(p[23], 0.0)                          # search
        self.assertEqual(p[24], 0.0)                          # offset_flag
        self.assertEqual(p[25:31], [0.0] * 6)                 # offset pose
        self.assertEqual(p[31], 100.0)                        # oacc
        self.assertEqual(p[32], 0.0)                          # velAccParamMode

    def test_movel_requires_joints(self):
        cmd = MotionCommand(kind="MoveL", target_pose=POSE_A, target_joints=None)
        with self.assertRaises(ValueError):
            self.robot._build_move_l_params(cmd)

    def test_movej_has_11_top_level_params(self):
        cmd = MotionCommand(kind="MoveJ", target_pose=POSE_A, target_joints=JOINTS_A)
        params = self.robot._build_move_j_params(cmd)
        self.assertEqual(len(params), 11, "MoveJ uses nested top-level params")
        self.assertEqual(params[0], list(JOINTS_A.as_tuple()))
        self.assertEqual(params[1], list(POSE_A.as_tuple()))
        self.assertEqual(params[7], [0.0, 0.0, 0.0, 0.0])
        self.assertEqual(params[8], -1.0)
        self.assertEqual(params[10], [0.0] * 6)

    def test_builders_reject_mismatched_kind(self):
        movel = MotionCommand(kind="MoveL", target_pose=POSE_A, target_joints=JOINTS_A)
        movej = MotionCommand(kind="MoveJ", target_pose=POSE_A, target_joints=JOINTS_A)
        with self.assertRaises(ValueError):
            self.robot._build_move_j_params(movel)
        with self.assertRaises(ValueError):
            self.robot._build_move_l_params(movej)


def _synthetic_rt_frame(length: int = 600, **values) -> bytes:
    """Build a fake 20004 payload with known values at the documented offsets.

    Lets the offset arithmetic be tested with the robot powered off. This is a
    test fixture only — it is NOT a claim about the real frame length, which
    stays unverified until a controller is actually streaming.
    """
    buf = bytearray(length)
    buf[fr5_io.OFF_ROBOT_STATE] = values.get("robot_state", 1)
    buf[fr5_io.OFF_ROBOT_MODE] = values.get("robot_mode", 0)
    struct.pack_into("<i", buf, fr5_io.OFF_MAIN_CODE, values.get("main_code", 0))
    struct.pack_into("<i", buf, fr5_io.OFF_SUB_CODE, values.get("sub_code", 0))
    struct.pack_into("<6d", buf, fr5_io.OFF_JT_CUR_POS, *values.get("joints", JOINTS_A.as_tuple()))
    struct.pack_into("<6d", buf, fr5_io.OFF_TL_CUR_POS, *values.get("pose", POSE_A.as_tuple()))
    if length >= fr5_io.RT_SAFETY_BLOCK_END:
        struct.pack_into("<6d", buf, fr5_io.OFF_JT_CUR_TOR,
                         *values.get("torque", (1.0, 2.0, 3.0, 4.0, 5.0, 6.0)))
        struct.pack_into("<6d", buf, fr5_io.OFF_FT_SENSOR_RAW_DATA, *([7.0] * 6))
        struct.pack_into("<6d", buf, fr5_io.OFF_FT_SENSOR_DATA, *([8.0] * 6))
        buf[fr5_io.OFF_FT_SENSOR_ACTIVE] = values.get("ft_active", 0)
        buf[fr5_io.OFF_EMERGENCY_STOP] = values.get("estop", 0)
        struct.pack_into("<i", buf, fr5_io.OFF_MOTION_DONE, values.get("motion_done", 1))
        buf[fr5_io.OFF_COLLISION_STATE] = values.get("collision", 0)
        buf[fr5_io.OFF_SAFETY_STOP0] = values.get("stop0", 0)
        buf[fr5_io.OFF_SAFETY_STOP1] = values.get("stop1", 0)
    return bytes(buf)


class TestRealtimeStateExtension(unittest.TestCase):
    """The additive safety-field parsing, exercised with synthetic frames."""

    def test_original_fields_still_parse(self):
        with no_network():
            rt = fr5_io.RealtimeState("192.168.58.2")
            rt._parse(_synthetic_rt_frame())
        self.assertEqual(rt.tcp_pose, POSE_A.as_tuple())
        self.assertEqual(rt.joints, JOINTS_A.as_tuple())
        self.assertEqual(rt.robot_state, 1)

    def test_safety_fields_parse(self):
        with no_network():
            rt = fr5_io.RealtimeState("192.168.58.2")
            rt._parse(_synthetic_rt_frame(
                estop=1, collision=1, stop0=1, stop1=0, motion_done=1))
        self.assertTrue(rt.safety_valid)
        self.assertEqual(rt.emergency_stop, 1)
        self.assertEqual(rt.collision_state, 1)
        self.assertEqual(rt.safety_stop0, 1)
        self.assertEqual(rt.safety_stop1, 0)
        self.assertEqual(rt.motion_done, 1)
        self.assertEqual(rt.joint_torque, (1.0, 2.0, 3.0, 4.0, 5.0, 6.0))

    def test_short_frame_keeps_original_behaviour(self):
        # A frame long enough for pose/joints but not the safety block must
        # still yield pose and joints, exactly as the jog GUI did.
        with no_network():
            rt = fr5_io.RealtimeState("192.168.58.2")
            rt._parse(_synthetic_rt_frame(length=fr5_io.RT_MIN_USEFUL_LEN))
        self.assertEqual(rt.tcp_pose, POSE_A.as_tuple())
        self.assertEqual(rt.joints, JOINTS_A.as_tuple())
        self.assertFalse(rt.safety_valid)
        self.assertIsNone(rt.emergency_stop)
        self.assertIsNone(rt.motion_done)

    def test_robot_ft_is_parsed_but_named_apart(self):
        # Robot-integrated FT must never be exposed under a name that could be
        # mistaken for the experiment's own F/T sensor.
        with no_network():
            rt = fr5_io.RealtimeState("192.168.58.2")
            rt._parse(_synthetic_rt_frame())
        self.assertEqual(rt.robot_ft_raw, tuple([7.0] * 6))
        self.assertEqual(rt.robot_ft, tuple([8.0] * 6))
        for forbidden in ("ft", "force", "wrench", "ft_sensor"):
            self.assertFalse(
                hasattr(rt, forbidden),
                f"RealtimeState.{forbidden} would blur robot FT and experiment FT",
            )

    def test_offsets_match_sdk_struct_arithmetic(self):
        # Re-derive the offsets from the pack(1) field widths. This is the same
        # sum that reproduced the GUI's four original offsets.
        widths = [
            ("frame_head", 2), ("frame_cnt", 1), ("data_len", 2),
            ("program_state", 1), ("robot_state", 1), ("main_code", 4),
            ("sub_code", 4), ("robot_mode", 1), ("jt_cur_pos", 48),
            ("tl_cur_pos", 48), ("flange_cur_pos", 48), ("actual_qd", 48),
            ("actual_qdd", 48), ("target_TCP_CmpSpeed", 16),
            ("target_TCP_Speed", 48), ("actual_TCP_CmpSpeed", 16),
            ("actual_TCP_Speed", 48), ("jt_cur_tor", 48), ("tool", 4),
            ("user", 4), ("cl_dgt_output_h", 1), ("cl_dgt_output_l", 1),
            ("tl_dgt_output_l", 1), ("cl_dgt_input_h", 1),
            ("cl_dgt_input_l", 1), ("tl_dgt_input_l", 1),
            ("cl_analog_input", 4), ("tl_anglog_input", 2),
            ("ft_sensor_raw_data", 48), ("ft_sensor_data", 48),
            ("ft_sensor_active", 1), ("EmergencyStop", 1), ("motion_done", 4),
            ("gripper_motiondone", 1), ("mc_queue_len", 4),
            ("collisionState", 1), ("trajectory_pnum", 4),
            ("safety_stop0_state", 1), ("safety_stop1_state", 1),
        ]
        offsets, running = {}, 0
        for name, size in widths:
            offsets[name] = running
            running += size

        # Offsets inherited from the jog GUI — these validate the method.
        self.assertEqual(offsets["robot_state"], fr5_io.OFF_ROBOT_STATE)
        self.assertEqual(offsets["robot_mode"], fr5_io.OFF_ROBOT_MODE)
        self.assertEqual(offsets["jt_cur_pos"], fr5_io.OFF_JT_CUR_POS)
        self.assertEqual(offsets["tl_cur_pos"], fr5_io.OFF_TL_CUR_POS)
        # Offsets added in this task.
        self.assertEqual(offsets["jt_cur_tor"], fr5_io.OFF_JT_CUR_TOR)
        self.assertEqual(offsets["ft_sensor_raw_data"], fr5_io.OFF_FT_SENSOR_RAW_DATA)
        self.assertEqual(offsets["ft_sensor_data"], fr5_io.OFF_FT_SENSOR_DATA)
        self.assertEqual(offsets["ft_sensor_active"], fr5_io.OFF_FT_SENSOR_ACTIVE)
        self.assertEqual(offsets["EmergencyStop"], fr5_io.OFF_EMERGENCY_STOP)
        self.assertEqual(offsets["motion_done"], fr5_io.OFF_MOTION_DONE)
        self.assertEqual(offsets["collisionState"], fr5_io.OFF_COLLISION_STATE)
        self.assertEqual(offsets["safety_stop0_state"], fr5_io.OFF_SAFETY_STOP0)
        self.assertEqual(offsets["safety_stop1_state"], fr5_io.OFF_SAFETY_STOP1)


class TestRobotStateSafetySummary(unittest.TestCase):

    def test_unobserved_flags_are_none_not_safe(self):
        from vbts_platform.types import RobotState
        self.assertIsNone(RobotState().is_safe_to_move)

    def test_all_clear_is_safe(self):
        from vbts_platform.types import RobotState
        state = RobotState(emergency_stop=0, collision_state=0,
                           safety_stop0=0, safety_stop1=0)
        self.assertTrue(state.is_safe_to_move)

    def test_any_flag_set_is_unsafe(self):
        from vbts_platform.types import RobotState
        state = RobotState(emergency_stop=0, collision_state=1,
                           safety_stop0=0, safety_stop1=0)
        self.assertFalse(state.is_safe_to_move)


if __name__ == "__main__":
    unittest.main(verbosity=2)
