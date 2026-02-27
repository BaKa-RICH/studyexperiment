# StageA Contract Checklist

Scenario: `ramp__mlane_v2`

This checklist freezes hard constraints from the spec before building files.

- [x] Scenario folder and config naming: `ramp/scenarios/ramp__mlane_v2/ramp__mlane_v2.sumocfg`
- [x] Edge IDs must include: `main_h1 main_h2 main_h3 main_h4 ramp_h5 ramp_h6`
- [x] Merge junction ID must be: `n_merge` and internal edges `:n_merge_*` must exist after netconvert
- [x] Merge edge must be: `main_h4`
- [x] Stream prefixes in routes must be preserved: main routes start with `main_`, ramp routes start with `ramp_`
- [x] Priority strategy frozen for StageA: main/ramp priorities are equal (`2/2`)
