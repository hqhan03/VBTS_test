"""
vbts_platform — automation for vision-based tactile sensor experiments on an
FAIRINO FR5.

Importing this package performs no I/O and opens no sockets.

Layout:
    fr5_io           low-level FR5 transport, copied verbatim from the verified
                     fr5_tcp_jog_gui.py (which stays in place, unmodified)
    types            RobotPose / JointState / RobotState / MotionCommand
    robot_interface  the only class experiment protocols should use

Defaults are safe: RobotInterface() is dry-run and cannot move the robot.
"""

from .types import JointState, MotionCommand, RobotPose, RobotState
from .robot_interface import (
    MotionNotAllowedError,
    NotConnectedError,
    RobotInterface,
    RobotInterfaceError,
)

__all__ = [
    "JointState",
    "MotionCommand",
    "RobotPose",
    "RobotState",
    "RobotInterface",
    "RobotInterfaceError",
    "MotionNotAllowedError",
    "NotConnectedError",
]
