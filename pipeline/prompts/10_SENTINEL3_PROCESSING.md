# Step 10 — Sentinel-3 OLCI/SLSTR Acquisition and Processing

## Read first

Source sections 1.2 and 4.2; product Stage 1; Steps 01-09.

## Build

Extend the verified Copernicus client with Sentinel-3 search/download commands and
metadata for OLCI ocean colour and SLSTR SST Level-1/Level-2 candidates: product
ID, footprint, time, processing level, quality/cloud flags, geometry and native
resolution. Select exact variables/products only after checking official docs.

Extract chlorophyll-a, CDOM, turbidity and SST when scientifically present; keep
units, retrieval algorithm/product version, uncertainty and quality flags. Apply
cloud/invalid masks. Preserve native grids and raw products. Any reprojection or
resampling is derived, fully recorded, and never presented as Sentinel-1 detail.

Create explicit co-registration outputs that link Sentinel-3 observations to SAR
scenes/grid cells by footprint and time, including coverage fraction, time delta,
native resolution and interpolation method.

## Tests and gates

- Mocked search/download/metadata parsing plus tiny xarray fixtures for variables,
  quality masks, units and native-grid preservation.
- A resolution assertion prevents accidental optical upscaling claims.
- Missing variables/products produce clear unavailable results, not fabricated
  arrays or guessed product IDs.
