You are a senior geospatial data engineer and machine-learning dataset engineer.

Your task is to design and implement a complete, reproducible Python pipeline for collecting, processing, aligning, validating, documenting, and exporting a multimodal dataset for marine pollution and oil-spill detection.

The dataset will later be used for:

* CNN-based satellite-image classification
* Semantic segmentation of pollution and oil-spill regions
* Multimodal models combining satellite imagery with weather, ocean, vessel, coastline, and infrastructure data
* Spatial and temporal risk prediction
* Train, validation, and test experiments

The solution must use free or genuinely open data sources wherever possible. Never silently use a paid API, commercial dataset, unofficial scraper, or source whose licence does not permit the intended use.

## 1. Primary data sources

Implement adapters for the following sources.

### 1.1 Sentinel-1

Primary source:

* Copernicus Data Space Ecosystem

Required products:

* Sentinel-1 GRD
* Prefer IW acquisition mode for coastal and open-sea oil-spill analysis
* VV polarization
* VH polarization where available
* Product metadata
* Orbit information
* Incidence-angle information
* Acquisition start and end time
* Relative orbit number
* Processing level
* Product identifier
* Platform name
* Footprint
* Instrument mode
* Pass direction
* Pixel spacing and resolution
* Processing baseline when available

Use Sentinel-1 as the main radar source because synthetic-aperture radar can operate during day or night and through cloud cover.

Support:

* Search by bounding box or polygon
* Search by date range
* Search by product type
* Search by polarization
* Search by orbit direction
* Search by relative orbit
* Cloud-independent acquisition filtering
* Local caching
* Resume after interruption
* Checksum validation
* Duplicate detection

Implement authentication using environment variables or a local `.env` file.

Never hardcode usernames, passwords, refresh tokens, or access tokens.

Supported access methods may include:

* Copernicus Data Space catalogue APIs
* OData
* STAC
* Sentinel Hub APIs where their free-use conditions permit the intended workload

Prefer open standards and the simplest stable official API.

### 1.2 Sentinel-3

Primary source:

* Copernicus Data Space Ecosystem

Candidate products:

* SLSTR sea-surface-temperature products
* OLCI ocean-colour products
* Relevant Level-1 or Level-2 products
* Chlorophyll or water-quality variables where useful
* Quality flags
* Cloud masks
* Acquisition geometry
* Observation timestamp
* Product identifier
* Footprint
* Processing level

Sentinel-3 data should not be treated as having the same spatial resolution as Sentinel-1.

Do not resize Sentinel-3 imagery and pretend that it has Sentinel-1-level detail. Preserve its original resolution and record every resampling operation.

### 1.3 Atmospheric weather

Primary source:

* Open-Meteo Historical Weather API or Archive API

Collect variables such as:

* Precipitation
* Rain
* Wind speed at 10 metres
* Wind direction at 10 metres
* Wind gusts
* Surface pressure
* Air temperature
* Relative humidity
* Cloud cover
* Visibility where available
* Weather-code information where useful

Requirements:

* Use UTC internally.
* Record the exact Open-Meteo model or upstream reanalysis dataset selected.
* Do not rely on an automatic “best match” model without recording which model supplied each result.
* Record the source model, grid resolution, temporal resolution and retrieval timestamp.
* Preserve raw API responses.
* Store attribution and licence information.
* Mark Open-Meteo free-tier data as non-commercial unless the licence currently attached to the selected endpoint explicitly allows the intended use.
* Implement configurable rate limiting and retries.
* Do not exceed published free-tier limits.

Open-Meteo historical data may come from reanalysis rather than direct measurements. Record this clearly in dataset metadata.

### 1.4 Ocean variables

Primary source:

* Copernicus Marine Service and Copernicus Marine Data Store

Use the official Copernicus Marine Toolbox or Python API where possible.

Collect variables such as:

* Sea-surface temperature
* Zonal surface-current velocity, `u`
* Meridional surface-current velocity, `v`
* Current speed
* Current direction
* Sea-surface height
* Wave height where available
* Wave direction where available
* Surface salinity where useful
* Mixed-layer depth where useful

For every variable, record:

* Product ID
* Dataset ID
* Dataset version
* Variable name
* Units
* Horizontal resolution
* Vertical level
* Temporal resolution
* Observation, analysis or forecast status
* Model or observation origin
* Timestamp
* Quality flags
* Retrieval date
* Licence
* Citation requirements

Prefer observation or reanalysis products for historical model training.

Do not mix forecasts and reanalysis values without an explicit field describing their data type.

### 1.5 Coastline, ports and static geospatial context

Candidate free sources:

* OpenStreetMap through Overpass API
* EMODnet for European marine areas
* Official national open-data portals when their licences permit reuse

Collect:

* Coastline geometry
* Shoreline geometry
* Ports
* Harbours
* Terminals
* Marinas
* Refineries
* Storage facilities
* Industrial coastal facilities
* Offshore platforms
* Oil and gas wells where available
* Pipelines
* Shipping lanes or mapped routes
* Marine protected areas where useful
* Country boundaries
* Exclusive economic zones where licensing permits

For OpenStreetMap-derived data:

* Preserve the OpenStreetMap attribution.
* Record that the data is under ODbL.
* Record the Overpass query.
* Record the retrieval timestamp.
* Store the original OSM identifiers and tags.
* Do not imply that OpenStreetMap infrastructure records are complete or authoritative.

For EMODnet-derived products:

* Preserve the individual dataset’s source, update date and licence.
* Do not assume all underlying datasets have identical coverage or reliability.
* Clearly distinguish European coverage from global coverage.

### 1.6 Shipping and vessel activity

Preferred source:

* Global Fishing Watch APIs and downloadable public datasets, subject to their current API and dataset terms

Potential data:

* Aggregated vessel presence
* Vessel events
* Vessel tracks where publicly available
* Fishing and non-fishing activity
* AIS-derived activity summaries
* Vessel identity information where permitted
* Sentinel-1-based vessel detections where available
* AIS-matched and unmatched SAR vessel detections

Important restrictions:

* Do not claim that raw global AIS messages are freely available if they are not.
* Do not scrape commercial AIS websites.
* Do not bypass authentication, quotas or download restrictions.
* Store only fields allowed by the source’s terms.
* Record whether data represents raw AIS, processed AIS, gridded vessel presence, inferred activity or SAR vessel detection.
* Record AIS limitations such as reception gaps, disabled transponders, spoofing, inaccurate identities and incomplete small-vessel coverage.

If Global Fishing Watch does not provide data suitable for a requested region or period, create a clean adapter interface and document the missing source rather than inventing data.

### 1.7 Oil infrastructure

Candidate sources:

* EMODnet Human Activities for European waters
* OpenStreetMap
* Global Energy Monitor datasets where their current licence and access process permit use
* National open-data portals
* Government offshore-energy registries

Collect where legally available:

* Offshore platforms
* Oil fields
* Gas fields
* Extraction sites
* Refineries
* Storage terminals
* Crude-oil pipelines
* Petroleum-product pipelines
* LNG terminals where relevant
* Facility operating status
* Facility coordinates or geometry
* Source confidence
* Last update date

Never merge infrastructure data without preserving its original source identifier.

A location inferred from a map, article, satellite image or approximate project description must not be marked as a verified coordinate.

Use fields such as:

* `geometry_accuracy`
* `location_confidence`
* `location_method`
* `source_authority`
* `last_verified_at`

## 2. Pollution labels and masks

The pipeline must support multiple label sources.

Possible label sources include:

* Expert-drawn oil-spill polygons
* Government incident records
* Copernicus Emergency Management products
* CleanSeaNet-related public products where legally available
* Published research datasets
* Human annotation
* Weak labels derived from incident reports
* Candidate detections produced by an algorithm
* Negative examples selected from appropriate control regions

Never treat all label types as equally trustworthy.

Every label must have:

* `label_id`
* `scene_id`
* `class_id`
* `class_name`
* `geometry`
* `label_source`
* `source_record_id`
* `source_url_or_identifier`
* `annotation_method`
* `annotator_type`
* `annotation_timestamp`
* `label_confidence`
* `verification_status`
* `number_of_reviewers`
* `inter_annotator_agreement`, when available
* `incident_date`
* `incident_time_uncertainty`
* `spatial_uncertainty_m`
* `temporal_uncertainty_minutes`
* `is_weak_label`
* `is_machine_generated`
* `quality_notes`
* `licence`
* `citation`

### 2.1 Initial label classes

Make the class ontology configurable rather than hardcoding it throughout the code.

Use an initial ontology such as:

* `0: background_water`
* `1: confirmed_mineral_oil_spill`
* `2: probable_mineral_oil_spill`
* `3: look_alike`
* `4: natural_biogenic_slick`
* `5: algal_bloom_or_ocean_front`
* `6: low_wind_area`
* `7: vessel`
* `8: land`
* `9: cloud_or_invalid_optical_pixel`
* `10: unknown_or_unreviewed`

Explain the intended meaning of every class in a machine-readable `label_ontology.yaml`.

Do not force uncertain observations into the confirmed-oil class.

### 2.2 Label confidence

Use a configurable confidence system such as:

* `verified`: confirmed by a reliable authority or multiple expert sources
* `high`: expert annotation supported by contextual evidence
* `medium`: probable spill but not fully confirmed
* `low`: weak label or automatic candidate
* `unknown`: insufficient provenance

Keep confidence separate from class.

For example, `probable_mineral_oil_spill` is a semantic class, while `medium` is confidence in that annotation.

### 2.3 Mask generation

Generate segmentation masks only after:

* Reprojecting the annotation into the image CRS
* Validating polygon geometry
* Clipping to the image footprint
* Recording the rasterization resolution
* Recording `all_touched`
* Recording overlap rules
* Recording class-priority rules

Preserve both:

* Original vector annotations
* Rasterized masks

Supported formats:

* GeoJSON or GeoPackage for vectors
* GeoTIFF for georeferenced masks
* PNG masks only as an additional training representation

Never use JPEG for categorical masks.

## 3. Sentinel-1 preprocessing

Implement a configurable preprocessing pipeline.

Candidate operations:

1. Apply precise orbit information where available.
2. Remove thermal noise.
3. Calibrate to sigma-nought or gamma-nought.
4. Convert to decibels where configured.
5. Apply speckle filtering only as an optional experiment.
6. Perform terrain correction.
7. Mask invalid border noise.
8. Reproject to the selected target CRS.
9. Clip to the area of interest.
10. Generate consistent image tiles.
11. Compute optional derived channels.

Possible channels:

* VV
* VH
* VV in dB
* VH in dB
* VV/VH ratio
* VV minus VH in dB
* Local texture statistics
* Incidence angle
* Land mask
* Distance to coastline
* Distance to nearest vessel
* Distance to nearest platform

Preserve the raw product.

Never overwrite raw data with processed data.

Every preprocessing operation must be captured in a processing manifest containing:

* Operation name
* Software library
* Software version
* Parameters
* Input checksum
* Output checksum
* Start time
* End time
* Warnings
* Failure status

Preferred tools may include:

* `rasterio`
* `rioxarray`
* `xarray`
* `geopandas`
* `shapely`
* `pyproj`
* `numpy`
* `scipy`
* GDAL
* ESA SNAP through a command-line adapter when genuinely needed

Avoid requiring SNAP for every operation if a reliable pure-Python or GDAL-based method exists.

## 4. Spatial and temporal alignment

Every satellite scene must be linked to matching contextual records.

Use the satellite acquisition midpoint as the default reference timestamp:

`scene_time = acquisition_start + (acquisition_end - acquisition_start) / 2`

Store:

* Acquisition start
* Acquisition end
* Midpoint
* Source timezone
* Normalized UTC timestamp

### 4.1 Weather matching

For each satellite scene:

* Retrieve or select weather records around the acquisition time.
* Prefer the closest available hourly record.
* Optionally support interpolation between adjacent time steps.
* Store the original timestamps used.
* Store the absolute time difference.
* Store whether interpolation was used.
* Store the interpolation method.
* Reject or flag records outside a configurable threshold.

Suggested default thresholds:

* Preferred weather difference: no more than 30 minutes
* Acceptable weather difference: no more than 90 minutes
* Otherwise: mark as unmatched

These values must be configurable.

### 4.2 Ocean-current and SST matching

For each scene:

* Select the ocean product that covers the image footprint and timestamp.
* Record whether the value is instantaneous, hourly, daily mean or model analysis.
* Preserve the product’s native grid.
* Interpolate to satellite pixels only in a derived output.
* Store the interpolation method.
* Do not imply that a daily-mean current field precisely represents the current at the satellite acquisition minute.

Suggested fields:

* `current_time_before`
* `current_time_after`
* `current_time_delta_minutes`
* `current_interpolated`
* `current_temporal_resolution`
* `current_product_type`
* `sst_time_delta_minutes`
* `sst_interpolated`
* `ocean_match_quality`

### 4.3 Vessel matching

For vessel records:

* Use a configurable time window around the satellite acquisition.
* Keep original vessel timestamps.
* Interpolate positions only when mathematically justified.
* Do not interpolate across long AIS gaps.
* Record the gap duration.
* Store vessel-to-pixel and vessel-to-spill distances.
* Store whether a vessel track intersects or approaches a candidate spill.
* Do not label a vessel as the pollution source based only on proximity.

### 4.4 Spatial alignment

Use a consistent geospatial convention:

* Longitude/latitude storage in EPSG:4326
* Local projected CRS for distance and area calculations
* Explicit axis order
* Explicit pixel origin
* Explicit affine transform
* Explicit nodata value

For every resampled raster, record:

* Source CRS
* Target CRS
* Source resolution
* Target resolution
* Resampling method
* Source dimensions
* Target dimensions

Use nearest-neighbour resampling for categorical masks.

Use bilinear or another justified method for continuous environmental variables.

## 5. Dataset tiling

Build configurable geospatial tiles.

Suggested defaults:

* Tile size: 256×256 or 512×512 pixels
* Configurable ground sampling distance
* Configurable overlap
* Consistent CRS within a dataset version
* Minimum valid-water percentage
* Optional minimum positive-mask percentage

For every tile, save:

* Tile ID
* Parent scene ID
* Bounding box
* Polygon footprint
* CRS
* Affine transform
* Pixel resolution
* Channels
* Mask path
* Positive-pixel count
* Class histogram
* Water percentage
* Land percentage
* Invalid-pixel percentage
* Environmental feature record
* Vessel-context record
* Infrastructure-context record
* Split assignment
* Source and licence references

Do not discard all empty-mask tiles.

Generate a controlled and documented negative dataset.

Negative tiles should include:

* Normal open water
* Coastal water
* Harbours
* Low-wind areas
* Natural slick-like patterns
* Algal or ocean-front patterns
* Vessel wakes
* Rain-cell effects where observable
* Different seasons
* Different sea states

Prevent easy shortcuts where all positive samples come from one country, year, orbit or sensor-processing version.

## 6. Train, validation and test splitting

Do not perform a naive random tile split.

Adjacent tiles from the same scene must not appear in different splits.

Implement grouped splitting using one or more of:

* Incident ID
* Original satellite product ID
* Acquisition date
* Geographic region
* Spatial grid cell
* Orbit
* Platform
* Annotating organisation

Recommended strategy:

* Training: earlier incidents and selected regions
* Validation: held-out incidents and spatial groups
* Test: entirely held-out incidents, regions or time periods

Support at least these split modes:

* `group_by_scene`
* `group_by_incident`
* `spatial_holdout`
* `temporal_holdout`
* `region_holdout`
* `combined_spatiotemporal_holdout`

Generate a leakage report that checks for:

* Same Sentinel product in multiple splits
* Overlapping tile footprints across splits
* Same incident in multiple splits
* Near-duplicate imagery across splits
* Same label geometry in multiple splits
* Same vessel event duplicated across splits
* Strong spatial proximity between test and training samples
* Temporal adjacency that could make the test set trivial

Store split rules and random seeds in a versioned configuration file.

## 7. Provenance and licences

Create a machine-readable source registry.

Suggested file:

`metadata/source_registry.yaml`

For every source, include:

* Source name
* Provider
* Dataset or product name
* Official identifier
* Access method
* API or download interface
* Licence name
* Licence version
* Attribution text
* Commercial-use status
* Redistribution status
* Modification status
* Share-alike requirements
* Account requirement
* API-key requirement
* Rate limits
* Geographic coverage
* Temporal coverage
* Spatial resolution
* Temporal resolution
* Retrieval timestamp
* Source version
* Citation
* Known limitations
* Terms last checked
* Terms-document checksum or archived text reference

Do not guess a licence.

If the licence cannot be verified:

* Mark the source as `licence_status: unresolved`.
* Do not include it in a redistributable dataset.
* Allow it only in a quarantined research area.
* Produce a warning in the final report.

Keep source-data licences separate from software licences.

## 8. Dataset manifests

Produce these outputs:

* `dataset_manifest.parquet`
* `scenes.parquet`
* `tiles.parquet`
* `labels.parquet`
* `environment.parquet`
* `vessels.parquet`
* `infrastructure.parquet`
* `source_registry.yaml`
* `label_ontology.yaml`
* `split_manifest.parquet`
* `quality_report.json`
* `licence_report.md`
* `dataset_card.md`
* `known_issues.md`
* `checksums.sha256`

The main dataset manifest should link all modalities using stable identifiers.

Suggested keys:

* `scene_id`
* `tile_id`
* `incident_id`
* `label_id`
* `weather_record_id`
* `ocean_record_id`
* `vessel_context_id`
* `infrastructure_context_id`
* `dataset_version`

Do not use local file paths as permanent IDs.

## 9. Dataset card

Automatically generate a dataset card explaining:

* Dataset purpose
* Intended ML tasks
* Geographic coverage
* Temporal coverage
* Satellite products
* Weather sources
* Ocean sources
* Shipping sources
* Infrastructure sources
* Label classes
* Label-creation process
* Label confidence
* Known class ambiguity
* Preprocessing
* Spatial alignment
* Temporal alignment
* Train/validation/test split
* Leakage controls
* Missing-data patterns
* Quality-control results
* Licences
* Attribution requirements
* Ethical and legal limitations
* Recommended uses
* Prohibited or unreliable uses
* Dataset version
* Code commit hash
* Reproduction command

Explicitly state that dark regions in SAR imagery are not automatically oil spills. Look-alikes may be caused by low wind, natural films, biological activity, rain cells, currents, ocean fronts and other phenomena.

## 10. Quality assurance

Implement automated checks for:

* Corrupt downloads
* Missing metadata
* Duplicate scenes
* Duplicate tiles
* Invalid geometries
* CRS mismatches
* Misaligned masks
* Empty masks
* Masks outside scene boundaries
* Impossible latitude or longitude
* Invalid timestamps
* Future timestamps in historical data
* Weather records outside matching thresholds
* Ocean records outside matching thresholds
* Unexpected units
* NaN percentages
* Extreme raster values
* Invalid class IDs
* Missing licence records
* Cross-split leakage
* Excessive class imbalance
* Geographic imbalance
* Seasonal imbalance
* Sensor and orbit imbalance
* Infrastructure records without provenance
* Vessel tracks with unrealistic speed jumps

Produce both:

* Machine-readable quality output
* Human-readable quality report

Do not hide failed checks.

## 11. Reliability scoring

Create reliability fields separately for each modality:

* `satellite_quality_score`
* `label_quality_score`
* `weather_match_score`
* `ocean_match_score`
* `vessel_data_quality_score`
* `infrastructure_quality_score`
* `overall_sample_quality_score`

Do not calculate the overall score as an unexplained average.

Document the formula and allow it to be configured.

Samples with weak labels or poor temporal matching should remain identifiable so researchers can:

* Exclude them
* Weight them differently
* Use them for semi-supervised learning
* Use them only in exploratory experiments

## 12. Software architecture

Use a modular Python package structure such as:

```text
marine_dataset/
    pyproject.toml
    README.md
    .env.example
    configs/
        default.yaml
        regions/
        sources/
    src/
        marine_dataset/
            cli.py
            config.py
            logging_config.py
            identifiers.py
            storage.py
            provenance.py
            licences.py
            schemas.py
            sources/
                copernicus_dataspace.py
                sentinel1.py
                sentinel3.py
                open_meteo.py
                copernicus_marine.py
                global_fishing_watch.py
                osm_overpass.py
                emodnet.py
                oil_infrastructure.py
            processing/
                sentinel1.py
                sentinel3.py
                raster.py
                vector.py
                masks.py
                tiling.py
            alignment/
                temporal.py
                spatial.py
                weather.py
                ocean.py
                vessels.py
            labels/
                ontology.py
                importers.py
                rasterize.py
                quality.py
            splitting/
                grouped.py
                spatial.py
                temporal.py
                leakage.py
            validation/
                checks.py
                reports.py
            manifests/
                builder.py
                dataset_card.py
    tests/
        unit/
        integration/
        fixtures/
```

## 13. Command-line interface

Create commands similar to:

```bash
marine-data init-config
marine-data search-sentinel1 --config configs/default.yaml
marine-data download-sentinel1 --config configs/default.yaml
marine-data search-sentinel3 --config configs/default.yaml
marine-data download-sentinel3 --config configs/default.yaml
marine-data collect-weather --config configs/default.yaml
marine-data collect-ocean --config configs/default.yaml
marine-data collect-vessels --config configs/default.yaml
marine-data collect-infrastructure --config configs/default.yaml
marine-data import-labels --config configs/default.yaml
marine-data preprocess --config configs/default.yaml
marine-data align --config configs/default.yaml
marine-data tile --config configs/default.yaml
marine-data split --config configs/default.yaml
marine-data validate --config configs/default.yaml
marine-data build-manifest --config configs/default.yaml
marine-data build-dataset-card --config configs/default.yaml
marine-data run-all --config configs/default.yaml
```

Commands must:

* Be restartable
* Be idempotent where practical
* Log progress
* Produce clear error messages
* Support dry-run mode
* Support region and date filters
* Avoid redownloading valid existing files
* Store failed records for retry
* Exit with a non-zero code when critical validation fails

## 14. Storage format

Use:

* GeoTIFF or cloud-optimized GeoTIFF for geospatial rasters
* GeoPackage, GeoParquet or GeoJSON for vector data
* Parquet for tabular manifests
* NetCDF or Zarr for multidimensional ocean and weather grids
* YAML for human-editable configuration
* JSON for machine-readable reports

Create directories such as:

```text
data/
    raw/
        sentinel1/
        sentinel3/
        weather/
        ocean/
        vessels/
        infrastructure/
        labels/
    interim/
    processed/
        scenes/
        tiles/
        masks/
        environmental_grids/
    manifests/
    reports/
    cache/
    quarantine/
```

The `raw` directory must be immutable from the pipeline’s perspective.

## 15. Configuration

All important values must be configurable, including:

* Geographic regions
* Date ranges
* Satellite product types
* Polarizations
* Orbit direction
* Tile size
* Target resolution
* Target CRS
* Temporal matching thresholds
* Vessel matching window
* Weather variables
* Ocean variables
* Label ontology
* Negative-sampling ratio
* Split strategy
* Random seed
* Concurrency
* Rate limits
* Retry policy
* Storage paths
* Compression
* Quality thresholds

Provide a documented sample configuration.

## 16. Engineering requirements

Use:

* Python 3.11 or newer
* Type hints
* Pydantic or equivalent schema validation
* Structured logging
* Unit tests
* Integration tests using small fixtures
* Retry with exponential backoff
* HTTP timeouts
* Rate limiting
* Connection pooling
* Checksums
* Dependency pinning
* Reproducible environments
* Clear exception classes

Avoid:

* Notebook-only implementation
* Hardcoded geographic regions
* Hardcoded credentials
* Silent exception handling
* Unbounded concurrency
* Saving everything as CSV
* Guessing missing metadata
* Fabricating unavailable labels
* Treating model outputs as ground truth
* Assuming every dark SAR patch is pollution

## 17. Deliverables

Generate:

1. A concise architecture explanation.
2. A complete project tree.
3. `pyproject.toml`.
4. Configuration schemas.
5. A sample `default.yaml`.
6. Source-adapter interfaces.
7. Working Sentinel-1 search and download implementation.
8. Working Sentinel-3 search and download implementation.
9. Working Open-Meteo historical-weather collector.
10. Working Copernicus Marine SST and surface-current collector.
11. Initial OpenStreetMap or EMODnet infrastructure collector.
12. A Global Fishing Watch adapter if authorised API access is available.
13. Label-import and mask-generation modules.
14. Temporal and spatial alignment modules.
15. Tiling code.
16. Grouped split and leakage-detection code.
17. Quality-validation code.
18. Dataset manifest generation.
19. Dataset-card generation.
20. Tests and execution instructions.

## 18. Implementation order

Build the system incrementally.

Phase 1:

* Configuration
* Schemas
* Provenance registry
* Sentinel-1 catalogue search
* Small test download
* Open-Meteo collection
* Copernicus Marine collection

Phase 2:

* Sentinel-1 preprocessing
* Label import
* Mask rasterization
* Temporal alignment
* Tiling
* Dataset manifests

Phase 3:

* Sentinel-3
* Vessel data
* Infrastructure
* Advanced quality checks
* Grouped train/test split
* Dataset card

Phase 4:

* Parallel downloading
* Zarr support
* Cloud-optimized outputs
* Full reproducibility and performance improvements

At the end of each phase:

* Run tests.
* Show commands used.
* Show generated files.
* Report failed checks.
* Do not continue by pretending unavailable credentials or datasets exist.
* Leave explicit TODO adapters for sources requiring registration or manual approval.

## 19. First response instructions

In your first response:

1. Restate the architecture in no more than 15 concise points.
2. Identify which sources require registration, credentials or manual dataset approval.
3. Highlight all licence risks.
4. Propose the initial directory structure.
5. Provide the dependency list.
6. Provide the initial configuration file.
7. Begin implementing Phase 1 with complete runnable Python code.
8. Do not provide pseudocode where working code can reasonably be written.
9. Do not fabricate API endpoints, product IDs, credentials or licence terms.
10. When uncertain about a current API, verify it against official documentation before implementing it.
