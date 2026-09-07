#!/bin/bash
# One sensor of the Pass B force-estimation pass, end to end.
#
#   pass_b_sensor.sh <sensor_id> [probe]        probe defaults to ball8
#
# WHY THIS EXISTS, AND WHY IT IS IN TWO STAGES
# --------------------------------------------
# Pass B's expensive step is `collect`: ten to thirteen minutes of the ~16 a
# sensor takes. Everything before it is about three minutes, and 60 s of that
# was being spent on two steps that this pass does not need:
#
#   touchcheck (16 s) weighs the contact the search found. The zero phase then
#   does the same thing again on every approach, with its own lift check, so in
#   a pass that runs zero it costs 16 s to learn nothing new. Pass A has always
#   skipped it; Pass B was not, by oversight.
#
#   search (45 s) descends onto the gel to find the surface. The zero phase
#   re-measures it properly anyway, so the search is only there for the case
#   where the height on record is too wrong for the zero approach to reach --
#   which happened once, on 9DTact_hard_3mm_r2 (2026-09-06), where the registry
#   was off by more than the approach could travel.
#
# So the cheap path is tried first and the search is paid for only when it has
# actually failed. The two stages exist so that failure costs three minutes and
# not sixteen: a `collect` that fails has nothing to do with the surface, and
# re-running the whole protocol with the search would be sixteen minutes spent
# on the wrong hypothesis.
set -u
PY=/usr/bin/python3
export PYTHONUNBUFFERED=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
S="$1"; P="${2:-ball8}"
DS="20260907_passB_${P}"

# shape and scale are Pass A products: the depth ladder belongs to the shape
# and resolution tests, and the image scale belongs to the sensor's optics and
# was measured once, in the ball4 pass.
COMMON=(--sensor "$S" --probe "$P" --dataset "$DS" --confirm RUN)
CHEAP=(--skip shape,scale,search,touchcheck)     # trust the surface on record
WITH_SEARCH=(--skip shape,scale,touchcheck)      # measure it instead

echo "=== $S / $P: stage 1, up to contactmap (surface from the registry) ==="
if ! "$PY" "$ROOT/scripts/run_one_sensor.py" "${COMMON[@]}" "${CHEAP[@]}" --to contactmap; then
  echo
  echo "  === stage 1 failed; retrying it WITH the surface search ==="
  # Same steps, but let the search measure the surface instead of trusting the
  # record. touchcheck stays skipped -- it was never the problem.
  if ! "$PY" "$ROOT/scripts/run_one_sensor.py" "${COMMON[@]}" "${WITH_SEARCH[@]}" \
        --to contactmap; then
    echo "=== $S / $P finished rc=1 (stage 1) ==="
    exit 1
  fi
fi

echo "=== $S / $P: stage 2, collect ==="
"$PY" "$ROOT/scripts/run_one_sensor.py" "${COMMON[@]}" "${CHEAP[@]}" --from collect --to park
rc=$?
echo "=== $S / $P finished rc=$rc ==="
exit $rc
