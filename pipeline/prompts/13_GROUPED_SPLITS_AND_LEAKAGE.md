# Step 13 — Grouped Splits and Leakage Detection

## Read first

Source section 6 and section 5 negatives; Steps 01-12.

## Build

Implement `group_by_scene`, `group_by_incident`, `spatial_holdout`,
`temporal_holdout`, `region_holdout`, and `combined_spatiotemporal_holdout`.
Support grouping by incident, product, date, region/grid, orbit, platform and
annotator organisation. Store rules and seeds in versioned config. Default toward
earlier/selected training data, held-out validation incidents/spatial groups, and
entirely held-out test incidents/regions/periods.

Build a leakage report checking same product/incident/label/vessel event across
splits, adjacent or overlapping footprints, near-duplicate imagery, strong spatial
proximity and trivial temporal adjacency. Ensure all tiles from a scene remain in
one split. Compute normalization/class-balancing statistics from training only.

## Tests and gates

- Deterministic tests cover every split mode, small/imbalanced group failures,
  overlap boundaries, near-duplicates and temporal/spatial buffer thresholds.
- Intentionally contaminated fixtures are detected and critical leakage returns a
  non-zero validation result.
- Report group/class/geography/season/sensor/orbit distributions for each split.
- Never “fix” leakage by deleting evidence without reporting what changed.
