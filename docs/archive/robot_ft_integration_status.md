# Robot ↔ F/T integration status

As of 2026-08-26.

**The F/T side is finished. The robot side has not yet been contacted, and is
currently blocked by a host network problem, not by anything on the robot.**

Companion documents:
- `docs/ft_robot_frame_integration.md` — what a frame transform will require
- `scripts/robot_readonly_check.py` — the read-only connection check
- `scripts/analyze_ft_robot_frame.py` — frame gap analysis

---

## 1. ATI side — complete

| | |
|---|---|
| Sensor | ATI Mini45 s/n FT29831, SI-145-5 |
| Calibration | `FT29831.cal`, used exactly as supplied |
| Frame | `ATI_sensor_frame`, N and N·m |
| DAQ | NI PCIe-6343 `Dev1`, connector 0, SCB-68A, 9105-IFPS-1 |
| Mapping | SG0→ai0, SG1→ai2, SG2→ai1, SG3→ai3, SG4→ai4, SG5→**ai7** |
| Status | `channel_mapping_confirmed: true`, `all_channels_healthy: true` |

**Validated**: 1.004 kg gives Fz −1.54 % with 0.14 N of lateral; noise floor
σ_Fz ≈ 57 mN, σ_Fx ≈ 15 mN; right-handed frame confirmed independently via the
`Ty = h·Fx` / `Tx = −h·Fy` relation across eight lateral pushes.

**Sign convention** (relative to the operator's position, which still needs
re-expressing against a fixed reference):

| | |
|---|---|
| +Fx | operator's left |
| +Fy | operator's back |
| +Fz | up — compression reads negative |
| +Tz | counter-clockwise from above |

**Known unusable DAQ paths**, recorded in `ft_config.yaml` and blocked by tests:
`Dev1/ai5` (terminals 60/26 — open) and `Dev1/ai6` (couples 2.1 % of its
predecessor). Neither is assigned to a gauge.

---

## 2. Robot side — code ready, hardware not yet contacted

### Communication

| | |
|---|---|
| Protocol | XML-RPC on port **20003** (commands and queries) |
| State | binary stream on port **20004**, `0x5A5A` framed |
| Address | 192.168.58.2 |
| SDK | none needed — XML-RPC method names equal the C++ SDK method names |

`fr5_io.py` carries this verbatim from the verified `fr5_tcp_jog_gui.py`.

### Read-only APIs available

Through `RobotInterface`:

| Method | Source | Returns |
|---|---|---|
| `connect(read_only=True)` | — | opens 20004 + 20003, **no enable, no mode, no speed** |
| `get_tcp_pose()` | 20004 stream | TCP pose in the **robot base frame**, mm/deg |
| `get_joint_positions()` | 20004 stream | six joint angles, deg |
| `get_robot_state()` | 20004 stream | state, mode, error codes, E-stop, collision, safety stops |
| `disconnect()` | — | closes both |

Through XML-RPC query (whitelisted in `robot_readonly_check.py`):
`GetSDKVersion`, `GetActualTCPNum`, `GetActualWObjNum`,
`GetActualToolFlangePose`, `GetToolCoordWithID`, `GetRobotErrorCode`,
`GetRobotCurJointsConfig`, and others — 16 in total, all `Get*`.

Note `GetActualTCPPose` and `GetActualJointPosDegree` are **not** RPC calls in
the SDK: they read the cached 20004 packet (`robot.cpp:4376`, `4138`). So
`RealtimeState` is already their exact equivalent.

### Pose convention

`[x, y, z, rx, ry, rz]`, mm and degrees, **fixed-axis (extrinsic) RPY** —
identical to what this codebase uses on the F/T side, so no unit or angle
conversion is needed once the frames are related.

---

## 3. Current blocker — host network, not the robot

The cable is plugged in and a link is up:

```
enp131s0    carrier=1    operstate=up
```

But `enp131s0` has **no IP address**, and both saved profiles are bound to an
interface that no longer exists:

```
Fairino              connection.interface-name: enp129s0   ← gone
Fairino-buttonbox    connection.interface-name: enp129s0   ← gone
```

The machine renumbered its PCI devices on the 2026-08-25 reboot:
`enp129s0 → enp131s0`, `wlp130s0 → wlp132s0`. The profiles were never rebound,
so neither can activate.

**Consequence, and it is the dangerous part:**

```
ip route get 192.168.58.2
→ 192.168.58.2 via 192.168.0.1 dev wlp132s0
```

The robot's address currently resolves through the **WiFi default gateway** —
the office router. Connecting in this state would send XML-RPC to whatever
answers there. `robot_readonly_check.py` refuses to connect for exactly this
reason and reports the route it found.

`~/Desktop/fr5_net.sh` cannot fix it either: it hard-codes `IFACE=enp129s0`.

### To resolve

Rebind the profile to the current interface, then bring it up:

```bash
nmcli con mod Fairino connection.interface-name enp131s0
nmcli con up Fairino
ip route get 192.168.58.2      # must now show: dev enp131s0
```

`Fairino` is the "cabinet" profile — 192.168.58.80/24 plus 192.168.57.10/24 and
the `192.168.58.2/32 via 192.168.57.2` host route. It is the profile documented
as verified end-to-end in `~/Desktop/FR5_network_connection_notes.md`.

Note the warning in those notes: that `/32` host route beats the `/24` connected
route, so leaving it loaded while the cable is in the button-box jack makes that
jack look dead. Switch the profile whenever the cable moves.

**This is a host network change and has not been made.** It is outside the scope
of "do not change robot configuration", but it modifies saved system profiles,
so it is left for the operator to authorise.

---

## 4. Missing information for TCP calibration

TCP calibration is the bottleneck: nothing on the robot side can be related to
the sensor until the indenter tip is a known point.

| Needed | Status |
|---|---|
| Network path to the robot | **BLOCKED** — see §3 |
| Robot powered and reachable | not yet verified |
| `Mode()` semantics for protocol motion | `operation_mode: null` — resolvable by reading `robot_mode` off the 20004 stream during the read-only connect |
| Indenter physically mounted | not confirmed |
| ~~Ø4 mm steel-ball tip geometry~~ | **OBSOLETE** — the ball design was replaced by a monolithic printed indenter; TCP calibrated 2026-08-31, see `docs/tcp_calibration_history.md` |
| Free tool register id to write into | `default_tool_id: 0` in use; range [0..14] |
| 4-point calibration procedure | SDK functions confirmed present (`robot.h:863, 870, 883`) |

The read-only connection answers two of these for free — reachability and the
`Mode()` question — which is why it comes first.

---

## 5. Next required steps, in order

1. **Fix the network binding** (§3). Nothing proceeds without it.
2. **Run `robot_readonly_check.py --connect`.** Confirms the robot answers,
   captures the current pose, tool id and tool frame, and records `robot_mode`,
   which settles `operation_mode` in `robot_config.yaml`.
3. **Record `operation_mode`** from that observation. This is the last
   unverified item in the robot config.
4. **Mount and measure the indenter**, then run the FR5 4-point TCP
   calibration: `SetTcp4RefPoint(1..4)` → `ComputeTcp4()` → `SetToolCoord()`.
   That is real motion and needs both motion gates opened deliberately.
5. **Establish the sensor↔base transform** — see
   `docs/ft_robot_frame_integration.md` §5. Fit `R` from three axis-aligned
   pushes, then verify on a fourth direction that was not used in the fit.

Steps 1–3 involve no motion. Step 4 is the first time the robot moves, and it
should not be attempted until steps 1–3 have all passed.

---

## 6. Safety design of the read-only check

Three mechanisms, all enforced rather than promised:

1. **Network preflight** — refuses to connect unless the route to the robot
   leaves via a dedicated ethernet interface that is not the default route.
2. **Method whitelist** — every XML-RPC call passes through a proxy that raises
   `PermissionError` unless the method is one of 16 read-only `Get*` queries.
   Verified: `RobotEnable`, `Mode`, `MoveJ`, `MoveL`, `ServoJ`, `SetToolCoord`,
   `SetSpeed`, `ImmStopJOG`, `StartJOG` and `SetDO` are all blocked.
3. **Read-only connect** — `RobotInterface.connect(read_only=True)` deliberately
   omits the `RobotEnable(1) → Mode(1) → SetSpeed(n)` sequence that
   `fr5_tcp_jog_gui.py` runs on connect. Observing must never energise.

The motion gates in `robot_interface.py` are untouched and remain closed:
`dry_run: true` and `allow_real_motion: false` in `robot_config.yaml`. The
read-only path bypasses neither — it simply does not go through the motion gate,
because it issues no motion.
