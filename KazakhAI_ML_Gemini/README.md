# Caspian Sea AI Environmental Monitoring & Forecasting Platform
**AI/ML Engine Repository (Hackathon Solution & Production Architecture)**

This repository houses the Machine Learning and geospatial predictive analysis pipeline for automated marine pollution detection, classification, severity evaluation, and multi-week forecasting across the Caspian Sea.

## Architecture Overview
- **Unified Semantic Segmentation**: Multi-class segmenter (U-Net / DeepLabV3+) identifying clean water, oil spills, algal blooms, industrial runoff, and sediment.
- **Vector Drift & Diffusion Engine**: Physics-informed Eulerian/Lagrangian trajectory simulation projecting pollution spread across $+1, +2, +3,$ and $+4$ weeks using environmental wind and ocean current velocity vectors.
- **Severity & Risk Assessment**: Automated cleanup priority ranking incorporating pollutant toxicity weights, surface area ($\text{km}^2$), and spatial proximity to coastlines and offshore energy infrastructure.

## Directory Structure
```text
caspian-ai-monitor/
├── api/
│   └── ml_service.py          # FastAPI server exposing ML inference & forecasting REST routes
├── src/
│   ├── models/
│   │   ├── drift_forecast.py  # Vector Drift & Spreading simulation engine (+1 to +4 weeks)
│   │   └── losses.py          # Combined Dice + Focal Loss for class imbalance training
│   └── pipeline/
│       ├── severity_scorer.py # Multi-factor severity & cleanup priority evaluation
│       └── inferencer.py      # Unified prediction pipeline (supports mock demo mode)
├── requirements.txt           # Python package dependencies
└── test_demo.py               # Standalone demo verification script
```

## Quickstart & Setup

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Run End-to-End Demo**:
   Execute the standalone pipeline demo to verify output JSON schemas and forecasting simulations:
   ```bash
   python test_demo.py
   ```

3. **Start FastAPI Model Serving Sidecar**:
   Unblock frontend and backend developers immediately by starting the mock inference API server:
   ```bash
   uvicorn api.ml_service:app --reload --port 8000
   ```
   * Interactive API docs will be accessible at: `http://localhost:8000/docs`
