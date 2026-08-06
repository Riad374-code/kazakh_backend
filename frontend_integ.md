# Frontend Integration Guide — Khudaferin API (Caspian Sea AI Marine Pollution & Hydrodynamics)

This document is the **authoritative contract** the frontend team should follow when
integrating the Khudaferin backend. Every endpoint, its purpose, its parameters, its
response shape, and how the UI should consume it is documented below.

---

## 1. How to run the backend

### Local development

```
cd KazakhAI_ML_Gemini
uvicorn api.app:app --host 0.0.0.0 --port 8000 --reload
```

- API base URL (local dev): `http://localhost:8000`
- Swagger/OpenAPI UI: `http://localhost:8000/docs`
- Redoc UI: `http://localhost:8000/redoc`

The server **bootstraps** the SQLite operational store (`data/kazakh_ai.db`) on startup
and starts a **background scheduler** that recomputes all analysis stages periodically
(default interval `3600s`, configurable via env `REFRESH_INTERVAL_SECONDS`). You do NOT
need to pre-seed anything — data is generated from verified pipeline checkpoints.

### Deployed (Railway)

The repo is Railway-ready (root `Dockerfile` + `railway.toml`). After deployment the API
base URL is the Railway-generated domain, e.g. `https://khudaferin.up.railway.app`.
Swagger lives at `<base>/docs`; the machine-readable spec at `<base>/openapi.json`.

Use `GET <base>/api/v1` to programmatically discover the full route list at runtime.

Environment variables you may set on Railway:

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `CORS_ORIGINS` | `*` | Comma-separated frontend origins allowed by CORS. |
| `REFRESH_INTERVAL_SECONDS` | `3600` | Scheduler refresh interval. |
| `DATABASE_PATH` | unset | SQLite file path; set to a Volume mount for persistence. |

### CORS
CORS is wide open by default (`allow_origins=["*"]`, credentials disabled). In production,
set `CORS_ORIGINS` to your frontend host(s) so the browser allows credentialed requests.

### Auth
There is **no authentication**. Do not expose `/admin/*` endpoints in production-facing
UIs, or gate them behind a server-side auth layer.

---

## 2. Global response envelope

Non-streaming REST endpoints return JSON with this shape:

```jsonc
{
  "status": "success",
  "data_type": "<what kind of data this is>",
  "...": "endpoint-specific payload"
}
```

- `status` is `"success"` normally, or `True`/`False` on a few legacy routes.
- Every list endpoint also reports `count`/`returned` so the UI can render table totals
  without scanning the payload.
- **404** errors return `{"detail": "..."}` (FastAPI standard).
- **500** admin errors return `{"detail": "..."}` with a message.

---

## 3. Endpoint reference (grouped)

Legend — `B` = Business data, `A` = Admin/system, `L` = Legacy compatibility.

---

### 3.1 Glass / Health

#### `GET /`
**Purpose:** Root health checkpoint.

#### `GET /api/v1`
**Purpose:** API discovery index. Returns project metadata plus the full list of routes so
the frontend can render navigation / confirm a route exists before calling it.

```jsonc
{
  "status": "success",
  "project": "khudaferin",
  "api_version": "2.2.0-RAILWAY",
  "documentation": "/docs",
  "openapi_spec": "/openapi.json",
  "routes": [ {"method": "GET", "path": "/api/v1/health", "methods": ["GET"]}, ... ]
}
```

#### `GET /api/v1/health`
**Purpose:** Diagnostics, model roster, DB read counts, scheduler status, active checkpoints.
Use this on the frontend to detect backend readiness and to render a "system status"
badge (models online, DB counts).

```jsonc
{
  "server_status": "ONLINE",
  "project": "khudaferin",
  "api_version": "2.2.0-RAILWAY",
  "region_coverage": "Caspian Sea Basin (EPSG:4326)",
  "active_models": {
    "anomaly_detection": "Stage 1 rolling z-score (SAR + water quality)",
    "u_net_segmentation_accuracy": "91.00% IoU (Verified Step 14)",
    "multi_modal_classifier": "Bayesian Sensor Fusion (Verified Step 15)",
    "hydrodynamic_trajectory_engine": "30-Day Lagrangian Tracker (Verified Step 16)",
    "cleanup_priority_matrix": "8-Factor Multi-Criteria Evaluation (Verified Step 17)"
  },
  "database_counts": { /* same as /api/v1/stats */ },
  "background_scheduler": { "status": "active", "interval_seconds": 3600, "endpoint": "POST /api/v1/admin/refresh" }
}
```

---

### 3.2 Pollution incidents

#### `GET /api/v1/incidents`
**Purpose:** Ranked "Index Data" table of all active incidents, filterable client-side.
**Query params (all optional):**
- `status` — exact match on incident status (e.g. `active`)
- `type` — exact match on `pollution_type` (e.g. `oil_hydrocarbon`, `river_sediment`)
- `min_priority` / `max_priority` — numeric `priority_score` bounds
- `limit` — default 100, max 1000

**Response:**
```jsonc
{
  "status": "success",
  "data_type": "pollution_index",
  "returned": 4,
  "incidents": [ /* incident objects, see 3.2.1 */ ]
}
```

#### 3.2.1 The `incident` object (used in many endpoints)
```jsonc
{
  "incident_id": "SPILL_2026_001_BAKU_HARBOR",
  "location_name": "Baku Offshore Oil Sector (Nearshore Bay)",
  "coordinates_lat": 40.38,          // WGS84 latitude
  "coordinates_lon": 50.05,          // WGS84 longitude
  "pollution_type": "oil_hydrocarbon", // oil_hydrocarbon | river_sediment | coastal_plastic ...
  "size_km2": 18.5,
  "toxicity_score": 1.0,             // 0..1
  "severity_index": null,            // nullable
  "detection_confidence": 0.96,      // 0..1
  "priority_score": 78.1,            // higher = more urgent (drives global ranking)
  "urgency_classification": "CRITICAL EMERGENCY - IMMEDIATE COASTAL CONTAINMENT REQUIRED",
  "coastline_distance_m": 1200.0,
  "population_density_sqkm": 2800.0,
  "in_protected_ecosystem_zone": 0, // 0 | 1
  "economic_impact_estimate_usd": 2500000.0,
  "forecast_spread_rate_km2_day": 3.8,
  "status": "active",                 // status_filter target
  "detected_at": "2026-..."           // ISO timestamp
}
```
**Frontend use:** incident map markers, ranked leaderboard, detail drill-down.

#### `GET /api/v1/incidents/{incident_id}`
**Purpose:** Full incident detail with its forecast frames, oil&gas risk scores, and energy
impact rows all in one call (single round-trip for a detail page).
**Special value:** `{incident_id}` may be `index` → returns the raw ranked index table.

```jsonc
{
  "status": "success",
  "incident": { /* Incident object */ },
  "forecasts":   [ /* ForecastFrame, see 3.4 */ ],
  "risk_scores": [ /* enriched RiskScore, see 3.5 */ ],
  "energy_impact":[/* EnergyImpact, see 3.6 */ ]
}
```

#### `GET /api/v1/incidents/{incident_id}/forecast`
**Purpose:** just the 30-day forecast animation frames for one incident (time-lapse overlay).

#### `GET /api/v1/incidents/{incident_id}/risk`
**Purpose:** risk scores for one incident, already enriched with the matching `asset` catalog
object on each row (`{...risk, "asset": {...}}`). Use for the per-incident infrastructure
risk panel.

---

### 3.3 Energy impact

#### `GET /api/v1/energy-impact`
**Purpose:** economic/energy benefit summary per incident (Stage 5).
**Response:** keys = `incident_id`; each value:
```jsonc
{
  "incident": { /* Incident object */ },
  "asset_breakdown": [ /* EnergyImpact rows */ ],
  "totals": {
    "assets": 2,
    "maintenance_savings_usd": 18200000,
    "disruption_avoided_usd": 15500000,
    "carbon_avoided_tons_co2e": 420.5
  }
}
```

#### 3.3.1 The `EnergyImpact` object
```jsonc
{
  "impact_id": 1, "incident_id": "SPILL_...", "asset_id": "PLAT_NEET_DASHLARI",
  "infrastructure_protection": 0.78,        // 0..1 fraction of asset shielded
  "maintenance_savings_usd": 9100000.0,
  "avoided_downtime_hours": 180.0,
  "operational_disruption_avoided_usd": 7750000.0,
  "environmental_benefit": "string",
  "carbon_impact_tons_co2e": 210.25,
  "energy_impact_score": 83.45,             // overall usefulness score
  "computed_at": "ISO timestamp"
}
```
> Frontend: use `totals` for KPIs; `asset_breakdown` for the per-asset bar chart.

---

### 3.4 Oil & Gas risk & infrastructure

#### `GET /api/v1/oil-gas/risk`
**Purpose:** global per-asset risk rank list (highest risk first) with filters.
```jsonc
{
  "status":"success","data_type":"oil_gas_risk","returned":42,
  "risk_scores":[ { ...RiskScore, "asset": {Asset} } ]   // sorted risk_score DESC
}
```
Query params (optional): `country`, `category`, `limit` (default 200).

#### 3.4.1 The `RiskScore` object
```jsonc
{
  "risk_id": 1, "incident_id": "SPILL_...", "asset_id": "PLAT_NEET_DASHLARI",
  "distance_km": 27.75,
  "arrival_days": 3.3,            // how many days until slick reaches asset
  "threat_level": "CRITICAL",     // LOW | MODERATE | HIGH | CRITICAL
  "risk_score": 82.86,            // 0..100
  "inspection_priority": "IMMEDIATE", // IMMEDIATE | SHORT-TERM | MONITOR
  "computed_at": "ISO"
}
```

#### `GET /api/v1/assets`
**Purpose:** infrastructure catalog (platforms, ports, pipelines, refineries, renewables).
`?category=` filters. Response: `{ "status","assets":[Asset],"count":n }`.
**Notes will be on count** `.count` for totals; `assets` for markers.

#### 3.4.2 The `Asset` object
```jsonc
{
  "asset_id": "PLAT_NEET_DASHLARI",
  "name": "Neft Daslari (Oil Rocks)",
  "category": "offshore_platform",  // offshore_platform | pipeline | port | refinery | renewable ...
  "subcategory": "...",
  "country": "Azerbaijan",          // Kazakhstan | Azerbaijan | Russia | Iran | Turkmenistan
  "coordinates_lat": 40.0, "coordinates_lon": 50.0,
  "replacement_value_usd": 1000000000.0,
  "description": "..."
}
```

---

### 3.5 Heatmap, stats, trends, anomalies, timeline

#### `GET /api/v1/stats`
**Purpose:** single object with everything for overview KPIs.
```jsonc
{
  "status":"success",
  "stats": {
    "incidents":4,"forecast_frames":5,"anomaly_masks":24,"risk_scores":42,
    "energy_impacts":42,"infrastructure_assets":23,"heatmap_cells":100,
    "weather_records":18,"max_priority_score":78.1,
    "incidents_by_type": {"oil_hydrocarbon":3,"river_sediment":1},
    "total_maintenance_savings_usd":359205953.0,
    "total_disruption_avoided_usd":231416665.0
  }
}
```

#### `GET /api/v1/trends/sea-level`
**Purpose:** Caspian sea-level change series (for time-series chart).
Each record: `{"period", "level_cm", "change_cm", "trend"}` — `trend` is textual label.

#### `GET /api/v1/trends`
**Purpose:** the full Casual Trend Panel in one call.
```jsonc
{
  "status":"success","data_type":"caspian_trend_panel",
  "sea_level":        [ ...same as /sea-level ],
  "exposed_area":     [ TrendRow... ],
  "pollution_statistics":[ TrendRow... ],
  "projections":      [ TrendRow... ]
}
```
`TrendRow`: `{"trend_id", "metric", "period_start", "period_end", "value", "category"}`.

#### `GET /api/v1/anomalies?week=YYYY-MM-DD`
**Purpose:** Stage-1 weekly anomaly mask patches (from SAR + water-quality z-scores).
Each row:
```jsonc
{"anomaly_id":1, "week_start":"2026-...", "coordinates_lat":.., "coordinates_lon":..,
 "sar_z_score":.., "water_quality_z_score":.., "chlorophyll":.., "turbidity":.., "cdom":..,
 "sar_anomaly":true, "water_quality_anomaly":false, "confidence":..,
 "predicted_type":"zwater_outflow"}
```
Pass `week` to render a single-week heat patch; omit to get all weeks.

#### `GET /api/v1/timeline`
**Purpose:** a flat event list across forecast milestones for building a timeline.
```jsonc
{ "status":"success","events":[ { incident + forecast-frame fields below } ],"count":n }
```
Event fields: `incident_id, location_name, pollution_type, priority_score, forecast_day,
horizon_week, centroid_lat, centroid_lon, dispersion_radius_km, spread_area_km2,
remaining_mass_tons, active_fraction, beached_fraction`.
Params: `incident_id`, `start_day`, `end_day` (0..35).

#### `GET /api/v1/weather?limit=`
**Purpose:** weather/rainfall history. Records:
```jsonc
{"record_id":1, "observed_at":"ISO", "coordinates_lat":43.65, "coordinates_lon":51.26,
 "wind_speed_ms":12.7, "wind_direction_deg":295.0, "rainfall_mm":0.0,
 "sea_surface_temp_c":27.1, "source":"open-meteo-live"}
```
> `source` = `open-meteo-live` (live) or `synthetic-fallback` (offline). Show a freshness badge.

---

### 3.6 Prediction maps & heatmap (legacy / animation)

#### `GET /api/v1/forecast/trajectory/{incident_id}`
**Purpose:** 30-day Lagrangian drift animation data for a Slideshow / Mapbox / Leaflet
time-lapse slider (legacy checkpoint stream).
```jsonc
{ "status":"success", "data_type":"prediction_map_trajectory", "incident_id":"SPILL_...",
  "simulation_metadata": {"origin_coordinates":[40.35,50.45], "total_duration_days":30, "particle_count":500, ...},
  "animation_frames":[ {"step":0,"day":0.0,"active_":"particles"...},{"step":1,...} ] }
```
`animation_frames[i]` per frame: `step, day, active_particles, beached_particles,
remaining_floating_oil_tons, centroid_lat, centroid_lon, dispersion_radius_km`.
(defaults to `SPILL_2026_001_BAKU_HARBOR` if no id).

#### `GET /api/v1/heatmap/grid`
**Purpose:** 2D regional risk heatmap matrix (checkpoint). `grid_cells[i]`:
```jsonc
{ "cell_id":"CASPIAN_GRID_0036",
  "coordinates_center":[40.245,50.735], "bounding_box":[39.71,50.35, 40.78,51.12],
  "threating_gravity_severity_score":62.79, "zone_classification":"ELEVATED RISK CORRIDOR ...",
  "layer_breakdown": { ... named risk layers } }
```

---

### 3.7 Admin / integration (do NOT expose these to end users)

#### `POST /api/v1/admin/refresh`
Recompute all analysis stages (risk, energy, trend, anomaly) + ingest weather; returns the
refresh result dict. 500 on failure.
**Body (optional, typed):** `{"recompute_weather": true}` — set `false` to skip the weather pass.
Calling with `{}` or no body is fully supported (backwards compatible).

#### `POST /api/v1/admin/weather`
Live weather/rain ingestion only.

---

### 3.8 Live / segmentation (Future)

#### `POST /api/v1/detect/segment`
**Purpose:** live SAR segmentation probe.
**Body (typed schema):**
```jsonc
{ "scene_id": "S1A_IW_GRD_BAKU_2026", "latitude": 40.4, "longitude": 50.3 }
```
All three fields are optional (defaults `"LIVE_SAR_OBSERVATION_CASPIAN"`, `40.35`, `50.45`);
`latitude`/`longitude` are range-validated (`±90` / `±180`) — invalid values return HTTP `422`.
**Response:** `{ "status":"success", "scene_id":..., "segmentation_result": { "anomaly_detected":true,
"predicted_class":"oil_hydrocarbon","ai_confidence":95.8,
"polygon_boundary_geojson":{Polygon GeoJSON}, "recommended_action":"..." } }`
> The returned `polygon_boundary_geojson` is already GeoJSON — draw it directly on the map.

---

## 4. Frontend checklist / recommendations

1. **Models/Fetch strategy (SSR vs CSR):**
   - Use a typed fetch layer; map every response shape above into TS/JS interfaces to avoid
     stringly drift. This doc's JSON samples are copy-paste-able type seeds.
2. **Map layers recommended:**
   - Incident markers ← `/api/v1/incidents` (and `/incidents/{id}` for popups)
   - Asset icons ← `/api/v1/assets`
   - Drift animation slider ← `/forecast/trajectory/{id}` (loop over `animation_frames`)
   - Regional heat overlay ← `/heatmap/grid` (map `threat_severity_score` to a color ramp)
   - Anomaly weekly layer ← `/anomalies?week=` (add a week picker)
3. **Live-ish dashboards:**
   - Sea level / trends ← `/trends`, `/trends/sea-level` (time-series charts)
   - Timeline ← `/timeline` (interval scrubber `start_day`/`end_day`)
4. **Polling plan (no websocket):** the backend has a background scheduler but no push API.
   - Poll `/health` or `/stats` every 10–30 s.
   - Call `POST /admin/refresh` when a demo user clicks "Refresh data" — then re-fetch
     dashboards.
5. **Error handling:** handle HTTP 404 `{"detail"}`; treat non-200 `status` gracefully; show some
   placeholder states (the backend returns `{"status":"success"}` over empty arrays, so empty
   arrays are the honest "no data yet" signal).

---

## 5. Data semantics cheat-sheet

| Field | Meaning | Typical/units |
|---|---|---|
| `priority_score` | global urgency score | 0..100 (higher=more urgent, sort desc) |
| `risk_score` (oil) | per-asset risk | 0..100 |
| `energy_impact_score` | benefit of protecting asset | 0..100 |
| `threat_level` | TEXT | LOW/MODERATE/HIGH/CRITICAL |
| `urgency_classification` | TEXT label | free text control |
| `coordinates_*` | WGS84 (EPSG:4326) | decimal degrees |
| money fields | USD | float |

---

## 6. Quick verify script (for frontend smoke test)

Fire every endpoint; expect 200.
```
GET  /
GET  /api/v1
GET  /api/v1/health
GET  /api/v1/incidents                       (+ ?status=&type=&min/max_priority=&limit=)
GET  /api/v1/incidents/{id}
GET  /api/v1/incidents/{id}/forecast
GET  /api/v1/incidents/{id}/risk
GET  /api/v1/energy-impact
GET  /api/v1/oil-gas/risk?country=&category=&limit=
GET  /api/v1/stats
GET  /api/v1/trends/sea-level
GET  /api/v1/trends
GET  /api/v1/anomalies?week=
GET  /api/v1/timeline
GET  /api/v1/weather
GET  /api/v1/forecast/trajectory/SPILL_2026_001_BAKU_HARBOR
GET  /api/v1/heatmap/grid
POST /api/v1/detect/segment   {"latitude":40.4,"longitude":50.3}
POST /api/v1/admin/refresh    {}
POST /api/v1/admin/weather    {}
```
*(All of the above have been verified to return `200 OK` against the current build — count was
 20 routes.)*