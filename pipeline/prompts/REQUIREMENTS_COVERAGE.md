# Requirements Coverage Map

The original `pipeline_inst.md` remains canonical. This map prevents requirements
from disappearing during the split; prompt 24 verifies bullet-level coverage.

| Source requirement | Owning prompt(s) |
|---|---|
| 1.1 Sentinel-1 | 04, 06 |
| 1.2 Sentinel-3 | 10 |
| 1.3 atmospheric weather | 05, 08 |
| 1.4 ocean variables | 05, 08 |
| 1.5 coastline/ports/static context | 11 |
| 1.6 shipping/vessel activity | 12 |
| 1.7 oil infrastructure | 11 |
| 2 labels, ontology, confidence, masks | 07 |
| 3 Sentinel-1 preprocessing | 06 |
| 4 spatial/temporal alignment | 08 |
| 5 tiling and controlled negatives | 08 |
| 6 grouped splits/leakage | 13 |
| 7 provenance/licences | 03 |
| 8 manifests/formats/IDs | 02, 09 |
| 9 dataset card | 23 |
| 10 quality assurance | 14 |
| 11 reliability scoring | 14 |
| 12 software architecture | 01 |
| 13 CLI | 01, 22 |
| 14 storage formats/layout/raw immutability | 01, 02, 09 |
| 15 configuration | 01 |
| 16 engineering requirements | shared contract, 01-24 |
| 17 deliverables | 01-14, 22-24 |
| 18 implementation order/phase gates | README, 01-14, 23-24 |
| 19 first-response obligations | 03, 23 |
| Product Stage 1 anomaly detection | 15 |
| Product Stage 2 classification/weak supervision | 07, 16 |
| Product Stage 3 movement forecast | 17 |
| Product Stage 4 prioritization | 18 |
| Product Stage 5 economic/energy impact | 19 |
| Product Stage 6 oil/gas heatmap | 20 |
| Final dashboard and Caspian trend panel | 21 |
| CNN/training readiness | 09, 15-17 |

## Cross-cutting invariants

- Official/current source verification and no fabrication: shared contract, 03-05,
  10-12, 24.
- Credentials, rate limits, retries, caching and restart: 01, 04-05, 10-12, 22.
- CRS, resolution, time, units, quality and provenance: 02, 06-10, 14-21.
- Licence-aware redistribution/quarantine: 03, 09, 11-12, 19, 23-24.
- Train-only fitting and leakage safety: 09, 13, 15-17, 24.
- Explainability, uncertainty and decision-support limitations: 14-21, 23-24.
