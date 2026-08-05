# Step 01 — Scaffold, Configuration, and CLI Skeleton

## Read first

`pipeline_inst.md` sections 12-16 and 18; `00_SHARED_CONTRACT.md`.

## Build

Create the `marine_dataset/` package tree from section 12, `pyproject.toml`,
README, `.env.example`, package modules, test folders, and the storage tree from
section 14. Implement validated configuration for every item in section 15:
regions/date ranges, products/polarizations/orbits, tiles/CRS/resolution, matching
windows, variables, ontology, negative sampling, split/seed, concurrency/rates,
retries, paths, compression, and quality thresholds.

Use Pydantic settings/models and YAML. Provide `configs/default.yaml` with safe,
small placeholder values clearly marked for user selection—not fake product IDs.
Create a Typer (or similarly lightweight) `marine-data` CLI with `--help`,
`init-config`, and placeholder command registrations for all section 13 commands.
Unimplemented commands must fail clearly, never report success.

## Tests and gates

- Unit tests cover valid config, bad date/CRS/rate/threshold values, env overrides,
  and round-trip YAML loading.
- `marine-data --help` and `marine-data init-config --dry-run` work.
- No network call occurs; no credentials or geographic region are hardcoded.
- Dependency groups separate runtime, geo/optional, ML/optional, and development.
- Document registration needs and platform prerequisites without installing them.

Do not implement source adapters or processing in this step.
