# Step 23 — Dataset Card, Reproducibility, and Performance Hardening

## Read first

Source sections 9, 16, 18 and 19; all earlier steps.

## Build

Generate the dataset card with every section 9 topic: purpose/tasks, geographic/
temporal coverage, all sources, classes/creation/confidence/ambiguity, processing,
alignment, splits/leakage, missingness/QA, licences/attribution, ethical/legal
limits, recommended/prohibited uses, version, commit and reproduction command.
Explicitly explain SAR dark-region look-alikes: low wind, natural films,
biological activity, rain cells, currents, fronts and other phenomena.

Generate `known_issues.md`, architecture summary (≤15 points), project tree,
dependency/access/licence inventory and exact execution instructions. Pin the
environment and record Python/dependency/GDAL/PROJ/SNAP versions where used.

Harden downloads with bounded parallelism/connection pooling; add optional Zarr
and COG outputs behind config only when benchmarked useful. Measure representative
fixture/runtime memory and document bottlenecks. Do not optimize away provenance,
checksums or validation.

## Tests and gates

- Rebuild the tiny dataset twice from clean derived directories; manifest IDs and
  checksums match except documented volatile metadata.
- Card fields derive from manifests/registry/config rather than copied claims.
- All generated files, commands and failed checks for each phase are reported.
- Registration/manual approval stays an explicit TODO, never simulated.
