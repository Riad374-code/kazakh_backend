# Shared Contract — Read Before Every Step

You are implementing one bounded step of a production-quality Python 3.11+
geospatial/ML system. Read `pipeline_inst.md`, this file, the current numbered
prompt, and all earlier files named by that prompt. Existing correct behavior is
part of the contract.

## Non-negotiable rules

- Work only on the current step. Prefer the smallest complete implementation.
- Never fabricate API endpoints, product/dataset IDs, credentials, labels,
  coordinates, licence terms, model scores, economic values, or test results.
- Verify unstable API and licence details in current official documentation.
  Record the URL, check time, and unresolved facts. Use official clients and open
  standards where practical. Never scrape or bypass quotas/authentication.
- Research and reuse maintained official clients or focused, battle-tested
  libraries before writing custom protocol/geospatial/ML infrastructure. Record
  why a dependency was accepted or rejected; add no speculative abstraction.
- Secrets come only from environment variables or `.env`; commit only
  `.env.example`. Logs and exceptions must not expose secrets.
- Treat `data/raw/` as immutable. Derived artifacts go to interim/processed,
  cache, reports, or quarantine. Validate inputs at every external boundary.
- Use UTC internally, stable content-independent IDs, explicit CRS/axis order,
  checksums, provenance, units, nodata, quality flags, and source timestamps.
- Never upscale Sentinel-3 and represent it as Sentinel-1 detail. Never call a
  dark SAR patch an oil spill without classification evidence.
- Keep semantic class and confidence separate. Keep forecast, analysis,
  reanalysis, observation, and machine-generated data explicitly distinguishable.
- Use immutable transformations: return new objects/files; do not mutate source
  objects or overwrite raw inputs.
- Functions should normally be under 50 lines, files under 400 lines (800 hard
  maximum), nesting under four levels, and errors explicit. Use typed interfaces,
  Pydantic validation, structured logging, bounded concurrency, timeouts, retries
  with backoff, and rate limiting.
- Tests must be deterministic, offline by default, and use tiny fixtures/mocks.
  Live integration tests require an explicit marker and credentials.

## Required completion response

At the end of a step, report:

1. Files created/changed and the reason for each.
2. Commands actually run and their exit status.
3. Acceptance gates passed/failed.
4. Credentials, registrations, licences, or external data still required.
5. Known limitations/TODOs without pretending they are complete.

Do not continue to the next numbered prompt.
