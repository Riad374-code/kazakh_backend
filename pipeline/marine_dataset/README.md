# marine-dataset

A reproducible Python 3.11+ pipeline for collecting, processing, aligning,
documenting and exporting a multimodal marine-pollution dataset. It never
fabricates data, endpoints, product IDs, credentials, licence terms or results.

Status: Steps 01-24 are implemented as compact, offline-safe pipeline blocks.
Live providers and authoritative coefficients remain explicit inputs.

## Feature map

The bounded requirements are defined in `../../pipeline_inst.md`.

| Step | Delivered |
|---|---|
| 01 | Package scaffold, validated config and CLI skeleton |
| 02 | Schemas, stable IDs, immutable-safe storage and processing manifests |
| 03 | Source registry, provenance, licence policy and reports |
| 04 | Filtered Sentinel-1 STAC discovery, range-resumed OData downloads, checksums and atomic raw ingestion |
| 05 | Rate-limited explicit-model Open-Meteo collection and an official Copernicus Marine subset boundary |
| 06 | Restartable ESA SNAP preprocessing, calibrated channels, manifests and checksums |
| 07 | Validated ontology/import, weak labels, reprojection, clipping and GeoTIFF masks |
| 08 | Weather/ocean/vessel matching, geospatial tiles and deterministic stratified negatives |
| 09 | Relational manifests, deterministic sample index, ML export contract and checksums |
| 10 | Sentinel-3 metadata, quality-bit masks, native-grid extraction and co-registration |
| 11-14 | Context/vessel fixtures, deterministic splits, leakage and compact QA |
| 15-20 | Anomaly, classification, advection, prioritization, impact and heatmap baselines |
| 21-24 | API envelope, CLI orchestration, dataset card and acceptance report |

## Install

```bash
cd pipeline/marine_dataset
uv sync --locked --all-extras
```

Core dependencies install by default. Geo, ML and development packages remain
separate extras in `pyproject.toml`; `uv.lock` pins the tested environment.

## Quick start

```bash
marine-data init-config --config configs/default.yaml
marine-data search-sentinel1 --config configs/default.yaml --dry-run
marine-data search-sentinel3 --config configs/default.yaml --dry-run
marine-data collect-weather --config configs/default.yaml --dry-run
marine-data collect-ocean --config configs/default.yaml --dry-run
marine-data import-labels --dry-run
marine-data preprocess --dry-run
marine-data align --dry-run
marine-data tile --dry-run
marine-data build-manifest --output-dir data/manifests --allow-empty
```

`--allow-empty` creates a schema-only Step 09 bundle with honest `not_run`
statuses. For a training-ready bundle, pass `--tables-json` containing the eight
validated tables and the channel-ordered `ml_export_contract`. Run
`marine-data <command> --help` for real preprocess, align, tile and Sentinel-3
input/output options.

Steps 11-24 use small JSON fixtures and never fabricate live provider data.

## Scientific boundaries

- Full Sentinel-1 SAFE orbit application, thermal-noise removal, calibration and
  terrain correction execute through ESA SNAP GPT. Set `SNAP_GPT` or pass
  `--snap-executable`; the Python layer never substitutes an unverified approximation.
- Sentinel-3 native grids/resolution and every resampling operation are retained.
  `ADG443_NN` and `TSM_NN` are named CDOM/turbidity proxies, not direct measures.
- Copernicus Marine has no dedicated Caspian product and does not confirm complete
  Caspian current/SST coverage. Select IDs using `copernicusmarine describe`,
  probe returned coverage and mark fully masked modalities unavailable.
- SAR dark regions are anomalies, not automatically oil spills.

## Security, storage and licensing

Copy `.env.example` to `.env` and provide credentials locally. Never commit
secrets. `data/raw/` artifacts are staged under `data/interim/`, finalized with
an exclusive atomic link, re-hashed and never replaced. Source-data licences remain separate from the Apache-2.0
software licence; unresolved or incompatible sources are quarantined and excluded
from redistributable builds.

## Tests

```bash
.venv/Scripts/python -m pytest
.venv/Scripts/python -m ruff check src tests
.venv/Scripts/python -m pytest --cov=marine_dataset --cov-fail-under=80
```

Live provider tests and downloads require explicit user credentials and product
or dataset IDs; offline tests never contact external services.
