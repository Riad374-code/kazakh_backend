# Step 04 — Copernicus Authentication and Sentinel-1 Acquisition

## Read first

Source section 1.1, sections 3, 7, 13 and 18 Phase 1; Steps 01-03.

## Build

Using the simplest stable official Copernicus Data Space interface (prefer STAC
or official catalogue APIs after verifying docs), implement environment-based
authentication, token redaction, catalogue search, pagination, metadata mapping,
download, resume, checksum validation, cache reuse, and duplicate detection.

Support bbox/polygon, dates, GRD, IW, VV and optional VH, pass direction, and
relative orbit filters. Persist product ID, platform, footprint, start/end,
instrument mode, polarizations, pass, orbit/relative orbit, processing level,
pixel spacing/resolution, incidence-angle availability, and processing baseline.
Store raw responses and complete products without modification.

Expose `search-sentinel1` and `download-sentinel1` with dry-run, region/date
filters, structured progress, failed-record retry files, bounded concurrency,
timeouts/backoff/rate limiting, idempotence, and non-zero critical failures.

## Tests and gates

- Mocked pagination/filter/auth/401/retry/range-resume/checksum/duplicate cases.
- An interrupted download cannot masquerade as complete.
- One opt-in live smoke test downloads only a user-selected small product/asset.
- No invented endpoint, credential, or free-use claim; unresolved access is a
  documented TODO adapter, not fake data.
