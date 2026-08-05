# Step 24 — End-to-End Acceptance and Requirement Audit

## Read first

Read `pipeline_inst.md` in full, `00_PRODUCT_VISION.md`,
`REQUIREMENTS_COVERAGE.md`, and the complete implementation. This is an audit and
fix step, not a feature-expansion step.

## Execute

1. Build a traceability table from every source bullet and product-stage output to
   code, config, test and artifact. Mark `pass`, `partial`, `blocked` or `missing`.
2. Run formatting, linting, typing, unit tests, offline integration tests, CLI
   smoke tests, security/secret scan, licence gates and tiny end-to-end build.
3. Inspect the generated manifests, masks, splits, QA/licence reports, dataset
   card, anomaly/classification/forecast/ranking/impact/heatmap fixture outputs.
4. Check raw immutability, checksum/resume behavior, stable IDs, UTC/CRS/units,
   native Sentinel-3 resolution, weak-label separation, no future/split leakage,
   missing-data handling, uncertainty/provenance and non-zero critical failures.
5. Fix defects within existing scope. Do not hide unresolved external blockers.

## Final gates

- Every requirement has exactly one owning implementation step and evidence, or a
  plainly documented blocker with reason and next action.
- No hardcoded secret, fabricated endpoint/licence/product/result, silent catch,
  local-path ID, JPEG mask, raw overwrite, or naive random tile split exists.
- Documentation commands work from a clean environment.
- Self-review the final diff by CRITICAL/HIGH/MEDIUM/LOW severity. Resolve all
  CRITICAL/HIGH issues before declaring completion.

Return the traceability summary, test commands/results, generated files, failures,
external requirements, known limitations and exact reproduction command.
