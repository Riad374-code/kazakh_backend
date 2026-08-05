# Step 17 — Stage 3 Pollution Movement Forecast

## Read first

Product Stage 3; source ocean/weather/alignment/split rules; Steps 05, 08, 13-16.

## Build

Construct trajectory examples from detected pollution geometry and timestamp,
wind direction/speed, surface-current u/v, rainfall, river discharge, temperature,
historical movement, season and sea-level trend. Record coordinate conventions,
forecast horizon, timestep, units, observation/forecast origin, missing data and
uncertainty. Do not treat daily means as instantaneous forcing.

Implement a persistence/advection baseline first, then an XGBoost regressor when
data supports supervised training. Define common interfaces for GRU/LSTM; leave a
temporal GNN as an explicit future extension. Never train a deep model merely to
satisfy a class name when samples are inadequate.

For 7, 14, 28/30 days output expected georeferenced trajectory, spread
probability, concentration/probability map and confidence. Coast/country impact
statements must be computed by geometric intersection and calibrated probability,
with model version and evidence.

## Tests and gates

- Synthetic constant wind/current tests verify direction, speed, units, timestep,
  coastline intersection and probability bounds.
- Hindcast evaluation uses grouped temporal/spatial holdouts and reports trajectory
  displacement, spatial overlap and calibration with support counts.
- No future forcing or future pollution observations leak into inputs.
- Unsupported river discharge/sea-level data remains explicit missing input.
