# Step 14 — Quality Assurance and Reliability Scoring

## Read first

Source sections 10 and 11; Steps 01-13.

## Build

Implement every automated check in section 10: corruption, metadata, duplicates,
geometry/CRS/mask alignment and bounds, empty masks, coordinates/timestamps,
weather/ocean thresholds, units/NaNs/extremes, class IDs/licences, leakage, class/
geographic/season/sensor/orbit imbalance, infrastructure provenance, and vessel
speed jumps. Produce machine JSON and a human report. Never hide failed checks;
critical failures make CLI validation non-zero.

Implement the exact separate fields `satellite_quality_score`,
`label_quality_score`, `weather_match_score`, `ocean_match_score`,
`vessel_data_quality_score`, `infrastructure_quality_score`, and
`overall_sample_quality_score`. Use a versioned configurable
formula with named components, weights, missing-data policy and explanation per
sample. The overall score must not be an unexplained average. Preserve weak/poor
samples so researchers can filter, weight, use semi-supervised, or explore them.

## Tests and gates

- One fixture triggers each check and verifies severity/evidence/remediation.
- Score boundary, missing-modality and configuration tests are deterministic.
- Reports include denominators and cannot show “pass” when a check did not run.
- Run validation on the tiny end-to-end dataset from Step 09 and resolve all code
  defects; genuine data limitations remain visible known issues.
