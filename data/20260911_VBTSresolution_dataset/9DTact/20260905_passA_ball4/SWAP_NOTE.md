# 9DTact_hard_2mm_r1 <-> 9DTact_hard_3mm_r2 were physically swapped

Found 2026-09-06 and confirmed by the operator. The two units had been
exchanged in storage some time between 2026-09-03 and 2026-09-05, so every run
in `20260905_passA_cyl4` and `20260905_passA_ball4` carried the wrong name.
Directory names and the sensor_id inside meta.yaml / state.json / samples.csv
have been exchanged in both passes; the data itself is untouched.

How it was found: gel surface height groups very tightly by thickness --
1 mm: 25.52-26.33,  2 mm: 26.36-26.81,  3 mm: 27.70-27.82 (sd 0.05).
The unit labelled hard_2mm_r1 measured 27.69/27.84, which is 5.3 sigma from the
2 mm group and inside the 3 mm group; the one labelled hard_3mm_r2 measured
26.50/26.65, 25 sigma from the 3 mm group and inside the 2 mm group. Both
passes agreed, so it was not a one-off.

`20260903_ladder_protocol` is NOT affected and was left alone. Its samples.csv
records the tcp_z at first contact: 39.853 mm under the name hard_3mm_r2
against 38.599 mm under hard_2mm_r1, i.e. the 3 mm gel sat 1.25 mm higher, as
it should. The swap happened after that session.

`9DTact_hard_2mm_r1__failed1` and `__failed2` in the ball4 pass are the two
aborted attempts on that unit from 2026-09-06 (registry surface stale by 1.2 mm,
so the approach never reached the gel), kept for the record.
