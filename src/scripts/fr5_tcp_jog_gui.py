#!/usr/bin/env python3
"""
FR5 TCP Jog — a standalone GUI for jogging the Fairino FR5 end-effector.

Controls the TCP (tool centre point) along X / Y / Z and about RX / RY / RZ,
with a live speed control and a live pose readout.

No SDK install required. The FR5 controller speaks two protocols we use here:

  * port 20003 — a plain XML-RPC server (this is what libfairino wraps).
                 We call StartJOG / ImmStopJOG / RobotEnable / Mode / SetSpeed
                 straight from Python's stdlib xmlrpc.client.
  * port 20004 — a binary real-time state stream, one packet per cycle,
                 framed 0x5A5A. We parse the TCP pose and joint angles out of it.

Networking: see FR5_network_connection_notes.md. The short version is that the
PC must be plugged into the RJ45 on the yellow E-stop button box (or have the
Option B host route in place), and the robot lives at 192.168.58.2.

Usage:
    python3 fr5_tcp_jog_gui.py
    python3 fr5_tcp_jog_gui.py --ip 192.168.58.2
"""

from __future__ import annotations

import argparse
import queue
import socket
import struct
import threading
import time
import tkinter as tk
import xmlrpc.client
from tkinter import ttk

# --------------------------------------------------------------------------
# Protocol constants (taken from libfairino: robot.cpp / robot_types.h)
# --------------------------------------------------------------------------

DEFAULT_ROBOT_IP = "192.168.58.2"
RPC_PORT = 20003          # XML-RPC command server
RT_PORT = 20004           # real-time state stream
RPC_TIMEOUT_S = 3.0

# StartJOG "ref" — which frame the jog is expressed in.
FRAME_JOINT = 0
FRAME_BASE = 2
FRAME_TOOL = 4
FRAME_WOBJ = 8

# StopJOG takes a *different* code than StartJOG for the same frame.
STOP_REF_FOR = {FRAME_JOINT: 1, FRAME_BASE: 3, FRAME_TOOL: 5, FRAME_WOBJ: 9}

FRAME_CHOICES = [
    ("Base frame", FRAME_BASE),
    ("Tool frame", FRAME_TOOL),
    ("Workpiece frame", FRAME_WOBJ),
]

# StartJOG "nb" — axis index. 1-3 translate, 4-6 rotate about the fixed axes.
AXIS_X, AXIS_Y, AXIS_Z = 1, 2, 3
AXIS_RX, AXIS_RY, AXIS_RZ = 4, 5, 6

DIR_NEG, DIR_POS = 0, 1

# How often we re-issue StartJOG while a button is held. Each StartJOG runs for
# at most `max_dis`, so re-issuing is what turns it into continuous motion.
JOG_REFRESH_HZ = 10.0

# Real-time packet layout. The struct is #pragma pack(1), so these are exact
# byte offsets from the start of the frame.
RT_HEADER = struct.Struct("<HBH")   # frame_head, frame_cnt, data_len
OFF_PROGRAM_STATE = 5               # uint8
OFF_ROBOT_STATE = 6                 # uint8
OFF_MAIN_CODE = 7                   # int32
OFF_SUB_CODE = 11                   # int32
OFF_ROBOT_MODE = 15                 # uint8
OFF_JT_CUR_POS = 16                 # double[6], deg
OFF_TL_CUR_POS = 64                 # double[6], mm + deg
RT_MIN_USEFUL_LEN = OFF_TL_CUR_POS + 48
RT_MAX_FRAME = 4096

ROBOT_STATE_NAMES = {1: "stopped", 2: "running", 3: "paused", 4: "drag-teach"}

# Error codes worth naming; anything else is reported numerically.
ERROR_NAMES = {
    -4: "XML-RPC command failed",
    -3: "XML-RPC communication failed",
    -2: "network communication error",
    -1: "other error",
    3: "wrong number of parameters",
    4: "parameter out of range",
    14: "instruction execution failed",
    18: "a program is already running",
    25: "computation failed",
    28: "inverse kinematics failed",
    29: "joint value out of limit",
    30: "non-resettable fault — power-cycle the control box",
    38: "singular pose",
    99: "safety stop triggered",
    112: "target pose unreachable",
}


def describe_error(code: int) -> str:
    if code == 0:
        return "ok"
    name = ERROR_NAMES.get(code)
    return f"error {code} ({name})" if name else f"error {code}"


# --------------------------------------------------------------------------
# XML-RPC command channel
# --------------------------------------------------------------------------


class _TimeoutTransport(xmlrpc.client.Transport):
    """Transport that bounds every call, so a dead robot can't hang the GUI."""

    def __init__(self, timeout: float) -> None:
        super().__init__()
        self._timeout = timeout

    def make_connection(self, host):
        conn = super().make_connection(host)
        conn.timeout = self._timeout
        return conn


class FR5Commands:
    """Thin, thread-safe wrapper over the FR5's XML-RPC interface."""

    def __init__(self, ip: str, timeout: float = RPC_TIMEOUT_S) -> None:
        self.ip = ip
        self._lock = threading.Lock()
        self._proxy = xmlrpc.client.ServerProxy(
            f"http://{ip}:{RPC_PORT}/RPC2",
            transport=_TimeoutTransport(timeout),
            allow_none=True,
        )

    def _call(self, method: str, *args) -> int:
        with self._lock:
            result = getattr(self._proxy, method)(*args)
        try:
            return int(result)
        except (TypeError, ValueError):
            return 0

    # -- lifecycle ---------------------------------------------------------
    def get_sdk_version(self) -> int:
        # Cheap round-trip used purely to prove the RPC server is alive.
        return self._call("GetSDKVersion")

    def enable(self, on: bool) -> int:
        return self._call("RobotEnable", 1 if on else 0)

    def set_mode(self, manual: bool) -> int:
        """Mode(1) = manual, Mode(0) = auto. Jogging wants manual."""
        return self._call("Mode", 1 if manual else 0)

    def set_speed(self, percent: int) -> int:
        return self._call("SetSpeed", int(percent))

    # -- motion ------------------------------------------------------------
    def start_jog(
        self, ref: int, axis: int, direction: int, vel: float, acc: float, max_dis: float
    ) -> int:
        return self._call(
            "StartJOG", int(ref), int(axis), int(direction),
            float(vel), float(acc), float(max_dis),
        )

    def stop_jog(self, ref: int) -> int:
        """Decelerated stop for one frame."""
        return self._call("StopJOG", int(STOP_REF_FOR.get(ref, 3)))

    def imm_stop_jog(self) -> int:
        """Immediate stop of any jog, whatever frame it was started in."""
        return self._call("ImmStopJOG")

    def close(self) -> None:
        try:
            with self._lock:
                self._proxy("close")()
        except Exception:
            pass


# --------------------------------------------------------------------------
# Real-time state stream (port 20004)
# --------------------------------------------------------------------------


class RealtimeState:
    """Background reader for the FR5's 20004 state stream.

    Runs until stopped, reconnecting on its own. All published values are
    plain tuples/ints swapped in atomically, so the GUI can read them without
    locking.
    """

    def __init__(self, ip: str) -> None:
        self.ip = ip
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

        self.connected = False
        self.last_update = 0.0
        self.tcp_pose: tuple[float, ...] | None = None
        self.joints: tuple[float, ...] | None = None
        self.robot_state = 0
        self.robot_mode = 0
        self.main_code = 0
        self.sub_code = 0

    def start(self) -> None:
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None
        self.connected = False

    @property
    def is_fresh(self) -> bool:
        return self.connected and (time.monotonic() - self.last_update) < 1.5

    def _run(self) -> None:
        while not self._stop.is_set():
            sock = None
            try:
                sock = socket.create_connection((self.ip, RT_PORT), timeout=3.0)
                sock.settimeout(1.0)
                self.connected = True
                buf = bytearray()
                while not self._stop.is_set():
                    try:
                        chunk = sock.recv(8192)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    buf += chunk
                    self._consume(buf)
                    if len(buf) > 4 * RT_MAX_FRAME:  # resync guard
                        del buf[:-RT_MAX_FRAME]
            except OSError:
                pass
            finally:
                self.connected = False
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass
            if not self._stop.is_set():
                self._stop.wait(1.0)

    def _consume(self, buf: bytearray) -> None:
        while True:
            idx = buf.find(b"\x5a\x5a")
            if idx < 0:
                # Keep the last byte: it might be the first half of a header.
                if len(buf) > 1:
                    del buf[: len(buf) - 1]
                return
            if idx:
                del buf[:idx]
            if len(buf) < RT_HEADER.size:
                return
            _, _cnt, data_len = RT_HEADER.unpack_from(buf, 0)
            total = 5 + data_len + 2  # header + payload + uint16 checksum
            if data_len <= 0 or total > RT_MAX_FRAME:
                del buf[:2]  # bogus header, keep hunting
                continue
            if len(buf) < total:
                return
            frame = bytes(buf[:total])
            del buf[:total]
            if len(frame) >= RT_MIN_USEFUL_LEN:
                self._parse(frame)

    def _parse(self, frame: bytes) -> None:
        try:
            joints = struct.unpack_from("<6d", frame, OFF_JT_CUR_POS)
            pose = struct.unpack_from("<6d", frame, OFF_TL_CUR_POS)
            self.robot_state = frame[OFF_ROBOT_STATE]
            self.robot_mode = frame[OFF_ROBOT_MODE]
            self.main_code = struct.unpack_from("<i", frame, OFF_MAIN_CODE)[0]
            self.sub_code = struct.unpack_from("<i", frame, OFF_SUB_CODE)[0]
        except struct.error:
            return
        self.joints = joints
        self.tcp_pose = pose
        self.last_update = time.monotonic()


# --------------------------------------------------------------------------
# Jog engine
# --------------------------------------------------------------------------


class JogEngine:
    """Turns 'a button is held' into a stream of StartJOG calls.

    Owns its own thread so the Tk main loop never blocks on the network. Only
    one axis jogs at a time — pressing a second button takes over from the
    first, which matches how a teach pendant behaves.
    """

    def __init__(self, on_error) -> None:
        self._cmds: FR5Commands | None = None
        self._on_error = on_error
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._active: tuple[int, int] | None = None   # (axis, direction)
        self._needs_stop = False
        self._last_error: str | None = None

        self.frame = FRAME_BASE
        self.velocity = 20.0
        self.acceleration = 50.0
        self.max_distance = 20.0

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def attach(self, cmds: FR5Commands | None) -> None:
        with self._lock:
            self._cmds = cmds
            self._active = None
            self._last_error = None
        self._wake.set()

    @property
    def active_axis(self) -> tuple[int, int] | None:
        return self._active

    def press(self, axis: int, direction: int) -> None:
        with self._lock:
            if self._cmds is None:
                return
            self._active = (axis, direction)
        self._wake.set()

    def release(self, axis: int, direction: int) -> None:
        with self._lock:
            if self._active == (axis, direction):
                self._active = None
                self._needs_stop = True
        self._wake.set()

    def release_all(self) -> None:
        with self._lock:
            if self._active is not None:
                self._needs_stop = True
            self._active = None
        self._wake.set()

    def shutdown(self) -> None:
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=2.0)

    def _report(self, message: str | None) -> None:
        """Log only on transitions, so a persistent fault can't spam the log."""
        if message != self._last_error:
            self._last_error = message
            if message:
                self._on_error(message)

    def _run(self) -> None:
        period = 1.0 / JOG_REFRESH_HZ
        while not self._stop.is_set():
            with self._lock:
                cmds = self._cmds
                active = self._active
                needs_stop = self._needs_stop
                self._needs_stop = False
                frame, vel = self.frame, self.velocity
                acc, max_dis = self.acceleration, self.max_distance

            if cmds is None:
                self._wake.wait(0.2)
                self._wake.clear()
                continue

            if needs_stop:
                try:
                    cmds.imm_stop_jog()
                except Exception as exc:
                    self._report(f"stop jog failed: {exc}")

            if active is None:
                self._wake.wait(0.2)
                self._wake.clear()
                continue

            axis, direction = active
            try:
                code = cmds.start_jog(frame, axis, direction, vel, acc, max_dis)
                self._report(None if code == 0 else f"jog rejected: {describe_error(code)}")
            except Exception as exc:
                self._report(f"jog failed: {exc}")
                time.sleep(0.3)
                continue

            self._wake.wait(period)
            self._wake.clear()

        # Best effort: never leave the arm moving when the app goes away.
        with self._lock:
            cmds = self._cmds
        if cmds is not None:
            try:
                cmds.imm_stop_jog()
            except Exception:
                pass


# --------------------------------------------------------------------------
# GUI
# --------------------------------------------------------------------------

BG = "#1e1f26"
PANEL = "#282a36"
FG = "#e6e6ec"
MUTED = "#9a9ab0"
ACCENT = "#6ea8fe"

# Standard robotics colour convention: X red, Y green, Z blue.
AXIS_COLOURS = {
    AXIS_X: "#c8453c", AXIS_Y: "#3f9a52", AXIS_Z: "#3d6fc4",
    AXIS_RX: "#a8564f", AXIS_RY: "#4d7f58", AXIS_RZ: "#4a6394",
}

TRANSLATION_AXES = [(AXIS_X, "X"), (AXIS_Y, "Y"), (AXIS_Z, "Z")]
ROTATION_AXES = [(AXIS_RX, "RX"), (AXIS_RY, "RY"), (AXIS_RZ, "RZ")]

# Keyboard: WASD/QE for translation, IJKL/UO for rotation.
KEY_BINDINGS = {
    "a": (AXIS_X, DIR_NEG), "d": (AXIS_X, DIR_POS),
    "s": (AXIS_Y, DIR_NEG), "w": (AXIS_Y, DIR_POS),
    "q": (AXIS_Z, DIR_NEG), "e": (AXIS_Z, DIR_POS),
    "j": (AXIS_RX, DIR_NEG), "l": (AXIS_RX, DIR_POS),
    "k": (AXIS_RY, DIR_NEG), "i": (AXIS_RY, DIR_POS),
    "u": (AXIS_RZ, DIR_NEG), "o": (AXIS_RZ, DIR_POS),
}


class FR5JogApp:
    def __init__(self, root: tk.Tk, ip: str) -> None:
        self.root = root
        self.cmds: FR5Commands | None = None
        self.rt: RealtimeState | None = None
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.jog = JogEngine(on_error=lambda m: self.events.put(("log", m)))

        self._key_release_jobs: dict[str, str] = {}
        self._jog_buttons: dict[tuple[int, int], tk.Button] = {}
        self._speed_job: str | None = None

        root.title("FR5 TCP Jog")
        root.configure(bg=BG)
        root.geometry("900x960")
        root.minsize(860, 620)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.ip_var = tk.StringVar(value=ip)
        self.status_var = tk.StringVar(value="Disconnected")
        self.frame_var = tk.StringVar(value=FRAME_CHOICES[0][0])
        self.speed_var = tk.DoubleVar(value=20.0)
        self.accel_var = tk.DoubleVar(value=50.0)
        self.step_var = tk.DoubleVar(value=20.0)
        self.auto_init_var = tk.BooleanVar(value=True)
        self.pose_vars = [tk.StringVar(value="—") for _ in range(6)]
        self.joint_vars = [tk.StringVar(value="—") for _ in range(6)]
        self.robot_state_var = tk.StringVar(value="—")

        self._build_style()
        self._build_connection_bar()
        self._build_robot_bar()
        self._build_speed_panel()
        self._build_jog_panel()
        self._build_stop_button()
        self._build_readout()
        self._build_log()

        self._bind_keys()
        self.set_controls_enabled(False)
        self.root.after(80, self._pump_events)
        self.root.after(100, self._refresh_readout)
        self.log(f"Ready. Robot IP {ip}. Connect to begin.")
        self.log("Hold a jog button (or its key) to move; release to stop.")

    # -- chrome ------------------------------------------------------------
    def _build_style(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("Panel.TLabel", background=PANEL, foreground=FG)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
        style.configure("Value.TLabel", background=PANEL, foreground=ACCENT,
                        font=("DejaVu Sans Mono", 13, "bold"))
        style.configure("Head.TLabel", background=BG, foreground=FG,
                        font=("DejaVu Sans", 11, "bold"))
        style.configure("TCheckbutton", background=BG, foreground=FG)
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("TScale", background=BG)

    def _section(self, parent, title: str | None = None) -> ttk.Frame:
        if title:
            ttk.Label(parent, text=title, style="Head.TLabel").pack(
                anchor="w", padx=14, pady=(8, 1))
        frame = ttk.Frame(parent, style="Panel.TFrame")
        frame.pack(fill="x", padx=12, pady=(0, 4))
        return frame

    def _build_connection_bar(self) -> None:
        bar = self._section(self.root, "Connection")
        inner = ttk.Frame(bar, style="Panel.TFrame")
        inner.pack(fill="x", padx=10, pady=10)

        ttk.Label(inner, text="Robot IP", style="PanelMuted.TLabel").pack(side="left")
        entry = ttk.Entry(inner, textvariable=self.ip_var, width=16)
        entry.pack(side="left", padx=(8, 12))

        self.connect_btn = tk.Button(
            inner, text="Connect", command=self.toggle_connection,
            bg="#3d6fc4", fg="white", activebackground="#4d7fd4",
            relief="flat", padx=18, pady=6, font=("DejaVu Sans", 10, "bold"),
            cursor="hand2",
        )
        self.connect_btn.pack(side="left")

        self.status_dot = tk.Canvas(inner, width=14, height=14, bg=PANEL,
                                    highlightthickness=0)
        self.status_dot.pack(side="left", padx=(18, 6))
        self._dot = self.status_dot.create_oval(2, 2, 12, 12, fill="#c8453c", outline="")
        ttk.Label(inner, textvariable=self.status_var, style="Panel.TLabel").pack(side="left")

    def _build_robot_bar(self) -> None:
        bar = self._section(self.root, "Robot")
        inner = ttk.Frame(bar, style="Panel.TFrame")
        inner.pack(fill="x", padx=10, pady=10)

        self.enable_btn = tk.Button(
            inner, text="Enable", command=lambda: self.async_call("enable", True),
            bg="#3f9a52", fg="white", activebackground="#4faa62", relief="flat",
            padx=16, pady=6, font=("DejaVu Sans", 10, "bold"), cursor="hand2")
        self.enable_btn.pack(side="left")

        self.disable_btn = tk.Button(
            inner, text="Disable", command=lambda: self.async_call("enable", False),
            bg="#5a5c68", fg="white", activebackground="#6a6c78",
            relief="flat", padx=16, pady=6, font=("DejaVu Sans", 10, "bold"),
            cursor="hand2")
        self.disable_btn.pack(side="left", padx=(8, 20))

        ttk.Label(inner, text="Jog frame", style="PanelMuted.TLabel").pack(side="left")
        combo = ttk.Combobox(
            inner, textvariable=self.frame_var, state="readonly", width=18,
            values=[name for name, _ in FRAME_CHOICES])
        combo.pack(side="left", padx=(8, 20))
        combo.bind("<<ComboboxSelected>>", self._on_frame_changed)

        ttk.Checkbutton(
            inner, text="Enable + manual mode on connect",
            variable=self.auto_init_var, style="TCheckbutton").pack(side="left")

        ttk.Label(inner, textvariable=self.robot_state_var,
                  style="PanelMuted.TLabel").pack(side="right")

    def _build_speed_panel(self) -> None:
        bar = self._section(self.root, "Motion")
        inner = ttk.Frame(bar, style="Panel.TFrame")
        inner.pack(fill="x", padx=10, pady=10)
        inner.columnconfigure(1, weight=1)

        self.speed_label = self._slider_row(
            inner, 0, "Speed", self.speed_var, 1, 100, "%", self._on_speed_changed)
        self.accel_label = self._slider_row(
            inner, 1, "Acceleration", self.accel_var, 1, 100, "%", self._on_accel_changed)
        self.step_label = self._slider_row(
            inner, 2, "Motion step", self.step_var, 1, 100, "mm/deg", self._on_step_changed)

        presets = ttk.Frame(inner, style="Panel.TFrame")
        presets.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(presets, text="Speed presets", style="PanelMuted.TLabel").pack(side="left")
        for value in (5, 10, 25, 50, 100):
            tk.Button(
                presets, text=f"{value}%", command=lambda v=value: self._set_speed(v),
                bg="#3a3c48", fg=FG, activebackground="#4a4c58",
                relief="flat", padx=10, pady=3, cursor="hand2",
            ).pack(side="left", padx=(8, 0))

        ttk.Label(
            inner,
            text="Speed is the jog velocity as a percentage of the robot's maximum. "
                 "Start low — 5–10% — until you trust the workspace.",
            style="PanelMuted.TLabel", wraplength=780, justify="left",
        ).grid(row=4, column=0, columnspan=3, sticky="w", pady=(6, 0))

    def _slider_row(self, parent, row, label, var, lo, hi, unit, callback):
        ttk.Label(parent, text=label, style="Panel.TLabel", width=13).grid(
            row=row, column=0, sticky="w", pady=4)
        scale = ttk.Scale(parent, from_=lo, to=hi, variable=var, orient="horizontal",
                          command=callback)
        scale.grid(row=row, column=1, sticky="ew", padx=10, pady=2)
        value_label = ttk.Label(parent, text=f"{var.get():.0f} {unit}",
                                style="Value.TLabel", width=11, anchor="e")
        value_label.grid(row=row, column=2, sticky="e", pady=2)
        return value_label, unit

    def _build_jog_panel(self) -> None:
        ttk.Label(self.root, text="Jog TCP", style="Head.TLabel").pack(
            anchor="w", padx=14, pady=(8, 1))
        wrapper = ttk.Frame(self.root, style="TFrame")
        wrapper.pack(fill="x", padx=12)
        wrapper.columnconfigure(0, weight=1)
        wrapper.columnconfigure(1, weight=1)

        self._build_jog_group(
            wrapper, 0, "Translation  (mm)", TRANSLATION_AXES,
            ["A / D", "S / W", "Q / E"])
        self._build_jog_group(
            wrapper, 1, "Rotation  (deg)", ROTATION_AXES,
            ["J / L", "K / I", "U / O"])

    def _build_jog_group(self, parent, column, title, axes, keys) -> None:
        group = ttk.Frame(parent, style="Panel.TFrame")
        group.grid(row=0, column=column, sticky="nsew",
                   padx=(0, 6) if column == 0 else (6, 0))
        group.columnconfigure(0, weight=1)
        group.columnconfigure(2, weight=1)

        ttk.Label(group, text=title, style="Panel.TLabel",
                  font=("DejaVu Sans", 10, "bold")).grid(
            row=0, column=0, columnspan=3, pady=(10, 6))

        for row, ((axis, name), key_hint) in enumerate(zip(axes, keys), start=1):
            colour = AXIS_COLOURS[axis]
            minus = self._jog_button(group, f"−  {name}", axis, DIR_NEG, colour)
            minus.grid(row=row, column=0, sticky="ew", padx=(10, 4), pady=4)

            centre = ttk.Frame(group, style="Panel.TFrame")
            centre.grid(row=row, column=1, padx=2)
            ttk.Label(centre, text=name, style="Panel.TLabel",
                      font=("DejaVu Sans", 12, "bold")).pack()
            ttk.Label(centre, text=key_hint, style="PanelMuted.TLabel",
                      font=("DejaVu Sans", 8)).pack()

            plus = self._jog_button(group, f"{name}  +", axis, DIR_POS, colour)
            plus.grid(row=row, column=2, sticky="ew", padx=(4, 10), pady=4)

        group.grid_rowconfigure(len(axes) + 1, minsize=8)

    def _jog_button(self, parent, text, axis, direction, colour) -> tk.Button:
        btn = tk.Button(
            parent, text=text, bg=colour, fg="white", activebackground=colour,
            activeforeground="white", relief="flat", font=("DejaVu Sans", 13, "bold"),
            width=9, pady=10, cursor="hand2", takefocus=False,
            disabledforeground="#7a7a8a",
        )
        btn.bind("<ButtonPress-1>", lambda _e: self._press(axis, direction))
        btn.bind("<ButtonRelease-1>", lambda _e: self._release(axis, direction))
        # Sliding off the button counts as letting go.
        btn.bind("<Leave>", lambda _e: self._release(axis, direction))
        self._jog_buttons[(axis, direction)] = btn
        return btn

    def _build_stop_button(self) -> None:
        frame = ttk.Frame(self.root, style="TFrame")
        frame.pack(fill="x", padx=12, pady=(12, 4))
        self.stop_btn = tk.Button(
            frame, text="■   S T O P   (Space / Esc)", command=self.emergency_stop,
            bg="#b8322a", fg="white", activebackground="#d8423a", relief="flat",
            font=("DejaVu Sans", 15, "bold"), pady=11, cursor="hand2", takefocus=False)
        self.stop_btn.pack(fill="x")

    def _build_readout(self) -> None:
        bar = self._section(self.root, "Live state")
        inner = ttk.Frame(bar, style="Panel.TFrame")
        inner.pack(fill="x", padx=10, pady=10)

        ttk.Label(inner, text="TCP pose", style="PanelMuted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4))
        for i, name in enumerate(["X", "Y", "Z", "RX", "RY", "RZ"]):
            cell = ttk.Frame(inner, style="Panel.TFrame")
            cell.grid(row=1, column=i, padx=(0, 14), sticky="w")
            ttk.Label(cell, text=name, style="PanelMuted.TLabel").pack(anchor="w")
            ttk.Label(cell, textvariable=self.pose_vars[i], style="Value.TLabel",
                      width=10, anchor="w").pack(anchor="w")

        ttk.Label(inner, text="Joints (deg)", style="PanelMuted.TLabel").grid(
            row=2, column=0, sticky="w", pady=(8, 2))
        for i in range(6):
            cell = ttk.Frame(inner, style="Panel.TFrame")
            cell.grid(row=3, column=i, padx=(0, 14), sticky="w")
            ttk.Label(cell, text=f"J{i + 1}", style="PanelMuted.TLabel").pack(anchor="w")
            ttk.Label(cell, textvariable=self.joint_vars[i], style="Value.TLabel",
                      width=10, anchor="w").pack(anchor="w")

    def _build_log(self) -> None:
        ttk.Label(self.root, text="Log", style="Head.TLabel").pack(
            anchor="w", padx=14, pady=(8, 1))
        frame = ttk.Frame(self.root, style="Panel.TFrame")
        frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))
        self.log_text = tk.Text(
            frame, height=4, bg=PANEL, fg=MUTED, relief="flat", wrap="word",
            font=("DejaVu Sans Mono", 9), insertbackground=FG)
        self.log_text.pack(side="left", fill="both", expand=True, padx=(8, 0), pady=8)
        scroll = ttk.Scrollbar(frame, command=self.log_text.yview)
        scroll.pack(side="right", fill="y", pady=8, padx=(0, 4))
        self.log_text.configure(yscrollcommand=scroll.set, state="disabled")

    # -- keyboard ----------------------------------------------------------
    def _bind_keys(self) -> None:
        for key in KEY_BINDINGS:
            self.root.bind(f"<KeyPress-{key}>", self._on_key_press)
            self.root.bind(f"<KeyRelease-{key}>", self._on_key_release)
            self.root.bind(f"<KeyPress-{key.upper()}>", self._on_key_press)
            self.root.bind(f"<KeyRelease-{key.upper()}>", self._on_key_release)
        self.root.bind("<space>", lambda _e: self.emergency_stop())
        self.root.bind("<Escape>", lambda _e: self.emergency_stop())
        # Losing focus must never leave the arm running.
        self.root.bind("<FocusOut>", lambda _e: self.jog.release_all())

    def _on_key_press(self, event: tk.Event) -> None:
        key = event.keysym.lower()
        binding = KEY_BINDINGS.get(key)
        if binding is None or self.cmds is None:
            return
        # X11 autorepeat emits release/press pairs; cancel the pending stop.
        job = self._key_release_jobs.pop(key, None)
        if job is not None:
            self.root.after_cancel(job)
        self._press(*binding)

    def _on_key_release(self, event: tk.Event) -> None:
        key = event.keysym.lower()
        binding = KEY_BINDINGS.get(key)
        if binding is None:
            return
        job = self._key_release_jobs.pop(key, None)
        if job is not None:
            self.root.after_cancel(job)
        self._key_release_jobs[key] = self.root.after(
            60, lambda k=key, b=binding: self._key_release_fire(k, b))

    def _key_release_fire(self, key: str, binding: tuple[int, int]) -> None:
        self._key_release_jobs.pop(key, None)
        self._release(*binding)

    # -- jog plumbing ------------------------------------------------------
    def _press(self, axis: int, direction: int) -> None:
        if self.cmds is None:
            return
        self.jog.press(axis, direction)
        btn = self._jog_buttons.get((axis, direction))
        if btn is not None:
            btn.configure(relief="sunken")

    def _release(self, axis: int, direction: int) -> None:
        self.jog.release(axis, direction)
        btn = self._jog_buttons.get((axis, direction))
        if btn is not None:
            btn.configure(relief="flat")

    def emergency_stop(self) -> None:
        self.jog.release_all()
        for btn in self._jog_buttons.values():
            btn.configure(relief="flat")
        if self.cmds is not None:
            self.async_call("stop")

    # -- settings callbacks ------------------------------------------------
    def _on_frame_changed(self, _event=None) -> None:
        name = self.frame_var.get()
        for label, value in FRAME_CHOICES:
            if label == name:
                self.jog.frame = value
                self.log(f"Jog frame set to {label}.")
                return

    def _set_speed(self, value: float) -> None:
        self.speed_var.set(value)
        self._on_speed_changed(value)

    def _on_speed_changed(self, value) -> None:
        speed = float(value)
        self.jog.velocity = speed
        self.speed_label[0].configure(text=f"{speed:.0f} {self.speed_label[1]}")
        # Keep the controller's global override in step, but debounce it —
        # dragging a slider must not fire hundreds of RPCs.
        if self._speed_job is not None:
            self.root.after_cancel(self._speed_job)
        self._speed_job = self.root.after(250, self._push_speed)

    def _push_speed(self) -> None:
        self._speed_job = None
        if self.cmds is not None:
            self.async_call("set_speed", int(self.speed_var.get()), quiet=True)

    def _on_accel_changed(self, value) -> None:
        accel = float(value)
        self.jog.acceleration = accel
        self.accel_label[0].configure(text=f"{accel:.0f} {self.accel_label[1]}")

    def _on_step_changed(self, value) -> None:
        step = float(value)
        self.jog.max_distance = step
        self.step_label[0].configure(text=f"{step:.0f} {self.step_label[1]}")

    # -- connection --------------------------------------------------------
    def toggle_connection(self) -> None:
        if self.cmds is None:
            self.connect()
        else:
            self.disconnect()

    def connect(self) -> None:
        ip = self.ip_var.get().strip()
        if not ip:
            self.log("Enter a robot IP first.")
            return
        self.connect_btn.configure(state="disabled", text="Connecting…")
        self.status_var.set(f"Connecting to {ip}…")
        threading.Thread(target=self._connect_worker, args=(ip,), daemon=True).start()

    def _connect_worker(self, ip: str) -> None:
        try:
            cmds = FR5Commands(ip)
            cmds.get_sdk_version()  # proves the RPC server answered
        except Exception as exc:
            self.events.put(("connect_failed", f"{type(exc).__name__}: {exc}"))
            return

        messages = []
        if self.auto_init_var.get():
            for label, fn in (
                ("RobotEnable(1)", lambda: cmds.enable(True)),
                ("Mode(1) manual", lambda: cmds.set_mode(True)),
                ("SetSpeed", lambda: cmds.set_speed(int(self.speed_var.get()))),
            ):
                try:
                    code = fn()
                    messages.append(f"{label} → {describe_error(code)}")
                except Exception as exc:
                    messages.append(f"{label} → failed: {exc}")

        rt = RealtimeState(ip)
        rt.start()
        self.events.put(("connected", (cmds, rt, messages)))

    def disconnect(self) -> None:
        self.jog.release_all()
        time.sleep(0.15)  # let the engine push its final ImmStopJOG
        self.jog.attach(None)
        if self.rt is not None:
            self.rt.stop()
            self.rt = None
        if self.cmds is not None:
            try:
                self.cmds.imm_stop_jog()
            except Exception:
                pass
            self.cmds.close()
            self.cmds = None
        self.set_controls_enabled(False)
        self.connect_btn.configure(text="Connect", state="normal", bg="#3d6fc4")
        self.status_var.set("Disconnected")
        self.status_dot.itemconfigure(self._dot, fill="#c8453c")
        for var in self.pose_vars + self.joint_vars:
            var.set("—")
        self.robot_state_var.set("—")
        self.log("Disconnected.")

    def async_call(self, action: str, *args, quiet: bool = False) -> None:
        cmds = self.cmds
        if cmds is None:
            return

        def worker() -> None:
            try:
                if action == "enable":
                    code = cmds.enable(bool(args[0]))
                    label = "Enable" if args[0] else "Disable"
                elif action == "set_speed":
                    code = cmds.set_speed(int(args[0]))
                    label = f"SetSpeed({int(args[0])})"
                elif action == "stop":
                    code = cmds.imm_stop_jog()
                    label = "STOP"
                else:
                    return
            except Exception as exc:
                self.events.put(("log", f"{action} failed: {exc}"))
                return
            if not quiet or code != 0:
                self.events.put(("log", f"{label} → {describe_error(code)}"))

        threading.Thread(target=worker, daemon=True).start()

    def set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for btn in self._jog_buttons.values():
            btn.configure(state=state)
        self.enable_btn.configure(state=state)
        self.disable_btn.configure(state=state)

    # -- event pump / refresh ---------------------------------------------
    def _pump_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self.log(str(payload))
                elif kind == "connected":
                    cmds, rt, messages = payload
                    self.cmds = cmds
                    self.rt = rt
                    self.jog.attach(cmds)
                    self.set_controls_enabled(True)
                    self.connect_btn.configure(
                        text="Disconnect", state="normal", bg="#5a5c68")
                    self.status_var.set(f"Connected to {cmds.ip}")
                    self.status_dot.itemconfigure(self._dot, fill="#3f9a52")
                    self.log(f"Connected to {cmds.ip}:{RPC_PORT}.")
                    for message in messages:
                        self.log(f"  {message}")
                    self.root.focus_set()
                elif kind == "connect_failed":
                    self.connect_btn.configure(state="normal", text="Connect")
                    self.status_var.set("Connection failed")
                    self.status_dot.itemconfigure(self._dot, fill="#c8453c")
                    self.log(f"Connection failed: {payload}")
                    self.log(
                        "Check the cable is in the RJ45 on the yellow E-stop button "
                        "box (see FR5_network_connection_notes.md), then: "
                        f"ping {self.ip_var.get().strip()}")
        except queue.Empty:
            pass
        self.root.after(80, self._pump_events)

    def _refresh_readout(self) -> None:
        rt = self.rt
        if rt is not None and rt.is_fresh:
            if rt.tcp_pose is not None:
                for i, value in enumerate(rt.tcp_pose):
                    self.pose_vars[i].set(f"{value:8.2f}")
            if rt.joints is not None:
                for i, value in enumerate(rt.joints):
                    self.joint_vars[i].set(f"{value:8.2f}")
            state = ROBOT_STATE_NAMES.get(rt.robot_state, f"state {rt.robot_state}")
            mode = "manual" if rt.robot_mode == 1 else "auto"
            fault = "" if rt.main_code == 0 else f"  ·  fault {rt.main_code}/{rt.sub_code}"
            self.robot_state_var.set(f"{state}  ·  {mode}{fault}")
        elif self.cmds is not None:
            self.robot_state_var.set("waiting for state stream…")
        self.root.after(100, self._refresh_readout)

    def log(self, message: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{stamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def on_close(self) -> None:
        try:
            self.jog.release_all()
            time.sleep(0.15)
            self.jog.shutdown()
            if self.rt is not None:
                self.rt.stop()
            if self.cmds is not None:
                try:
                    self.cmds.imm_stop_jog()
                except Exception:
                    pass
                self.cmds.close()
        finally:
            self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description="Jog the Fairino FR5 TCP from a GUI.")
    parser.add_argument("--ip", default=DEFAULT_ROBOT_IP,
                        help=f"robot controller IP (default {DEFAULT_ROBOT_IP})")
    args = parser.parse_args()

    root = tk.Tk()
    FR5JogApp(root, args.ip)
    root.mainloop()


if __name__ == "__main__":
    main()
