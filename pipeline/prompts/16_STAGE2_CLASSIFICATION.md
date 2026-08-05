# Step 16 — Stage 2 Weakly Supervised Pollution Classification

## Read first

Product Stage 2; source label/split/quality requirements; Steps 07-15.

## Build

Create an immutable feature table for SAR signatures, chlorophyll, turbidity,
CDOM, river distance, shipping density, oil fields, wind, rainfall, SST and
sea-level change. Record feature time, units, provenance, availability and quality.
Do not silently zero-impute absent modalities.

Train/evaluate reproducible Random Forest and, when installed, XGBoost baselines;
an optional small CNN may consume the documented image channels. Use only weak
rules from Step 07 to bootstrap labels and keep weak/verified sources separate.
Fit preprocessing/calibration on training only. Use grouped splits and report per-
class support, confusion matrix, precision/recall/F1, calibration and uncertainty.

Publish pollution type among oil/hydrocarbon, algal bloom, river sediment,
industrial runoff, exposed contaminated lakebed, plus classification confidence,
estimated severity, model/data version and explanation. Add abstention/unknown for
out-of-domain, low-quality or low-confidence samples.

## Tests and gates

- Tiny deterministic training fixture verifies feature order, saved-model reload,
  no split leakage, missing features, abstention and output schema.
- Severity is a versioned formula/model with units and assumptions, not a synonym
  for classifier confidence.
- Never claim weak-label validation as real-world confirmed performance.
