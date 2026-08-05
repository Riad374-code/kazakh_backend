# Step 20 — Stage 6 Oil and Gas Risk Heatmap

## Read first

Product Stage 6; Steps 11-12 and 15-19.

## Build

Generate a versioned dynamic risk layer from active/historical oil pollution,
shipping density, platforms, pipelines, export terminals, ports, refineries and
forecast paths. Preserve source layers; derived risk cells/assets link back to
event, forecast, asset and model IDs.

For each grid cell and asset, output risk/confidence, threat band, expected arrival
window, contributing events, inspection-priority suggestion, data freshness,
uncertainty, missing layers and explanation. Separate active observation,
historical density and forecast risk. Use documented spatial/temporal decay and do
not convert absence of infrastructure records into safety.

Export COG/GeoParquet and vector-tile-ready artifacts with CRS, resolution, time,
nodata, units and style metadata. Rendering style must not alter numeric risk.

## Tests and gates

- Synthetic geometry verifies path/asset intersection, arrival ordering, decay,
  stale data, no-data and aggregation.
- Risk is monotonic under controlled higher probability/severity inputs.
- Asset coordinates marked approximate remain visibly lower confidence.
- Outputs are deterministic and loadable without the dashboard.
