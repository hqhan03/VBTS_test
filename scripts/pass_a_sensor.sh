#!/bin/bash
# One sensor of one Pass A probe pass, end to end.
#
#   pass_a_sensor.sh <sensor_id> <probe_id> [--full-scale]
#
# The plane must be measured at every mounting because re-seating the sensor
# moves it; the image scale must not, because it belongs to the sensor's own
# optics. So only the first probe pass over a sensor takes --full-scale, and
# every later pass measures the plane alone -- 40 s rather than 80, and it is
# the reason --plane-only exists.
set -u
PY=/usr/bin/python3
# Unbuffered, so the parent's own prints and its children's land in the log in
# the order they happened. Buffered, the parent's lines were flushed late and a
# child's output appeared to have vanished -- which cost two separate
# diagnoses on 2026-09-06 before the cause turned out to be ordering.
export PYTHONUNBUFFERED=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S="$1"; P="$2"
DS="20260905_passA_${P}"

# The paired-cylinder probes are two 1 mm posts and they snap. Two things
# follow, both requested by the operator on 2026-09-06:
#   * the ladder stops at 0.3 mm instead of 0.6;
#   * the image-scale/plane phase is skipped entirely. It presses the probe at
#     ten lateral offsets to a force target derived from the gel's stiffness,
#     which on a 1 mm post is a large stress for a measurement we do not need:
#     twelve of seventeen units already have a trusted scale from the ball4 or
#     cube4 pass, and that scale belongs to the sensor's optics, not to the
#     probe in use.
case "$P" in
  # Ladder to 0.3 mm, but the zero approach may go to 0.5 mm past first
  # contact: the ladder is the data, the zero is what the data is measured
  # from, and at 0.3 mm the force fit could not pin it (sigma 0.05 mm, half a
  # rung). Two 1 mm posts survived 1.19 mm at 0.47 N on 2026-09-07; 0.5 mm is
  # the operator's limit for routine use.
  pair*) LADDER="--depths 0.1,0.2,0.3 --zero-read-s 0.25 --zero-stop-depth 0.5 --zero-margin 2.0"
         SKIP_SCALE=1 ;;
  *)     LADDER=""; SKIP_SCALE=0 ;;
esac

# Whatever happens -- a phase exiting non-zero, a Ctrl-C, an error under `set -u`
# -- the probe must not be left near the gel. Every `|| exit 1` below used to
# skip the park at the bottom, so a failed zero phase left the tip in contact
# and it took a human to notice. A trap cannot be forgotten the way a cleanup
# line at the end of each branch can.
park_clear() {
  rc=$?
  "$PY" "$ROOT/scripts/run_one_sensor.py" --sensor "$S" --probe "$P" \
        --dataset "$DS" --from enable --to enable --confirm RUN >/dev/null 2>&1 || true
  "$PY" "$ROOT/scripts/run_one_sensor.py" --sensor "$S" --probe "$P" \
        --dataset "$DS" --from park --to park --confirm RUN 2>&1 | grep -E "parked|!!" || true
  # One terminator on EVERY path. The success line "=== S / P done ===" is not
  # printed when a phase exits non-zero, so anything waiting on it waits for
  # ever -- which cost 30 idle minutes on 2026-09-06 after the zero phase
  # failed on 9DTact_hard_3mm_r2. Wait on this line instead.
  echo "=== $S / $P finished rc=$rc ==="
}
trap park_clear EXIT INT TERM
# The image scale belongs to the sensor's optics and does not move when the
# unit is re-seated, so it is measured ONCE per sensor -- in the ball4 pass,
# because a sphere leaves a compact mark that cross-correlation locks onto
# while a flat punch leaves a broad featureless disc it slides on (measured
# 2026-09-05: ball4 residuals 0.76-2.69 px with the two rotation angles
# agreeing to 1.17 deg, against cyl4 y-rows of 3.6-15.8 px). Every other pass
# measures only the PLANE, which does move with every mounting.
# The full scale costs ~150 s and is a property of the sensor's optics, so it
# is worth paying ONCE. Measured 2026-09-06: re-measuring 9DTact_soft_2mm_r1
# after a re-mount gave 87.46 then 88.90 px/mm, 1.6 % apart, while nominally
# identical sensors differ by 15 % -- so it must be measured per sensor and
# need not be repeated per sensor. Ask the data whether this one already has a
# trusted scale rather than assuming the ball4 pass is its first.
if [ "${3:-}" = "--full-scale" ] || [ "${3:-}" = "--plane-only" ]; then
  MODE="$3"
elif "$PY" - "$S" <<'EOF'
import glob, json, sys
from pathlib import Path
want = sys.argv[1]
for p in glob.glob("data/*/*/state.json"):
    if Path(p).parent.name.replace("__2", "").replace("__badzero", "") != want:
        continue
    for sc in json.loads(Path(p).read_text()).get("scale", {}).values():
        if sc.get("scale_trusted"):
            sys.exit(0)          # found one: plane is enough
sys.exit(1)
EOF
then
  echo "  scale on record for $S -- measuring the plane only"
  MODE="--plane-only"
else
  MODE="--full-scale"
fi

# Skipping `search` saves 40 s by trusting the surface on record, and the zero
# phase re-measures it anyway. But the record can be wrong by more than the
# approach can travel: on 9DTact_hard_3mm_r2 (2026-09-06) the registry said
# 27.750 mm, the approach descended 1.56 mm without ever meeting the gel, and
# every fit failed. That is exactly what the 40 s search is for, so pay it --
# but only when the cheap path has actually failed.
if ! "$PY" "$ROOT/scripts/run_one_sensor.py" --sensor "$S" --probe "$P" \
        --dataset "$DS" --to shape --skip search,touchcheck $LADDER --confirm RUN; then
  echo
  echo "  === retrying $S with the surface search ==="
  "$PY" "$ROOT/scripts/run_one_sensor.py" --sensor "$S" --probe "$P" \
        --dataset "$DS" --to shape --skip touchcheck $LADDER --confirm RUN || exit 1
fi

if [ "$SKIP_SCALE" = "1" ]; then
  echo "  $P is a fragile paired-cylinder probe -- skipping the scale/plane phase"
elif [ "$MODE" = "--full-scale" ]; then
  "$PY" "$ROOT/scripts/run_indentation.py" --phase scale --sensor "$S" \
        --probe "$P" --dataset "$DS" || exit 1
else
  "$PY" "$ROOT/scripts/run_indentation.py" --phase scale --sensor "$S" \
        --probe "$P" --dataset "$DS" --plane-only || exit 1
fi

# The lift clear of the gel is the EXIT trap's job now, so it happens on the
# failure paths above too, not only here.
echo "=== $S / $P done ==="
