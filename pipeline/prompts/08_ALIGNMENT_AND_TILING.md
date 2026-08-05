# Step 08 — Spatial/Temporal Alignment, Negative Sampling, and Tiling

## Read first

Source sections 4 and 5; Steps 01-07.

## Build

Compute scene time exactly as acquisition midpoint and retain start/end, source
timezone and normalized UTC. Implement weather matching (preferred ≤30 min,
acceptable ≤90 min, configurable), ocean coverage/time matching, and vessel
matching interfaces. Retain timestamps, deltas, interpolation flags/methods,
resolution/product type and match quality. Do not imply daily ocean means describe
the acquisition minute; do not bridge unjustified AIS gaps or infer polluters from
proximity.

Use EPSG:4326 for canonical lon/lat and an explicit local projected CRS for
distance/area. Record axis order, pixel origin, affine, nodata, source/target CRS,
resolution, dimensions and resampling. Preserve native environmental grids;
pixel-aligned grids are derived outputs only.

Build configurable 256/512 tiles, GSD, overlap, water/positive thresholds and all
section 5 tile metadata. Retain controlled empty masks. Sample documented
negatives across open/coastal/harbour water, low wind, natural slicks, blooms/
fronts, wakes, rain effects, seasons and sea states. Prevent geography/year/orbit/
processing-version shortcuts.

## Tests and gates

- Boundary tests for time thresholds/interpolation, CRS/affine alignment, tiling
  edges/overlaps and deterministic negative sampling.
- Mask pixels align with image pixels; categorical resampling is nearest-neighbour.
- Every tile links environmental/vessel/infrastructure context or records why it
  is unmatched.
