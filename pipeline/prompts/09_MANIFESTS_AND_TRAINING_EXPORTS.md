# Step 09 — Dataset Manifests and Training-Ready Exports

## Read first

Source sections 8 and 14; product Stages 1-3; Steps 01-08.

## Build

Generate all required artifacts: `dataset_manifest.parquet`, `scenes.parquet`,
`tiles.parquet`, `labels.parquet`, `environment.parquet`, `vessels.parquet`,
`infrastructure.parquet`, `source_registry.yaml`, `label_ontology.yaml`,
`split_manifest.parquet`, `quality_report.json`, `licence_report.md`,
`dataset_card.md`, `known_issues.md`, and `checksums.sha256`.

Link modalities with stable `scene_id`, `tile_id`, `incident_id`, `label_id`,
weather/ocean/vessel/infrastructure context IDs and `dataset_version`. Validate
foreign keys, uniqueness, schema version, relative artifact references,
provenance/licences, checksums and row counts. Use GeoTIFF/COG for rasters,
GeoPackage/GeoParquet/GeoJSON for vectors, Parquet for tables, NetCDF/Zarr for
grids, YAML for config and JSON for machine reports.

Provide an ML export contract describing channel names/order, dtype, scale/units,
nodata/masks, normalization statistics computed from training only, target type,
sample weights, split IDs and feature availability. Include PyTorch-friendly
index metadata, but do not couple core data creation to one framework.

## Tests and gates

- A tiny fixture build produces every artifact and validates all links/checksums.
- No local path is treated as a permanent identifier.
- Missing modality is explicit, not silently row-dropped or zero-imputed.
- Exported samples can be loaded deterministically without network access.
