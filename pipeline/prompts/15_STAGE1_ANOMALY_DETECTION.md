# Step 15 — Stage 1 Multi-Sensor Unsupervised Anomaly Detection

## Read first

Product Stage 1; source sections 3-6 and 10-11; Steps 01-14.

## Build

Define a versioned weekly analysis grid and baseline periods without crossing
train/validation/test boundaries. Implement SAR dark-spot candidates plus local
texture features, and Sentinel-3 OLCI seasonal per-pixel anomalies for
chlorophyll-a, CDOM and turbidity using rolling robust statistics/configurable
z-scores. Handle missing/cloud/invalid pixels and insufficient history explicitly.

Fuse neither sensor blindly: publish separate SAR and water-quality anomaly masks,
then a calibrated confidence with named evidence, data quality, observation age,
coverage and uncertainty. An optional CNN anomaly detector must be isolated behind
a common interface and trained only on the training split; start with the
deterministic baseline.

Output georeferenced weekly masks and per-grid-cell tables with grid/time IDs,
sensor/product versions, baseline window, score, threshold, confidence, quality,
provenance and model/algorithm version.

## Tests and gates

- Synthetic time series verify rolling-window boundaries, season grouping, no
  future leakage, zero variance, missingness and known injected anomalies.
- Geospatial outputs retain CRS/transform/nodata and align to the declared grid.
- Dark spots are named `sar_anomaly`, never confirmed oil.
- Compare against simple baselines and report metrics only when labels exist;
  never invent performance.
