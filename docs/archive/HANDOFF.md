# VBTS testing platform — handoff

Last updated 2026-08-31.

Everything lives under `~/Desktop/KDC-tactile-testing-platform/`. Nothing this
project creates goes anywhere else.

---

## 0. Read this first — four things that will bite you

**1. Use `/usr/bin/python3`, not `python3`.**
`python3` on PATH is Anaconda, which does **not** have `nidaqmx`. Every script
here must run as:

```bash
/usr/bin/python3 scripts/<name>.py
```

**2. `Dev1/ai5` and `Dev1/ai6` are broken. Never assign a gauge to them.**
`ai5` is an open circuit; `ai6` couples 2.1 % of whatever channel precedes it.
Both are recorded in `ft_config.yaml` under `known_hardware_faults`, and a unit
test fails if either is ever put back into the channel list.

**3. The robot cannot move by accident, and that is deliberate.**
`RobotInterface` has three independent gates. Read §6 before trying to move
anything; don't "fix" the gates to get past them.

**4. `SetToolCoord` is not a store-only call.** FAIRINO documents it as
"set **and load**" — it activates the register it writes. To store a tool frame
without making it active, use `SetToolList`. See §7.

---

## 1. What this is

Automation for vision-based tactile sensor (VBTS) experiments. A robot presses a
printed spherical indenter into a VBTS while a force/torque sensor underneath
measures the contact wrench.

```
                     FR5 robot
                         │
              monolithic Form 4 indenter
              (spherical tip printed as one piece)
                         │
                      ↓ presses
                       VBTS
                         │
                 3D printed holder
                         │
                  ATI Mini45 F/T
                         │
                       mount
                         │
                  optical table
```

**Note the arrangement**: the F/T sensor is *table-mounted*, not on the robot
flange. That matters for frame transforms — see `ft_robot_frame_integration.md`.

**The indenter changed on 2026-08-31.** It used to be a printed body with a
Ø4 mm steel ball bonded on; the ball detached during the first calibration
attempt and the part was redesigned as a single piece. Anything referring to a
steel ball, or to a CAD TCP of 34.4 mm, is describing hardware that no longer
exists.

---

## 2. Status at a glance

| Subsystem | State |
|---|---|
| **F/T acquisition** | **Done and validated.** Ready for experiments. |
| Robot read-only connection | **Working.** |
| Robot motion | Never attempted. Gates closed. |
| **Indenter TCP calibration** | **Done.** Two runs agree to 0.160 mm. |
| **TCP written to controller** | **Applied.** Tool 1 = `[0.003, 0.322, 36.794, 0,0,0]`, active. |
| Sensor ↔ robot frame transform | **Measured.** `docs/sensor_base_transform.md` |
| Camera / synchronised logger | **Working.** `run_indentation.py` |

### Where things stand

The TCP is applied. Tool 1 holds `[0.003, 0.322, 36.794, 0, 0, 0]` and is the
active tool; tool 0 is untouched.

It had to go in through the **web UI**, because `SetToolList` over XML-RPC
returns success and writes nothing on this firmware (§8). The robot has never
been commanded to move by this project.

The next real task is the sensor-to-robot-base transform — §9.

---

## 3. Confirmed hardware configuration

### F/T chain

| | |
|---|---|
| Sensor | ATI Mini45, s/n **FT29831**, SI-145-5 (145 N / 5 N·m) |
| Calibration | `FT29831.cal` in the project root — used exactly as supplied |
| Interface | ATI 9105-IFPS-1 → SCB-68A terminal block |
| DAQ | NI PCIe-6343 `Dev1`, **connector 0 (upper)**, serial 0x222BE10 |
| Mode | differential, ±10 V, 2000 Hz, 200 samples/read, 200 settle samples |
| Output | N and N·m, frame `ATI_sensor_frame` |

**Channel mapping** (confirmed by measurement, not assumption):

| Gauge | Channel | SCB-68A terminals |
|---|---|---|
| SG0 | `Dev1/ai0` | 68 − **34** |
| SG1 | `Dev1/ai2` | 65 − 66 |
| SG2 | `Dev1/ai1` | 33 − 31 |
| SG3 | `Dev1/ai3` | 30 − 63 |
| SG4 | `Dev1/ai4` | 28 − 61 |
| SG5 | **`Dev1/ai7`** | AI7+ / AI15− (relocated) |

Note SG1/SG2 cross over, and SG0's reference is terminal **34**, not 35.

### Robot

| | |
|---|---|
| Controller | FAIRINO FR5 at **192.168.58.2** |
| Protocol | XML-RPC port 20003, binary state stream port 20004. No SDK needed. |
| PC interface | `enp131s0`, NM profile `Fairino` (192.168.58.80/24 + 192.168.57.10/24 + `192.168.58.2/32 via 192.168.57.2`) |
| Cable | control cabinet **user network port** |
| Tool / user register | 0 / 0, **tool 0 offset is zero** — TCP currently equals flange |
| Pose convention | `[x, y, z, rx, ry, rz]`, mm and deg, **fixed-axis (extrinsic) RPY**, `R = Rz·Ry·Rx` |

### Indenter

| | |
|---|---|
| Part | monolithic indenter printed on a Formlabs Form 4 |
| Tip | spherical, printed as part of the body — no ball, no adhesive |
| TCP definition | centre of the printed spherical tip |
| CAD nominal | `[0, 0, 35.97]` mm from the flange face |
| Calibration fixture | 90° cone, Ø6 mm × 3 mm deep, fixed to the optical table |

---

## 4. Validated F/T performance

From `data/final_ft_validation/20260826_091442/`:

| | |
|---|---|
| 1.004 kg check | Fz −9.694 N vs −9.846 N expected → **−1.54 %** |
| Cross-axis | 0.140 N, 1.4 % of Fz |
| Noise σ_Fz | **0.057 N** |
| Noise σ_Fx / σ_Fy | 0.015 / 0.017 N |
| Noise σ_Tx/Ty/Tz | ~0.0005 N·m |

Use **σ (std)**, not peak-to-peak, for contact thresholds — a single-sample ADC
glitch inflates p2p by 10× without moving σ.

### Sensor frame sign convention

From `data/manual_ft_excitation_final/20260826_091843/`:

| | |
|---|---|
| +Fx | operator's **left** |
| +Fy | operator's **back** |
| +Fz | **up** — compression reads **negative** |
| +Tz | **counter-clockwise** from above |

Right-handedness verified independently: a lateral force at height *h* gave
`Ty = h·Fx` and `Tx = −h·Fy` with *h* = 9.6–14.3 mm consistently across eight
pushes and two different axis pairs.

**Caveat**: "left" and "back" are relative to where the operator stood. Before
building a robot transform these must be re-expressed against the table or the
robot base.

---

## 5. TCP calibration result

Full detail in `docs/tcp_calibration_history.md`.

| Run | Indenter | TCP (mm) | rms | cond | spread |
|---|---|---|---|---|---|
| 1 | glued steel ball — **obsolete** | `[0.127, 0.427, 36.847]` | 0.454 | 6.9 | 64.9° |
| **2** | monolithic Form 4 | `[-0.049, 0.370, 36.831]` | 0.143 | 8.0 | 53.8° |
| **3** | monolithic Form 4 (same part) | `[0.055, 0.274, 36.757]` | 0.147 | 7.3 | 63.0° |

**Repeatability**: Run 2 vs Run 3 differ by **0.160 mm** in 3D. Same physical
part, never re-seated, independent pose sets — so this is procedure
repeatability, not part variation. It is the same size as either run's own rms,
meaning the two runs are not statistically distinguishable.

**Adopted value** (chosen by the operator, component-wise mean of Runs 2 and 3):

```
[0.003, 0.322, 36.794, 0.000, 0.000, 0.000]
```

Run 1 is excluded from the mean — different hardware.

**The rotation is a definition, not a measurement.** A sphere seated in a cone
constrains position only; it carries no orientation information. The tool frame
rotation is set to zero relative to the flange by choice. If a rotated tool
frame is ever needed, that requires the FR5 six-point method.

### The CAD discrepancy is real and unresolved

All three runs land **0.79–0.88 mm above** the CAD z of 35.97 mm, and the spread
among those three offsets (0.074 mm) is smaller than any single run's residual.
Random error does not reproduce itself three times in the same direction at the
same magnitude. This is systematic.

It is **not** cone seating depth. In `R_i t + p_i = c` the sphere-centre
position `c` is solved for alongside `t`, so how deep the sphere sits cancels
out as long as it sits the same way each time. Open candidates:

1. the printed part's actual flange-face-to-sphere-centre distance vs CAD
2. the FR5 flange frame origin vs the CAD mounting-face datum
3. printed spherical tip form error

Resolving it needs a caliper on the physical part, not another calibration run.
**Do not "correct" the TCP toward CAD.** CAD is the sanity check, not the truth.

---

## 6. How to run things

All commands from the project root, all with `/usr/bin/python3`.

### Everyday F/T use

```bash
# 1. Confirm all six gauge channels are actually driven.
#    Run this after ANY wiring change. It catches open channels that the
#    ordinary health check passes.
/usr/bin/python3 scripts/check_channel_integrity.py

# 2. See the live configuration and take a short passive acquisition.
/usr/bin/python3 scripts/test_ft_readonly.py --seconds 3

# 3. Measure the noise floor. Sensor must be untouched.
/usr/bin/python3 scripts/measure_ft_baseline.py --seconds 10

# 4. Validate against a known mass. Prompts you to remove, then place it.
/usr/bin/python3 scripts/test_weight_validation.py
```

### Robot, read-only

```bash
# Route check only — opens nothing.
/usr/bin/python3 scripts/robot_readonly_check.py

# Connect and read state, pose, tool registers.
/usr/bin/python3 scripts/robot_readonly_check.py --connect
```

### TCP calibration

Two ways to record poses. The **capture** form is one pose per invocation, which
is what to use when someone is walking the operator through it; **record** holds
an interactive loop open.

```bash
# Verify the maths with synthetic poses. No hardware needed.
/usr/bin/python3 scripts/prepare_tcp_calibration.py --self-test

# Open a run directory and back up robot state.
/usr/bin/python3 scripts/prepare_tcp_calibration.py --phase connect \
    --run-id Run4 --purpose <why> --previous-run <path>

# Record ONE pose and exit. Repeat per pose.
#   --reset          archive the previous pose set first (do this once, at the start)
#   --distinct-from  refuse a pose that merely repeats an earlier run's
#   --drop           discard the most recent pose
/usr/bin/python3 scripts/prepare_tcp_calibration.py --phase capture --reset
/usr/bin/python3 scripts/prepare_tcp_calibration.py --phase capture \
    --distinct-from data/tcp_calibration/_recorded_poses_archived_run2_*.json

# Solve, report, and compare against an earlier run. Never writes to the robot.
/usr/bin/python3 scripts/prepare_tcp_calibration.py --phase compute \
    --compare-with data/tcp_calibration/20260831_125056/tcp_result.yaml
```

**Pose procedure** — for every pose, in this order:

1. retract the tip fully clear of the cone
2. change orientation **while clear of the fixture**
3. approach slowly and seat the tip lightly
4. let it settle, then capture

Never re-orient while the tip is in the cone. Seating it and then twisting drags
the tip across the cone face, which moves the very point the solver assumes is
fixed. The script reads the flange pose twice 0.3 s apart and refuses to record
if it moved more than 0.05 mm.

Aim for 6–8 poses, roll and pitch both directions plus two diagonals, ≥40°
maximum orientation separation, condition number < 20.

### Writing a TCP to the controller

```bash
# Show the exact XML-RPC call without sending it.
/usr/bin/python3 scripts/apply_tcp_to_tool_register.py --api set_tool_list --dry-run

# Send it. The confirm token is mandatory.
/usr/bin/python3 scripts/apply_tcp_to_tool_register.py \
    --api set_tool_list --tool-id 1 --confirm WRITE-TOOL-1
```

This is the **only** script in the project that writes to the controller. It
refuses tool 0, refuses a bad route, refuses a robot that is not in a settled
error-free manual stop, and after writing it re-reads all 16 registers plus the
active tool id to prove nothing else moved.

### Indentation runs (F/T + robot pose + VBTS image, synchronised)

One sensor, start to finish (moves the robot; the confirm token is mandatory):

```bash
/usr/bin/python3 scripts/run_one_sensor.py --sensor DIGIT_hard_3mm_r1 --confirm RUN
/usr/bin/python3 scripts/run_one_sensor.py --sensor ... --from collect   # resume
/usr/bin/python3 scripts/campaign.py --status                             # what is done
```

Steps: enable → liftoff → align → newrun → tare → reference → qc → search →
touchcheck → characterize → contactmap → **collect** → retract → zerocheck → summary.
`collect` is continuous capture: loading/unloading cycles and four-direction
shear cycles repeat until exactly `capture_policy.frames_per_sensor` frames
(3000) are saved, each labelled with the F/T mean over its own exposure window
and the interpolated TCP pose. Every sensor therefore yields the same number of
training frames. See `docs/measurement_protocol.md` for the moves and
`docs/data_recording.md` for what lands where.

The single-sample phases (`--phase sample`, `series`, `shear`, `force-series`,
`force-shear`) still exist for hand-driven work.

**Camera**: 1920×1080 YUYV (uncompressed) is capped at 5 fps by the camera and
by the 205 ms exposure. 15 fps needs MJPG + exposure 666 + gamma 200 — lossy;
the measured cost is in `config/camera_config.yaml`. **Disk**: a 3000-frame run
is ~9 GB as PNG (54 sensors ≈ 490 GB; 1.5 TB free on 2026-09-04) or ~1 GB as
raw MJPG.

### Tests

```bash
/usr/bin/python3 -m pytest tests/ -q          # 127 tests, all passing
```

---

## 7. Safety architecture

### Robot motion — three gates

| Gate | Default | Effect |
|---|---|---|
| 1. `dry_run` | `True` | no socket opens, no RPC is sent |
| 2. `allow_real_motion` | `False` | `dry_run=False` alone raises `RuntimeError` |
| 3. real RPC dispatch | not wired | raises `NotImplementedError` |

Gate 3 exists because two protocol facts are still unverified: which `Mode()`
value protocol MoveL needs, and the Cartesian MoveL path (which needs
`GetInverseKin` first — the XML-RPC `MoveL` requires both joint and Cartesian
targets in one message). It disappears once those are confirmed on hardware.
Gates 1 and 2 are permanent.

### Read-only robot access

Diagnostic scripts use a whitelisted XML-RPC proxy: only `Get*` queries pass,
everything else raises `PermissionError` before reaching the wire. Verified
blocked: `SetToolCoord`, `SetTcp4RefPoint`, `ComputeTcp4`, `SetToolList`,
`RobotEnable`, `Mode`, `MoveJ`, `MoveL`, `ServoJ`, `StartJOG`, `SetDO`, `SetAO`,
`SetSpeed`.

`apply_tcp_to_tool_register.py` is deliberately outside that proxy. It is the
one place a write can happen, and it can only send `SetToolCoord` or
`SetToolList`.

### Network preflight

Every robot-touching script checks the route first. If traffic for 192.168.58.2
would leave via the **default** route, it refuses to connect.

**This is not theoretical — it fired on 2026-08-31 and stopped a tool write from
going to the office router** after the robot's ethernet link dropped.

### F/T

Analog **input** only. No output task, no device reset, no NI MAX write.

---

## 8. Things that already cost days — don't rediscover them

**The SG5 saga (tasks 5–16).** Forces looked plausible but Fx was wrong by up to
38 N. Root cause: SG5's reference was wired to terminal 35 (AI GND) instead of
34 (AI0−), leaving the differential negative floating. An open DAQ input does
not read zero — it returns whatever the multiplexer sampled before it, which
looks like a stable, in-range, load-correlated signal. Because SG5's Fz
coefficient is small (+1.18 N/V) and its Fx coefficient is large (+23.73 N/V),
Fz stayed nearly correct while Fx was garbage.

Lessons baked into the code:
- `check_channel_integrity.py` exists because the ordinary health check passes
  ghosting channels.
- `channel_mapping_confirmed` and `all_channels_healthy` are **separate flags**.

**Condition number, not residual, tells you if a TCP fit is trustworthy.**
Seen twice, in both Run 2 and Run 3: at three poses the residual was *better*
than the final answer's (0.143 and 0.074 mm) while the TCP was wrong by 2.2 mm
and 0.71 mm respectively. The only warning was the condition number — 159 and
150, against 8 and 7 when converged. A pose set that is too similar fits itself
beautifully and answers the wrong question.

**The VBTS camera must never run on auto exposure.** A VBTS encodes gel
deformation in pixel intensity, so a camera adjusting its own exposure makes
contact and camera housekeeping the same signal. Measured here: frame-to-frame
mean brightness varied by **20.4** on auto and **0.09** locked — 224x. Gain is
not controllable on this camera (always reads -1) and exposure clamps at 2047,
which alone gives a mean of only 41; `brightness` is what lifts the level.
`camera_interface.py` re-reads every control after setting it and refuses to
hand back a camera that silently stayed on auto.

**MJPG is not an option for gel images.** It reaches 15 fps against YUYV's 5,
but JPEG ringing corrupts exactly the intensity gradients a VBTS reads.

**A residual that ignores the force level is a moving zero, not bad geometry.**
The frame-transform fit sat at 4.4 mm and put the sensor origin above the parts
being pressed. The residual torque was the same size at 5 N as at 17 N — a
geometric error would scale with force. The tare had drifted 0.057 N·m over
3.5 hours. F/T zeros wander at roughly 0.0012 N·m per minute here; interleave
zero checks and never reuse an old tare.

**Jogging by hand drops the controller back to manual mode.** Protocol MoveL
needs auto (`Mode(0)`); the web UI and the pendant switch to manual (`Mode(1)`)
to jog, and leave it there. So any hand positioning between automated moves
silently disarms protocol motion, and `enable_protocol_motion.py` has to be run
again. `move_probe.py` checks the mode before every command rather than assuming
it survived.

**The motion sequence is not the jog sequence.** `fr5_tcp_jog_gui.py` connects
with RobotEnable(1) -> Mode(1) -> SetSpeed and jogs fine — that is the manual
path. Protocol motion needs ResetAllError -> **Mode(0)** -> RobotEnable(1) ->
SetSpeed, in that order, taken from the node that ran this robot for 521 MoveJ
calls (`teleop_slave/src/fairino_lowlevel_controller_node.cpp:275-300`).

**`SetToolList` over XML-RPC is a no-op on this firmware.** It returns 0 —
success, not the -506 an undefined method gives — and changes nothing. Proven by
entering `1.111 / 2.222 / 3.333` from the web UI and reading it back correctly:
the read path is fine, the write API is not. Any script that writes a tool
register **must verify by read-back**; the return code means nothing here.

**`SetToolCoord` activates what it writes.** FAIRINO's API_Instruction
(2024-05-30) says "set **and load** specific index tool coordinate". Its
signature also differs from `SetToolList`, which stores without loading:

```
SetToolCoord(id, [x,y,z,rx,ry,rz], type, install, toolID, loadNum)   # robot.cpp:3069
SetToolList (id, [x,y,z,rx,ry,rz], type, install, loadNum)           # robot.cpp:3115
    type = 0 tool frame / 1 sensor frame;  install = 0 robot end / 1 external
```

There is also a numbering disagreement: the C++ SDK documents the register range
as `[0..14]`, the XML-RPC doc says `1 to 15`. In practice `GetToolCoordWithID`
answers for 0–15 and the active tool reports as 0, which fits the SDK's 0-based
scheme — but a write should still be verified by reading **all** registers back,
which the apply script does.

**There is no API to read a tool's name or metadata.** The SDK exposes only
`GetToolCoordWithID`, `GetExToolCoordWithID` and `GetActualTCPNum`. An all-zero
register is therefore not proof that the register is unused. Check the teach
pendant if it matters.

**Interface renaming.** A reboot renumbered PCI buses: `enp129s0 → enp131s0`,
`wlp130s0 → wlp132s0`. Both `Fairino` profiles were bound to the old name and
could not activate, so 192.168.58.2 resolved through WiFi. `Fairino` is now
rebound to `enp131s0`.

**This can happen again on any reboot.** If the robot becomes unreachable, check
`ip route get 192.168.58.2` first, then `cat /sys/class/net/enp131s0/carrier`.
Those two distinguish the three failure modes seen so far: profile bound to a
stale name (carrier 1, wrong route), link physically down (carrier 0), and
profile simply not up. A durable fix for the first is to bind by MAC:

```bash
nmcli con mod Fairino 802-3-ethernet.mac-address 10:ff:e0:8d:9c:ce
```

Not applied yet. There is only one ethernet port on this PC, so it is safe.

**`~/Desktop/fr5_net.sh` is stale** — it hard-codes `IFACE=enp129s0`.

**The calibration file's `<BasicTransform>`** (Dz = 6.858 mm) is already folded
into `<UserAxis>`. Do not apply it again.

**Do not modify** `FT29831.cal`, `ati_calibration.py`, the wrench conversion, or
`fr5_tcp_jog_gui.py` (kept as the manual jog reference tool).

---

## 9. What to do next, in order

1. **Optionally measure the indenter with calipers.** Flange face to tip centre.
   This is the cheapest test of the 0.82 mm CAD discrepancy and it either
   confirms the calibration or points at the CAD datum.

2. **Resolve `operation_mode`.** Currently `null` in `robot_config.yaml`. The
   RT stream confirmed the encoding (`1 = manual`, observed live), but which
   mode protocol MoveL needs is still open. Evidence favours `Mode(0)` — the
   C++ teleop node used it for 521 successful MoveJ runs on this robot.

3. **Run the first indentation series** — `run_indentation.py`, see §6.

4. **Re-verify the frame transform** against the now-compliant gel. Soft contact
   allows clean lateral pushes along known base directions, testing `R`
   differently from the torque fit that produced it.

5. **Robot automation** if force ramps are needed. Gate 3 is unwired and
   `operation_mode` is unresolved; both are needed before the robot moves.

---

## 10. Document map

| File | Contents |
|---|---|
| `docs/HANDOFF.md` | this file |
| `docs/tcp_calibration_history.md` | all three TCP runs, repeatability, the CAD discrepancy |
| `docs/ft_robot_frame_integration.md` | what a sensor↔robot transform requires, and the procedure |
| `docs/robot_ft_integration_status.md` | robot-side API inventory, network details |
| `docs/HANDOFF_20260826.md.bak` | the previous handoff, superseded |
| `config/ft_config.yaml` | F/T configuration — heavily commented with the *why* |
| `config/robot_config.yaml` | robot configuration and the motion gates |
| `config/camera_config.yaml` | camera settings, and why each one is fixed |
| `docs/sensor_base_transform.md` | the sensor↔base transform and how it was measured |
| `~/Desktop/FR5_network_connection_notes.md` | FR5 network troubleshooting (outside project) |

The configs carry the reasoning inline. When something looks arbitrary there,
the comment explains what measurement produced it.
