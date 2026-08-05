# Step 05 — Weather and Ocean Collectors

## Read first

Source sections 1.3, 1.4, 4.1, 4.2 and Phase 1; Steps 01-04.

## Build

Implement two separate official adapters.

**Open-Meteo:** collect precipitation/rain, 10 m wind speed/direction/gusts,
pressure, temperature, humidity, cloud, visibility and weather code when the
selected endpoint provides them. Record exact model/upstream reanalysis, grid and
temporal resolution, response/retrieval timestamps, raw response, attribution,
licence, units, and missing variables. Never use an unrecorded automatic “best”.

**Copernicus Marine:** use the official toolbox/API for SST, surface current u/v
and derived speed/direction, SSH, and optional waves/salinity/mixed-layer depth.
Record product/dataset IDs and versions, variable/units, grid/level/resolution,
time, quality, origin, observation/analysis/reanalysis/forecast type, retrieval,
licence and citation. Never silently mix forecast and reanalysis.

Expose CLI collectors with raw preservation, cache, rate/retry/timeout controls,
dry-run and credential-safe errors. Derive current speed/direction with documented
conventions and new immutable outputs.

## Tests and gates

- Offline fixtures test parsing, units, missing values, model/product typing,
  vector derivation, caching, quotas and retries.
- Live tests are opt-in and tiny.
- Historical training defaults to observation/reanalysis, with forecast rejected
  unless config explicitly permits it.
