# Step 12 — Vessel Activity and Shipping Density

## Read first

Source sections 1.6 and 4.3; product Stages 2 and 6; Steps 01-11.

## Build

Create a provider-neutral vessel adapter and an authorised Global Fishing Watch
implementation only when current access permits it. Support allowed aggregated
presence/events/tracks, fishing/non-fishing activity, identities, SAR detections,
and AIS-matched/unmatched detections. Record whether each record is raw AIS,
processed AIS, gridded presence, inferred activity or SAR detection.

Implement scene time-window matching, original timestamps, justified position
interpolation, maximum AIS gap, gap duration, vessel-to-pixel/spill distances,
track approach/intersection and gridded shipping density. Proximity must not label
a vessel as pollution source.

Record reception gaps, disabled/spoofed transponders, identity uncertainty and
small-vessel limitations. Store only fields permitted by terms. Never scrape
commercial AIS sites or claim raw global AIS is free.

## Tests and gates

- Offline fixtures test window edges, dateline-safe geometry, gaps, speed-jump
  rejection, interpolation, density and provenance.
- Missing authorisation yields a documented adapter/TODO and explicit unavailable
  modality; it never blocks unrelated pipeline stages or invents data.
- Logs/exports obey field-level access and licence rules.
