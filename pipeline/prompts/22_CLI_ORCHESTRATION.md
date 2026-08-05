# Step 22 — Complete CLI, Restartability, and Run-All Orchestration

## Read first

Source section 13 and all implemented steps.

## Build

Finish every required command: init config; search/download Sentinel-1/3; collect
weather/ocean/vessels/infrastructure; import labels; preprocess; align; tile;
split; validate; build manifest/card; and `run-all`. Add explicit commands for
Stage 1-6 artifacts where implemented.

Each command supports config, dry-run, region/date filters where relevant,
structured logs, progress, idempotence, cache/checksum reuse, failed-record retry,
bounded concurrency and clear non-zero exits. `run-all` uses dependency order,
durable checkpoints keyed by config/input/code versions, resumes safely, and does
not mark skipped/blocked work complete. A changed dependency invalidates only
affected downstream checkpoints.

## Tests and gates

- CLI help documents inputs/outputs, network/auth needs and exit codes.
- Offline end-to-end fixture exercises successful run, dry-run, interruption,
  resume, retry, config change, critical validation failure and optional-source
  unavailability.
- No valid artifact is redownloaded or overwritten unnecessarily.
- Missing credentials stop only dependent steps and are reported once, safely.
