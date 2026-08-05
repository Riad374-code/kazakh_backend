# Step 02 — Schemas, Stable IDs, Storage, and Processing Manifests

## Read first

Source sections 2, 4, 5, 8, 11, 14 and 16; Steps 01 and shared contract.

## Build

Implement typed, validated schemas for scenes, labels, tiles, environmental
records, vessel context, infrastructure context, split assignments, source
references, modality reliability, and processing operations. Include every field
explicitly required in sections 2, 4, 5, 8 and 11; optionality must reflect real
availability, not omission.

Implement deterministic stable identifiers from canonical source identifiers and
versioned namespaces. Local paths must never be IDs. Implement safe storage APIs
for atomic derived writes, directory creation, content checksums, duplicate
detection, cache lookup, quarantine, and immutable-raw enforcement. A processing
manifest must record operation/library/version/parameters, input/output checksums,
start/end times, warnings, and failure status.

## Tests and gates

- Same canonical input yields the same ID; materially different input does not.
- Attempts to overwrite raw files fail before writing.
- Atomic-write failure leaves no valid-looking partial artifact.
- Schema tests cover impossible coordinates/times, invalid scores/class IDs,
  missing CRS/units/provenance, and observation-vs-forecast typing.
- Checksums and duplicate detection use tiny fixtures and pass cross-platform.

Do not add API clients or geospatial resampling.
