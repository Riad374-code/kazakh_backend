# Marine Pollution Build Pipeline

This folder turns `../pipeline_inst.md` and the product vision in
`prompts/00_PRODUCT_VISION.md` into a sequence of implementation prompts that a
small or open-source coding model can execute one step at a time.

## How to run it

1. Keep `pipeline_inst.md` unchanged; it is the canonical requirement source.
2. Start from a clean branch and run prompts in numeric order.
3. Give the model only the current prompt, `00_SHARED_CONTRACT.md`, and the files
   explicitly listed under **Read first**. It may inspect existing code as needed.
4. Do not advance until every acceptance gate passes or the model records a
   concrete blocker. Missing credentials or unavailable datasets are valid
   blockers; invented data, endpoints, licences, and results are not.
5. Review the diff and test output after every step. Commit only after human
   review, using a conventional commit message.
6. Re-run `24_END_TO_END_ACCEPTANCE.md` after any cross-cutting change.

The source document's section 19 asks for architecture, access/licence analysis,
dependencies, configuration, and runnable Phase 1 code in one first response. This
pipeline deliberately preserves those outcomes across Steps 01-05 so a smaller
model is not asked to scaffold and implement four external systems at once.

## Prompt sequence

| Range | Outcome |
|---|---|
| 01-03 | Runnable package foundation, schemas, provenance and licensing |
| 04-06 | Sentinel-1, weather, ocean collection and SAR preprocessing |
| 07-09 | Labels, alignment, tiles, manifests and training-ready exports |
| 10-14 | Sentinel-3, context sources, leakage-safe splits and QA |
| 15-20 | Detect, classify, forecast, prioritize and assess energy risk |
| 21-23 | Dashboard contracts, CLI orchestration and reproducibility |
| 24 | End-to-end audit against every requirement |

`REQUIREMENTS_COVERAGE.md` maps all source sections and product stages to their
owning prompt. A prompt may rely on earlier work, but it must not silently move
unfinished requirements to a later step.
