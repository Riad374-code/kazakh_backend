# Step 11 — Coastline, Ecosystems, Population, and Energy Infrastructure

## Read first

Source sections 1.5 and 1.7; product Stages 2, 4-6; Steps 01-10.

## Build

Implement OpenStreetMap (OSM) Overpass first, with clean interfaces for EMODnet, national portals,
Global Energy Monitor and government registries. Collect available coast/shore,
rivers, ports/harbours/terminals/marinas, refineries/storage/industrial facilities,
platforms, wells/fields, pipelines/routes, protected areas, boundaries/EEZs,
fisheries/economic assets, population context, renewables and cooling-water
intakes. Absence from a source means unknown, not absent.

Preserve original geometry, identifier, tags, source authority, retrieval/update
time, licence and coverage. Store `geometry_accuracy`, `location_confidence`,
`location_method`, `source_authority`, `last_verified_at`, operating status and
source confidence. Approximate/inferred locations must never be verified.

Derive versioned distance/intersection features for rivers, coastline, protected
ecosystems, population, fisheries, ports, oil fields and energy assets using a
valid projected CRS. Cache queries, respect quotas, preserve the Overpass query,
and flag incomplete/non-authoritative coverage.

## Tests and gates

- Offline OSM fixtures test tag normalization, geometry, attribution and IDs.
- Mixed-source merge preserves all source IDs and disagreement rather than
  silently choosing one coordinate.
- Distance/area tests use known geometries and units.
- Unverified licences/locations are quarantined or visibly downgraded.
