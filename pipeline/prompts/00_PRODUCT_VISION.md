# Product Vision and ML Outcomes

This document preserves the product requirements that complement
`pipeline_inst.md`. The dataset pipeline must support an AI-powered Caspian Sea
environmental decision-support platform, progressing from **detect → classify →
forecast → prioritize → assess infrastructure impact**.

## Stage 1 — Multi-sensor anomaly detection (unsupervised)

- Sentinel-1 SAR: dark-spot detection, texture analysis, and an optional CNN
  anomaly detector.
- Sentinel-3 OLCI: chlorophyll-a, CDOM, turbidity, and per-pixel seasonal anomaly
  using a rolling z-score.
- Weekly, per-grid-cell outputs: SAR anomaly mask, water-quality anomaly mask,
  and confidence score.

## Stage 2 — Pollution source classification (weakly supervised)

- Classes: oil/hydrocarbon, algal bloom, river sediment, industrial runoff, and
  exposed contaminated lakebed.
- Features: SAR signatures, chlorophyll, turbidity, CDOM, distance to rivers,
  shipping density, oil fields, wind, rainfall, SST, and sea-level change.
- Candidate models: Random Forest, XGBoost, and optional small CNN.
- Expert rules create weak labels before training. Output pollution type,
  classification confidence, and estimated severity.

## Stage 3 — Pollution movement forecast

- Inputs: current location, wind direction/speed, surface currents, rainfall,
  river discharge, temperature, historical movement, season, and sea-level trend.
- Candidate models: XGBoost regressor, GRU, LSTM; temporal graph neural network is
  a future extension.
- For each detection output expected trajectory, spread probability, pollution
  concentration map, and confidence for 1-4 weeks (including 7, 14 and 30 days).
- The system should support evidence-backed statements such as probability of an
  oil spill reaching Kazakhstan's western coast within 14 days or drifting toward
  Turkmenistan. It must never emit such numbers without model evidence.

## Stage 4 — Pollution prioritization

Rank cleanup using pollution size, toxicity, distance to coastline, nearby
population, protected ecosystems, economic assets, fisheries, oil
infrastructure, probability of international spread, cleanup cost, and forecast
confidence. Outputs include ranked cleanup recommendations, environmental damage,
economic loss, and cleanup urgency. Example ordering: large oil spill approaching
Aktau Port; industrial runoff threatening fish habitat; offshore algal bloom.

## Stage 5 — Economic and energy impact

- Oil/gas protection: offshore platforms, pipelines, export terminals, ports;
  estimate infrastructure risk, maintenance savings, and avoided disruption.
- Renewable/industrial protection: coastal solar/wind farms and cooling-water
  intakes; estimate fouling, cooling-efficiency, and maintenance effects.
- Carbon: estimate emissions avoided by early intervention, reduced cleanup fuel,
  and ecosystem-recovery contribution.
- Output an Energy Impact Score. Any currency, downtime, or carbon estimate must
  expose assumptions, units, uncertainty, source, and calculation version.
- The supplied illustrative example says cleanup of “Pollution A” could protect
  offshore oil infrastructure and cooling-water systems, avoid `$3.2M` in
  maintenance, and reduce expected downtime by `18%`. These numbers are example
  presentation values only; the implementation must not report them as evidence.

## Stage 6 — Oil and gas risk heatmap

Combine active/historical oil pollution, shipping density, offshore platforms,
pipelines, export terminals, ports, refineries, and forecast paths. Show high-risk
assets, expected arrival time, threat level, and inspection priority.

## Final dashboard

Provide current detections and confidence; classifications for oil, algal bloom,
industrial runoff, sediment, and lakebed contamination; 7/14/30-day forecasts;
ranked cleanup actions; environmental/economic impact; an oil/gas heatmap; an
Energy Impact panel; and a Caspian trend panel for sea-level decline, newly
exposed contaminated areas, and future exposure. The dashboard is decision
support, not an autonomous authority, and must display provenance, uncertainty,
model version, timestamps, missing inputs, and limitations.

## Overall value proposition

The goal is not another satellite pollution detector. It is a Caspian Sea
decision-support platform that detects pollution with multi-sensor imagery,
classifies its likely type/source, forecasts 1-4 week spread, prioritizes cleanup
by environmental and economic impact, assesses Kazakhstan oil/gas and broader
energy risk, and tracks long-term change from Caspian sea-level decline. This
technical-to-action progression is central to the hackathon/environmental-
innovation narrative for policymakers and industry.
