# marine-dataset

A reproducible Python 3.11+ pipeline for collecting, processing, aligning,
validating, documenting, and exporting a **multimodal marine pollution and
oil-spill detection dataset**.

It relies exclusively on free or genuinely open data sources (Copernicus,
Open-Meteo, Copernicus Marine, OpenStreetMap, EMODnet, Global Fishing Watch).
It never fabricates data, endpoints, product IDs, credentials, or licence terms.

> **Status (Steps 01-03):** runnable package foundation, validated configuration,
> type-safe schemas, stable identifiers, safe storage APIs, source/provenance
> registry, and licence gates. **No source adapter or processing is implemented
> yet** — network collection begins in later steps.

## Feature map

This repo implements the bounded steps defined in `../pipeline_inst.md`:

| Step | What is delivered |
|------|-------------------|
| 01   | Package scaffold, `pyproject.toml`, validated config, `marine-data` CLI skeleton |
| 02   | Typed schemas, stable identifiers, immutable-safe storage, processing manifests |
| 03   | `source_registry.yaml`, provenance services, licence policy + `licence_report.md` |

## Install

```bash
cd marine_dataset
python -m pip install -e ".[dev]"
```

Dependencies are grouped so optional geo/ML heavy packages are not installed
unnecessarily: `runtime` (core), `geo` (rasterio/geopandas), `ml` (numpy),
`dev` (pytest/ruff). Platform prerequisites (GDAL, PROJ) are documented in the
relevant adapter step, not force-installed here.

## Quick start

```bash
# Print help
marine-data --help

# Validate the shipped default config and create the storage tree (no network)
marine-data init-config --config configs/default.yaml
```

All collection/processing commands are registered but **fail clearly with a
non-zero exit** until their owning step is built. They never report success.

## Configuration

Configuration is validated Pydantic models loaded from YAML, with optional
`MARINE_DATA_*` environment overrides. See `configs/default.yaml` for the
documented sample. **The shipped region/date values are safe placeholders** and
must be replaced with the user's real study area.

Secrets are never hardcoded. See `.env.example` for the full list of supported
environment variables; commit only `.env.example`, never `.env`.

## Storage layout

`init-config` creates the section-14 tree. `data/raw/` is treated as immutable
by the pipeline (`marine_dataset.storage` enforces this).

## Documentation-only source prerequisites

Registration and access requirements are documented in each source module and in
`marine_dataset/provenance.py` / the source registry; nothing is installed or
contacted at this stage.

## Testing

```bash
python -m pytest          # default: offline unit tests (no network/credentials)
python -m pytest -m integration   # requires explicit credentials/marker
```

## Licence & provenance

Source-data licences are kept separate from software licences. Everything is
tracked in `source_registry.yaml` with `licence_status` gates. Unresolved or
incompatible sources are quarantined and excluded from redistributable builds.
This project's own code is Apache-2.0 (see `pyproject.toml`).