# Step 18 — Stage 4 Pollution Prioritization Engine

## Read first

Product Stage 4; Steps 11, 14, 16-17.

## Build

Implement a transparent, configuration-versioned multi-criteria score using
pollution size, toxicity, coast distance, nearby population, protected ecosystems,
economic assets, fisheries, oil infrastructure, international spread probability,
cleanup cost and forecast confidence. Define source, units, normalization,
direction, weight, missing-value policy and uncertainty for every factor.

Return ranked event IDs, priority band, component contributions, confidence,
sensitivity to uncertain inputs, missing factors, explanation and suggested
inspection/response—not an autonomous cleanup order. Keep estimated environmental
damage, economic loss and urgency distinct. Permit country/agency policy profiles
without hardcoding Kazakhstan-specific weights.

## Tests and gates

- Hand-calculated fixtures verify formula, ordering, ties, missing factors,
  monotonicity and deterministic ranking.
- Sensitivity output shows when plausible weight/uncertainty changes reorder top
  events.
- Low forecast confidence cannot silently increase certainty of priority.
- Example scenarios (Aktau-bound oil, fish-habitat runoff, offshore bloom) are
  clearly synthetic fixtures, never reported as current events.
