# Step 19 — Stage 5 Economic, Energy, and Carbon Impact

## Read first

Product Stage 5; Steps 03, 11, 17-18.

## Build

Create versioned calculation modules for risk to platforms, pipelines, export
terminals, ports, refineries/storage, coastal solar/wind assets and cooling-water
intakes. Estimate maintenance exposure, potential operational disruption,
equipment fouling/cooling loss, cleanup-fuel effects, emissions and ecosystem
recovery only when authoritative coefficients/asset values are configured.

Return an Energy Impact Score plus separate physical and monetary estimates. Every
output must include currency/base year, units, time horizon, coefficient source,
calculation version, scenario assumptions, uncertainty interval, missing inputs
and whether it is observed, modelled or scenario-based. Avoided cost or downtime
is never a factual saving before verification.

## Tests and gates

- Dimension/unit and currency/base-year validation prevent incomparable sums.
- Hand-calculated synthetic scenarios test exposure, uncertainty propagation and
  missing coefficients.
- Without verified coefficients, emit qualitative/relative risk and `not
  estimated`; never fabricate values such as $3.2M or 18%.
- Licence/provenance gates apply to asset and economic datasets.
