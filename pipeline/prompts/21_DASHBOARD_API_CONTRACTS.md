# Step 21 — Decision-Support API and Dashboard Data Contracts

## Read first

Complete product vision; source provenance/quality requirements; Steps 15-20.

## Build

Define versioned API schemas/services for detections and confidence;
classifications; 7/14/30-day forecast paths/maps; ranked cleanup recommendations,
damage/loss/urgency; oil/gas heatmap and at-risk infrastructure; Energy Impact;
and a Caspian trend panel for sea-level decline, newly exposed contaminated areas
and future exposure. Use existing artifacts—do not recompute scientific models in
presentation handlers.

Every response includes generated/observed time, data/model/config versions,
provenance links, quality/confidence/uncertainty, missing inputs, units, spatial
reference, stale-data indicator and limitations. Define filters/pagination and
stable GeoJSON/tile URLs without exposing local paths or secrets. Add rate limits,
input validation and safe error envelopes if HTTP endpoints are implemented.

Provide a minimal operator-facing reference view only if the repository already
contains a web stack; otherwise deliver OpenAPI/data contracts and fixture payloads
for the dashboard team. Clearly label scenarios, predictions and observations.

## Tests and gates

- Contract tests cover all panels, invalid region/time/event IDs, pagination,
  stale/missing data and CRS/units.
- No unsupported national-impact sentence or fabricated current event appears.
- Outputs remain usable by GIS clients and expose uncertainty prominently.
