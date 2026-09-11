# 9DTact_soft_2mm_r2__WRONG_SENSOR* — data from the wrong unit

2026-09-07. A pair100 run was started for 9DTact_soft_2mm_r2 before that unit
was actually mounted; 9DTact_soft_3mm_r2 was still in the holder. The run was
stopped during the zero phase, so these directories hold a zero measured on
soft_3mm_r2 under soft_2mm_r2's name, and no ladder frames. They are kept only
so the mistake is visible; do not use them.

No harm to the hardware: the probe never went past the zero approach's 0.5 mm
and soft_3mm_r2 had just had exactly that treatment in its own pair100 run.

The lesson is procedural, not technical -- the run was launched on the
assumption that a "장착완" for the previous sensor meant this one was ready.
Wait for the confirmation that names THIS sensor.
