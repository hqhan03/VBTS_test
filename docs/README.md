# docs — what to read for what

Written 2026-09-07 when the folder was consolidated. Thirteen files had grown
into three overlapping accounts of the frame transform, two entry points and a
rendered HTML copy of a page that had since changed. What is left is one file
per question.

| I want to know… | read |
|---|---|
| what the campaign is, its four tests, where it stands | **`campaign_protocol.md`** ← start here |
| what the robot actually does, move by move, and every measured number behind it | **`measurement_protocol.md`** |
| where a file gets written and what is in it | `data_recording.md` |
| how the sensor frame, the base frame and the gel relate | `frames_and_transforms.md` |
| where the TCP number came from | `tcp_calibration_history.md` |
| **test 2, shape reconstruction — method and all 17 units' results** | **`shape_reconstruction.md`** |
| **test 3, spatial resolution — method and all 17 units' results** | **`spatial_resolution.md`** |
| can hardness and thickness be one variable (contact radius)? — an attempt | `contact_variable.md` |
| why a sphere reads the surface too deep | `hertz_zero_bias.md` |
| why a paired probe's two posts press unequally | `pair_contact_asymmetry.md` |
| the 2026-09-05 single-unit shape pilot | `shape_reconstruction_pilot.html` |
| superseded documents, kept for provenance | `archive/` |

**The machine-readable truth is in `config/`, not here.**
`sensor_registry.yaml` (per-sensor limits, gel models, capture policy),
`probes.yaml` (probe geometry, TCP, contact laws), `ft_config.yaml` (wiring,
faults, calibration) and `camera_config.yaml` are what the code reads. A number
in a document that disagrees with the config is out of date; the config wins.

---

## Four things that will bite you

**1. Use `/usr/bin/python3`, not `python3`.** `python3` on PATH is Anaconda,
which does not have `nidaqmx`. `run_one_sensor.py` checks this at startup and
refuses **before the robot moves**.

**2. `Dev1/ai5` and `Dev1/ai6` are broken. Never assign a gauge to them.**
`ai5` is an open circuit; `ai6` couples 2.1 % of whatever channel precedes it.
SG5 lives on `ai7` because of this. Both faults are in `ft_config.yaml` under
`known_hardware_faults`, and a unit test fails if either goes back into the
channel list. Every early "phantom lateral force" result traces to this.

**3. The robot cannot move by accident, and that is deliberate.** Do not
"fix" the gates to get past them.

**4. `SetToolCoord` is not a store-only call.** FAIRINO documents it as "set
**and load**" — it activates the register it writes. Use `SetToolList` to store
without activating. **Tool 0 must never be overwritten**, and tool 1 already
carries the applied TCP: do not change it without asking the operator.

---

## What stops the robot moving when it should not

There are two different safety stories in this repo and the older documents
only described the first one.

**The legacy `RobotInterface` gates.** `dry_run=True` by default (no socket
opens), `allow_real_motion=False` (turning off `dry_run` alone raises), and the
real RPC dispatch was never wired. **Nothing in the campaign goes through this
class.** It is the untaken path; leave it alone.

**The path the campaign actually uses** is `move_probe.py` and
`run_indentation.py`, and its guards are:

| guard | what it does |
|---|---|
| `--confirm MOVE` / `--confirm RUN` | no script commands motion without the literal token on the command line |
| read-only proxy | diagnostics use a whitelist that only passes `Get*`; `SetToolCoord`, `MoveL`, `RobotEnable` and friends raise `PermissionError` before reaching the wire |
| network preflight | every robot-touching script checks the route first and refuses if traffic for 192.168.58.2 would leave by the default route |
| `ready_to_move()` | refuses while the controller is in manual mode — which is where hand jogging always leaves it |
| joint-step ceiling | a planned move whose largest joint change exceeds the ceiling is refused as a reconfiguration, not sent. This is what catches a wrong IK branch, which on this arm moves a joint by over 200 degrees |
| tilt / radial gates | a probe more than a few degrees off the gel normal, or off the sensor axis, stops the run |
| park on every exit | a failed run, an exception and Ctrl-C all lift the probe clear before the process ends |

`apply_tcp_to_tool_register.py` is deliberately outside the read-only proxy. It
is the one place a write can happen, and it can only send `SetToolCoord` or
`SetToolList`. **Tool 0 must never be overwritten**; tool 1 carries the applied
TCP and must not be changed without asking the operator.

---

## Running a sensor

```bash
# Pass B (force estimation), one sensor, end to end — about 15 minutes
scripts/pass_b_sensor.sh 9DTact_soft_1mm_r1

# Pass A (shape + resolution), one sensor for one probe
scripts/pass_a_sensor.sh 9DTact_soft_1mm_r1 pair050

# read-only: where is the arm, is it ready to move
/usr/bin/python3 scripts/move_probe.py --status

# lift clear of the gel, whatever state a run left things in
/usr/bin/python3 scripts/run_one_sensor.py --sensor <id> --from park --to park --confirm RUN
```

Both pass scripts leave the probe **78 mm above the gel** on every exit path,
including failures and Ctrl-C. If a run ever ends without that, something is
wrong — check with `--status` before touching anything.

## Analysing

```bash
# spatial resolution for one pass and one sensor
/usr/bin/python3 scripts/analyse_resolution.py 20260905_passA_pair050 9DTact_hard_3mm_r2

# shape reconstruction, every unit (writes data/9DTact/shape_reconstruction*.csv)
/usr/bin/python3 scripts/analyse_shape.py

# the gel-normal correction for a unit (commands no motion)
/usr/bin/python3 scripts/gel_normal.py --sensor 9DTact_hard_3mm_r1
```

---

## The habit that this project keeps re-learning

Every speed hypothesis formed by reasoning here has been wrong or marginal. The
large wins came from timing the parts: the camera was throwing away every
second frame for a week (2.44 fps against a 4.89 fps limit) and no amount of
thinking about USB bandwidth found it — a three-line benchmark did, in one
minute. Likewise, "the contact wandered off axis" was a message that sent three
runs looking for something that moved; the radial was constant to 0.010 mm and
the offset was inherited from before the phase even started.

**Measure it before believing it, and write the measured number next to the
decision it justifies.** That is why the documents here are full of parenthetical
figures — they are what makes a choice reviewable later.
