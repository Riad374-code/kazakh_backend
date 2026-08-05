# Step 07 — Label Ontology, Import, Masks, and Weak Labels

## Read first

Source section 2; product Stage 2; Steps 01-06.

## Build

Create machine-readable `label_ontology.yaml` with definitions for all initial
classes 0-10 from section 2.1. Keep class, confidence (`verified/high/medium/low/
unknown`), verification state, weak-label status and machine-generation status
independent. Implement importers for expert vectors, incident records, research
datasets and algorithm candidates through one validated interface. Preserve every
required label field from section 2; unavailable fields must be explicit nulls
with provenance/quality notes, not guessed.

Implement configurable expert-rule weak labelling for the five product classes:
oil/hydrocarbon, algal bloom, river sediment, industrial runoff, exposed
contaminated lakebed. Rules must be versioned, explainable, uncertainty-aware and
must never relabel their output as verified ground truth.

Validate/repair only safely repairable geometries, reproject to image CRS, clip to
footprint, and rasterize with recorded resolution, `all_touched`, overlap and
class-priority rules. Preserve original vectors and GeoTIFF masks; PNG is optional
and JPEG forbidden.

## Tests and gates

- Tests cover every ontology class/confidence, invalid/self-intersecting/outside
  polygons, overlaps, reprojection, categorical nearest-neighbour behavior and
  deterministic rasterization.
- Uncertain observations cannot enter confirmed oil by default.
- Weak-rule output contains rule/version/evidence and remains machine-generated.
- No unavailable public label source is fabricated.
